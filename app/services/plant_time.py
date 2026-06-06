from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from flask import g, has_request_context
import pytz

from app.models import AuditEvent, DriverLog
from app.services.driver_wait import dock_time_review_label
from app.services.load_state import build_driver_log_route_context, cargo_delta_for_stop, classify_stop_role, is_empty_load
from app.services.plant_addresses import PLANT_LABELS, plant_label


DETROIT_TZ = pytz.timezone("America/Detroit")
MIN_SAMPLE_MINUTES = 3
MAX_SAMPLE_MINUTES = 6 * 60
RECENT_HISTORY_DAYS = 30
TODAY_WEIGHT = 0.7
HISTORY_WEIGHT = 0.3


def _plant_code(value):
    wanted = (value or "").strip().lower()
    if not wanted:
        return ""
    for code, label in PLANT_LABELS.items():
        if wanted in {code.lower(), label.lower()}:
            return code
    return (value or "").strip()


def _format_clock(dt):
    if not dt:
        return ""
    return dt.strftime("%I:%M%p").lower().lstrip("0")


def format_minutes(minutes):
    if minutes is None:
        return "No baseline"
    minutes = int(round(minutes))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _parse_local_hhmm(route_date, value):
    value = (value or "").strip()
    if not route_date or not value:
        return None
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            parsed = datetime.strptime(value, fmt).time()
            return DETROIT_TZ.localize(datetime.combine(route_date, parsed))
        except ValueError:
            continue
    return None


