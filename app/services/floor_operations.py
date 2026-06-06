"""Floor-operations snapshot derived from real records.

Builds the data behind shared manager route and move summaries. Everything is
derived from existing records (MoveRequest, DriverLog, PlantTransfer,
ShiftRecord, DamageReport, ActivityEvent); nothing is fabricated. When a signal
is unavailable the count is 0 and lists are empty, so callers can safely render
"No current data".

Public entry point: :func:`build_floor_operations_snapshot`.
"""
import re
from datetime import date as date_cls, datetime, timedelta

from sqlalchemy import or_

from app.models import ActivityEvent, DamageReport, DriverLog, MoveRequest, ShiftRecord
from app.services.cargo_state import cargo_state_for_log, cargo_state_for_request
from app.services.driver_wait import wait_minutes_for_log
from app.services.issue_severity import classify_issue
from app.services.load_state import is_empty_load
from app.services.plant_addresses import plant_label

# Statuses that represent live, not-yet-closed work.
ACTIVE_STATUSES = ("open", "acknowledged", "assigned", "in_progress", "waiting", "blocked", "needs_review")
HOT_PRIORITIES = ("hot", "safety")
DECLINE_ACTIONS = ("declined", "decline", "rejected", "reassign_declined")
DUE_SOON_HOURS = 2
DEFAULT_WAIT_THRESHOLD = 30

STATUS_LABELS = {
    "open": "Open",
    "acknowledged": "Acknowledged",
    "assigned": "Assigned",
    "in_progress": "In Progress",
    "waiting": "Waiting",
    "blocked": "Blocked",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "needs_review": "Needs Review",
}

PRIORITY_LABELS = {
    "low": "Low",
    "normal": "Normal",
    "high": "High",
    "hot": "HOT",
    "safety": "Safety",
}


def _clean(value):
    return str(value or "").strip()


def _status_label(status):
    status = (status or "open").lower()
    return STATUS_LABELS.get(status, status.replace("_", " ").title() or "—")


def _priority_label(priority):
    priority = (priority or "normal").lower()
    return PRIORITY_LABELS.get(priority, priority.title())


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "_", _clean(label).lower()).strip("_") or "unspecified"


def _norm_location(value):
    """Normalize free-text location to a display label, or None if blank."""
    text = _clean(value)
    if not text:
        return None
    return plant_label(text) or text


def _day_bounds(target):
    start = datetime.combine(target, datetime.min.time())
    return start, start + timedelta(days=1)


def _is_unassigned(req):
    return not (req.assigned_driver_id or _clean(req.assigned_driver_text))


def _has_decline_signal(req, declined=False):
    if declined or getattr(req, "declined", False):
        return True
    text = " ".join(
        _clean(getattr(req, attr, ""))
        for attr in ("status", "blocked_reason", "closed_reason", "notes", "assigned_driver_text")
    ).lower()
    return "declin" in text or "rejected" in text


def _has_open_issue(req, has_open_damage=False):
    if has_open_damage:
        return True
    if (req.status or "").lower() == "needs_review":
        return True
    return bool(_clean(req.blocked_reason))


def _departed(log):
    return bool(log is not None and _clean(getattr(log, "depart_time", None)))


# --------------------------------------------------------------------------- #
# Next action                                                                  #
# --------------------------------------------------------------------------- #
def next_action_for_request(req, *, declined=False, has_open_issue=False, cargo=None):
    """Return the single clearest next action for a move request.

    Priority follows the approved map. The in-progress/waiting operational
    sub-state uses cargo -> departure -> document -> issue ordering.
    """
    status = (req.status or "open").lower()

    # A real decline signal takes precedence over everything else.
    if _has_decline_signal(req, declined):
        return "Reassign declined move"

    if status == "cancelled":
        return "No action needed"
    if status == "completed":
        return "Resolve cargo review" if has_open_issue else "No action needed"
    if status == "blocked":
        return "Resolve blocker"
    if status == "needs_review":
        return "Resolve cargo review"

    if status in ("open", "acknowledged") and _is_unassigned(req):
        return "Assign driver"
    if status == "open":  # has a driver but is not yet acknowledged
        return "Acknowledge request"

    route_linked = bool(req.linked_driver_log_id or _clean(req.linked_route_id))
    if status in ("assigned", "acknowledged") and not route_linked:
        return "Start or link route"

    # Active with a route/stop: resolve the operational sub-state.
    log = req.linked_driver_log
    state = (cargo or cargo_state_for_request(req, log=log))["state"]
    has_cargo_detail = bool(_clean(req.cargo_text) or _clean(req.part_number))
    if state == "unknown" or not has_cargo_detail:
        return "Confirm cargo"
    if log is not None and not _departed(log):
        return "Record departure"
    if not (req.linked_document_id or req.linked_plant_transfer_id):
        return "Attach document"
    if has_open_issue:
        return "Resolve cargo review"
    # Completion proof present, nothing open, but not yet marked completed.
    if state == "delivered":
        return "Close request"
    return "No action needed"


