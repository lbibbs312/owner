"""Operations & Audit Defense Board view model.

This is a pure *presentation* layer on top of
:func:`app.services.production_flow.build_production_flow_context`, which remains
the single source of truth for production movement (it summarizes real
MoveRequest / DriverLog / PlantTransfer / DamageReport / ExceptionEvent
records).  This module adds the things a spatial board needs and nothing more:

* ring-layout geometry for facility nodes,
* SVG endpoints for the lanes between them,
* placement for the active move tokens that ride those lanes,
* per-node stat tiles (in / out / wait / delay / damage / proof-gap),
* an exception ticker, header counters, and a default "system summary",
* a per-move proof/audit checklist derived from real linked records.

It deliberately does **not** invent telemetry (no GPS, scans, cameras) or
fabricated dollar "savings".  Anything the backend does not track is rendered
as an explicit empty state by the template, exactly like the rest of the app.
"""
import math

from app.services.production_flow import build_production_flow_context

# Logical canvas size. The template renders the board at this size inside a
# scrollable viewport; coordinates below are all in these logical pixels.
CANVAS_W = 1100
CANVAS_H = 600
CARD_W = 168
CARD_H = 110
TOKEN_W = 136
TOKEN_H = 48

# Ring radii used to lay facility nodes out around the canvas centre.
_RING_RX = 408
_RING_RY = 214
# Pixels trimmed off each end of a lane so the line does not run under a card.
_LANE_TRIM = 86

# Move-request statuses that are still "in flight" and therefore drawn as tokens.
ACTIVE_MOVE_STATUSES = {
    "open",
    "acknowledged",
    "assigned",
    "in_progress",
    "waiting",
    "blocked",
    "needs_review",
}

# worst_status -> visual state suffix shared by node borders and lanes.
_STATE_BY_WORST = {
    "blocked": "danger",
    "waiting": "warning",
    "active": "active",
    "open": "active",
    "completed": "idle",
    "none": "idle",
}

# Rank used to sort the exception ticker (higher = more urgent).
_SEVERITY_RANK = {
    "critical": 5,
    "blocked": 4,
    "needs_review": 4,
    "high": 3,
    "action": 2,
    "medium": 2,
    "waiting": 1,
    "watch": 1,
}


def _round(value):
    return round(float(value), 1)


def _state(worst_status):
    return _STATE_BY_WORST.get(worst_status or "none", "idle")


def _ring_positions(nodes):
    """Assign a centre + card top-left to each node around an ellipse."""
    count = len(nodes)
    cx, cy = CANVAS_W / 2, CANVAS_H / 2
    positions = {}
    for index, node in enumerate(nodes):
        if count == 1:
            x, y = cx, cy
        else:
            theta = -math.pi / 2 + (2 * math.pi * index / count)
            x = cx + _RING_RX * math.cos(theta)
            y = cy + _RING_RY * math.sin(theta)
        positions[node["key"]] = {
            "cx": _round(x),
            "cy": _round(y),
            "left": _round(x - CARD_W / 2),
            "top": _round(y - CARD_H / 2),
        }
    return positions


def _label_to_key(nodes):
    return {node["label"]: node["key"] for node in nodes}


def _active_move_items(items):
    return [
        item
        for item in items
        if item.get("item_type") == "move_request"
        and (item.get("status") or "open") in ACTIVE_MOVE_STATUSES
    ]


def _node_stat_tiles(nodes, move_items, label_key):
    """Per-node tiles, all derived from real records.

    in/out/proof-gap come from the active move items; wait/delay/damage/
    no-pickup come from the counts production_flow already accumulated.
    """
    inbound = {node["key"]: 0 for node in nodes}
    outbound = {node["key"]: 0 for node in nodes}
    proof_gap = {node["key"]: 0 for node in nodes}

    for item in move_items:
        origin_key = label_key.get(item.get("origin_label"))
        dest_key = label_key.get(item.get("destination_label"))
        if origin_key in outbound:
            outbound[origin_key] += 1
        if dest_key in inbound:
            inbound[dest_key] += 1
        if not item.get("proof_recorded"):
            for key in {origin_key, dest_key}:
                if key in proof_gap:
                    proof_gap[key] += 1

    tiles = {}
    for node in nodes:
        key = node["key"]
        tiles[key] = {
            "in": inbound[key],
            "out": outbound[key],
            "wait": node.get("waiting_count", 0),
            "dly": node.get("delay_count", 0),
            "nop": node.get("no_pickup_count", 0),
            "dmg": node.get("damage_count", 0),
            "gap": proof_gap[key],
            "open": node.get("open_count", 0),
            "active": node.get("active_count", 0),
            "blocked": node.get("blocked_count", 0),
            "completed": node.get("completed_count", 0),
            "issues": node.get("issue_count", 0),
        }
    return tiles


