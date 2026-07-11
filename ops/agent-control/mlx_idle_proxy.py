#!/usr/bin/env python3
"""Idle-start proxy for local MLX OpenAI-compatible model servers."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
LOCALHOST_NAMES = {"localhost", "localhost.localdomain"}
PUBLIC_BIND_HOSTS = {"", "0.0.0.0", "::"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class QueueGate:
    """Serialize work so a single local MLX model server is not overrun."""

    def __init__(self, *, capacity: int):
        self.capacity = max(0, int(capacity))
        self._condition = threading.Condition()
        self._active = False
        self._waiting = 0
        self._next_ticket = 0
        self._serving_ticket = 0
        self._oldest_active_started_at: Optional[float] = None
        self.accepted_requests = 0
        self.completed_requests = 0
        self.failed_requests = 0
        self.rejected_requests = 0

    def acquire(self) -> bool:
        with self._condition:
            if self._active or self._next_ticket != self._serving_ticket:
                if self._waiting >= self.capacity:
                    self.rejected_requests += 1
                    return False
                self._waiting += 1
            ticket = self._next_ticket
            self._next_ticket += 1
            try:
                while self._active or ticket != self._serving_ticket:
                    self._condition.wait()
            finally:
                if ticket != self._serving_ticket:
                    self._waiting = max(0, self._waiting - 1)
            if self._waiting and ticket == self._serving_ticket:
                self._waiting -= 1
            self._active = True
            self._oldest_active_started_at = time.time()
            self.accepted_requests += 1
            return True

    def release(self, *, failed: bool) -> None:
        with self._condition:
            if failed:
                self.failed_requests += 1
            else:
                self.completed_requests += 1
            self._active = False
            self._oldest_active_started_at = None
            self._serving_ticket += 1
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            active_seconds = 0.0
            if self._oldest_active_started_at is not None:
                active_seconds = time.time() - self._oldest_active_started_at
            return {
                "active_requests": 1 if self._active else 0,
                "queued_requests": self._waiting,
                "queued_capacity": self.capacity,
                "accepted_requests": self.accepted_requests,
                "completed_requests": self.completed_requests,
                "failed_requests": self.failed_requests,
                "rejected_requests": self.rejected_requests,
                "oldest_active_request_seconds": round(active_seconds, 3),
            }


class ModelManager:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.lock = threading.RLock()
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.active_requests = 0
        self.last_used_at = 0.0
        self.last_start_at = 0.0
        self.last_stop_at = 0.0
        self.last_error = ""
        self.log_path = Path(args.model_log_path).expanduser()
        self.pid_path = Path(args.pid_path).expanduser()
        self.state_path = Path(args.state_path).expanduser()
        self.model_path = str(Path(args.model_path).expanduser())
        self.upstream_base_url = f"http://{args.upstream_host}:{args.upstream_port}"
        self.listen_base_url = f"http://{args.listen_host}:{args.listen_port}"
        self._stop_event = threading.Event()
        self._reaper = threading.Thread(target=self._idle_reaper, daemon=True)
        self._reaper.start()
        self.write_status(
            model_state="sleeping",
            message="Idle proxy is healthy; model will start on the next inference request.",
        )

    def shutdown(self) -> None:
        self._stop_event.set()
        self.stop_model(reason="proxy shutdown")

    def snapshot(self) -> dict[str, Any]:
        upstream_ready = self.upstream_healthy()
        with self.lock:
            process_alive = self.process is not None and self.process.poll() is None
            pid = self.process.pid if process_alive and self.process is not None else None
            active = self.active_requests
            idle_for = 0.0
            if self.last_used_at:
                idle_for = max(0.0, time.time() - self.last_used_at)
            if upstream_ready:
                model_state = "running"
            elif process_alive:
                model_state = "starting"
            else:
                model_state = "sleeping"
            return {
                "model_state": model_state,
                "upstream_ready": upstream_ready,
                "managed_pid": pid,
                "active_model_requests": active,
                "idle_seconds": self.args.idle_seconds,
                "idle_for_seconds": round(idle_for, 3),
                "last_start_at": self._format_ts(self.last_start_at),
                "last_stop_at": self._format_ts(self.last_stop_at),
                "last_used_at": self._format_ts(self.last_used_at),
                "last_error": self.last_error,
                "model_id": self.args.model_id,
                "model_path": self.model_path,
                "upstream": self.upstream_base_url,
            }

    def mark_request_started(self) -> None:
        with self.lock:
            self.active_requests += 1

    def mark_request_finished(self) -> None:
        with self.lock:
            self.active_requests = max(0, self.active_requests - 1)
            self.last_used_at = time.time()
            self.write_status(
                model_state="running" if self.upstream_healthy() else "sleeping",
                message="Model request finished.",
            )

    def ensure_started(self) -> bool:
        if self.upstream_healthy():
            with self.lock:
                self.last_used_at = time.time()
                self.write_status(model_state="running", message="Model is already running.")
            return True

        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.write_status(model_state="starting", message="Waiting for model server to become ready.")
                return self.wait_ready()

            if not Path(self.model_path).exists():
                self.last_error = f"model path does not exist: {self.model_path}"
                self.write_status(model_state="error", message=self.last_error, status="error")
                return False

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.pid_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = self.log_path.open("ab")
            command = [
                self.args.python,
                "-m",
                "mlx_lm",
                "server",
                "--model",
                self.model_path,
                "--host",
                self.args.upstream_host,
                "--port",
                str(self.args.upstream_port),
                "--max-tokens",
                str(self.args.max_tokens),
                "--temp",
                str(self.args.temp),
                "--chat-template-args",
                '{"enable_thinking":false}',
            ]
            self.last_start_at = time.time()
            self.last_used_at = self.last_start_at
            self.last_error = ""
            self.write_status(model_state="starting", message="Starting MLX model server.")
            self.process = subprocess.Popen(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.pid_path.write_text(f"{self.process.pid}\n", encoding="utf-8")

        return self.wait_ready()

    def wait_ready(self) -> bool:
        deadline = time.time() + float(self.args.cold_start_timeout)
        while time.time() < deadline:
            with self.lock:
                if self.process is not None and self.process.poll() is not None:
                    self.last_error = f"model server exited with code {self.process.returncode}"
                    self.write_status(model_state="error", message=self.last_error, status="error")
                    return False
            if self.upstream_healthy():
                self.write_status(model_state="running", message="MLX model server is ready.")
                return True
            time.sleep(1.0)
        self.last_error = "model server did not become ready before timeout"
        self.write_status(model_state="error", message=self.last_error, status="error")
        return False

    def stop_model(self, *, reason: str) -> None:
        with self.lock:
            process = self.process
            self.process = None
            self.active_requests = 0
            if process is None or process.poll() is not None:
                self.write_status(model_state="sleeping", message=f"Model is sleeping: {reason}.")
                return
            self.write_status(model_state="stopping", message=f"Stopping MLX model server: {reason}.")
            pid = process.pid

        with contextlib.suppress(Exception):
            os.killpg(pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(Exception):
                os.killpg(pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                process.wait(timeout=5)

        with self.lock:
            self.last_stop_at = time.time()
            with contextlib.suppress(FileNotFoundError):
                self.pid_path.unlink()
            self.write_status(model_state="sleeping", message=f"Model is sleeping: {reason}.")

    def upstream_healthy(self) -> bool:
        try:
            request = Request(f"{self.upstream_base_url}/health", method="GET")
            with urlopen(request, timeout=float(self.args.health_timeout)) as response:
                return int(response.status) < 500
        except Exception:
            return False

    def write_status(self, *, model_state: str, message: str, status: str = "ok") -> None:
        payload = {
            "generated_at": utc_now(),
            "status": status,
            "message": message,
            "service": self.args.service_name,
            "model_state": model_state,
            "base_url": self.listen_base_url,
            "upstream_url": self.upstream_base_url,
            "model_path": self.model_path,
            "model_id": self.args.model_id,
            "idle_seconds": self.args.idle_seconds,
            "pid": self.process.pid if self.process is not None and self.process.poll() is None else None,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _idle_reaper(self) -> None:
        while not self._stop_event.wait(float(self.args.idle_check_seconds)):
            with self.lock:
                process_alive = self.process is not None and self.process.poll() is None
                active = self.active_requests
                last_used_at = self.last_used_at
            if not process_alive or active:
                continue
            if last_used_at and time.time() - last_used_at >= float(self.args.idle_seconds):
                self.stop_model(reason=f"idle for {int(time.time() - last_used_at)} seconds")

    @staticmethod
    def _format_ts(value: float) -> str:
        if not value:
            return ""
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")


class IdleProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls: type[BaseHTTPRequestHandler],
        *,
        manager: ModelManager,
        timeout: float,
        queue_capacity: int,
        service_name: str,
    ):
        super().__init__(server_address, handler_cls)
        self.manager = manager
        self.timeout = timeout
        self.service_name = service_name
        self.started_at = time.time()
        self.queue_gate = QueueGate(capacity=queue_capacity)


class IdleProxyHandler(BaseHTTPRequestHandler):
    server_version = "MLXIdleProxy/1.0"

    def do_GET(self):  # noqa: N802
        path = urlsplit(self.path).path
        if path in {"/health", "/healthz", "/readyz", "/stats"}:
            self._send_json(
                {
                    "ok": True,
                    "service": self.server.service_name,
                    "uptime_seconds": round(time.time() - self.server.started_at, 3),
                    **self.server.manager.snapshot(),
                    **self.server.queue_gate.snapshot(),
                }
            )
            return
        self._proxy()

    def do_POST(self):  # noqa: N802
        self._proxy()

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/v1/"):
            self._send_json({"error": "not_found"}, status=404)
            return
        if not self.server.queue_gate.acquire():
            self._send_json({"error": "queue_full"}, status=429)
            return

        failed = False
        self.server.manager.mark_request_started()
        try:
            if not self.server.manager.ensure_started():
                failed = True
                self._send_json(
                    {
                        "error": "model_unavailable",
                        "detail": self.server.manager.snapshot(),
                    },
                    status=503,
                )
                return

            body = b""
            if self.command in {"POST", "PUT", "PATCH"}:
                try:
                    content_length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    content_length = 0
                if content_length:
                    body = self.rfile.read(content_length)

            target = f"{self.server.manager.upstream_base_url}{self.path}"
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
            }
            request = Request(target, data=body or None, headers=headers, method=self.command)
            try:
                with urlopen(request, timeout=self.server.timeout) as response:
                    payload = response.read()
                    self.send_response(response.status)
                    self._send_common_headers()
                    for key, value in response.headers.items():
                        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() not in {"content-length", "server", "date"}:
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
            except HTTPError as exc:
                payload = exc.read()
                failed = exc.code >= 500
                self.send_response(exc.code)
                self._send_common_headers()
                self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (TimeoutError, URLError, OSError) as exc:
                failed = True
                self._send_json({"error": "upstream_unavailable", "detail": str(exc)}, status=502)
        finally:
            self.server.manager.mark_request_finished()
            self.server.queue_gate.release(failed=failed)

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-NTC-Agent-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}", flush=True)


def host_is_loopback(hostname: Optional[str]) -> bool:
    host = (hostname or "").strip().strip("[]").lower()
    if host in LOCALHOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    bind_host = (args.listen_host or "").strip().lower()
    if bind_host in PUBLIC_BIND_HOSTS and not args.allow_public_bind:
        parser.error("refusing public bind without --allow-public-bind")
    if not host_is_loopback(args.upstream_host):
        parser.error("upstream host must be loopback")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a low-power idle proxy for an MLX model server.")
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--pid-path", required=True)
    parser.add_argument("--model-log-path", required=True)
    parser.add_argument("--python", default="/usr/bin/python3")
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--temp", default="0.0")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--cold-start-timeout", type=float, default=120.0)
    parser.add_argument("--health-timeout", type=float, default=3.0)
    parser.add_argument("--idle-seconds", type=float, default=900.0)
    parser.add_argument("--idle-check-seconds", type=float, default=15.0)
    parser.add_argument("--queue-capacity", type=int, default=8)
    parser.add_argument("--allow-public-bind", action="store_true")
    args = parser.parse_args()
    validate_args(parser, args)
    return args


def main() -> int:
    args = parse_args()
    manager = ModelManager(args)
    server = IdleProxyServer(
        (args.listen_host, args.listen_port),
        IdleProxyHandler,
        manager=manager,
        timeout=args.timeout,
        queue_capacity=args.queue_capacity,
        service_name=args.service_name,
    )
    print(
        f"{args.service_name} listening on http://{args.listen_host}:{args.listen_port} "
        f"-> {manager.upstream_base_url} idle={args.idle_seconds}s",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        manager.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
