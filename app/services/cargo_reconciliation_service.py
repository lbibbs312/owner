"""Cargo reconciliation rules for manager route approval."""

from app.services.load_state import route_problem_reason, secondary_not_dropped_reason
from app.services.plant_addresses import plant_label


def _plant(log, route):
    return (route or {}).get("plant") or plant_label(getattr(log, "plant_name", ""))


def reconcile_cargo(logs, log_routes=None):
    """Classify cargo state from route context.

    Multi-stop cargo is normal when a primary load is dropped and a secondary load
    continues to its own destination. Both primary unloads and secondary drops count
    as cargo closeout events.
    """
    log_routes = log_routes or {}
    issues = []
    final_cargo = None

    for index, log in enumerate(logs):
        route = log_routes.get(log.id, {})
        plant = _plant(log, route)
        cargo_issue = secondary_not_dropped_reason(log) or route_problem_reason(log)
        if cargo_issue:
            issues.append(f"{plant}: {cargo_issue}")
        if route.get("unload_blocked") or route.get("secondary_drop_blocked"):
            blocked = route.get("unload_reason") or route.get("secondary_drop_reason") or "Cargo still marked onboard at destination"
            issues.append(f"{plant}: {blocked}")
        if route.get("unloaded_on_arrival") or route.get("secondary_dropped_on_arrival"):
            final_cargo = {
                "index": index,
                "log": log,
                "log_id": getattr(log, "id", None),
                "plant": plant,
                "type": "secondary_drop" if route.get("secondary_dropped_on_arrival") and not route.get("unloaded_on_arrival") else "primary_unload",
            }

    later_cargo_issues = []
    if final_cargo:
        for log in logs[final_cargo["index"] + 1:]:
            route = log_routes.get(log.id, {})
            if route.get("unload_blocked") or route.get("secondary_drop_blocked"):
                later_cargo_issues.append(_plant(log, route))

    return {
        "issues": issues,
        "final_cargo": final_cargo,
        "later_cargo_issues": later_cargo_issues,
    }
