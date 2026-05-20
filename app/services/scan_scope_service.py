"""Scan scoping helpers for route reports."""


def route_stop_ids(logs):
    return [log.id for log in logs if getattr(log, "id", None) is not None]


def route_scope_id(logs):
    if not logs:
        return None
    first = logs[0]
    driver_id = getattr(first, "driver_id", None)
    route_date = getattr(first, "date", None)
    if not driver_id or not route_date:
        return None
    return f"driver:{driver_id}:date:{route_date.isoformat() if hasattr(route_date, 'isoformat') else route_date}"


def scan_is_for_route(event, logs):
    stop_ids = set(route_stop_ids(logs))
    scope_id = route_scope_id(logs)
    return bool(
        (scope_id and getattr(event, "route_id", None) == scope_id)
        or getattr(event, "stop_id", None) in stop_ids
        or getattr(event, "driver_log_id", None) in stop_ids
    )
