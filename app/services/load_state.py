from datetime import date, datetime
import pytz

from app.services.plant_addresses import PLANT_LABELS, plant_label

LOAD_SUFFIX = " Load"
HOT_PART_SUFFIX = " Hot Part"
LEGACY_SIZE_LOADS = {"quarter", "half", "partial", "full", "loaded"}
UNLOAD_NOT_COMPLETED_PREFIX = "Unload not completed:"
SECONDARY_NOT_DROPPED_PREFIX = "Second-stop cargo not dropped:"
LEGACY_SECONDARY_NOT_DROPPED_PREFIX = "Hot part not dropped:"
SECONDARY_NOT_DROPPED_PREFIXES = (SECONDARY_NOT_DROPPED_PREFIX, LEGACY_SECONDARY_NOT_DROPPED_PREFIX)
TRUCK_ISSUE_PREFIX = "Truck issue:"
DETROIT_TZ = pytz.timezone("America/Detroit")
UTC_TZ = pytz.utc
MIN_PLANT_TRANSFER_MINUTES = 3


def _clean(value):
    return (value or "").strip()


def _norm(value):
    return _clean(value).lower()


def _plant_code(value):
    wanted = _norm(value)
    if not wanted:
        return None
    for code, label in PLANT_LABELS.items():
        if wanted in {_norm(code), _norm(label)}:
            return code
    return _clean(value)


def _reason_parts(log):
    reason = _clean(getattr(log, "downtime_reason", ""))
    return [part.strip() for part in reason.split(";") if part.strip()]


def _prefixed_reason(log, prefix):
    for part in _reason_parts(log):
        if part.startswith(prefix):
            return part[len(prefix) :].strip()
    return ""


def is_empty_load(value):
    return _norm(value) in {"", "empty"}


def is_legacy_size_load(value):
    return _norm(value) in LEGACY_SIZE_LOADS


def destination_load_value(plant_code):
    plant = _plant_code(plant_code)
    return f"{plant_label(plant)}{LOAD_SUFFIX}" if plant else "Empty"


def hot_part_load_value(plant_code):
    plant = _plant_code(plant_code)
    return f"{plant_label(plant)}{HOT_PART_SUFFIX}" if plant else ""


def secondary_load_value(plant_code, load_type="load"):
    return hot_part_load_value(plant_code) if _norm(load_type) == "hot" else destination_load_value(plant_code)


def load_type_from_load(value):
    return "hot" if _norm(value).endswith(_norm(HOT_PART_SUFFIX)) else "load"


def destination_from_load(value):
    text = _clean(value)
    if is_empty_load(text):
        return None
    lowered = _norm(text)
    for suffix in (LOAD_SUFFIX, HOT_PART_SUFFIX):
        if lowered.endswith(_norm(suffix)):
            text = text[: -len(suffix)].strip()
            break
    for code, label in PLANT_LABELS.items():
        if _norm(text) in {_norm(code), _norm(label)}:
            return code
    return None


def load_display(value):
    if is_empty_load(value):
        return "Empty"
    destination = destination_from_load(value)
    if destination and _norm(value).endswith(_norm(HOT_PART_SUFFIX)):
        return hot_part_load_value(destination)
    if destination:
        return destination_load_value(destination)
    return _clean(value)


def cargo_display(primary_load, secondary_load=None):
    primary = load_display(primary_load)
    secondary = load_display(secondary_load)
    parts = []
    if primary and primary != "Empty":
        parts.append(primary)
    if secondary and secondary != "Empty":
        parts.append(secondary)
    return " + ".join(parts) if parts else "Empty"


def is_load_for_plant(load_value, plant_name):
    destination = destination_from_load(load_value)
    return bool(destination and destination == _plant_code(plant_name))


def unload_not_completed(log):
    return bool(_prefixed_reason(log, UNLOAD_NOT_COMPLETED_PREFIX))


def unload_not_completed_reason(log):
    return _prefixed_reason(log, UNLOAD_NOT_COMPLETED_PREFIX)


def secondary_not_dropped(log):
    return bool(secondary_not_dropped_reason(log))


def secondary_not_dropped_reason(log):
    for prefix in SECONDARY_NOT_DROPPED_PREFIXES:
        reason = _prefixed_reason(log, prefix)
        if reason:
            return reason
    return ""


def truck_issue_reason(log):
    return _prefixed_reason(log, TRUCK_ISSUE_PREFIX)


def route_problem_reason(log):
    reason_parts = []
    for part in _reason_parts(log):
        if part.startswith((UNLOAD_NOT_COMPLETED_PREFIX, TRUCK_ISSUE_PREFIX) + SECONDARY_NOT_DROPPED_PREFIXES):
            continue
        reason_parts.append(part)
    return "; ".join(reason_parts)


def _driver_log_sort_key(log):
    return (log.date or date.min, log.arrive_time or "", log.created_at or datetime.min, log.id or 0)