def _lane_geometry(lanes, positions):
    placed = []
    for lane in lanes:
        origin = positions.get(lane["origin_key"])
        dest = positions.get(lane["destination_key"])
        if not origin or not dest:
            continue
        x1, y1, x2, y2 = origin["cx"], origin["cy"], dest["cx"], dest["cy"]
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        start_x, start_y = x1 + ux * _LANE_TRIM, y1 + uy * _LANE_TRIM
        end_x, end_y = x2 - ux * _LANE_TRIM, y2 - uy * _LANE_TRIM
        placed.append(
            {
                **lane,
                "lane_key": f"{lane['origin_key']}--{lane['destination_key']}",
                "x1": _round(start_x),
                "y1": _round(start_y),
                "x2": _round(end_x),
                "y2": _round(end_y),
                "mid_x": _round((start_x + end_x) / 2),
                "mid_y": _round((start_y + end_y) / 2),
                "perp_x": round(-uy, 3),
                "perp_y": round(ux, 3),
                "state": _state(lane.get("worst_status")),
            }
        )
    return placed


def _token_badge(item):
    status = item.get("status") or "open"
    if item.get("hot"):
        return {"label": "HOT", "tone": "danger"}
    if status in {"blocked", "needs_review"}:
        return {"label": item.get("status_label") or "Blocked", "tone": "danger"}
    if status == "waiting":
        return {"label": "WAIT", "tone": "warning"}
    if status in {"assigned", "in_progress"}:
        return {"label": "ACTIVE", "tone": "active"}
    return {"label": item.get("status_label") or "Open", "tone": "info"}


def _proof_checklist(item):
    """Audit checklist for a move, built only from records we actually keep.

    No GPS / scan / camera steps: those are not tracked, so they are not
    claimed here.
    """
    return [
        {"label": "Request logged", "state": "complete"},
        {"label": "Driver assigned", "state": _done(item.get("assigned"))},
        {"label": "Arrival recorded", "state": _done(item.get("arrival_recorded"))},
        {"label": "Plant transfer created", "state": _done(item.get("linked_transfer_id"))},
        {"label": "Departure recorded", "state": _done(item.get("departure_recorded"))},
        {"label": "Proof document attached", "state": _done(item.get("proof_recorded"))},
    ]


def _done(value):
    return "complete" if value else "pending"


def _place_tokens(move_views, lanes, positions, label_key):
    lane_by_pair = {(lane["origin_key"], lane["destination_key"]): lane for lane in lanes}

    # First pass: resolve each token's anchor (a lane, or a single node) so we
    # can stagger multiple tokens that share the same anchor.
    resolved = []
    group_counts = {}
    for item in move_views:
        origin_key = label_key.get(item.get("origin_label"))
        dest_key = label_key.get(item.get("destination_label"))
        lane = lane_by_pair.get((origin_key, dest_key))
        anchor = ("lane", lane["lane_key"]) if lane else ("node", origin_key or dest_key)
        resolved.append((item, lane, origin_key, dest_key, anchor))
        group_counts[anchor] = group_counts.get(anchor, 0) + 1

    tokens = []
    seen = {}
    for item, lane, origin_key, dest_key, anchor in resolved:
        index = seen.get(anchor, 0)
        seen[anchor] = index + 1
        total = group_counts[anchor]
        offset = (index - (total - 1) / 2) * (TOKEN_H + 12)

        if lane:
            base_x, base_y = lane["mid_x"], lane["mid_y"]
            x = base_x + lane["perp_x"] * offset
            y = base_y + lane["perp_y"] * offset
        else:
            pos = positions.get(origin_key or dest_key)
            if not pos:
                continue
            x = pos["cx"]
            y = pos["cy"] - CARD_H / 2 - 30 - index * (TOKEN_H + 8)

        tokens.append(
            {
                **item,
                "left": _round(x - TOKEN_W / 2),
                "top": _round(y - TOKEN_H / 2),
            }
        )
    return tokens


