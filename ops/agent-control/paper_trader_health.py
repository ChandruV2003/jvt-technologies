#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
AUTOTRADER_ROOT = Path("/Users/c.s.d.v.r.s./Developer/JVT-AutoTrader")
TRADER_STATE = AUTOTRADER_ROOT / "state"
REPORT_JSON = STATE_ROOT / "latest-paper-trader-health.json"
REPORT_MD = STATE_ROOT / "latest-paper-trader-health.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds(value: object) -> int | None:
    parsed = parse_dt(value)
    if not parsed:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_report() -> dict[str, Any]:
    account = load_json(TRADER_STATE / "latest_account_snapshot.json")
    backtest = load_json(TRADER_STATE / "latest_backtest.json")
    paper_bot = load_json(TRADER_STATE / "latest_paper_bot_report.json")
    account_payload = account.get("account") if isinstance(account.get("account"), dict) else {}
    plans = paper_bot.get("plans") if isinstance(paper_bot.get("plans"), list) else []
    planned_orders = [plan for plan in plans if plan.get("status") not in {"no_order", None, ""}]
    backtest_results = backtest.get("results") if isinstance(backtest.get("results"), list) else []
    paper_candidate_symbols = backtest.get("paper_candidate_symbols") if isinstance(backtest.get("paper_candidate_symbols"), list) else []
    underperformed = [
        row.get("symbol")
        for row in backtest_results
        if isinstance(row, dict) and float(row.get("signal_return_pct") or 0) < float(row.get("buy_hold_return_pct") or 0)
    ]
    account_age = age_seconds(account.get("checked_at"))
    backtest_age = age_seconds(backtest.get("generated_at"))
    bot_age = age_seconds(paper_bot.get("generated_at"))
    findings: list[str] = []
    if not AUTOTRADER_ROOT.exists():
        findings.append("AutoTrader repo is missing.")
    if not account:
        findings.append("No latest paper account snapshot found.")
    elif account_age is not None and account_age > 24 * 60 * 60:
        findings.append("Paper account snapshot is older than 24 hours.")
    if not backtest:
        findings.append("No latest backtest report found.")
    elif backtest_age is not None and backtest_age > 24 * 60 * 60:
        findings.append("Backtest report is older than 24 hours.")
    if not paper_bot:
        findings.append("No latest paper bot report found.")
    if planned_orders:
        findings.append("Paper bot generated non-hold order plans; review before any execution.")
    if underperformed:
        findings.append("Backtest signals currently trail buy-hold on one or more symbols.")
    if backtest and not paper_candidate_symbols:
        findings.append("No symbols currently pass the paper-candidate edge filter.")
    return {
        "generated_at": utc_now(),
        "ok": AUTOTRADER_ROOT.exists() and bool(account) and bool(backtest) and bool(paper_bot),
        "mode": paper_bot.get("mode") or account.get("mode") or "paper-research",
        "repo": str(AUTOTRADER_ROOT),
        "account_snapshot_age_seconds": account_age,
        "backtest_age_seconds": backtest_age,
        "paper_bot_age_seconds": bot_age,
        "equity": account_payload.get("equity") or (paper_bot.get("account") or {}).get("equity"),
        "buying_power": account_payload.get("buying_power") or (paper_bot.get("account") or {}).get("buying_power"),
        "pattern_day_trader": account_payload.get("pattern_day_trader"),
        "trading_blocked": account_payload.get("trading_blocked"),
        "positions": (account.get("positions") or [])[:12],
        "paper_order_plan_count": len(planned_orders),
        "backtest_symbol_count": len(backtest_results),
        "underperformed_symbols": [symbol for symbol in underperformed if symbol],
        "paper_candidate_symbols": paper_candidate_symbols,
        "decision": backtest.get("decision") or "No live trading decision available.",
        "findings": findings,
        "guardrail": "Paper-only research. No live endpoint, fund movement, order execution, wallets, mining, or staking.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Paper Trader Health",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Account snapshot age: `{report['account_snapshot_age_seconds']}` seconds",
        f"- Backtest age: `{report['backtest_age_seconds']}` seconds",
        f"- Paper bot age: `{report['paper_bot_age_seconds']}` seconds",
        f"- Paper order plans: `{report['paper_order_plan_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Decision",
        "",
        str(report.get("decision") or ""),
        "",
        "## Findings",
        "",
    ]
    if report.get("findings"):
        lines.extend(f"- {item}" for item in report["findings"])
    else:
        lines.append("- No findings.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "mode": report["mode"], "findings": len(report["findings"])}))


if __name__ == "__main__":
    main()