def _arrival_local_datetime(log):
    value = _clean(getattr(log, "arrive_time", ""))
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return UTC_TZ.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def _depart_local_datetime(log):
    value = _clean(getattr(log, "depart_time", ""))
    if not value or not getattr(log, "date", None):
        return None
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def _state(primary_destination=None, secondary_destination=None, secondary_value=None):
    primary_value = destination_load_value(primary_destination) if primary_destination else "Empty"
    secondary_value = load_display(secondary_value) if secondary_value else (hot_part_load_value(secondary_destination) if secondary_destination else "")
    return {
        "value": primary_value,
        "destination": primary_destination,
        "destination_label": plant_label(primary_destination) if primary_destination else None,
        "secondary_value": secondary_value,
        "secondary_destination": secondary_destination,
        "secondary_destination_label": plant_label(secondary_destination) if secondary_destination else None,
        "cargo_display": cargo_display(primary_value, secondary_value),
    }


def current_load_after_logs(logs):
    current_primary_destination = None
    current_secondary_destination = None
    current_secondary_value = ""

    for log in sorted(logs, key=_driver_log_sort_key):
        arrival_destination = destination_from_load(log.load_size)
        if arrival_destination:
            current_primary_destination = arrival_destination
        elif is_empty_load(log.load_size) and current_primary_destination is None:
            current_primary_destination = None

        plant = _plant_code(log.plant_name)
        if current_primary_destination and current_primary_destination == plant and not unload_not_completed(log):
            current_primary_destination = None
        if current_secondary_destination and current_secondary_destination == plant and not secondary_not_dropped(log):
            current_secondary_destination = None
            current_secondary_value = ""

        if not log.depart_time:
            open_secondary_raw = getattr(log, "secondary_load", None)
            open_secondary_destination = destination_from_load(open_secondary_raw)
            if open_secondary_destination:
                current_secondary_destination = open_secondary_destination
                current_secondary_value = load_display(open_secondary_raw)
            continue

        if log.depart_load_size is not None:
            depart_destination = destination_from_load(log.depart_load_size)
            if is_empty_load(log.depart_load_size):
                current_primary_destination = None
            elif depart_destination:
                current_primary_destination = depart_destination

        depart_secondary_raw = getattr(log, "secondary_load", None)
        depart_secondary_destination = destination_from_load(depart_secondary_raw)
        if depart_secondary_destination:
            current_secondary_destination = depart_secondary_destination
            current_secondary_value = load_display(depart_secondary_raw)
        elif current_secondary_destination and current_secondary_destination == plant and not secondary_not_dropped(log):
            current_secondary_destination = None
            current_secondary_value = ""

    return _state(current_primary_destination, current_secondary_destination, current_secondary_value)


