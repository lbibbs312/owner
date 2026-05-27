"""Canonical stop-summary lines for the Driver Route Audit Sheet.

The audit sheet's Stop Details column previously rendered freeform prose
generated inline in the print template:

    "Raleigh East: No pickup recorded; departed empty."
    "Kraft Plant: Loaded two stops. Departed with Raleigh East Load +
     52nd Street L Load. First stop after departure: 52nd Street L."

That output mixed first-class events (loads, drops, waits) with state echoes
of adjacent table columns (Transit Cargo, next-row Route), and it framed
every stop as a pickup attempt regardless of what actually happened. Drop
events were never named -- a delivery rendered as "No pickup recorded".

This module builds the Stop Details cell as a list of canonical-shape lines
from the typed cargo deltas already computed in ``load_state``:

    {plant}: {purpose label}.
    Delivered {cargo}.        (one line per drop event)
    Loaded {cargo}.           (one line per pickup event)
    Continuing with {cargo}.  (only when carry-through cargo + a drop)
    Departed empty.           (only when departing empty after work here)
    Deviation: {reason}.      (when deviation flagged, with reason)
    Wait {label}.             (when wait time recorded)
    {exception lines...}      (unload blocked, secondary not dropped, etc.)

Templates render lines as separate paragraphs without injecting prose of
their own. Per AGENTS.md, the template must not invent route/cargo meaning.
"""

from app.services.plant_addresses import plant_label


SHIFT_START = "shift_start"
SHIFT_END = "shift_end"
PICKUP = "pickup_origin"
DELIVERY = "drop_only"
DELIVERY_RETAINED = "multi_stop_drop"
COMBINED = "mixed_transfer"
SERVICE = "service_stop"
WAIT_ONLY = "wait_only"
NO_PICKUP = "no_pickup"
CURRENT_OPEN = "current_open"
FINAL_STOP = "final_stop"

STOP_PURPOSES = (
    SHIFT_START,
    SHIFT_END,
    PICKUP,
    DELIVERY,
    DELIVERY_RETAINED,
    COMBINED,
    SERVICE,
    WAIT_ONLY,
    NO_PICKUP,
    CURRENT_OPEN,
    FINAL_STOP,
)

_PURPOSE_LABELS = {
    SHIFT_START: "Shift start",
    SHIFT_END: "Shift end",
    PICKUP: "Pickup",
    DELIVERY: "Delivery",
    DELIVERY_RETAINED: "Delivery",
    COMBINED: "Pickup and delivery",
    SERVICE: "Service stop",
    WAIT_ONLY: "Stop (no cargo events)",
    NO_PICKUP: "Stop (no pickup, departed empty)",
    CURRENT_OPEN: "Currently at stop, awaiting departure",
    FINAL_STOP: "Final stop",
}


def _route_get(route, key, default=None):
    return (route or {}).get(key, default)


def _has_cargo_events(route):
    return bool(_route_get(route, "cargo_added") or _route_get(route, "cargo_removed"))


def classify_stop_purpose(route, log, *, is_first, is_last, route_finalized, current_open=False):
    """Return a typed stop purpose, extending ``classify_stop_role`` with
    shift-context purposes (SHIFT_START, SHIFT_END, WAIT_ONLY).

    ``stop_role`` already covers cargo-derived purposes (pickup_origin,
    drop_only, multi_stop_drop, mixed_transfer, service_stop, no_pickup,
    current_open, final_stop). This function adds the contextual cases
    that depend on a log's position in the route.
    """
    if current_open:
        return CURRENT_OPEN

    role = _route_get(route, "stop_role")
    has_depart = bool(getattr(log, "depart_time", None))
    has_events = _has_cargo_events(route)
    is_service = bool(_route_get(route, "service_stop"))

    # Service stops keep their typed label regardless of position.
    if is_service:
        return SERVICE

    # End-of-shift terminus: last log in route, departed, with no work here.
    # Distinguish this from a delivery that happens to be the last stop --
    # if cargo moved here, the relevant purpose is the delivery/pickup.
    if is_last and has_depart and not has_events and route_finalized:
        return SHIFT_END
    if is_last and has_depart and not has_events and role in {None, "no_pickup", "final_stop"}:
        return SHIFT_END

    # Shift origin: first log of the route, departed, no cargo work here
    # (driver clocked in / picked up the truck and rolled).
    if is_first and has_depart and not has_events and role in {None, "no_pickup"}:
        return SHIFT_START

    # No cargo events but the stop happened -- distinguish from "no pickup
    # was attempted." WAIT_ONLY means the truck stopped somewhere but didn't
    # load or unload, typically a meeting / staging / yard touch.
    if has_depart and not has_events and role == "no_pickup" and not getattr(log, "no_pickup", False):
        return WAIT_ONLY

    return role or WAIT_ONLY


