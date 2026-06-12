from datetime import date, datetime
import re

import pytz

from app.services.plant_addresses import (
    PLANT_LABELS,
    UNKNOWN_LOAD_LABEL,
    UNKNOWN_PLANT_LABEL,
    is_ambiguous_plant,
    plant_label,
)

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
SERVICE_STOP_TERMS = ("ryder", "fuel", "gas", "service", "truck stop")


def _clean(value):
    return (value or "").strip()


def _norm(value):
    return _clean(value).lower()


def _plant_code(value):
    wanted = _norm(value)
    if not wanted:
        return None
    if is_ambiguous_plant(value):
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
    return _norm(value) in {"", "empty", "none", "no load", "no pickup", "no-pickup", "n/a", "na", "--", "null"}


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
    if is_ambiguous_plant(text):
        return None
    for code, label in PLANT_LABELS.items():
        if _norm(text) in {_norm(code), _norm(label)}:
            return code
    return None


def load_display(value):
    if is_empty_load(value):
        return "Empty"
    text = _clean(value)
    normalized_text = text
    for suffix in (LOAD_SUFFIX, HOT_PART_SUFFIX):
        if _norm(normalized_text).endswith(_norm(suffix)):
            normalized_text = normalized_text[: -len(suffix)].strip()
            break
    if is_ambiguous_plant(normalized_text):
        return UNKNOWN_LOAD_LABEL
    destination = destination_from_load(value)
    if destination and _norm(value).endswith(_norm(HOT_PART_SUFFIX)):
        return hot_part_load_value(destination)
    if destination:
        return destination_load_value(destination)
    return text


def normalize_cargo_value(value):
    """Return the canonical cargo label used by route-state services."""
    return freight_cargo_text(load_display(value))


FREIGHT_DESTINATION_SEPARATOR = " -> "
_FREIGHT_MATCH_STOPWORDS = {"inc", "llc", "co", "corp", "corporation", "company", "the", "of", "and"}


def is_freight_load(value):
    """Freeform (day-driver) cargo the plant chain cannot resolve to a code."""
    return bool(
        not is_empty_load(value)
        and not is_legacy_size_load(value)
        and destination_from_load(value) is None
    )


def freight_destination_text(value):
    """The typed '-> destination' part of a freight label, if any."""
    text = _clean(value)
    if FREIGHT_DESTINATION_SEPARATOR in text:
        return text.split(FREIGHT_DESTINATION_SEPARATOR)[-1].strip()
    return ""


def freight_cargo_text(value):
    """The cargo part of a freeform freight label, without its destination."""
    text = _clean(value)
    if FREIGHT_DESTINATION_SEPARATOR in text:
        return text.rsplit(FREIGHT_DESTINATION_SEPARATOR, 1)[0].strip()
    return text


def _freight_with_prior_destination(previous, current):
    current = _clean(current)
    if not current:
        return ""
    if freight_destination_text(current):
        return current
    if (
        previous
        and freight_destination_text(previous)
        and _norm(freight_cargo_text(previous)) == _norm(freight_cargo_text(current))
    ):
        return previous
    return current


def _match_text(value):
    return re.sub(r"[^a-z0-9 ]+", " ", _norm(value)).strip()


def freight_load_destined_here(load_value, *location_texts):
    """Match a typed freight destination against a stop's name/address.

    Case- and punctuation-insensitive; 'Raleigh east' matches a stop named
    'Raleigh East' or an address containing it.
    """
    destination = _match_text(freight_destination_text(load_value))
    if not destination:
        return False
    haystacks = [_match_text(text) for text in location_texts if _clean(text)]
    for haystack in haystacks:
        if haystack and (destination in haystack or haystack in destination):
            return True
    tokens = {token for token in destination.split() if token not in _FREIGHT_MATCH_STOPWORDS}
    if not tokens:
        return False
    combined = set()
    for haystack in haystacks:
        combined.update(haystack.split())
    return tokens <= combined


def cargo_display(primary_load, secondary_load=None):
    primary = freight_cargo_text(load_display(primary_load))
    secondary = freight_cargo_text(load_display(secondary_load))
    parts = []
    if primary and primary != "Empty":
        parts.append(primary)
    if secondary and secondary != "Empty":
        parts.append(secondary)
    return " + ".join(parts) if parts else "Empty"


def normalized_cargo_items(primary_load=None, secondary_load=None):
    """Return normalized non-empty cargo labels for comparison/reporting."""
    items = []
    for value in (primary_load, secondary_load):
        for part in _clean(value).split("+"):
            label = normalize_cargo_value(part)
            if label and label != "Empty" and label not in items:
                items.append(label)
    return tuple(items)


