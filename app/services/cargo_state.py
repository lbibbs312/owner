"""Cargo-state normalization for display.

Derives a normalized cargo state from *existing* records only — DriverLog
load fields (arrived-with / departed-with), no_pickup, MoveRequest status, an
optional open-damage signal, and linked document/transfer presence. No new
model is introduced and no telemetry is invented.

The functions are pure (no DB access): callers pass any extra signals such as
``has_open_damage``. This keeps them cheap to call in loops and easy to test.
"""
from app.services.load_state import is_empty_load

# Canonical states, ordered roughly along the move lifecycle.
STATES = (
    "unknown", "empty", "requested", "assigned", "loaded", "onboard",
    "delivered", "held", "short", "damaged", "returned", "pending_document",
)

STATE_LABELS = {
    "unknown": "Unknown",
    "empty": "Empty",
    "requested": "Requested",
    "assigned": "Assigned",
    "loaded": "Loaded",
    "onboard": "Onboard",
    "delivered": "Delivered",
    "held": "Held",
    "short": "Short",
    "damaged": "Damaged",
    "returned": "Returned",
    "pending_document": "Document Needed",
}

_SHORT_TOKENS = ("short", "partial", "quarter", "half")
_RETURN_TOKENS = ("return", "returned", "rtn")

_REQUEST_STATUS_STATES = {
    "open": "requested",
    "acknowledged": "requested",
    "assigned": "assigned",
    "in_progress": "onboard",
    "waiting": "onboard",
    "blocked": "held",
    "completed": "delivered",
    "cancelled": "unknown",
    "needs_review": "onboard",
}


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def cargo_state_label(state):
    return STATE_LABELS.get(state, STATE_LABELS["unknown"])


def _build(state):
    state = state if state in STATE_LABELS else "unknown"
    return {"state": state, "label": STATE_LABELS[state]}


def normalize_cargo_state(raw):
    """Map a free-text cargo descriptor to one of the canonical states."""
    text = _norm(raw)
    if not text:
        return _build("unknown")
    if text in STATE_LABELS:
        return _build(text)
    if is_empty_load(text):
        return _build("empty")
    for token in _RETURN_TOKENS:
        if token in text:
            return _build("returned")
    for token in _SHORT_TOKENS:
        if token in text:
            return _build("short")
    if "damage" in text:
        return _build("damaged")
    if "deliver" in text or "dropped" in text:
        return _build("delivered")
    # A named load that isn't empty means there is cargo aboard.
    return _build("onboard")


def cargo_state_for_log(log, *, has_open_damage=False):
    """Cargo state implied by a single driver-log stop (physical truth)."""
    if log is None:
        return _build("unknown")
    if has_open_damage:
        return _build("damaged")

    arrived = getattr(log, "load_size", None)
    departed = getattr(log, "depart_time", None)
    departed_with = getattr(log, "depart_load_size", None)

    # Still parked at the stop (no departure recorded yet).
    if not str(departed or "").strip():
        if getattr(log, "no_pickup", False) or is_empty_load(arrived):
            return _build("empty")
        if any(token in _norm(arrived) for token in _SHORT_TOKENS):
            return _build("short")
        return _build("onboard")

    # Departed this stop — what is the truck carrying onward?
    if is_empty_load(departed_with):
        return _build("delivered")
    if any(token in _norm(departed_with) for token in _SHORT_TOKENS):
        return _build("short")
    return _build("onboard")


def cargo_state_for_request(req, *, log=None, has_open_damage=False):
    """Cargo state for a move request.

    Prefers the physical truth from a linked driver log; otherwise falls back
    to the request status. Completion without a linked document/transfer is
    surfaced as ``pending_document``; an open damage signal wins outright.
    """
    if req is None:
        return _build("unknown")
    if has_open_damage:
        return _build("damaged")

    status = _norm(getattr(req, "status", "")) or "open"

    if status == "completed" and not (
        getattr(req, "linked_document_id", None) or getattr(req, "linked_plant_transfer_id", None)
    ):
        return _build("pending_document")

    if log is not None:
        return cargo_state_for_log(log, has_open_damage=has_open_damage)

    return _build(_REQUEST_STATUS_STATES.get(status, "unknown"))