def build_driver_log_route_context(logs):
    by_group = {}
    for log in logs:
        by_group.setdefault((log.driver_id, log.date), []).append(log)

    routes = {}
    for group_logs in by_group.values():
        current_primary_destination = None
        current_secondary_destination = None
        current_secondary_value = ""  # full display string, e.g. "PPL Load" or "PPL Hot Part"

        sorted_logs = sorted(group_logs, key=_driver_log_sort_key)
        for index, log in enumerate(sorted_logs):
            next_log = sorted_logs[index + 1] if index + 1 < len(sorted_logs) else None
            next_plant = _plant_code(getattr(next_log, "plant_name", None)) if next_log else None
            plant = _plant_code(log.plant_name) or "Unknown"
            completed = bool(log.depart_time)
            arrival_destination = destination_from_load(log.load_size)

            if arrival_destination:
                current_primary_destination = arrival_destination
            elif is_empty_load(log.load_size) and current_primary_destination is None:
                current_primary_destination = None

            arrive_primary = destination_load_value(current_primary_destination) if current_primary_destination else "Empty"
            arrive_secondary = current_secondary_value
            arrived_at_primary_destination = bool(current_primary_destination and current_primary_destination == plant)
            arrived_at_secondary_destination = bool(current_secondary_destination and current_secondary_destination == plant)
            primary_unload_blocked = arrived_at_primary_destination and unload_not_completed(log)
            secondary_drop_blocked = arrived_at_secondary_destination and secondary_not_dropped(log)
            unloaded_on_arrival = arrived_at_primary_destination and not primary_unload_blocked
            secondary_dropped_on_arrival = arrived_at_secondary_destination and not secondary_drop_blocked

            after_primary_destination = None if unloaded_on_arrival else current_primary_destination
            after_secondary_destination = None if secondary_dropped_on_arrival else current_secondary_destination
            after_secondary_value = "" if secondary_dropped_on_arrival else current_secondary_value
            after_primary = destination_load_value(after_primary_destination) if after_primary_destination else "Empty"
            after_secondary = after_secondary_value

            depart_size = log.depart_load_size
            if depart_size is None:
                depart_primary = None
                depart_secondary = None
                depart_cargo = None
                if unloaded_on_arrival and secondary_dropped_on_arrival:
                    action = "Unloaded + secondary dropped"
                elif unloaded_on_arrival:
                    action = "Unloaded"
                elif secondary_dropped_on_arrival:
                    action = "Secondary load dropped"
                else:
                    action = "At stop"
                next_primary_destination = after_primary_destination
                next_secondary_destination = after_secondary_destination
                next_secondary_value = after_secondary_value
            else:
                depart_destination = destination_from_load(depart_size)
                if is_empty_load(depart_size):
                    depart_primary = "Empty"
                    next_primary_destination = None
                elif depart_destination:
                    depart_primary = destination_load_value(depart_destination)
                    next_primary_destination = depart_destination
                elif is_legacy_size_load(depart_size) and next_plant:
                    depart_primary = destination_load_value(next_plant)
                    next_primary_destination = next_plant
                else:
                    depart_primary = load_display(depart_size)
                    next_primary_destination = after_primary_destination

                secondary_load_raw = getattr(log, "secondary_load", None)
                depart_secondary_destination = destination_from_load(secondary_load_raw)
                if depart_secondary_destination:
                    depart_secondary = load_display(secondary_load_raw)  # preserve Load vs Hot Part suffix
                    next_secondary_destination = depart_secondary_destination
                    next_secondary_value = depart_secondary
                else:
                    depart_secondary = after_secondary
                    next_secondary_destination = after_secondary_destination
                    next_secondary_value = after_secondary_value

                depart_cargo = cargo_display(depart_primary, depart_secondary)
                if depart_secondary and depart_secondary != "Empty" and depart_primary and depart_primary != "Empty":
                    action = "Loaded two stops"
                elif depart_secondary and depart_secondary != "Empty":
                    action = "Picked up another stop"
                elif depart_primary == "Empty":
                    action = "Unloaded, departed empty" if unloaded_on_arrival else "Departed empty"
                else:
                    action = "Picked up load"

            deviation = bool(
                current_primary_destination
                and current_primary_destination != plant
                and (current_secondary_destination or destination_from_load(getattr(log, "secondary_load", None)) or getattr(log, "hot_parts", False))
            )

            warnings = []
            if unloaded_on_arrival:
                warnings.append(f"Delivered {arrive_primary} here")
            elif primary_unload_blocked:
                warnings.append(f"{arrive_primary} is still marked onboard at its destination")
            if secondary_dropped_on_arrival and arrive_secondary:
                warnings.append(f"Dropped {arrive_secondary} here")
            elif secondary_drop_blocked and arrive_secondary:
                warnings.append(f"{arrive_secondary} is still marked onboard at its destination")
            previous_log = sorted_logs[index - 1] if index > 0 else None
            if previous_log:
                previous_departure = _depart_local_datetime(previous_log)
                current_arrival = _arrival_local_datetime(log)
                previous_plant = _plant_code(previous_log.plant_name) or "Unknown"
                if previous_departure and current_arrival:
                    transit_minutes = int((current_arrival - previous_departure).total_seconds() // 60)
                    if transit_minutes < 0:
                        warnings.append(f"Arrival is before departure from {plant_label(previous_plant)}")
                    elif previous_plant != plant and transit_minutes < MIN_PLANT_TRANSFER_MINUTES:
                        warnings.append(f"Only {transit_minutes} min from {plant_label(previous_plant)} to {plant_label(plant)}; verify times or add missing stop")
            if not completed:
                warnings.append("Open stop - record departure/load before creating the next stop")

            routes[log.id] = {
                "plant": plant_label(plant),
                "arrive_desc": arrive_primary,
                "arrive_secondary_desc": arrive_secondary,
                "arrive_cargo_desc": cargo_display(arrive_primary, arrive_secondary),
                "arrive_load": load_display(log.load_size),
                "depart_desc": depart_primary,
                "depart_secondary_desc": depart_secondary,
                "depart_cargo_desc": depart_cargo,
                "depart_load": load_display(depart_size) if depart_size is not None else None,
                "depart_plan": f"Departed with {depart_cargo}" if depart_cargo is not None else None,
                "next_stop": plant_label(next_plant) if next_plant else None,
                "action": action,
                "state": "No pickup" if log.no_pickup else ("Completed" if completed else "Open"),
                "class": "complete" if completed else "open",
                "unloaded_on_arrival": unloaded_on_arrival,
                "unload_blocked": primary_unload_blocked,
                "unload_reason": unload_not_completed_reason(log),
                "secondary_dropped_on_arrival": secondary_dropped_on_arrival,
                "secondary_drop_blocked": secondary_drop_blocked,
                "secondary_drop_reason": secondary_not_dropped_reason(log),
                "after_arrival_primary": after_primary,
                "after_arrival_secondary": after_secondary,
                "after_arrival_cargo": cargo_display(after_primary, after_secondary),
                "primary_destination": current_primary_destination,
                "secondary_destination": current_secondary_destination,
                "deviation": deviation,
                "warnings": warnings,
            }

            current_primary_destination = next_primary_destination
            current_secondary_destination = next_secondary_destination
            current_secondary_value = next_secondary_value

    return routes
