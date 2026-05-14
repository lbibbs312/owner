"""Operational services: audit logging, exception/delay/savings analytics.

These helpers are intentionally self-contained and can be called from the
new ops blueprint. They read from the new ORM models in ``models.py``.
Legacy inline models in ``lacksdrivers.py`` / ``db_setup.py`` are NOT
used here — those routes should be migrated to this module in a follow-up.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from models import (
    db,
    ActivityEvent,
    AuditEvent,
    DamageReport,
    DriverLog,
    OperationalFollowUp,
    PlantTransfer,
    PreTrip,
    Task,
)

DEFAULT_DOCK_DELAY_MINUTES = 30

# Severity ranking: high > medium > low.
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _json_dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def record_audit_event(
    user_id: int,
    target_type: str,
    target_id: Optional[int],
    action: str,
    reason: Optional[str] = None,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Persist an AuditEvent row. Commit is left to the caller."""
    event = AuditEvent(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        reason=reason,
        before_values=_json_dump(before_values),
        after_values=_json_dump(after_values),
    )
    db.session.add(event)
    return event


def model_snapshot(instance: Any, fields: Iterable[str]) -> Dict[str, Any]:
    """Return a plain dict of ``fields`` from ``instance``.

    Handles ``None`` instances by returning ``{}`` so callers can pass freshly
    instantiated objects without special-casing.
    """
    if instance is None:
        return {}
    out: Dict[str, Any] = {}
    for f in fields:
        out[f] = getattr(instance, f, None)
    return out


# ---------------------------------------------------------------------------
# Week window helper
# ---------------------------------------------------------------------------

