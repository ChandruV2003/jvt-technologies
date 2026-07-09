from __future__ import annotations

from typing import Any


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sent_count(sent: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in sent:
            return _int(sent.get(key))
    return 0


def _is_critical(findings: list[dict[str, Any]] | None) -> bool:
    return any(str(item.get("severity") or "").lower() == "critical" for item in findings or [])


def resolve_send_caps(
    policy: dict[str, Any],
    sent: dict[str, Any],
    approved_counts: dict[str, Any] | None = None,
    inbox_new: int = 0,
    critical_findings: list[dict[str, Any]] | None = None,
    tcp_severity: str | None = None,
) -> dict[str, Any]:
    """Resolve effective outbound caps without bypassing hard safety ceilings."""

    approved_counts = approved_counts or {}
    base_initial = _int(policy.get("daily_initial_send_cap"))
    base_followup = _int(policy.get("daily_followup_send_cap"))
    base_total = _int(policy.get("max_total_outbound_per_day"), base_initial + base_followup)

    dynamic = policy.get("dynamic_send_caps")
    if not isinstance(dynamic, dict):
        dynamic = {}

    initial = base_initial
    followup = base_followup
    total = base_total
    adjustments: list[str] = []

    max_initial = _int(dynamic.get("max_initial_send_cap"), base_initial)
    max_followup = _int(dynamic.get("max_followup_send_cap"), base_followup)
    max_total = _int(dynamic.get("max_total_outbound_per_day"), base_total)
    if max_initial < base_initial:
        max_initial = base_initial
    if max_followup < base_followup:
        max_followup = base_followup
    if max_total < base_total:
        max_total = base_total

    sent_initial = _sent_count(sent, "initial", "initial_today")
    sent_followup = _sent_count(sent, "followup", "followup_today")
    sent_total = _sent_count(sent, "total")
    if not sent_total:
        sent_total = sent_initial + sent_followup

    tcp = str(tcp_severity or "").lower()
    critical = _is_critical(critical_findings)
    health_green = inbox_new == 0 and not critical and tcp not in {"critical", "warning"}
    health_clear_enough_for_borrow = inbox_new == 0 and not critical and tcp != "critical"

    if dynamic.get("enabled", False):
        if dynamic.get("allow_followups_to_borrow_unused_initial", True) and health_clear_enough_for_borrow:
            unused_initial = max(0, initial - sent_initial)
            followup_backlog = _int(approved_counts.get("followup"))
            if unused_initial and followup_backlog:
                borrowed = min(unused_initial, max_followup - followup)
                if borrowed > 0:
                    followup += borrowed
                    adjustments.append(f"followups borrowed {borrowed} unused initial slot(s)")

        if health_green:
            backlog = _int(approved_counts.get("total"))
            threshold = _int(dynamic.get("healthy_backlog_threshold"), 25)
            if backlog >= threshold:
                total_boost = min(_int(dynamic.get("healthy_total_boost"), 0), max_total - total)
                followup_boost = min(_int(dynamic.get("healthy_followup_boost"), 0), max_followup - followup)
                initial_boost = min(_int(dynamic.get("healthy_initial_boost"), 0), max_initial - initial)
                if total_boost > 0:
                    total += total_boost
                    adjustments.append(f"healthy backlog raised total cap by {total_boost}")
                if followup_boost > 0:
                    followup += followup_boost
                    adjustments.append(f"healthy backlog raised follow-up cap by {followup_boost}")
                if initial_boost > 0:
                    initial += initial_boost
                    adjustments.append(f"healthy backlog raised initial cap by {initial_boost}")
        elif tcp == "warning":
            adjustments.append("total cap held at base because TCP pressure is warning-level")
        elif tcp == "critical":
            adjustments.append("dynamic cap expansion disabled because TCP pressure is critical")
        elif inbox_new:
            adjustments.append("dynamic cap expansion disabled until inbox is triaged")
        elif critical:
            adjustments.append("dynamic cap expansion disabled because a critical watchdog finding is active")

    total = min(total, initial + followup, max_total)
    return {
        "dynamic_enabled": bool(dynamic.get("enabled", False)),
        "base": {
            "initial": base_initial,
            "followup": base_followup,
            "total": base_total,
        },
        "effective": {
            "initial": min(initial, max_initial),
            "followup": min(followup, max_followup),
            "total": total,
        },
        "max": {
            "initial": max_initial,
            "followup": max_followup,
            "total": max_total,
        },
        "remaining": {
            "initial": max(0, min(initial, max_initial) - sent_initial),
            "followup": max(0, min(followup, max_followup) - sent_followup),
            "total": max(0, total - sent_total),
        },
        "health": {
            "inbox_new": inbox_new,
            "critical_watchdog_findings": len(critical_findings or []),
            "tcp_severity": tcp or "unknown",
            "green": health_green,
        },
        "adjustments": adjustments,
    }