def cargo_delta_for_stop(log, route=None):
    """Summarize cargo movement at a stop from route context without guessing.

    This keeps actual cargo separate from next-load predictions. It only reports
    cargo as delivered or picked up when the route context or log values make
    that movement explicit.
    """
    route = route or {}
    arrived = normalized_cargo_items(
        route.get("arrive_desc") if route.get("arrive_desc") is not None else getattr(log, "load_size", None),
        route.get("arrive_secondary_desc") if route.get("arrive_secondary_desc") is not None else None,
    )
    departed = normalized_cargo_items(
        route.get("depart_desc") if route.get("depart_desc") is not None else getattr(log, "depart_load_size", None),
        route.get("depart_secondary_desc") if route.get("depart_secondary_desc") is not None else getattr(log, "secondary_load", None),
    )

    delivered = []
    if route.get("unloaded_on_arrival"):
        delivered.extend(normalized_cargo_items(route.get("arrive_desc")))
    if route.get("secondary_dropped_on_arrival"):
        delivered.extend(normalized_cargo_items(route.get("arrive_secondary_desc")))

    delivered_set = set(delivered)
    picked_up = [item for item in departed if item not in arrived or item in delivered_set]
    retained = [item for item in departed if item in arrived and item not in delivered_set]
    removed = [item for item in arrived if item not in departed and item not in delivered_set]

    return {
        "plant": route.get("plant") or plant_label(getattr(log, "plant_name", None)),
        "arrived": arrived,
        "departed": departed,
        "delivered": tuple(dict.fromkeys(delivered)),
        "picked_up": tuple(dict.fromkeys(picked_up)),
        "retained": tuple(dict.fromkeys(retained)),
        "removed": tuple(dict.fromkeys(removed)),
        "open": not bool(getattr(log, "depart_time", None)),
    }


def is_service_stop(log):
    """Return whether this route stop is for fuel, maintenance, meeting, or service."""
    plant_text = f"{getattr(log, 'plant_name', '')} {plant_label(getattr(log, 'plant_name', ''))}".lower()
    return bool(
        getattr(log, "maintenance", False)
        or getattr(log, "fuel", False)
        or getattr(log, "meeting", False)
        or truck_issue_reason(log)
        or any(term in plant_text for term in SERVICE_STOP_TERMS)
    )


def service_stop_label(log):
    if getattr(log, "fuel", False):
        return "Fuel stop"
    if getattr(log, "maintenance", False) or truck_issue_reason(log):
        return "Maintenance stop"
    if getattr(log, "meeting", False):
        return "Meeting stop"
    plant_text = f"{getattr(log, 'plant_name', '')} {plant_label(getattr(log, 'plant_name', ''))}".lower()
    if "ryder" in plant_text:
        return "Ryder service stop"
    return "Service stop"


def classify_stop_role(log, route=None, *, is_current_open=False, is_final_stop=False):
    """Classify a stop's cargo role from explicit cargo deltas."""
    delta = cargo_delta_for_stop(log, route)
    if is_current_open and delta["open"]:
        return "current_open"
    if is_service_stop(log):
        return "service_stop"
    if is_final_stop:
        return "final_stop"
    if delta["open"]:
        return "current_open"
    has_delivery = bool(delta["delivered"] or delta["removed"])
    has_pickup = bool(delta["picked_up"])
    if has_delivery and has_pickup:
        return "mixed_transfer"
    if has_delivery:
        return "multi_stop_drop" if delta["retained"] else "drop_only"
    if has_pickup:
        return "pickup_origin"
    if getattr(log, "no_pickup", False) or not delta["departed"]:
        return "no_pickup"
    if delta["retained"]:
        return "multi_stop_drop"
    return "no_pickup"