def route_next_action(route_context, *, has_high_issue=False, missing_document=False):
    """Route-level next action for the driver dashboard (from route context)."""
    if has_high_issue:
        return "Open issue details"
    current = getattr(route_context, "current_stop", None)
    if current is not None and not _departed(current):
        if cargo_state_for_log(current)["state"] == "unknown":
            return "Confirm cargo"
        return "Record departure"
    if missing_document:
        return "Attach document"
    rows = getattr(route_context, "rows", None) or []
    if getattr(route_context, "route_status", None) == "active" and rows:
        return "Complete route"
    return "No action needed"


# --------------------------------------------------------------------------- #
# Rows                                                                         #
# --------------------------------------------------------------------------- #
def _due_label(req):
    if _clean(req.due_time_text):
        return _clean(req.due_time_text)
    if req.due_at:
        return req.due_at.strftime("%b %d %I:%M%p").replace(" 0", " ").lower()
    return ""


def request_row(req, *, declined_ids=frozenset(), damaged_log_ids=frozenset()):
    """Flatten a MoveRequest into a display row for tables/cards."""
    log = req.linked_driver_log
    has_dmg = bool(log and log.id in damaged_log_ids)
    cargo = cargo_state_for_request(req, log=log, has_open_damage=has_dmg)
    open_issue = _has_open_issue(req, has_dmg)
    next_action = next_action_for_request(
        req, declined=(req.id in declined_ids), has_open_issue=open_issue, cargo=cargo
    )
    status = (req.status or "open").lower()
    priority = (req.priority or "normal").lower()
    return {
        "id": req.id,
        "number": req.display_number,
        "origin": _norm_location(req.origin_location_text) or "—",
        "destination": _norm_location(req.destination_location_text) or "—",
        "cargo": req.cargo_part_display or _clean(req.cargo_text) or "—",
        "part_number": _clean(req.part_number),
        "priority": priority,
        "priority_label": _priority_label(priority),
        "is_hot": priority in HOT_PRIORITIES,
        "status": status,
        "status_label": _status_label(status),
        "driver": req.assigned_display or "Unassigned",
        "due_label": _due_label(req),
        "due_at": req.due_at,
        "cargo_state": cargo["state"],
        "cargo_state_label": cargo["label"],
        "next_action": next_action,
        "has_open_issue": open_issue,
    }


def assigned_move_queue(driver_id, date=None, limit=None):
    """Active move requests assigned to a specific driver (most urgent first)."""
    if not driver_id:
        return []
    requests = (
        MoveRequest.query.filter(
            MoveRequest.assigned_driver_id == driver_id,
            MoveRequest.status.in_(ACTIVE_STATUSES),
        )
        .order_by(MoveRequest.due_at.is_(None), MoveRequest.due_at.asc(), MoveRequest.requested_at.desc())
        .all()
    )
    declined_ids, damaged_log_ids = _signal_sets(requests)
    rows = [request_row(r, declined_ids=declined_ids, damaged_log_ids=damaged_log_ids) for r in requests]
    return rows[:limit] if limit else rows


# --------------------------------------------------------------------------- #
# Map status helpers                                                           #
# --------------------------------------------------------------------------- #
def _node_worst_status(node):
    if node["blocked_count"]:
        return "blocked"
    if node["waiting_count"]:
        return "waiting"
    if node["active_move_count"]:
        return "active"
    if node["open_request_count"]:
        return "open"
    if node["completed_today_count"]:
        return "completed"
    return "none"


def _edge_worst_status(edge):
    if edge["blocked_count"]:
        return "blocked"
    if edge["active_count"]:
        return "active"
    if edge["open_count"]:
        return "open"
    if edge["completed_count"]:
        return "completed"
    return "none"


def _signal_sets(requests):
    """Precompute decline + open-damage signals for a batch of requests."""
    request_ids = [r.id for r in requests]
    declined_ids = set()
    if request_ids:
        events = (
            ActivityEvent.query.filter(
                ActivityEvent.target_type == "move_request",
                ActivityEvent.target_id.in_(request_ids),
                ActivityEvent.action.in_(DECLINE_ACTIONS),
            ).all()
        )
        declined_ids = {event.target_id for event in events}
    log_ids = [r.linked_driver_log_id for r in requests if r.linked_driver_log_id]
    damaged_log_ids = set()
    if log_ids:
        reports = (
            DamageReport.query.filter(
                DamageReport.status != "closed",
                DamageReport.driver_log_id.in_(log_ids),
            ).all()
        )
        damaged_log_ids = {report.driver_log_id for report in reports}
    return declined_ids, damaged_log_ids


