from collections import Counter

from app.services.plant_addresses import plant_label


DELAY_CLASSIFIERS = (
    ("vehicle-related issue", ("truck", "regen", "maintenance", "mechanical")),
    ("process/load-handling issue", ("forgot", "not dropped", "wrong load", "cargo")),
    ("plant/dock related issue", ("dock", "wait", "line", "plant")),
)


def _count_label(count, singular, plural=None):
    plural = plural or f"{singular}s"
    return f"{count} {singular if count == 1 else plural}"


def _was_were(count):
    return "was" if count == 1 else "were"


def _human_join(items):
    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _route_for(log, routes):
    return (routes or {}).get(getattr(log, "id", None)) or {}


def _stop_label(log, routes):
    route = _route_for(log, routes)
    return route.get("plant") or plant_label(getattr(log, "plant_name", ""))


def _truck_phrase(truck_id):
    if truck_id and truck_id != "Truck not set":
        return f"using truck {truck_id}"
    return "without a recorded truck ID"


def _delay_reason(log):
    reason = (getattr(log, "downtime_reason", "") or "").strip()
    if reason:
        if ":" in reason:
            reason = reason.split(":", 1)[1].strip() or reason
        return reason[:1].lower() + reason[1:]
    minutes = getattr(log, "dock_wait_minutes", None) or 0
    if minutes:
        return f"{minutes} minute dock wait"
    return ""


def _action_reason(reason):
    cleaned = (reason or "the recorded process issue").strip().rstrip(".")
    return cleaned.replace("not being", "was not")


def _classify_delay(log):
    reason = _delay_reason(log).lower()
    if getattr(log, "dock_wait_minutes", None) and not reason:
        reason = "dock wait"
    for label, keywords in DELAY_CLASSIFIERS:
        if any(keyword in reason for keyword in keywords):
            return label
    return "operational exception"


def _delay_fragments(delay_logs):
    fragments = []
    for delay_log in delay_logs:
        reason = _delay_reason(delay_log)
        label = _classify_delay(delay_log)
        if reason:
            fragments.append(f"one {label} involving {reason}")
        else:
            fragments.append(f"one {label}")
    return fragments


def _delay_summary(delay_logs):
    if not delay_logs:
        return "No delay events were reported."

    count = len(delay_logs)
    fragments = _delay_fragments(delay_logs)
    if len(fragments) <= 3:
        return (
            f"{_count_label(count, 'delay event')} {_was_were(count)} reported: "
            f"{_human_join(fragments)}."
        )

    counts = Counter(_classify_delay(delay_log) for delay_log in delay_logs)
    grouped = [_count_label(total, label, f"{label}s") for label, total in counts.items()]
    return f"{_count_label(count, 'delay event')} {_was_were(count)} reported: {_human_join(grouped)}."


def _damage_summary(damage_reports):
    if not damage_reports:
        return "No damage reports were filed."

    count = len(damage_reports)
    open_count = sum(1 for report in damage_reports if (getattr(report, "status", "") or "").lower() != "closed")
    summary = f"{_count_label(count, 'damage report')} {_was_were(count)} filed."
    if open_count:
        summary += f" {_count_label(open_count, 'report')} remains open and needs follow-up."
    return summary


def _flag_summary(day_logs):
    flags = []
    if any(getattr(log, "maintenance", False) for log in day_logs):
        flags.append("maintenance")
    if any(getattr(log, "fuel", False) for log in day_logs):
        flags.append("fuel")
    if any(getattr(log, "meeting", False) for log in day_logs):
        flags.append("meeting")
    if not flags:
        return ""
    return f"{_human_join(flags).capitalize()} was also flagged in the route log."


def _evidence_references(day_logs, routes, delay_logs, damage_reports, open_log):
    references = []
    for index, day_log in enumerate(day_logs, start=1):
        route = _route_for(day_log, routes)
        stop = route.get("plant") or plant_label(getattr(day_log, "plant_name", ""))
        if day_log is open_log or getattr(day_log, "id", None) == getattr(open_log, "id", None):
            references.append(f"Stop #{index}: {stop} remains open")
            break
    for delay_log in delay_logs:
        stop = _stop_label(delay_log, routes)
        reason = _delay_reason(delay_log) or "delay event"
        references.append(f"Delay proof: {stop}, {reason}")
    for report in damage_reports:
        status = (getattr(report, "status", "") or "open").lower()
        if status != "closed":
            stop = plant_label(getattr(report, "plant_name", ""))
            references.append(f"Damage proof: {stop}, report #{report.id} open")
    return references[:5]


def build_management_narrative(day_log):
    """Build deterministic management copy from collected day-log records."""
    log = day_log["log"]
    day_logs = day_log.get("day_logs") or [log]
    routes = day_log.get("log_routes") or {}
    delay_logs = day_log.get("delay_logs") or []
    damage_reports = day_log.get("damage_reports") or []
    truck_context = day_log.get("truck_context") or {}

    truck_id = truck_context.get("truck_id") or "Truck not set"
    stop_count = len(day_logs)
    open_logs = [day_stop for day_stop in day_logs if not getattr(day_stop, "depart_time", None)]
    open_log = log if not getattr(log, "depart_time", None) else (open_logs[0] if open_logs else None)
    open_stop = _stop_label(open_log, routes) if open_log else None

    base = f"This route recorded {_count_label(stop_count, 'stop')} {_truck_phrase(truck_id)}."
    if open_log:
        route_status = "In Progress / Open Stop"
        status_summary = (
            f"{base} The route is still open at {open_stop} because no departure/load-out "
            "time has been recorded."
        )
        main_issue = f"Open follow-up: record departure/load-out for {open_stop}."
    else:
        route_status = "Completed"
        status_summary = f"{base} The route was completed with departure times recorded for all stops."
        main_issue = "No open route stop is visible from the collected log data."

    delay_summary = _delay_summary(delay_logs)
    damage_summary = _damage_summary(damage_reports)
    flag_summary = _flag_summary(day_logs)
    exception_summary = " ".join(part for part in (delay_summary, damage_summary, flag_summary) if part)

    action_items = []
    if open_log:
        action_items.append(f"Close out the open {open_stop} stop.")
    for delay_log in delay_logs:
        if _classify_delay(delay_log) == "process/load-handling issue":
            action_items.append(f"Review why {_action_reason(_delay_reason(delay_log))}.")
    open_damage_count = sum(1 for report in damage_reports if (getattr(report, "status", "") or "").lower() != "closed")
    if open_damage_count == 1:
        action_items.append("Assign or close the open damage report.")
    elif open_damage_count > 1:
        action_items.append(f"Assign or close {_count_label(open_damage_count, 'open damage report')}.")
    if not action_items:
        action_items.append("No immediate management action is flagged from this log.")

    return {
        "status_summary": status_summary,
        "main_issue": main_issue,
        "exception_summary": exception_summary,
        "action_items": action_items,
        "evidence_references": _evidence_references(day_logs, routes, delay_logs, damage_reports, open_log),
        "route_status": route_status,
        "current_stop": open_stop or _stop_label(log, routes),
        "delay_count": len(delay_logs),
        "damage_count": len(damage_reports),
        "open_damage_count": open_damage_count,
    }