def purpose_label(purpose, route=None):
    """Human label for the stop's purpose, falling back to service label
    when the typed purpose is SERVICE."""
    if purpose == SERVICE and _route_get(route, "service_stop_label"):
        return _route_get(route, "service_stop_label")
    return _PURPOSE_LABELS.get(purpose, purpose.replace("_", " ").title())


def deviation_reason(route):
    """Return a short reason string for a flagged deviation, or None.

    The deviation flag in ``build_driver_log_route_context`` fires when the
    truck has primary cargo destined for plant A, the current stop is NOT
    plant A, and there is secondary cargo activity here. That is a
    detour-for-secondary-cargo pattern. Surface that as the reason so the
    audit chip is anchored to a specific cause rather than reading as a
    decorative red flag.
    """
    if not _route_get(route, "deviation"):
        return None
    primary_code = _route_get(route, "primary_destination")
    primary = plant_label(primary_code) if primary_code else "another plant"
    return f"Secondary cargo handled while load for {primary} still onboard"


def _format_cargo_list(items):
    items = [item for item in (items or ()) if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def build_stop_summary(
    route,
    log,
    *,
    is_first,
    is_last,
    route_finalized,
    wait_label=None,
    current_open=False,
):
    """Build the canonical Stop Details cell content for one route log.

    Returns a dict suitable for merging into the log's entry in
    ``log_routes``:

        {
          "stop_purpose": <typed string>,
          "purpose_label": <human label>,
          "summary_lines": [<sentence>, ...],
          "deviation_reason": <str or None>,
        }

    The first line is always ``"{plant}: {purpose label}."``. Subsequent
    lines describe events at this stop in a fixed order: deliveries,
    pickups, retained cargo (only when paired with a delivery), departure
    state (only when the stop changed nothing or was a shift-end), the
    deviation reason (only when flagged), wait time, and exceptions.
    """
    purpose = classify_stop_purpose(
        route, log,
        is_first=is_first,
        is_last=is_last,
        route_finalized=route_finalized,
        current_open=current_open,
    )
    label = purpose_label(purpose, route)

    plant = _route_get(route, "plant") or plant_label(getattr(log, "plant_name", None)) or "Stop"

    cargo_added = tuple(_route_get(route, "cargo_added") or ())
    cargo_removed = tuple(_route_get(route, "cargo_removed") or ())
    cargo_retained = tuple(_route_get(route, "cargo_retained") or ())
    has_depart = bool(getattr(log, "depart_time", None))

    lines = [f"{plant}: {label}."]

    for item in cargo_removed:
        lines.append(f"Delivered {item}.")

    for item in cargo_added:
        lines.append(f"Loaded {item}.")

    if cargo_retained and cargo_removed:
        lines.append(f"Continuing with {_format_cargo_list(cargo_retained)}.")

    # Explicit "Departed empty" only when the empty state is meaningful at
    # this stop: a no-pickup stop, a shift-end terminus, or a stop where
    # something was delivered and nothing reloaded. Avoid duplicating the
    # Transit Cargo column for normal pickup/delivery flow.
    departed_empty_meaningful = (
        has_depart
        and not cargo_added
        and not cargo_retained
        and (
            cargo_removed
            or purpose in {NO_PICKUP, SHIFT_END, WAIT_ONLY}
        )
    )
    if departed_empty_meaningful and purpose != SHIFT_END:
        lines.append("Departed empty.")

    reason = deviation_reason(route)

    if wait_label:
        lines.append(f"{wait_label}.")

    unload_blocked = _route_get(route, "unload_blocked")
    unload_reason = _route_get(route, "unload_reason")
    if unload_blocked and unload_reason:
        lines.append(f"Unload not completed: {unload_reason}.")

    secondary_blocked = _route_get(route, "secondary_drop_blocked")
    secondary_reason = _route_get(route, "secondary_drop_reason")
    if secondary_blocked and secondary_reason:
        lines.append(f"Secondary cargo not dropped: {secondary_reason}.")

    return {
        "stop_purpose": purpose,
        "purpose_label": label,
        "summary_lines": lines,
        "deviation_reason": reason,
    }