def _exception_reason(item):
    if item.get("item_type") == "route_stop":
        if item.get("no_pickup"):
            return "Failed pickup"
        if item.get("delayed"):
            return "Dock delay"
    return item.get("stage") or item.get("status_label") or "Exception"


def _exception_ticker(items):
    entries = []
    for item in items:
        item_type = item.get("item_type")
        status = item.get("status") or ""
        is_exception = item_type == "issue" or status in {
            "blocked",
            "needs_review",
            "critical",
            "high",
        }
        is_stop_flag = item_type == "route_stop" and (item.get("no_pickup") or item.get("delayed"))
        if not (is_exception or is_stop_flag):
            continue
        entries.append({**item, "reason": _exception_reason(item)})
    entries.sort(key=lambda entry: -_SEVERITY_RANK.get(entry.get("status"), 0))
    return entries


def build_operations_board_context(date=None, driver_id=None, selected_plant=None):
    """Return the full view model for the Operations & Audit Defense Board."""
    ctx = build_production_flow_context(
        date=date,
        driver_id=driver_id,
        selected_plant=selected_plant,
        mode="production",
    )

    nodes = ctx["flow_nodes"]
    positions = _ring_positions(nodes)
    label_key = _label_to_key(nodes)
    move_items = _active_move_items(ctx["flow_items"])
    move_views = [
        {**item, "badge": _token_badge(item), "checklist": _proof_checklist(item)}
        for item in move_items
    ]

    tiles = _node_stat_tiles(nodes, move_views, label_key)
    lanes = _lane_geometry(ctx["flow_lanes"], positions)
    tokens = _place_tokens(move_views, lanes, positions, label_key)
    ticker = _exception_ticker(ctx["flow_items"])

    positioned_nodes = [
        {
            **node,
            "pos": positions[node["key"]],
            "stats": tiles[node["key"]],
            "state": _state(node.get("worst_status")),
        }
        for node in nodes
    ]

    summary = ctx["queue_summary"]
    floor = ctx["floor_summary"]
    total_delays = sum(node.get("delay_count", 0) for node in nodes)
    total_no_pickup = sum(node.get("no_pickup_count", 0) for node in nodes)
    open_exceptions = floor.get("issue_count", 0) + summary.get("blocked_count", 0) + total_no_pickup

    header = {
        "active": summary.get("active_count", 0) + summary.get("waiting_count", 0),
        "delays": total_delays,
        "missing_proof": summary.get("document_needed_count", 0),
        "completed": summary.get("completed_count", 0),
        "exceptions": open_exceptions,
    }

    moves_needing_proof = [
        item
        for item in move_views
        if not item.get("proof_recorded") and item.get("status") not in {"completed", "cancelled"}
    ][:6]

    global_summary = {
        "open": summary.get("open_count", 0),
        "unassigned": summary.get("unassigned_count", 0),
        "exceptions": open_exceptions,
        "audit_pending": summary.get("document_needed_count", 0),
        "completed": summary.get("completed_count", 0),
        "hot": summary.get("hot_count", 0),
        "moves_needing_proof": moves_needing_proof,
        "top_exceptions": ticker[:6],
    }

    return {
        "date": ctx["date"],
        "canvas": {"width": CANVAS_W, "height": CANVAS_H},
        "nodes": positioned_nodes,
        "lanes": lanes,
        "tokens": tokens,
        "moves": move_views,
        "ticker": ticker,
        "header": header,
        "global_summary": global_summary,
        "selected_plant": ctx["selected_context"]["selected_plant"],
        "empty": not (positioned_nodes or tokens),
        "data_scope_note": floor.get("data_scope_note"),
        "source": ctx,
    }
