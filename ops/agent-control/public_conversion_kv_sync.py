#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = Path(os.environ.get("JVT_PUBLIC_CONVERSION_STATE_ROOT", CONTROL_ROOT / "state"))
CHECKPOINT_PATH = STATE_ROOT / "public-conversion-kv-sync-checkpoint.json"
REPORT_JSON = STATE_ROOT / "latest-public-conversion-kv-sync.json"
REPORT_MD = STATE_ROOT / "latest-public-conversion-kv-sync.md"
WRANGLER_CONFIG = REPO_ROOT / "site" / "wrangler.toml"
WRANGLER_BIN = Path(os.environ.get("JVT_WRANGLER_BIN", "/opt/homebrew/bin/wrangler"))
KV_BINDING = "JVT_CONVERSION_INTAKE"
KEY_PREFIXES = ("event:view:", "event:start:", "submission:")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,63}\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"(?i)\b(?:bearer|token|secret|api[_ -]?key)\b\s*[:=]?\s*\S+")

if str(CONTROL_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(CONTROL_ROOT))

import public_conversion_intake as intake


class KVClient(Protocol):
    def list_keys(self, prefix: str) -> list[str]: ...

    def get_json(self, key: str) -> dict[str, Any]: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def key_digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def sanitized_error(error: BaseException | str) -> str:
    text = re.sub(r"\s+", " ", str(error)).strip()
    text = EMAIL_RE.sub("[email-redacted]", text)
    text = TOKEN_RE.sub("[credential-redacted]", text)
    return text[:500]


def parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class WranglerKVClient:
    def __init__(
        self,
        *,
        config_path: Path = WRANGLER_CONFIG,
        wrangler_bin: Path = WRANGLER_BIN,
        binding: str = KV_BINDING,
    ):
        self.config_path = config_path
        self.wrangler_bin = wrangler_bin
        self.binding = binding

    def _run(self, arguments: list[str], timeout: int = 90) -> str:
        if not self.wrangler_bin.is_file():
            raise RuntimeError(f"Wrangler is missing at {self.wrangler_bin}")
        if not self.config_path.is_file():
            raise RuntimeError(f"Wrangler config is missing at {self.config_path}")
        environment = dict(os.environ)
        environment["PATH"] = f"/opt/homebrew/bin:{environment.get('PATH', '')}"
        result = subprocess.run(
            [str(self.wrangler_bin), *arguments, "--config", str(self.config_path)],
            cwd=str(REPO_ROOT),
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise RuntimeError(f"Wrangler KV command failed: {sanitized_error(detail)}")
        return result.stdout

    def list_keys(self, prefix: str) -> list[str]:
        output = self._run([
            "kv",
            "key",
            "list",
            "--binding",
            self.binding,
            "--remote",
            "--prefix",
            prefix,
        ])
        start = output.find("[")
        end = output.rfind("]")
        if start < 0 or end < start:
            raise RuntimeError("Wrangler KV key list did not return a JSON array.")
        payload = json.loads(output[start:end + 1])
        keys: list[str] = []
        for item in payload:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name.startswith(prefix):
                keys.append(name)
        return sorted(set(keys))

    def get_json(self, key: str) -> dict[str, Any]:
        output = self._run([
            "kv",
            "key",
            "get",
            key,
            "--binding",
            self.binding,
            "--remote",
            "--text",
        ])
        payload = json.loads(output)
        if not isinstance(payload, dict):
            raise RuntimeError("KV record was not a JSON object.")
        return payload


class FixtureKVClient:
    def __init__(self, fixture_path: Path):
        payload = load_json(fixture_path, {})
        if not isinstance(payload, dict):
            raise RuntimeError("Fixture JSON must be an object keyed by KV key.")
        self.records = payload

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.records if key.startswith(prefix))

    def get_json(self, key: str) -> dict[str, Any]:
        payload = self.records[key]
        if not isinstance(payload, dict):
            raise RuntimeError("Fixture KV record was not a JSON object.")
        return payload


def load_checkpoint(path: Path) -> dict[str, Any]:
    payload = load_json(path, {})
    processed = payload.get("processed_key_hashes") if isinstance(payload, dict) else {}
    return {
        "schema_version": 1,
        "updated_at": str(payload.get("updated_at") or "") if isinstance(payload, dict) else "",
        "processed_key_hashes": processed if isinstance(processed, dict) else {},
    }


def validate_key_record(key: str, payload: dict[str, Any]) -> tuple[str, str]:
    if key.startswith("submission:"):
        kind = "submission"
    elif key.startswith("event:view:"):
        kind = "view"
    elif key.startswith("event:start:"):
        kind = "start"
    else:
        raise RuntimeError("Unsupported KV key prefix.")
    submission_id = intake.clean_submission_id(payload.get("submission_id"))
    if not submission_id or not key.endswith(f":{submission_id}"):
        raise RuntimeError("KV key and payload submission identifier do not match.")
    if kind in {"view", "start"} and str(payload.get("event_type") or "") != kind:
        raise RuntimeError("KV event type does not match its key.")
    return kind, submission_id