def stop_role_details(log, route=None, *, is_current_open=False, is_final_stop=False):
    delta = cargo_delta_for_stop(log, route)
    role = classify_stop_role(log, route, is_current_open=is_current_open, is_final_stop=is_final_stop)
    cargo_added = tuple(delta["picked_up"])
    cargo_removed = tuple(dict.fromkeys(delta["delivered"] + delta["removed"]))
    cargo_retained = tuple(delta["retained"])
    return {
        "stop_role": role,
        "cargo_added": cargo_added,
        "cargo_removed": cargo_removed,
        "cargo_retained": cargo_retained,
        "arrival_cargo": " + ".join(delta["arrived"]) if delta["arrived"] else "Empty",
        "departure_cargo": " + ".join(delta["departed"]) if delta["departed"] else "Empty",
        "train_pickup_timing": bool(
            not delta["open"]
            and role in {"pickup_origin", "mixed_transfer"}
            and cargo_added
        ),
    }


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
    # Freight (freeform) loads ride along by their typed label — the plant
    # chain above can't see them at all.
    freight_primary = ""
    freight_secondary = ""

    for log in sorted(logs, key=_driver_log_sort_key):
        arrival_destination = destination_from_load(log.load_size)
        if arrival_destination:
            current_primary_destination = arrival_destination
        elif is_empty_load(log.load_size) and current_primary_destination is None:
            current_primary_destination = None
        if is_freight_load(log.load_size):
            freight_primary = _freight_with_prior_destination(freight_primary, log.load_size)

        plant = _plant_code(log.plant_name)
        if not log.depart_time:
            open_secondary_raw = getattr(log, "secondary_load", None)
            open_secondary_destination = destination_from_load(open_secondary_raw)
            if open_secondary_destination:
                current_secondary_destination = open_secondary_destination
                current_secondary_value = load_display(open_secondary_raw)
            elif is_freight_load(open_secondary_raw):
                freight_secondary = _freight_with_prior_destination(freight_secondary, open_secondary_raw)
            continue

        service_stop = is_service_stop(log)
        if current_primary_destination and current_primary_destination == plant and not service_stop and not unload_not_completed(log):
            current_primary_destination = None
        if current_secondary_destination and current_secondary_destination == plant and not service_stop and not secondary_not_dropped(log):
            current_secondary_destination = None
            current_secondary_value = ""

        if log.depart_load_size is not None:
            depart_destination = destination_from_load(log.depart_load_size)
            if is_empty_load(log.depart_load_size):
                current_primary_destination = None
            elif depart_destination:
                current_primary_destination = depart_destination
            # Departure is the freight truth: a freight label rides on, anything
            # else (Empty or a plant load) means the freight load left the truck.
            freight_primary = _freight_with_prior_destination(freight_primary, log.depart_load_size) if is_freight_load(log.depart_load_size) else ""

        depart_secondary_raw = getattr(log, "secondary_load", None)
        depart_secondary_destination = destination_from_load(depart_secondary_raw)
        if depart_secondary_destination:
            current_secondary_destination = depart_secondary_destination
            current_secondary_value = load_display(depart_secondary_raw)
        elif current_secondary_destination and current_secondary_destination == plant and not service_stop and not secondary_not_dropped(log):
            current_secondary_destination = None
            current_secondary_value = ""
        freight_secondary = _freight_with_prior_destination(freight_secondary, depart_secondary_raw) if is_freight_load(depart_secondary_raw) else ""

    state = _state(current_primary_destination, current_secondary_destination, current_secondary_value)
    if state["value"] == "Empty" and freight_primary:
        state["value"] = freight_cargo_text(freight_primary)
        inline_destination = freight_destination_text(freight_primary)
        if inline_destination:
            state["destination"] = inline_destination
            state["destination_label"] = inline_destination
    if not state["secondary_value"] and freight_secondary:
        state["secondary_value"] = freight_cargo_text(freight_secondary)
        inline_secondary = freight_destination_text(freight_secondary)
        if inline_secondary:
            state["secondary_destination"] = inline_secondary
            state["secondary_destination_label"] = inline_secondary
    state["cargo_display"] = cargo_display(state["value"], state["secondary_value"])
    return state


