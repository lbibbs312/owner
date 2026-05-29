"""Linear production-flow state machine.

Six stages, each with its own sub-state enum. These constants are the canonical
vocabulary the FlowEvent ledger, EntityCurrentState, and the constraint engine
all speak. UI labels live next to each value so the spatial board can render
them directly.
"""

# Stage 1 — WIP / Production
WIP_LOGGED = "wip_logged"
WIP_LOADING = "wip_loading"
WIP_IN_CYCLE = "wip_in_cycle"
WIP_UNLOADING = "wip_unloading"

# Stage 2 — Staging
STAGING_RACKED = "staging_racked"
STAGING_BAY_ASSIGNED = "staging_bay_assigned"
STAGING_READY_FOR_PICK = "staging_ready_for_pick"

# Stage 3 — Load Build
LOAD_ASSIGNED_TO_EQUIPMENT = "load_assigned_to_equipment"

# Stage 4 — Manifested
MANIFEST_LOCKED = "manifest_locked"

# Stage 5 — In Transit
TRANSIT_EN_ROUTE = "transit_en_route"

# Stage 6 — Receiving
RECEIVING_COMPLETED = "receiving_completed"

# Quality / scrap soft-locks (orthogonal to stages — they freeze progression)
QUALITY_HOLD = "quality_hold"
SCRAP = "scrap"

STAGE_ORDER = (
    "wip",
    "staging",
    "load_build",
    "manifested",
    "in_transit",
    "receiving",
)

STATE_TO_STAGE = {
    WIP_LOGGED: "wip",
    WIP_LOADING: "wip",
    WIP_IN_CYCLE: "wip",
    WIP_UNLOADING: "wip",
    STAGING_RACKED: "staging",
    STAGING_BAY_ASSIGNED: "staging",
    STAGING_READY_FOR_PICK: "staging",
    LOAD_ASSIGNED_TO_EQUIPMENT: "load_build",
    MANIFEST_LOCKED: "manifested",
    TRANSIT_EN_ROUTE: "in_transit",
    RECEIVING_COMPLETED: "receiving",
}

STAGE_LABELS = {
    "wip": "WIP / Production",
    "staging": "Staging",
    "load_build": "Load Build",
    "manifested": "Manifested",
    "in_transit": "In Transit",
    "receiving": "Receiving",
}

STATE_LABELS = {
    WIP_LOGGED: "Logged",
    WIP_LOADING: "Loading",
    WIP_IN_CYCLE: "In Cycle",
    WIP_UNLOADING: "Unloading",
    STAGING_RACKED: "Racked",
    STAGING_BAY_ASSIGNED: "Bay Assigned",
    STAGING_READY_FOR_PICK: "Ready for Pick",
    LOAD_ASSIGNED_TO_EQUIPMENT: "Assigned to Equipment",
    MANIFEST_LOCKED: "Manifest Locked",
    TRANSIT_EN_ROUTE: "En Route",
    RECEIVING_COMPLETED: "Completed",
    QUALITY_HOLD: "Quality Hold",
    SCRAP: "Scrap",
}

SOFT_LOCK_STATES = frozenset({QUALITY_HOLD, SCRAP})


def stage_for(state):
    return STATE_TO_STAGE.get(state)


def is_soft_locked(state):
    return state in SOFT_LOCK_STATES


def stage_index(state):
    stage = stage_for(state)
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else -1