def reconcile_record(kind: str, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    created_at = str(payload.get("created_at") or "") or None
    if kind == "submission":
        if dry_run:
            intake.validate_submission_payload(payload)
            return {"ok": True, "dry_run": True, "idempotent": False}
        return intake.submit_payload(
            payload,
            now=created_at,
            reconcile=True,
            refresh_existing_reports=False,
        )
    if dry_run:
        submission_id = intake.clean_submission_id(payload.get("submission_id"))
        if not submission_id:
            raise RuntimeError("Event has no valid submission identifier.")
        return {"ok": True, "dry_run": True, "already_seen": False}
    return intake.record_client_event(payload, kind, now=created_at)


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Public Conversion KV Sync",
        "",
        f"Generated: {report['generated_at']}",
        f"Overall OK: {report['ok']}",
        f"Source: {report['source']}",
        "",
        "## Reconciliation",
        f"- remote keys: {report['remote_key_count']}",
        f"- checkpointed keys: {report['checkpointed_key_count']}",
        f"- imported submissions: {report['imported_submission_count']}",
        f"- imported events: {report['imported_event_count']}",
        f"- idempotent records: {report['idempotent_count']}",
        f"- failed records: {report['failed_count']}",
        f"- unreconciled records: {report['unreconciled_count']}",
        f"- maximum handoff lag seconds: {report['max_handoff_lag_seconds']}",
        "",
        "## Guardrail",
        f"- {report['guardrail']}",
        "",
    ])


def sync_records(
    client: KVClient,
    *,
    checkpoint_path: Path = CHECKPOINT_PATH,
    report_json: Path = REPORT_JSON,
    report_md: Path = REPORT_MD,
    max_records: int = 100,
    dry_run: bool = False,
    refresh_reports: bool = True,
) -> dict[str, Any]:
    generated_at = utc_now()
    checkpoint = load_checkpoint(checkpoint_path)
    processed = checkpoint["processed_key_hashes"]
    remote_keys: list[str] = []
    list_errors: list[str] = []
    for prefix in KEY_PREFIXES:
        try:
            remote_keys.extend(client.list_keys(prefix))
        except Exception as exc:
            list_errors.append(sanitized_error(exc))
    remote_keys = sorted(set(remote_keys), key=lambda key: (0 if key.startswith("event:") else 1, key))
    candidates = [key for key in remote_keys if key_digest(key) not in processed]
    attempted = candidates[:max(0, max_records)]
    failures: list[dict[str, str]] = []
    imported_submission_count = 0
    imported_event_count = 0
    idempotent_count = 0
    handoff_lags: list[int] = []

    if not list_errors:
        for key in attempted:
            digest = key_digest(key)
            try:
                payload = client.get_json(key)
                kind, _submission_id = validate_key_record(key, payload)
                result = reconcile_record(kind, payload, dry_run=dry_run)
                if result.get("idempotent") or result.get("already_seen"):
                    idempotent_count += 1
                if kind == "submission":
                    imported_submission_count += 1
                else:
                    imported_event_count += 1
                created_at = parse_iso(payload.get("created_at"))
                if created_at:
                    handoff_lags.append(max(0, int((datetime.now(timezone.utc) - created_at).total_seconds())))
                if not dry_run:
                    processed[digest] = {
                        "kind": kind,
                        "processed_at": utc_now(),
                    }
                    checkpoint["updated_at"] = utc_now()
                    write_json(checkpoint_path, checkpoint)
            except Exception as exc:
                failures.append({
                    "key_hash": digest,
                    "error": sanitized_error(exc),
                })

    if not dry_run and imported_submission_count and refresh_reports:
        try:
            intake.refresh_pipeline_reports()
        except Exception as exc:
            failures.append({
                "key_hash": "__report_refresh__",
                "error": sanitized_error(exc),
            })

    checkpointed_remote_count = sum(key_digest(key) in processed for key in remote_keys)
    unreconciled_count = max(0, len(remote_keys) - checkpointed_remote_count)
    report = {
        "schema_version": 1,
        "generated_at": generated_at,
        "ok": not list_errors and not failures,
        "source": "cloudflare-kv-via-wrangler-oauth" if isinstance(client, WranglerKVClient) else "fixture",
        "binding": KV_BINDING,
        "dry_run": dry_run,
        "remote_key_count": len(remote_keys),
        "checkpointed_key_count": checkpointed_remote_count,
        "candidate_count": len(candidates),
        "attempted_count": len(attempted),
        "imported_submission_count": imported_submission_count,
        "imported_event_count": imported_event_count,
        "idempotent_count": idempotent_count,
        "failed_count": len(failures) + len(list_errors),
        "unreconciled_count": unreconciled_count,
        "max_handoff_lag_seconds": max(handoff_lags) if handoff_lags else None,
        "list_errors": list_errors,
        "failures": failures[:20],
        "checkpoint_path": str(checkpoint_path),
        "guardrail": (
            "Reads first-party JVT form records from Cloudflare KV and reconciles them into internal "
            "company memory only. No email, spend, trade, public post, account change, or external commitment."
        ),
    }
    write_json(report_json, report)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(render_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile first-party Cloudflare KV form records into JVT.")
    parser.add_argument("--fixture-json", type=Path)
    parser.add_argument("--config", type=Path, default=WRANGLER_CONFIG)
    parser.add_argument("--max-records", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-refresh-reports", action="store_true")
    args = parser.parse_args()

    client: KVClient
    if args.fixture_json:
        client = FixtureKVClient(args.fixture_json)
    else:
        client = WranglerKVClient(config_path=args.config)
    report = sync_records(
        client,
        max_records=max(0, args.max_records),
        dry_run=args.dry_run,
        refresh_reports=not args.no_refresh_reports,
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
