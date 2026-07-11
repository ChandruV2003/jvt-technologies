#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
CONFIG_PATH = CONTROL_ROOT / "config" / "model-router.json"
STATE_PATH = CONTROL_ROOT / "state" / "latest-model-router.json"
SNAPSHOT_LOCK = threading.RLock()
SNAPSHOT_CACHE: dict[str, Any] | None = None
SNAPSHOT_CACHE_AT = 0.0


DEFAULT_CONFIG: dict[str, Any] = {
    "listen_host": "127.0.0.1",
    "listen_port": 8760,
    "default_backend": "m4-mlx",
    "task_routes": {
        "triage": "m4-mlx",
        "lead_scoring": "m4-mlx",
        "outreach_copy": "m4-mlx",
        "status_summary": "m4-mlx",
        "strategy": "macbook-large-local",
        "deep_research": "macbook-large-local",
        "product_spec": "macbook-large-local",
        "code_planning": "macbook-large-local",
    },
    "fallback_order": ["m4-mlx"],
    "backends": {
        "m4-mlx": {
            "kind": "openai-compatible",
            "base_url": "http://127.0.0.1:11435",
            "model": "mlx-community/Qwen3-8B-4bit",
            "health_path": "/health",
            "enabled": True,
            "role": "always-on local triage and drafting",
        },
        "macbook-large-local": {
            "kind": "openai-compatible",
            "base_url": "",
            "model": "",
            "health_path": "/health",
            "gate_url": "http://100.90.245.45:8769/health",
            "enabled": True,
            "role": "opportunistic stronger local inference when MacBook power gate allows it",
        },
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    current = load_json(CONFIG_PATH, {})
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in current.items():
        if key == "backends" and isinstance(value, dict):
            merged["backends"].update(value)
        elif key == "task_routes" and isinstance(value, dict):
            merged["task_routes"].update(value)
        else:
            merged[key] = value
    return merged


def http_json(url: str, *, payload: dict[str, Any] | None = None, timeout: float = 8.0) -> tuple[bool, int | None, Any]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                body = raw.decode("utf-8", errors="replace")[:1000]
            return True, int(response.status), body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            body = str(exc)
        return False, int(exc.code), body
    except Exception as exc:
        return False, None, str(exc)


def backend_status(name: str, backend: dict[str, Any]) -> dict[str, Any]:
    status: dict[str, Any] = {
        "name": name,
        "kind": backend.get("kind"),
        "enabled": bool(backend.get("enabled", True)),
        "model": backend.get("model") or "",
        "base_url_configured": bool(str(backend.get("base_url") or "").strip()),
        "available": False,
        "checked_at": utc_now(),
    }
    if not status["enabled"]:
        status.update({"state": "disabled", "reason": "backend disabled"})
        return status

    gate_url = str(backend.get("gate_url") or "").strip()
    if gate_url:
        ok, code, body = http_json(gate_url, timeout=3)
        status["gate"] = {"ok": ok, "status": code, "body": body}
        if not ok or not isinstance(body, dict) or not body.get("allow_model_use"):
            status.update({"state": "blocked_by_gate", "reason": "power or reachability gate is not allowing model use"})
            return status

    base_url = str(backend.get("base_url") or "").rstrip("/")
    if not base_url:
        status.update({"state": "registered_no_endpoint", "reason": "backend is registered but no inference endpoint is configured"})
        return status

    health_path = str(backend.get("health_path") or "/health")
    if not health_path.startswith("/"):
        health_path = f"/{health_path}"
    ok, code, body = http_json(f"{base_url}{health_path}", timeout=3)
    status["health"] = {"ok": ok, "status": code, "body": body}
    if ok:
        status.update({"state": "available", "available": True})
    else:
        status.update({"state": "unhealthy", "reason": str(body)})
    return status


def snapshot(config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    global SNAPSHOT_CACHE, SNAPSHOT_CACHE_AT
    max_age = float(os.environ.get("JVT_MODEL_ROUTER_HEALTH_TTL_SECONDS") or config.get("health_cache_seconds") or 30)
    with SNAPSHOT_LOCK:
        if not force and SNAPSHOT_CACHE is not None and time.time() - SNAPSHOT_CACHE_AT < max_age:
            return SNAPSHOT_CACHE

    backends = config.get("backends") or {}
    items = {name: backend_status(name, backend) for name, backend in backends.items()}
    available = [name for name, item in items.items() if item.get("available")]
    payload = {
        "generated_at": utc_now(),
        "ok": bool(available),
        "listen": {
            "host": config.get("listen_host"),
            "port": config.get("listen_port"),
        },
        "default_backend": config.get("default_backend"),
        "available_backends": available,
        "backends": items,
        "routing_policy": {
            "task_routes": config.get("task_routes") or {},
            "fallback_order": config.get("fallback_order") or [],
        },
    }
    write_json(STATE_PATH, payload)
    with SNAPSHOT_LOCK:
        SNAPSHOT_CACHE = payload
        SNAPSHOT_CACHE_AT = time.time()
    return payload


def select_backend(config: dict[str, Any], payload: dict[str, Any], state: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    requested = str(payload.get("backend") or payload.get("jvt_backend") or "").strip()
    task_type = str(payload.get("task_type") or payload.get("jvt_task_type") or "triage").strip()
    candidates: list[str] = []
    if requested:
        candidates.append(requested)
    routed = (config.get("task_routes") or {}).get(task_type)
    if routed:
        candidates.append(str(routed))
    candidates.append(str(config.get("default_backend") or "m4-mlx"))
    candidates.extend(str(item) for item in (config.get("fallback_order") or []))

    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        item = (state.get("backends") or {}).get(name) or {}
        if item.get("available"):
            return name, item
    return None, {"reason": "no configured backend is currently available", "candidates": candidates}


def proxy_chat(config: dict[str, Any], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    state = snapshot(config)
    backend_name, selected = select_backend(config, payload, state)
    if not backend_name:
        return 503, {
            "error": "no_backend_available",
            "detail": selected,
            "router_state": state,
        }
    backend = (config.get("backends") or {}).get(backend_name) or {}
    base_url = str(backend.get("base_url") or "").rstrip("/")
    upstream_payload = dict(payload)
    upstream_payload.pop("backend", None)
    upstream_payload.pop("jvt_backend", None)
    upstream_payload.pop("task_type", None)
    upstream_payload.pop("jvt_task_type", None)
    if backend.get("model"):
        upstream_payload["model"] = backend["model"]

    ok, code, body = http_json(f"{base_url}/v1/chat/completions", payload=upstream_payload, timeout=float(os.environ.get("JVT_MODEL_ROUTER_TIMEOUT_SECONDS") or "180"))
    if not ok:
        return int(code or 502), {
            "error": "upstream_failed",
            "backend": backend_name,
            "status": code,
            "detail": body,
        }
    route_meta = {
        "backend": backend_name,
        "model": backend.get("model") or "",
        "selected_at": utc_now(),
    }
    if isinstance(body, dict):
        body.setdefault("jvt_router", route_meta)
        return int(code or 200), body
    return int(code or 200), {"response": body, "jvt_router": route_meta}


class Handler(BaseHTTPRequestHandler):
    server_version = "JVTModelRouter/1.0"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        config = ensure_config()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/health", "/status", "/api/status"}:
            query = urllib.parse.parse_qs(parsed.query)
            force = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
            self._send(200, snapshot(config, force=force))
            return
        if parsed.path == "/v1/models":
            state = snapshot(config)
            data = [
                {"id": name, "object": "model", "owned_by": "jvt", "available": item.get("available"), "state": item.get("state")}
                for name, item in (state.get("backends") or {}).items()
            ]
            self._send(200, {"object": "list", "data": data})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception as exc:
            self._send(400, {"error": "bad_json", "detail": str(exc)})
            return
        status, body = proxy_chat(ensure_config(), payload)
        self._send(status, body)

    def log_message(self, fmt: str, *args: Any) -> None:
        line = {
            "generated_at": utc_now(),
            "client": self.client_address[0],
            "message": fmt % args,
        }
        log_path = CONTROL_ROOT / "logs" / "model-router-access.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")


def serve(config: dict[str, Any]) -> None:
    host = str(config.get("listen_host") or "127.0.0.1")
    port = int(config.get("listen_port") or 8760)
    snapshot(config, force=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"status": "serving", "host": host, "port": port, "state": str(STATE_PATH)}, indent=2), flush=True)
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="JVT local model router.")
    parser.add_argument("command", choices=["serve", "status"], nargs="?", default="status")
    parser.add_argument("--refresh", action="store_true", help="Bypass the health cache for status output.")
    args = parser.parse_args()

    config = ensure_config()
    if args.command == "serve":
        serve(config)
        return
    print(json.dumps(snapshot(config, force=args.refresh), indent=2))


if __name__ == "__main__":
    main()
