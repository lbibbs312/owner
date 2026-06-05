"""Shared route-state rules for reports and manager review surfaces."""

from app.services.plant_addresses import plant_label


def _plant(log, route):
    return (route or {}).get("plant") or plant_label(getattr(log, "plant_name", ""))


def build_route_state(logs, log_routes=None, stop_forecasts=None, route_finalized=False):
    """Build route and stop state without requiring templates to infer meaning."""
    log_routes = log_routes or {}
    stop_forecasts = stop_forecasts or {}
    rows = []
    open_logs = [log for log in logs if not getattr(log, "depart_time", None)]
    current_open_log = open_logs[-1] if open_logs and logs and open_logs[-1].id == logs[-1].id else None
    route_end_log = current_open_log if route_finalized else None

    for index, log in enumerate(logs, start=1):
        route = log_routes.get(log.id, {})
        forecast = stop_forecasts.get(log.id, {})
        plant = _plant(log, route)
        is_open = not bool(getattr(log, "depart_time", None))
        is_current = bool(current_open_log and current_open_log.id == log.id and not route_finalized)
        is_route_end = bool(route_end_log and route_end_log.id == log.id)
        if is_current:
            status = "Current"
            note = "Awaiting load-out/departure"
        elif is_route_end:
            status = "Finalized"
            note = "Route finalized at final stop"
        elif is_open:
            status = "Open"
            note = "Missing departure"
        else:
            status = "Completed"
            note = route.get("action") or "Completed"
        rows.append({
            "index": index,
            "log": log,
            "route": route,
            "status": status,
            "plant": plant,
            "arrive_time": getattr(log, "arrive_time", None),
            "depart_time": getattr(log, "depart_time", None),
            "cargo_out": route.get("depart_cargo_desc") if route.get("depart_cargo_desc") is not None else (getattr(log, "depart_load_size", None) or "--"),
            "note": note,
            "forecast_status": forecast.get("status") or "On pace",
            "forecast_class": forecast.get("severity") or "ok",
        })

    current_activity = None
    if current_open_log and not route_finalized:
        route = log_routes.get(current_open_log.id, {})
        forecast = stop_forecasts.get(current_open_log.id, {})
        plant = _plant(current_open_log, route)
        current_activity = {
            "log": current_open_log,
            "plant": plant,
            "status": "Current Active Stop",
            "forecast_status": forecast.get("status") or "On pace",
            "forecast_class": forecast.get("severity") or "ok",
            "detail": "Awaiting load-out/departure",
            "pickup_estimate": f"Pickup estimate: ready around {forecast.get('ready_at_label')}" if forecast.get("ready_at_label") else "Pickup estimate: timing history pending",
        }

    if route_finalized:
        route_status = "Finalized"
    elif current_activity:
        route_status = "Active"
    elif logs and all(getattr(log, "depart_time", None) for log in logs):
        route_status = "Finalization Required"
    elif logs:
        route_status = "Active"
    else:
        route_status = "No Route"

    return {
        "route_status": route_status,
        "rows": rows,
        "current_activity": current_activity,
        "all_departed": bool(logs) and all(getattr(log, "depart_time", None) for log in logs),
    }