def build_driver_log_route_context(logs):
    by_group = {}
    for log in logs:
        by_group.setdefault((log.driver_id, log.date), []).append(log)

    routes = {}
    for group_logs in by_group.values():
        current_primary_destination = None
        current_secondary_destination = None
        current_secondary_value = ""  # full display string, e.g. "PPL Load" or "PPL Hot Part"
        # Freight (freeform) loads ride along by their typed label; the plant
        # chain above reads them as Empty.
        freight_primary = ""
        freight_secondary = ""

        sorted_logs = sorted(group_logs, key=_driver_log_sort_key)
        for index, log in enumerate(sorted_logs):
            next_log = sorted_logs[index + 1] if index + 1 < len(sorted_logs) else None
            next_plant = _plant_code(getattr(next_log, "plant_name", None)) if next_log else None
            plant = _plant_code(log.plant_name) or UNKNOWN_PLANT_LABEL
            completed = bool(log.depart_time)
            arrival_destination = destination_from_load(log.load_size)
            service_stop = is_service_stop(log)

            if arrival_destination:
                current_primary_destination = arrival_destination
            elif is_empty_load(log.load_size) and current_primary_destination is None:
                current_primary_destination = None
            if is_freight_load(log.load_size):
                freight_primary = _freight_with_prior_destination(freight_primary, log.load_size)
            if not completed and is_freight_load(getattr(log, "secondary_load", None)):
                # An open stop's secondary slot holds what it arrived with.
                freight_secondary = _freight_with_prior_destination(freight_secondary, log.secondary_load)
            arrive_freight_primary = freight_primary
            arrive_freight_secondary = freight_secondary

            arrive_primary = destination_load_value(current_primary_destination) if current_primary_destination else "Empty"
            if arrive_primary == "Empty" and arrive_freight_primary:
                arrive_primary = freight_cargo_text(arrive_freight_primary)
            arrive_secondary = current_secondary_value or freight_cargo_text(arrive_freight_secondary)
            arrived_at_primary_destination = bool(current_primary_destination and current_primary_destination == plant)
            arrived_at_secondary_destination = bool(current_secondary_destination and current_secondary_destination == plant)
            primary_unload_blocked = arrived_at_primary_destination and completed and not service_stop and unload_not_completed(log)
            secondary_drop_blocked = arrived_at_secondary_destination and completed and not service_stop and secondary_not_dropped(log)
            unloaded_on_arrival = arrived_at_primary_destination and completed and not service_stop and not primary_unload_blocked
            secondary_dropped_on_arrival = arrived_at_secondary_destination and completed and not service_stop and not secondary_drop_blocked

            after_primary_destination = None if unloaded_on_arrival else current_primary_destination
            after_secondary_destination = None if secondary_dropped_on_arrival else current_secondary_destination
            after_secondary_value = "" if secondary_dropped_on_arrival else current_secondary_value
            after_primary = destination_load_value(after_primary_destination) if after_primary_destination else "Empty"
            if after_primary == "Empty" and arrive_freight_primary:
                after_primary = freight_cargo_text(arrive_freight_primary)
            after_secondary = after_secondary_value or freight_cargo_text(arrive_freight_secondary)

            depart_size = log.depart_load_size
            if depart_size is None:
                depart_primary = None
                depart_secondary = None
                depart_cargo = None
                if service_stop:
                    action = service_stop_label(log)
                elif unloaded_on_arrival and secondary_dropped_on_arrival:
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
                    depart_primary = freight_cargo_text(load_display(depart_size))
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
                    if arrive_freight_secondary or is_freight_load(secondary_load_raw):
                        # Freight second loads: the closed stop's stored value is
                        # the departure truth — None/Empty means dropped here.
                        depart_secondary = freight_cargo_text(secondary_load_raw) if is_freight_load(secondary_load_raw) else ""

                # Departure is the freight truth for what rides to the next stop.
                freight_primary = _freight_with_prior_destination(freight_primary, depart_size) if is_freight_load(depart_size) else ""
                freight_secondary = _freight_with_prior_destination(freight_secondary, secondary_load_raw) if is_freight_load(secondary_load_raw) else ""

                depart_cargo = cargo_display(depart_primary, depart_secondary)
                if service_stop:
                    action = service_stop_label(log)
                elif depart_secondary and depart_secondary != "Empty" and depart_primary and depart_primary != "Empty":
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
                previous_plant = _plant_code(previous_log.plant_name) or UNKNOWN_PLANT_LABEL
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
                "arrived_at_primary_destination": arrived_at_primary_destination,
                "unload_blocked": primary_unload_blocked,
                "unload_reason": unload_not_completed_reason(log),
                "secondary_dropped_on_arrival": secondary_dropped_on_arrival,
                "arrived_at_secondary_destination": arrived_at_secondary_destination,
                "secondary_drop_blocked": secondary_drop_blocked,
                "secondary_drop_reason": secondary_not_dropped_reason(log),
                "after_arrival_primary": after_primary,
                "after_arrival_secondary": after_secondary,
                "after_arrival_cargo": cargo_display(after_primary, after_secondary),
                "primary_destination": current_primary_destination,
                "secondary_destination": current_secondary_destination,
                "service_stop": service_stop,
                "service_stop_label": service_stop_label(log) if service_stop else "",
                "deviation": deviation,
                "warnings": warnings,
            }

            current_primary_destination = next_primary_destination
            current_secondary_destination = next_secondary_destination
            current_secondary_value = next_secondary_value

    return routes