# --------------------------------------------------------------------------- #
# Snapshot                                                                     #
# --------------------------------------------------------------------------- #
def build_floor_operations_snapshot(date=None, driver_id=None, wait_threshold=None):
    """Return the full floor-operations snapshot.

    Keys: ``date``, ``queue_summary``, ``floor_cards``, ``map_nodes``,
    ``map_edges``, ``active_moves``, ``needs_attention`` (+ ``latest_requests``
    for the manager queue list). Safe on an empty database.
    """
    target = date or date_cls.today()
    threshold = wait_threshold or DEFAULT_WAIT_THRESHOLD
    day_start, day_end = _day_bounds(target)
    now = datetime.utcnow()
    due_soon_cutoff = now + timedelta(hours=DUE_SOON_HOURS)

    active_query = MoveRequest.query.filter(MoveRequest.status.in_(ACTIVE_STATUSES))
    completed_query = MoveRequest.query.filter(
        MoveRequest.status == "completed",
        MoveRequest.updated_at >= day_start,
        MoveRequest.updated_at < day_end,
    )
    if driver_id:
        driver_scope = or_(
            MoveRequest.assigned_driver_id == driver_id,
            MoveRequest.linked_driver_log.has(DriverLog.driver_id == driver_id),
        )
        active_query = active_query.filter(driver_scope)
        completed_query = completed_query.filter(driver_scope)
    active_requests = active_query.order_by(MoveRequest.requested_at.desc()).all()
    completed_today = completed_query.all()

    queue_summary = {
        "open_requests": len(active_requests),
        "hot_requests": len([r for r in active_requests if (r.priority or "").lower() in HOT_PRIORITIES]),
        "unassigned_requests": len([r for r in active_requests if _is_unassigned(r)]),
        "blocked_requests": len([r for r in active_requests if r.status == "blocked"]),
        "due_soon_requests": len([r for r in active_requests if r.due_at and r.due_at <= due_soon_cutoff]),
    }
    completed_today_count = len(completed_today)

    # --- Driver logs for the day -------------------------------------------
    log_query = DriverLog.query.filter(
        DriverLog.deleted_at.is_(None), DriverLog.date == target
    )
    if driver_id:
        log_query = log_query.filter_by(driver_id=driver_id)
    todays_logs = log_query.all()
    open_logs = [log for log in todays_logs if not _departed(log)]
    departed_logs = [log for log in todays_logs if _departed(log)]

    loading_now, unloading_now, waiting_over = [], [], []
    for log in open_logs:
        if is_empty_load(log.load_size) and not log.no_pickup:
            loading_now.append(log)
        elif not is_empty_load(log.load_size):
            unloading_now.append(log)
        minutes = wait_minutes_for_log(log, now=None)
        if minutes is not None and minutes >= threshold:
            waiting_over.append((log, minutes))

    shift_query = ShiftRecord.query.filter(ShiftRecord.end_time.is_(None))
    if driver_id:
        shift_query = shift_query.filter_by(user_id=driver_id)
    open_shift_driver_ids = {shift.user_id for shift in shift_query.all()}
    on_road_driver_ids = open_shift_driver_ids - {log.driver_id for log in open_logs}

    floor_cards = [
        {"key": "ready_to_move", "label": "Ready to Move", "tone": "info",
         "count": len([r for r in active_requests if r.status == "assigned"]),
         "hint": "Driver assigned, not started"},
        {"key": "loading_now", "label": "Loading Now", "tone": "warn",
         "count": len(loading_now), "hint": "At a pickup dock"},
        {"key": "unloading_now", "label": "Unloading Now", "tone": "warn",
         "count": len(unloading_now), "hint": "At a delivery dock"},
        {"key": "blocked_or_no_parts", "label": "Blocked / No Parts", "tone": "danger",
         "count": queue_summary["blocked_requests"], "hint": "Needs a manager decision"},
        {"key": "on_road", "label": "On Road", "tone": "info",
         "count": len(on_road_driver_ids), "hint": "Between stops"},
        {"key": "completed_recently", "label": "Completed Recently", "tone": "good",
         "count": completed_today_count, "hint": "Closed today"},
        {"key": "waiting_over_limit", "label": "Waiting Over Limit", "tone": "danger",
         "count": len(waiting_over), "hint": f"Over {threshold} min at a stop"},
        {"key": "hot_or_urgent", "label": "Hot / Urgent", "tone": "danger",
         "count": queue_summary["hot_requests"], "hint": "Hot or safety priority"},
    ]

    # --- Production flow map (facility/process, not GPS) -------------------
    nodes = {}

    def _node(label):
        key = _slug(label)
        if key not in nodes:
            nodes[key] = {
                "key": key, "label": label, "open_request_count": 0, "active_move_count": 0,
                "blocked_count": 0, "waiting_count": 0, "completed_today_count": 0,
            }
        return nodes[key]

    edges = {}

    def _edge(origin_label, dest_label):
        ok, dk = _slug(origin_label), _slug(dest_label)
        if (ok, dk) not in edges:
            edges[(ok, dk)] = {
                "origin_key": ok, "destination_key": dk,
                "origin_label": origin_label, "destination_label": dest_label,
                "open_count": 0, "active_count": 0, "completed_count": 0, "blocked_count": 0,
            }
        return edges[(ok, dk)]

    for req in active_requests:
        origin = _norm_location(req.origin_location_text)
        dest = _norm_location(req.destination_location_text)
        is_blocked = req.status == "blocked"
        is_active = req.status in ("assigned", "in_progress", "waiting")
        for label in (origin, dest):
            if not label:
                continue
            node = _node(label)
            node["open_request_count"] += 1
            node["blocked_count"] += 1 if is_blocked else 0
            node["active_move_count"] += 1 if is_active else 0
        if origin and dest:
            edge = _edge(origin, dest)
            edge["open_count"] += 1
            edge["active_count"] += 1 if is_active else 0
            edge["blocked_count"] += 1 if is_blocked else 0

    for req in completed_today:
        origin = _norm_location(req.origin_location_text)
        dest = _norm_location(req.destination_location_text)
        for label in (origin, dest):
            if label:
                _node(label)["completed_today_count"] += 1
        if origin and dest:
            _edge(origin, dest)["completed_count"] += 1

    for log in open_logs:
        label = _norm_location(log.plant_name)
        if label:
            _node(label)["waiting_count"] += 1
    for log in departed_logs:
        label = _norm_location(log.plant_name)
        if label:
            _node(label)["completed_today_count"] += 1

    map_nodes = []
    for node in nodes.values():
        node["worst_status"] = _node_worst_status(node)
        map_nodes.append(node)
    map_nodes.sort(key=lambda n: (-n["open_request_count"], -n["waiting_count"], n["label"]))

    map_edges = []
    for edge in edges.values():
        edge["worst_status"] = _edge_worst_status(edge)
        map_edges.append(edge)
    map_edges.sort(key=lambda e: (-(e["open_count"] + e["completed_count"]), e["origin_label"]))

    # --- In-flight moves, latest requests, needs attention -----------------
    declined_ids, damaged_log_ids = _signal_sets(active_requests)

    def _row(req):
        return request_row(req, declined_ids=declined_ids, damaged_log_ids=damaged_log_ids)

    active_moves = [_row(r) for r in active_requests if r.status in ("assigned", "in_progress", "waiting")]
    active_moves.sort(key=lambda r: (not r["is_hot"], r["due_at"] is None, r["due_at"] or now))
    latest_requests = [_row(r) for r in active_requests[:8]]

    needs_attention = []
    for req in active_requests:
        if req.status == "blocked":
            needs_attention.append({
                "label": f"{req.display_number} blocked",
                "detail": _clean(req.blocked_reason) or "Move request is blocked.",
                "issue": classify_issue(category="blocked", severity="high"),
                "target_type": "move_request", "target_id": req.id,
            })
        elif _is_unassigned(req) and (req.priority or "").lower() in HOT_PRIORITIES:
            needs_attention.append({
                "label": f"{req.display_number} unassigned (hot)",
                "detail": "Hot/safety request has no driver assigned.",
                "issue": classify_issue(category="Open hot move"),
                "target_type": "move_request", "target_id": req.id,
            })
    for log, minutes in waiting_over:
        needs_attention.append({
            "label": f"Long wait at {plant_label(log.plant_name)}",
            "detail": f"Stop open {minutes} min (over {threshold} min limit).",
            "issue": classify_issue(category="Delayed dock time", minutes=minutes, wait_threshold=threshold),
            "target_type": "driver_log", "target_id": log.id,
        })
    needs_attention.sort(key=lambda item: -item["issue"]["level_rank"])

    return {
        "date": target,
        "queue_summary": queue_summary,
        "floor_cards": floor_cards,
        "map_nodes": map_nodes,
        "map_edges": map_edges,
        "active_moves": active_moves,
        "needs_attention": needs_attention,
        "latest_requests": latest_requests,
    }