def _week_window(anchor: Optional[date]) -> tuple[date, date]:
    """Return Monday..Sunday inclusive for the week containing ``anchor``."""
    if anchor is None:
        anchor = date.today()
    start = anchor - timedelta(days=anchor.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


# ---------------------------------------------------------------------------
# Exception builder
# ---------------------------------------------------------------------------

def _add(items: List[Dict[str, Any]], **kwargs: Any) -> None:
    items.append(kwargs)


def build_exception_items(
    anchor: Optional[date] = None,
    dock_delay_minutes: int = DEFAULT_DOCK_DELAY_MINUTES,
) -> List[Dict[str, Any]]:
    """Return a list of exception dicts for the week containing ``anchor``.

    Each dict has: severity, category, label, detail, target_type, target_id.
    Sorted high -> medium -> low.
    """
    start, end = _week_window(anchor)
    items: List[Dict[str, Any]] = []

    # --- PlantTransfer paperwork gaps ---
    transfers = (
        PlantTransfer.query
        .filter(PlantTransfer.transfer_date >= start)
        .filter(PlantTransfer.transfer_date <= end)
        .filter(PlantTransfer.deleted_at.is_(None))
        .all()
    )
    for t in transfers:
        missing = []
        if not t.trailer_number:
            missing.append("trailer #")
        if not t.transfer_time:
            missing.append("time")
        if not t.driver_name:
            missing.append("driver")
        if not t.driver_initials:
            missing.append("initials")
        if missing:
            _add(
                items,
                severity="high" if len(missing) >= 2 else "medium",
                category="transfer",
                label=f"Transfer #{t.transfer_number or t.id} missing {', '.join(missing)}",
                detail=f"{t.ship_from or '?'} → {t.ship_to or '?'} on {t.transfer_date}",
                target_type="plant_transfer",
                target_id=t.id,
            )

    # --- DriverLog issues ---
    logs = (
        DriverLog.query
        .filter(DriverLog.date >= start)
        .filter(DriverLog.date <= end)
        .filter(DriverLog.deleted_at.is_(None))
        .all()
    )
    # Pretrips by user & date for same-day cross-reference.
    pretrips_by_user_date: Dict[tuple, List[PreTrip]] = defaultdict(list)
    pretrips = (
        PreTrip.query
        .filter(PreTrip.pretrip_date >= start)
        .filter(PreTrip.pretrip_date <= end)
        .filter(PreTrip.deleted_at.is_(None))
        .all()
    )
    for p in pretrips:
        pretrips_by_user_date[(p.user_id, p.pretrip_date)].append(p)

    for log in logs:
        same_day_pretrip = pretrips_by_user_date.get((log.driver_id, log.date))
        if not same_day_pretrip:
            _add(
                items,
                severity="high",
                category="log",
                label="Driver log has no same-day pretrip",
                detail=f"{log.plant_name} on {log.date}",
                target_type="driver_log",
                target_id=log.id,
            )
        if not log.arrive_time or not log.depart_time:
            _add(
                items,
                severity="medium",
                category="log",
                label="Driver log missing times",
                detail=f"arrive={log.arrive_time or '?'}, depart={log.depart_time or '?'} ({log.plant_name})",
                target_type="driver_log",
                target_id=log.id,
            )
        if log.no_pickup:
            _add(
                items,
                severity="medium",
                category="log",
                label="No-pickup at dock",
                detail=f"{log.plant_name} on {log.date}",
                target_type="driver_log",
                target_id=log.id,
            )
        if (log.dock_wait_minutes or 0) >= dock_delay_minutes:
            _add(
                items,
                severity="high",
                category="delay",
                label=f"Dock wait {log.dock_wait_minutes} min at {log.plant_name}",
                detail=f"threshold {dock_delay_minutes} min on {log.date}",
                target_type="driver_log",
                target_id=log.id,
            )

    # --- Open hot Tasks ---
    hot_tasks = (
        Task.query
        .filter(Task.is_hot.is_(True))
        .filter(Task.status != "completed")
        .all()
    )
    for tk in hot_tasks:
        _add(
            items,
            severity="high",
            category="hot_task",
            label=f"Hot task open: {tk.title}",
            detail=tk.details or "",
            target_type="task",
            target_id=tk.id,
        )

    # --- Open DamageReports ---
    open_damage = DamageReport.query.filter(DamageReport.status != "closed").all()
    for d in open_damage:
        _add(
            items,
            severity="high",
            category="damage",
            label=f"Open damage report #{d.id}",
            detail=(d.description or "")[:160],
            target_type="damage_report",
            target_id=d.id,
        )

    # --- Open OperationalFollowUps ---
    open_fu = OperationalFollowUp.query.filter(OperationalFollowUp.status != "closed").all()
    for f in open_fu:
        sev = "medium" if f.kind in ("wrong_location", "unclear_dispatch") else "low"
        _add(
            items,
            severity=sev,
            category="follow_up",
            label=f"Follow-up: {f.kind.replace('_', ' ')}",
            detail=(f.details or "")[:160],
            target_type="operational_follow_up",
            target_id=f.id,
        )

    items.sort(key=lambda d: _SEVERITY_RANK.get(d.get("severity", "low"), 99))
    return items


# ---------------------------------------------------------------------------
# Delay report
# ---------------------------------------------------------------------------

def build_delay_report(
    anchor: Optional[date] = None,
    dock_delay_minutes: int = DEFAULT_DOCK_DELAY_MINUTES,
) -> Dict[str, Any]:
    start, end = _week_window(anchor)
    logs = (
        DriverLog.query
        .filter(DriverLog.date >= start)
        .filter(DriverLog.date <= end)
        .filter(DriverLog.deleted_at.is_(None))
        .filter(DriverLog.dock_wait_minutes.isnot(None))
        .all()
    )

    plant_totals: Dict[str, List[int]] = defaultdict(list)
    delayed_logs = []
    for log in logs:
        wait = log.dock_wait_minutes or 0
        plant_totals[log.plant_name].append(wait)
        if wait >= dock_delay_minutes:
            delayed_logs.append(log)

    plant_averages = {
        plant: round(sum(values) / len(values), 1) if values else 0.0
        for plant, values in plant_totals.items()
    }

    return {
        "week_start": start,
        "week_end": end,
        "threshold": dock_delay_minutes,
        "delayed_logs": delayed_logs,
        "plant_averages": plant_averages,
        "total_logs_with_wait": len(logs),
    }


# ---------------------------------------------------------------------------
# Weekly savings
# ---------------------------------------------------------------------------

def build_weekly_savings(
    anchor: Optional[date] = None,
    dock_delay_minutes: int = DEFAULT_DOCK_DELAY_MINUTES,
) -> Dict[str, Any]:
    start, end = _week_window(anchor)

    transfers = (
        PlantTransfer.query
        .filter(PlantTransfer.transfer_date >= start)
        .filter(PlantTransfer.transfer_date <= end)
        .filter(PlantTransfer.deleted_at.is_(None))
        .all()
    )
    total_transfer_count = len(transfers)
    complete_transfer_count = sum(1 for t in transfers if t.is_complete)
    incomplete_transfer_count = total_transfer_count - complete_transfer_count
    transfer_completion_rate = (
        round(complete_transfer_count / total_transfer_count * 100, 1)
        if total_transfer_count else 0.0
    )

    # Hot moves: Tasks that were hot and have both accepted_at and completed_at
    # falling within the week.
    hot_tasks = (
        Task.query
        .filter(Task.is_hot.is_(True))
        .all()
    )
    hot_move_count = len(hot_tasks)
    hot_moves_completed_with_timestamps = sum(
        1 for tk in hot_tasks
        if tk.accepted_at and tk.completed_at
        and start <= tk.completed_at.date() <= end
    )

    # Same-day pretrip count: pretrips that share a date with at least one
    # of the same user's driver_logs.
    pretrips = (
        PreTrip.query
        .filter(PreTrip.pretrip_date >= start)
        .filter(PreTrip.pretrip_date <= end)
        .filter(PreTrip.deleted_at.is_(None))
        .all()
    )
    logs = (
        DriverLog.query
        .filter(DriverLog.date >= start)
        .filter(DriverLog.date <= end)
        .filter(DriverLog.deleted_at.is_(None))
        .all()
    )
    log_keys = {(l.driver_id, l.date) for l in logs}
    same_day_pretrip_count = sum(
        1 for p in pretrips if (p.user_id, p.pretrip_date) in log_keys
    )

    # Plant averages on dock wait (re-using delay report internals).
    delay = build_delay_report(anchor=anchor, dock_delay_minutes=dock_delay_minutes)
    plant_averages = delay["plant_averages"]
    delayed_dock_count = len(delay["delayed_logs"])

    # Damage reports created this week.
    damage_reports = (
        DamageReport.query
        .filter(DamageReport.created_at >= datetime.combine(start, datetime.min.time()))
        .filter(DamageReport.created_at <= datetime.combine(end, datetime.max.time()))
        .all()
    )
    damage_report_count = len(damage_reports)
    damage_reports_with_photos = sum(1 for d in damage_reports if d.photos)

    # Operational follow-ups by kind.
    fu_qs = (
        OperationalFollowUp.query
        .filter(OperationalFollowUp.created_at >= datetime.combine(start, datetime.min.time()))
        .filter(OperationalFollowUp.created_at <= datetime.combine(end, datetime.max.time()))
        .all()
    )
    wrong_location_or_unclear_dispatch_count = sum(
        1 for f in fu_qs if f.kind in ("wrong_location", "unclear_dispatch")
    )
    gage_tracking_followup_count = sum(
        1 for f in fu_qs if f.kind == "gage_tracking"
    )

    completed_moves = sum(1 for l in logs if l.arrive_time and l.depart_time)
    missing_paperwork_prevented = incomplete_transfer_count
    # 3 minutes of supervisor time saved per prevented incomplete transfer.
    supervisor_minutes_saved = missing_paperwork_prevented * 3

    return {
        "week_start": start,
        "week_end": end,
        "transfer_completion_rate": transfer_completion_rate,
        "complete_transfer_count": complete_transfer_count,
        "total_transfer_count": total_transfer_count,
        "incomplete_transfer_count": incomplete_transfer_count,
        "same_day_pretrip_count": same_day_pretrip_count,
        "hot_moves_completed_with_timestamps": hot_moves_completed_with_timestamps,
        "hot_move_count": hot_move_count,
        "plant_averages": plant_averages,
        "delayed_dock_count": delayed_dock_count,
        "damage_reports_with_photos": damage_reports_with_photos,
        "damage_report_count": damage_report_count,
        "wrong_location_or_unclear_dispatch_count": wrong_location_or_unclear_dispatch_count,
        "gage_tracking_followup_count": gage_tracking_followup_count,
        "completed_moves": completed_moves,
        "missing_paperwork_prevented": missing_paperwork_prevented,
        "supervisor_minutes_saved": supervisor_minutes_saved,
    }


# ---------------------------------------------------------------------------
# Activity feed helper (optional convenience).
# ---------------------------------------------------------------------------

def record_activity(
    user_id: int,
    category: str,
    action: str,
    title: str,
    details: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
) -> ActivityEvent:
    event = ActivityEvent(
        user_id=user_id,
        category=category,
        action=action,
        title=title,
        details=details,
        target_type=target_type,
        target_id=target_id,
    )
    db.session.add(event)
    return event