def arrival_local_dt(log):
    value = (getattr(log, "arrive_time", None) or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            utc_dt = pytz.utc.localize(datetime.strptime(value, fmt))
            return utc_dt.astimezone(DETROIT_TZ)
        except ValueError:
            continue
    return _parse_local_hhmm(getattr(log, "date", None), value)


def depart_local_dt(log):
    return _parse_local_hhmm(getattr(log, "date", None), getattr(log, "depart_time", None))


def stop_minutes(log):
    arrival = arrival_local_dt(log)
    departure = depart_local_dt(log)
    if not arrival or not departure:
        return None
    return int((departure - arrival).total_seconds() // 60)


def _action_type(log, route=None):
    if getattr(log, "hot_parts", False):
        return "hot_part"
    role = classify_stop_role(log, route)
    if role == "mixed_transfer":
        return "mixed"
    if role == "pickup_origin":
        return "load"
    if role in {"drop_only", "multi_stop_drop"}:
        return "unload"
    if role == "current_open":
        delta = cargo_delta_for_stop(log, route)
        if delta["arrived"] and delta["departed"]:
            return "mixed"
        if delta["departed"]:
            return "load"
        if delta["arrived"]:
            return "unload"
    return "non_cargo"


def plant_time_sample_eligibility(log, *, route=None, edited_log_ids=None):
    edited_log_ids = edited_log_ids or set()
    arrival = arrival_local_dt(log)
    departure = depart_local_dt(log)
    minutes = stop_minutes(log)
    role = classify_stop_role(log, route)
    action_type = _action_type(log, route)
    delta = cargo_delta_for_stop(log, route)
    has_cargo_activity = bool(delta["delivered"] or delta["picked_up"] or delta["removed"] or delta["retained"])
    excluded_reason = None

    if not getattr(log, "depart_time", None):
        excluded_reason = "Departure missing"
    elif arrival is None or departure is None:
        excluded_reason = "Arrival/departure time invalid"
    elif minutes is None or minutes < 0:
        excluded_reason = "Departure before arrival"
    elif minutes < MIN_SAMPLE_MINUTES:
        excluded_reason = "Under 3 minutes"
    elif minutes > MAX_SAMPLE_MINUTES:
        excluded_reason = "Over 6 hours"
    elif getattr(log, "maintenance", False):
        excluded_reason = "Maintenance stop"
    elif getattr(log, "fuel", False):
        excluded_reason = "Fuel stop"
    elif getattr(log, "meeting", False):
        excluded_reason = "Meeting stop"
    elif getattr(log, "id", None) in edited_log_ids:
        excluded_reason = "Manually corrected"
    elif role not in {"pickup_origin", "mixed_transfer"}:
        excluded_reason = f"Not pickup-origin stop: {role}"
    elif not delta["picked_up"]:
        excluded_reason = "No new cargo picked up"
    elif not has_cargo_activity and is_empty_load(getattr(log, "load_size", None)) and is_empty_load(getattr(log, "depart_load_size", None)):
        excluded_reason = "No cargo movement"

    return {
        "included": excluded_reason is None,
        "training_eligible": excluded_reason is None,
        "excluded_reason": excluded_reason,
        "stop_role": role,
        "action_type": action_type,
    }


def _edited_driver_log_ids(log_ids):
    if not log_ids:
        return set()
    return {
        target_id
        for target_id, in AuditEvent.query.with_entities(AuditEvent.target_id)
        .filter(
            AuditEvent.target_type == "driver_log",
            AuditEvent.target_id.in_(log_ids),
            AuditEvent.action.in_(["updated", "edited"]),
        )
        .all()
    }


def stop_time_sample(log, *, edited_log_ids=None, route=None):
    edited_log_ids = edited_log_ids or set()
    arrival = arrival_local_dt(log)
    departure = depart_local_dt(log)
    minutes = stop_minutes(log)
    eligibility = plant_time_sample_eligibility(log, route=route, edited_log_ids=edited_log_ids)

    return {
        "log": log,
        "plant_id": _plant_code(getattr(log, "plant_name", None)),
        "plant": plant_label(getattr(log, "plant_name", None)),
        "arrival": arrival,
        "departure": departure,
        "minutes": minutes,
        "minutes_label": format_minutes(minutes) if minutes is not None else "--",
        "action_type": eligibility["action_type"],
        "stop_role": eligibility["stop_role"],
        "training_eligible": eligibility["training_eligible"],
        "included": eligibility["included"],
        "excluded_reason": eligibility["excluded_reason"],
    }


def _request_sample_cache():
    if not has_request_context():
        return None
    cache = getattr(g, "_plant_time_sample_cache", None)
    if cache is None:
        cache = {}
        g._plant_time_sample_cache = cache
    return cache


def _recent_sample_groups(anchor_date, history_days=RECENT_HISTORY_DAYS):
    cache_key = (anchor_date, history_days)
    cache = _request_sample_cache()
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    start_date = anchor_date - timedelta(days=history_days)
    logs = (
        DriverLog.query.filter(
            DriverLog.deleted_at.is_(None),
            DriverLog.date >= start_date,
            DriverLog.date <= anchor_date,
        )
        .order_by(DriverLog.date.asc(), DriverLog.created_at.asc(), DriverLog.id.asc())
        .all()
    )
    edited_ids = _edited_driver_log_ids([log.id for log in logs])
    routes = build_driver_log_route_context(logs)
    groups = defaultdict(list)
    for log in logs:
        plant_id = _plant_code(getattr(log, "plant_name", None))
        if not plant_id:
            continue
        groups[plant_id].append(stop_time_sample(log, edited_log_ids=edited_ids, route=routes.get(log.id)))

    result = dict(groups)
    if cache is not None:
        cache[cache_key] = result
    return result


def _samples_for_plant(plant_id, anchor_date, history_days=RECENT_HISTORY_DAYS, exclude_log_id=None):
    plant_id = _plant_code(plant_id)
    samples = list(_recent_sample_groups(anchor_date, history_days).get(plant_id, []))
    if exclude_log_id is not None:
        samples = [
            sample for sample in samples
            if getattr(sample["log"], "id", None) != exclude_log_id
        ]
    return samples


def _average(samples):
    values = [sample["minutes"] for sample in samples if sample["included"] and sample["minutes"] is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _confidence(today_count, history_count):
    if today_count >= 5:
        return "High"
    if today_count >= 2:
        return "Medium"
    if today_count == 1:
        return "Low"
    if history_count:
        return "Historical estimate"
    return "No baseline"


def plant_time_forecast(plant_id, *, anchor_date=None, now=None, exclude_log_id=None):
    now = now or datetime.now(DETROIT_TZ)
    anchor_date = anchor_date or now.date()
    samples = _samples_for_plant(plant_id, anchor_date, exclude_log_id=exclude_log_id)
    today_samples = [sample for sample in samples if sample["log"].date == anchor_date and sample["included"]]
    history_samples = [sample for sample in samples if sample["log"].date < anchor_date and sample["included"]]

    today_average = _average(today_samples)
    history_average = _average(history_samples)
    if today_average is not None and history_average is not None:
        estimate = (today_average * TODAY_WEIGHT) + (history_average * HISTORY_WEIGHT)
        basis = f"Today {format_minutes(today_average)} from {len(today_samples)} load(s); 30-day {format_minutes(history_average)}"
    elif today_average is not None:
        estimate = today_average
        basis = f"Today {format_minutes(today_average)} from {len(today_samples)} load(s)"
    elif history_average is not None:
        estimate = history_average
        basis = f"30-day history {format_minutes(history_average)} from {len(history_samples)} load(s)"
    else:
        estimate = None
        basis = "No timing history yet"

    values = [sample["minutes"] for sample in today_samples if sample["minutes"] is not None]
    return {
        "plant_id": _plant_code(plant_id),
        "plant": plant_label(plant_id),
        "estimate_minutes": estimate,
        "estimate_label": format_minutes(estimate),
        "today_average": today_average,
        "today_average_label": format_minutes(today_average),
        "history_average": history_average,
        "history_average_label": format_minutes(history_average),
        "today_count": len(today_samples),
        "history_count": len(history_samples),
        "confidence": _confidence(len(today_samples), len(history_samples)),
        "basis": basis,
        "median_minutes": median(values) if values else None,
        "min_minutes": min(values) if values else None,
        "max_minutes": max(values) if values else None,
        "samples": samples,
    }


def forecast_for_stop(log, *, now=None):
    now = now or datetime.now(DETROIT_TZ)
    forecast = plant_time_forecast(
        getattr(log, "plant_name", None),
        anchor_date=getattr(log, "date", None) or now.date(),
        now=now,
        exclude_log_id=getattr(log, "id", None),
    )
    arrival = arrival_local_dt(log)
    departure = depart_local_dt(log)
    estimate = forecast["estimate_minutes"]
    ready_at = arrival + timedelta(minutes=estimate) if arrival and estimate is not None else None
    if arrival and departure:
        elapsed = int((departure - arrival).total_seconds() // 60)
    else:
        elapsed = int((now - arrival).total_seconds() // 60) if arrival else None
    if elapsed is not None and elapsed < 0:
        elapsed = 0
    remaining = int(round(estimate - elapsed)) if estimate is not None and elapsed is not None and not departure else 0 if departure else None

    status = "Collecting samples"
    severity = "muted"
    delay_minutes = None
    if elapsed is not None:
        delay_minutes = max(0, int(round(elapsed - estimate))) if estimate is not None else None
        status = dock_time_review_label(elapsed)
        if elapsed >= 180:
            severity = "high"
        elif elapsed >= 120:
            severity = "warning"
        else:
            severity = "ok"

    return {
        **forecast,
        "arrival": arrival,
        "arrival_label": _format_clock(arrival),
        "ready_at": ready_at,
        "ready_at_label": _format_clock(ready_at) if ready_at else "",
        "elapsed_minutes": elapsed,
        "elapsed_label": format_minutes(elapsed) if elapsed is not None else "--",
        "remaining_minutes": remaining,
        "remaining_label": format_minutes(max(0, remaining)) if remaining is not None else "--",
        "status": status,
        "severity": severity,
        "delay_minutes": delay_minutes,
    }


def route_stop_forecasts(logs, *, now=None):
    return {
        log.id: forecast_for_stop(log, now=now)
        for log in logs
        if getattr(log, "id", None) is not None
    }


def plant_forecast_rows(anchor_date=None, *, now=None):
    now = now or datetime.now(DETROIT_TZ)
    anchor_date = anchor_date or now.date()
    plant_ids = set(_recent_sample_groups(anchor_date).keys())
    rows = [plant_time_forecast(plant_id, anchor_date=anchor_date, now=now) for plant_id in plant_ids]
    return sorted(rows, key=lambda row: (row["estimate_minutes"] is None, -(row["estimate_minutes"] or 0), row["plant"]))
