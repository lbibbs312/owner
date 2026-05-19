from collections import Counter
from datetime import datetime

from app.services.plant_addresses import plant_label
from app.services.plant_time import DETROIT_TZ, arrival_local_dt


DELAY_CLASSIFIERS = (
    ("vehicle-related issue", ("truck", "regen", "maintenance", "mechanical")),
    ("process/load-handling issue", ("forgot", "not dropped", "wrong load", "cargo")),
    ("plant/dock related issue", ("dock", "wait", "line", "plant")),
)

REVIEW_SCAN_STATUSES = {
    "failed",
    "missing",
    "mismatch",
    "missed_drop",
    "needs_review",
    "pending",
    "pending_part",
    "unknown",
    "unexpected",
}

CRITICAL_SCAN_STATUSES = {"failed", "missing", "mismatch", "missed_drop", "unexpected"}
ACTIVE_STOP_REVIEW_MINUTES = 4 * 60


def _count_label(count, singular, plural=None):
    plural = plural or f"{singular}s"
    return f"{count} {singular if count == 1 else plural}"


def _count_word(count):
    words = {
        0: "No",
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    return words.get(count, str(count))


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
    if not log:
        return None
    route = _route_for(log, routes)
    return route.get("plant") or plant_label(getattr(log, "plant_name", ""))


def _stop_position(log, day_logs):
    if not log:
        return None
    for index, day_stop in enumerate(day_logs, start=1):
        if getattr(day_stop, "id", None) == getattr(log, "id", None):
            return index
    return None


def _truck_phrase(truck_id):
    if truck_id and truck_id != "Truck not set":
        return f"using truck {truck_id}"
    return "without a recorded truck ID"


def _driver_name(log):
    driver = getattr(log, "driver", None)
    return getattr(driver, "display_name", None) or getattr(driver, "username", None) or "Driver"


def _driver_short_name(log):
    return (_driver_name(log).split() or ["Driver"])[0]


def _raw_delay_reason(log):
    return (getattr(log, "downtime_reason", "") or "").strip()


def _delay_reason(log):
    raw = _raw_delay_reason(log)
    lowered = raw.lower()
    if "second-stop cargo" in lowered and ("not dropped" in lowered or "not being dropped" in lowered):
        return "second-stop cargo was not dropped"
    if raw:
        reason = raw
        if ":" in reason:
            reason = reason.split(":", 1)[1].strip() or reason
        return reason[:1].lower() + reason[1:]
    minutes = getattr(log, "dock_wait_minutes", None) or 0
    if minutes:
        return f"{minutes} minute dock wait"
    return ""


def _classify_delay(log):
    reason = f"{_raw_delay_reason(log)} {_delay_reason(log)}".lower()
    if getattr(log, "dock_wait_minutes", None) and not reason.strip():
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
        return ""

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
        return ""

    count = len(damage_reports)
    open_count = sum(
        1 for report in damage_reports if (getattr(report, "status", "") or "").lower() != "closed"
    )
    summary = f"{_count_label(count, 'damage report')} {_was_were(count)} filed."
    if open_count == 1:
        summary += " 1 damage report remains open and needs follow-up."
    elif open_count > 1:
        summary += f" {open_count} damage reports remain open and need follow-up."
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
    return f"{_human_join(flags).capitalize()} was flagged in the route log."


def has_damage_reports(damage_reports):
    return bool(damage_reports)


def has_damage_photos(damage_reports):
    return any(getattr(report, "photos", None) for report in damage_reports)


def has_delay_events(delay_logs):
    return bool(delay_logs)


def cargo_review_events(part_scan_events):
    return [
        event
        for event in part_scan_events
        if (getattr(event, "validation_status", "") or "").lower() in REVIEW_SCAN_STATUSES
    ]


def cargo_review_count(part_scan_events):
    return len(cargo_review_events(part_scan_events))


def critical_cargo_review_events(part_scan_events):
    return [
        event
        for event in cargo_review_events(part_scan_events)
        if (getattr(event, "validation_status", "") or "").lower() in CRITICAL_SCAN_STATUSES
    ]


def is_current_active_stop(open_log, day_logs):
    return bool(
        open_log
        and day_logs
        and getattr(day_logs[-1], "id", None) == getattr(open_log, "id", None)
    )


def _route_finalized(day_log):
    return bool(day_log.get("route_finalized"))


def _active_stop_minutes(open_log):
    if not open_log or not getattr(open_log, "arrive_time", None):
        return None
    log_date = getattr(open_log, "date", None)
    now = datetime.now(DETROIT_TZ)
    if log_date and log_date != now.date():
        return None
    arrived_at = arrival_local_dt(open_log)
    if not arrived_at:
        return None
    return max(0, int((now - arrived_at).total_seconds() // 60))


def is_open_stop_exception(open_log, day_logs, routes=None, route_finalized=False):
    if not open_log:
        return False
    if route_finalized:
        return True
    if not is_current_active_stop(open_log, day_logs):
        return True

    route = _route_for(open_log, routes)
    if route.get("unload_blocked") or route.get("secondary_drop_blocked"):
        return True

    active_minutes = _active_stop_minutes(open_log)
    return bool(active_minutes and active_minutes > ACTIVE_STOP_REVIEW_MINUTES)


def _arrival_label(log):
    local_dt = arrival_local_dt(log)
    if not local_dt:
        return "--"
    return local_dt.strftime("%I:%M%p").lower().lstrip("0")


def _scan_review_sentence(review_count):
    if review_count <= 0:
        return ""
    subject = "cargo scan" if review_count == 1 else "cargo scans"
    verb = "needs" if review_count == 1 else "need"
    return f"{_count_word(review_count)} {subject} {verb} manager confirmation."


def _scan_review_item_sentence(review_count):
    if review_count <= 0:
        return ""
    subject = "cargo scan" if review_count == 1 else "cargo scans"
    verb = "requires" if review_count == 1 else "require"
    return f"{review_count} {subject} {verb} manager confirmation."


def _event_status_sentence(delay_logs, damage_reports):
    delay_count = len(delay_logs)
    damage_count = len(damage_reports)
    if delay_count == 0 and damage_count == 0:
        return "No delay or damage events were reported today."
    if delay_count and damage_count:
        return (
            f"{_count_label(delay_count, 'delay event')} and "
            f"{_count_label(damage_count, 'damage report')} need review."
        )
    if delay_count:
        return f"{_count_label(delay_count, 'delay event')} {_was_were(delay_count)} reported."
    return f"{_count_label(damage_count, 'damage report')} {_was_were(damage_count)} filed."


def build_route_summary_sentence(
    log,
    completed_count,
    stop_count,
    active_stop,
    delay_logs,
    damage_reports,
    review_count,
):
    driver = _driver_short_name(log)
    pieces = [f"{driver} completed {completed_count} of {stop_count} stops."]
    if active_stop:
        pieces.append(f"He is currently at {active_stop['plant']} getting loaded.")
    elif completed_count >= stop_count:
        pieces.append("The route has departure/load-out recorded for every stop.")
    pieces.append(_event_status_sentence(delay_logs, damage_reports))
    review_sentence = _scan_review_sentence(review_count)
    if review_sentence:
        pieces.append(review_sentence)
    return " ".join(piece for piece in pieces if piece)


def _evidence_references(day_logs, routes, delay_logs, damage_reports, open_log, open_exception=False):
    references = []
    if open_log and open_exception:
        stop = _stop_label(open_log, routes)
        position = _stop_position(open_log, day_logs)
        references.append(f"Stop #{position}: {stop} is missing departure/load-out")
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


def _process_action_item(delay_log):
    reason = f"{_raw_delay_reason(delay_log)} {_delay_reason(delay_log)}".lower()
    if "second-stop cargo" in reason or "not dropped" in reason or "cargo" in reason:
        return "Review why the second-stop cargo was not dropped."
    if "wrong load" in reason:
        return "Review the wrong-load process issue."
    return "Review the process/load-handling exception."


def _severity_item(severity, title, text):
    return {"severity": severity, "title": title, "text": text}


def build_management_narrative(day_log):
    """Build deterministic management copy from collected day-log records."""
    log = day_log["log"]
    day_logs = day_log.get("day_logs") or [log]
    routes = day_log.get("log_routes") or {}
    delay_logs = day_log.get("delay_logs") or []
    damage_reports = day_log.get("damage_reports") or []
    truck_context = day_log.get("truck_context") or {}
    part_scan_events = day_log.get("part_scan_events") or []
    hot_part_proof = day_log.get("hot_part_proof")
    route_finalized = _route_finalized(day_log)

    truck_id = truck_context.get("truck_id") or "Truck not set"
    stop_count = len(day_logs)
    completed_count = sum(1 for day_stop in day_logs if getattr(day_stop, "depart_time", None))
    open_logs = [day_stop for day_stop in day_logs if not getattr(day_stop, "depart_time", None)]
    open_log = log if not getattr(log, "depart_time", None) else (open_logs[0] if open_logs else None)
    open_stop = _stop_label(open_log, routes) if open_log else None
    open_stop_position = _stop_position(open_log, day_logs) if open_log else None
    current_active = is_current_active_stop(open_log, day_logs)
    open_exception = is_open_stop_exception(open_log, day_logs, routes, route_finalized)
    review_events = cargo_review_events(part_scan_events)
    review_count = len(review_events)
    critical_scan_events = critical_cargo_review_events(part_scan_events)
    open_damage_count = sum(
        1 for report in damage_reports if (getattr(report, "status", "") or "").lower() != "closed"
    )

    active_stop = None
    if open_log and current_active and not open_exception:
        active_stop = {
            "log_id": getattr(open_log, "id", None),
            "position": open_stop_position,
            "plant": open_stop,
            "arrival_label": _arrival_label(open_log),
            "status": "Active",
            "summary": f"Driver is currently at {open_stop} getting loaded.",
            "detail": (
                f"Driver arrived at {_arrival_label(open_log)} and is getting loaded / awaiting departure."
            ),
        }

    if open_exception:
        route_status = "Needs Review"
    elif active_stop:
        route_status = "In Progress"
    else:
        route_status = "Completed"

    base = f"This route recorded {_count_label(stop_count, 'stop')} {_truck_phrase(truck_id)}."
    completed_text = f"{completed_count} of {stop_count} stops are completed."
    status_summary = f"{base} {completed_text}"
    main_issue = "Normal route activity is in progress." if active_stop else "No critical route closeout issue is visible."

    needs_review_items = []
    critical_exception_items = []

    scan_sentence = _scan_review_sentence(review_count)
    scan_review_item = _scan_review_item_sentence(review_count)
    if scan_review_item:
        needs_review_items.append(_severity_item("Needs Review", "Cargo Review", scan_review_item))

    if open_exception and open_log:
        critical_exception_items.append(
            _severity_item(
                "Critical",
                "Missing Departure",
                (
                    f"Stop #{open_stop_position} {open_stop} is missing departure/load-out "
                    "and needs manager review before route closeout."
                ),
            )
        )
    for delay_log in delay_logs:
        stop = _stop_label(delay_log, routes)
        reason = _delay_reason(delay_log) or "delay event"
        critical_exception_items.append(
            _severity_item("Critical", "Delay Event", f"{stop}: {reason}.")
        )
    if damage_reports:
        critical_exception_items.append(
            _severity_item(
                "Critical",
                "Damage Event",
                f"{_count_label(len(damage_reports), 'damage report')} {_was_were(len(damage_reports))} filed.",
            )
        )
    if critical_scan_events:
        critical_exception_items.append(
            _severity_item(
                "Critical",
                "Cargo Mismatch",
                f"{_count_label(len(critical_scan_events), 'cargo scan mismatch')} requires manager review.",
            )
        )
    if hot_part_proof and hot_part_proof.get("open_exception"):
        critical_exception_items.append(
            _severity_item("Critical", "Hot Part Exception", hot_part_proof["open_exception"])
        )

    action_items = []
    for item in needs_review_items + critical_exception_items:
        if item["text"] not in action_items:
            action_items.append(item["text"])
    for delay_log in delay_logs:
        if _classify_delay(delay_log) == "process/load-handling issue":
            item = _process_action_item(delay_log)
            if item not in action_items:
                action_items.append(item)
    if open_damage_count == 1:
        action_items.append("Assign or close the open damage report.")
    elif open_damage_count > 1:
        action_items.append(f"Assign or close {_count_label(open_damage_count, 'open damage report')}.")
    if hot_part_proof and hot_part_proof.get("open_exception"):
        action_items.append("Review the hot-part exception with dispatch.")

    summary_sentence = build_route_summary_sentence(
        log,
        completed_count,
        stop_count,
        active_stop,
        delay_logs,
        damage_reports,
        review_count,
    )
    delay_summary = _delay_summary(delay_logs)
    damage_summary = _damage_summary(damage_reports)
    flag_summary = _flag_summary(day_logs)
    event_summary = _event_status_sentence(delay_logs, damage_reports)
    exception_parts = [event_summary, flag_summary, scan_sentence]
    if hot_part_proof:
        hot_part_summary = hot_part_proof.get("proof_sentence") or ""
        if hot_part_proof.get("open_exception"):
            hot_part_summary = f"{hot_part_summary} Open exception: {hot_part_proof['open_exception']}."
        exception_parts.append(hot_part_summary)
    else:
        hot_part_summary = ""

    open_text = ""
    if active_stop:
        open_text = f"Current Active Stop: {open_stop}. {active_stop['detail']}"
    elif open_exception and open_log:
        open_text = (
            f"Stop #{open_stop_position} {open_stop} is missing departure/load-out "
            "and needs manager review."
        )
    else:
        open_text = "No open stops are visible; the route was completed."

    return {
        "status_summary": status_summary,
        "summary_sentence": summary_sentence,
        "main_issue": main_issue,
        "exception_summary": " ".join(part for part in exception_parts if part),
        "narrative_lines": [
            {"label": "Route activity", "text": completed_text},
            {"label": "Current activity", "text": open_text},
            {"label": "Delay and damage", "text": event_summary},
        ] + ([{"label": "Cargo review", "text": scan_sentence}] if scan_sentence else []),
        "action_items": action_items,
        "evidence_references": _evidence_references(
            day_logs, routes, delay_logs, damage_reports, open_log, open_exception
        ),
        "route_status": route_status,
        "current_stop": open_stop or _stop_label(log, routes),
        "current_activity": active_stop,
        "open_stop": open_stop,
        "open_stop_position": open_stop_position,
        "open_stop_exception": open_exception,
        "completed_stop_count": completed_count,
        "stop_count": stop_count,
        "delay_count": len(delay_logs),
        "damage_count": len(damage_reports),
        "open_damage_count": open_damage_count,
        "delay_summary": delay_summary,
        "damage_summary": damage_summary,
        "has_delay_events": has_delay_events(delay_logs),
        "has_damage_reports": has_damage_reports(damage_reports),
        "has_damage_photos": has_damage_photos(damage_reports),
        "cargo_review_events": review_events,
        "cargo_review_count": review_count,
        "needs_review_items": needs_review_items,
        "critical_exception_items": critical_exception_items,
        "critical_exception_count": len(critical_exception_items),
        "normal_event_summary": event_summary,
        "hot_part_summary": hot_part_summary,
    }
