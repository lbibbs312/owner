"""Scan scoping helpers for route reports."""


def route_stop_ids(logs):
    return [log.id for log in logs if getattr(log, "id", None) is not None]


def scan_is_for_route(event, logs):
    return getattr(event, "stop_id", None) in set(route_stop_ids(logs))
