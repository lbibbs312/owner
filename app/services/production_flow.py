"""Production-flow view models derived from real MoveDefense records.

This service is the widescreen / manager / plant-floor counterpart to
``route_map.py``.  It summarizes production movement pressure from existing
MoveRequest, DriverLog, PlantTransfer, issue, timing, and proof records.  It
does not invent unavailable production asset snapshots.
"""
import re
from datetime import date as date_cls
from datetime import datetime, timedelta

import pytz
from flask import has_request_context, url_for
from sqlalchemy import or_
from werkzeug.routing import BuildError

from app.models import DamageReport, DriverLog, ExceptionEvent, MoveRequest, PlantTransfer
from app.services.cargo_state import cargo_state_for_log, cargo_state_for_request
from app.services.driver_wait import wait_minutes_for_log
from app.services.floor_operations import ACTIVE_STATUSES, next_action_for_request
from app.services.issue_severity import DEFAULT_WAIT_THRESHOLD, classify_issue
from app.services.plant_addresses import PLANT_LABELS, plant_label
from app.services.plant_time import plant_forecast_rows

SAFE_EMPTY = "No current data"
NOT_TRACKED = "Not tracked yet"
DOCUMENT_MISSING = "Document not attached"
CARRIER_SNAPSHOT_EMPTY = "Carrier unit snapshot not connected yet"
RACK_SNAPSHOT_EMPTY = "Rack/capacity data not connected yet"
DATA_SCOPE_EMPTY = "Using route and move request data only"
DETROIT_TZ = pytz.timezone("America/Detroit")

# A dock wait at or above this many minutes is surfaced as a delay on the
# operations board. Mirrors issue_severity's wait threshold so the board and
# the issue badges agree on what "delayed" means.
DELAY_WAIT_THRESHOLD = DEFAULT_WAIT_THRESHOLD

OPEN_STATUSES = {"open", "acknowledged"}
ACTIVE_MOVE_STATUSES = {"assigned", "in_progress"}
WAITING_STATUSES = {"waiting"}
BLOCKED_STATUSES = {"blocked", "needs_review"}
COMPLETED_STATUSES = {"completed"}


def _clean(value):
    return str(value or "").strip()


def _target_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return date_cls.today()
    return date_cls.today()


def _day_bounds(target):
    local_start = DETROIT_TZ.localize(datetime.combine(target, datetime.min.time()))
    utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
    return utc_start, utc_start + timedelta(days=1)


def _safe_url(endpoint, **values):
    if not has_request_context():
        return None
    try:
        return url_for(endpoint, **values)
    except (BuildError, RuntimeError):
        return None


def _location_label(value):
    text = _clean(value)
    if not text:
        return None
    return plant_label(text) or text


def _location_key(value):
    text = _location_label(value) or "unspecified"
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unspecified"


def _short_code(value):
    text = _clean(value)
    if not text:
        return ""
    if text in PLANT_LABELS:
        return text
    for code, label in PLANT_LABELS.items():
        if label.lower() == text.lower():
            return code
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return text[:4].upper()
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(word[0] for word in words[:4]).upper()


def _status_label(status):
    text = _clean(status).replace("_", " ")
    return text.title() if text else SAFE_EMPTY


def _date_label(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d %I:%M%p").replace(" 0", " ").lower()
    return _clean(value)


def _age_minutes(value, *, now=None):
    if not isinstance(value, datetime):
        return None
    now = now or datetime.utcnow()
    minutes = int((now - value).total_seconds() // 60)
    return max(0, minutes)


def _quantity_text(req):
    return _clean(getattr(req, "quantity_display", "")) or _clean(getattr(req, "quantity_text", ""))


def _status_bucket(status):
    status = (status or "open").lower()
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status in WAITING_STATUSES:
        return "waiting"
    if status in ACTIVE_MOVE_STATUSES:
        return "active"
    if status in COMPLETED_STATUSES:
        return "completed"
    return "open"


def _worst_status(*, blocked_count=0, waiting_count=0, active_count=0, open_count=0, completed_count=0):
    if blocked_count:
        return "blocked"
    if waiting_count:
        return "waiting"
    if active_count:
        return "active"
    if open_count:
        return "open"
    if completed_count:
        return "completed"
    return "none"


def _node_next_action(node):
    if node["blocked_count"] or node["issue_count"]:
        return "Review issue"
    if node["waiting_count"]:
        return "Check waiting moves"
    if node["active_count"]:
        return "Track active moves"
    if node["open_count"]:
        return "Assign or acknowledge move"
    return "No action needed"


def _lane_type(status):
    if status == "blocked":
        return "blocked_flow"
    if status == "waiting":
        return "active_move"
    if status == "active":
        return "active_move"
    if status == "completed":
        return "completed_move"
    return "requested_move"


def _node(nodes, label, *, node_type="plant"):
    label = _location_label(label)
    if not label:
        return None
    key = _location_key(label)
    if key not in nodes:
        nodes[key] = {
            "key": key,
            "label": label,
            "short_code": _short_code(label),
            "node_type": node_type,
            "open_count": 0,
            "active_count": 0,
            "waiting_count": 0,
            "blocked_count": 0,
            "completed_count": 0,
            "issue_count": 0,
            "delay_count": 0,
            "no_pickup_count": 0,
            "damage_count": 0,
            "worst_status": "none",
            "next_action": "No action needed",
            "meta": {
                "timing": None,
                "data_sources": [],
                "carrier_unit_snapshot": None,
                "rack_capacity_snapshot": None,
                "production_snapshot_available": False,
                "snapshot_empty_state": CARRIER_SNAPSHOT_EMPTY,
                "rack_empty_state": RACK_SNAPSHOT_EMPTY,
            },
            "view_url": _safe_url("manager.move_requests", location=label),
            "active_moves_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes"),
            "timing_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes"),
        }
    return nodes[key]


def _lane(lanes, origin, destination):
    origin = _location_label(origin)
    destination = _location_label(destination)
    if not origin or not destination:
        return None
    origin_key = _location_key(origin)
    destination_key = _location_key(destination)
    key = (origin_key, destination_key)
    if key not in lanes:
        lanes[key] = {
            "origin_key": origin_key,
            "destination_key": destination_key,
            "origin_label": origin,
            "destination_label": destination,
            "lane_type": "requested_move",
            "open_count": 0,
            "active_count": 0,
            "completed_count": 0,
            "blocked_count": 0,
            "waiting_count": 0,
            "worst_status": "none",
            "oldest_age_minutes": None,
            "linked_request_ids": [],
            "linked_driver_log_ids": [],
            "linked_transfer_ids": [],
            "view_url": _safe_url("manager.move_requests", origin=origin, destination=destination),
        }
    return lanes[key]


def _bump_status(target, status, *, has_issue=False):
    bucket = _status_bucket(status)
    if bucket == "blocked":
        target["blocked_count"] += 1
    elif bucket == "waiting":
        target["waiting_count"] += 1
    elif bucket == "active":
        target["active_count"] += 1
    elif bucket == "completed":
        target["completed_count"] += 1
    else:
        target["open_count"] += 1
    if has_issue:
        target["issue_count"] = target.get("issue_count", 0) + 1


def _add_source(meta, source):
    sources = meta.setdefault("data_sources", [])
    if source not in sources:
        sources.append(source)


def _move_requests(target, *, driver_id=None, selected_move_request_id=None):
    start, end = _day_bounds(target)
    active = MoveRequest.query.filter(MoveRequest.status.in_(ACTIVE_STATUSES)).all()
    completed = MoveRequest.query.filter(
        MoveRequest.status == "completed",
        or_(
            MoveRequest.updated_at.between(start, end),
            MoveRequest.created_at.between(start, end),
        ),
    ).all()
    by_id = {req.id: req for req in active + completed}
    if selected_move_request_id and selected_move_request_id not in by_id:
        selected = MoveRequest.query.get(selected_move_request_id)
        if selected:
            by_id[selected.id] = selected
    rows = list(by_id.values())
    if driver_id:
        filtered = []
        for req in rows:
            linked_log = getattr(req, "linked_driver_log", None)
            if req.assigned_driver_id == driver_id or (linked_log is not None and linked_log.driver_id == driver_id):
                filtered.append(req)
        rows = filtered
    rows.sort(
        key=lambda req: (
            getattr(req, "due_at", None) is None,
            getattr(req, "due_at", None) or datetime.max,
            getattr(req, "requested_at", None) or datetime.min,
            getattr(req, "id", 0),
        )
    )
    return rows


def _driver_logs(target, *, driver_id=None, selected_stop_id=None):
    query = DriverLog.query.filter(DriverLog.deleted_at.is_(None), DriverLog.date == target)
    if driver_id:
        query = query.filter_by(driver_id=driver_id)
    logs = query.order_by(DriverLog.driver_id.asc(), DriverLog.created_at.asc(), DriverLog.id.asc()).all()
    if selected_stop_id and selected_stop_id not in {log.id for log in logs}:
        selected = DriverLog.query.get(selected_stop_id)
        if selected and not selected.deleted_at:
            logs.append(selected)
    return logs


def _plant_transfers(target, *, driver_id=None):
    query = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date == target,
    )
    if driver_id:
        query = query.filter_by(user_id=driver_id)
    return query.order_by(PlantTransfer.created_at.desc(), PlantTransfer.id.desc()).all()


def _damage_reports(target, *, driver_id=None):
    start, end = _day_bounds(target)
    query = DamageReport.query.filter(
        DamageReport.status != "closed",
        or_(
            DamageReport.damage_time.between(start, end),
            DamageReport.created_at.between(start, end),
        ),
    )
    if driver_id:
        query = query.filter_by(reported_by_id=driver_id)
    return query.order_by(DamageReport.created_at.desc(), DamageReport.id.desc()).all()


def _issue_events(target, *, driver_id=None):
    start, end = _day_bounds(target)
    query = ExceptionEvent.query.filter(
        or_(
            ExceptionEvent.event_date == target,
            ExceptionEvent.created_at.between(start, end),
        )
    )
    if driver_id:
        query = query.filter_by(driver_id=driver_id)
    return query.order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc()).all()


def _timing_by_node(target):
    rows = plant_forecast_rows(target)
    timing = {}
    for row in rows:
        key = _location_key(row.get("plant") or row.get("plant_id"))
        timing[key] = {
            "estimate_minutes": row.get("estimate_minutes"),
            "estimate_label": row.get("estimate_label"),
            "today_count": row.get("today_count"),
            "confidence": row.get("confidence"),
            "basis": row.get("basis"),
        }
    return timing


def _move_item(req, *, now, has_issue=False):
    log = getattr(req, "linked_driver_log", None)
    cargo = cargo_state_for_request(req, log=log)
    next_action = next_action_for_request(req, has_open_issue=has_issue, cargo=cargo)
    origin = _location_label(req.origin_location_text) or NOT_TRACKED
    destination = _location_label(req.destination_location_text) or NOT_TRACKED
    status = (req.status or "open").lower()
    return {
        "item_id": f"move_request-{req.id}",
        "item_type": "move_request",
        "label": req.display_number,
        "plant_location": f"{origin} -> {destination}",
        "stage": _status_label(status),
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(req.raw_text) or SAFE_EMPTY,
        "age_minutes": _age_minutes(req.requested_at, now=now),
        "status": status,
        "status_label": _status_label(status),
        "next_action": next_action,
        "linked_request_id": req.id,
        "linked_route_stop_id": req.linked_driver_log_id,
        "linked_document_id": req.linked_document_id,
        "linked_transfer_id": req.linked_plant_transfer_id,
        "origin_label": origin,
        "destination_label": destination,
        "cargo_text": _clean(req.cargo_text) or SAFE_EMPTY,
        "part_number": _clean(req.part_number),
        "quantity_text": _quantity_text(req),
        "priority": (req.priority or "normal").lower(),
        "assigned_driver": _clean(req.assigned_display) or "Unassigned",
        "assigned": bool(req.assigned_driver_id or _clean(req.assigned_driver_text)),
        "hot": (req.priority or "").lower() in {"hot", "safety"},
        "arrival_recorded": bool(getattr(log, "arrive_time", None)),
        "departure_recorded": bool(getattr(log, "depart_time", None)),
        "proof_recorded": bool(req.linked_plant_transfer_id or req.linked_document_id),
        "due_label": _clean(req.due_time_text),
        "equipment": _clean(req.equipment_display),
        "document_summary": f"Document #{req.linked_document_id}" if req.linked_document_id else DOCUMENT_MISSING,
        "view_url": _safe_url("manager.edit_move_request", request_id=req.id),
    }


def _route_item(log, *, now, issue_stop_ids=frozenset(), damaged_stop_ids=frozenset()):
    status = "completed" if log.depart_time else "waiting"
    has_issue = log.id in issue_stop_ids or log.id in damaged_stop_ids
    if has_issue and not log.depart_time:
        status = "needs_review"
    cargo = cargo_state_for_log(log, has_open_damage=log.id in damaged_stop_ids)
    wait_minutes = wait_minutes_for_log(log, now=None) if not log.depart_time else (log.dock_wait_minutes or 0)
    return {
        "item_id": f"route_stop-{log.id}",
        "item_type": "route_stop",
        "label": f"Stop {log.id}",
        "plant_location": _location_label(log.plant_name) or SAFE_EMPTY,
        "stage": "Completed" if log.depart_time else "Waiting",
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": cargo["label"],
        "age_minutes": wait_minutes if not log.depart_time else None,
        "status": status,
        "status_label": _status_label(status),
        "next_action": "Review issue" if has_issue else ("No action needed" if log.depart_time else "Record departure"),
        "linked_request_id": None,
        "linked_route_stop_id": log.id,
        "linked_document_id": None,
        "linked_transfer_id": None,
        "arrival_at": log.arrive_time or "",
        "departure_at": log.depart_time or "",
        "arrived_with": log.load_size or NOT_TRACKED,
        "departed_with": log.depart_load_size or NOT_TRACKED,
        "part_number": _clean(log.part_number),
        "no_pickup": bool(getattr(log, "no_pickup", False)),
        "delayed": bool((log.dock_wait_minutes or 0) >= DELAY_WAIT_THRESHOLD),
        "hot": bool(getattr(log, "hot_parts", False)),
        "view_url": _safe_url("manager.view_driver_log", log_id=log.id),
    }


def _transfer_item(transfer):
    origin = _location_label(transfer.ship_from) or NOT_TRACKED
    destination = _location_label(transfer.ship_to) or NOT_TRACKED
    transfer_number = transfer.transfer_number or transfer.id
    line_count = len(getattr(transfer, "lines", []) or [])
    return {
        "item_id": f"plant_transfer-{transfer.id}",
        "item_type": "plant_transfer",
        "label": f"Plant Transfer {transfer_number}",
        "plant_location": f"{origin} -> {destination}",
        "stage": "Proof",
        "trailer": _clean(transfer.trailer_number) or None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": f"{line_count} line{'s' if line_count != 1 else ''}" if line_count else "Transfer proof recorded",
        "age_minutes": None,
        "status": "completed",
        "status_label": "Completed",
        "next_action": "No action needed",
        "linked_request_id": None,
        "linked_route_stop_id": None,
        "linked_document_id": None,
        "linked_transfer_id": transfer.id,
        "origin_label": origin,
        "destination_label": destination,
        "view_url": None,
    }


def _damage_item(report, *, now):
    issue = classify_issue(category="damage", severity="critical")
    return {
        "item_id": f"damage-{report.id}",
        "item_type": "issue",
        "label": f"Damage Report #{report.id}",
        "plant_location": _location_label(report.plant_name) or SAFE_EMPTY,
        "stage": issue["category_label"],
        "trailer": _clean(report.trailer_number) or None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(report.description) or "Damage report recorded.",
        "age_minutes": _age_minutes(report.created_at, now=now),
        "status": "blocked",
        "status_label": issue["level_label"],
        "next_action": "Review issue",
        "linked_request_id": None,
        "linked_route_stop_id": report.driver_log_id,
        "linked_document_id": None,
        "linked_transfer_id": report.plant_transfer_id,
        "view_url": _safe_url("driver.view_damage_report", report_id=report.id),
    }


def _exception_item(event, *, now):
    issue = classify_issue(category=event.event_type, severity=event.severity, label=event.summary)
    return {
        "item_id": f"issue-{event.id}",
        "item_type": "issue",
        "label": event.summary,
        "plant_location": _location_label(event.plant_name) or SAFE_EMPTY,
        "stage": issue["category_label"],
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(event.details) or _clean(event.summary) or "Issue recorded.",
        "age_minutes": _age_minutes(event.created_at, now=now),
        "status": issue["level"],
        "status_label": issue["level_label"],
        "next_action": "Review issue",
        "linked_request_id": event.target_id if event.target_type == "move_request" else None,
        "linked_route_stop_id": event.stop_id or event.driver_log_id,
        "linked_document_id": None,
        "linked_transfer_id": event.target_id if event.target_type == "plant_transfer" else None,
        "view_url": None,
    }


def build_production_flow_context(
    date=None,
    driver_id=None,
    selected_plant=None,
    selected_move_request_id=None,
    selected_stop_id=None,
    mode="production",
):
    """Build a production-flow context from real MoveDefense records only."""
    target = _target_date(date)
    now = datetime.utcnow()
    requests = _move_requests(target, driver_id=driver_id, selected_move_request_id=selected_move_request_id)
    logs = _driver_logs(target, driver_id=driver_id, selected_stop_id=selected_stop_id)
    transfers = _plant_transfers(target, driver_id=driver_id)
    damage_reports = _damage_reports(target, driver_id=driver_id)
    issue_events = _issue_events(target, driver_id=driver_id)
    timing_by_node = _timing_by_node(target)

    nodes = {}
    lanes = {}
    items = []
    issue_stop_ids = {event.stop_id or event.driver_log_id for event in issue_events if event.stop_id or event.driver_log_id}
    damaged_stop_ids = {report.driver_log_id for report in damage_reports if report.driver_log_id}

    queue_summary = {
        "open_count": 0,
        "active_count": 0,
        "waiting_count": 0,
        "blocked_count": 0,
        "completed_count": 0,
        "unassigned_count": 0,
        "needs_attention_count": 0,
        "document_needed_count": 0,
        "hot_count": 0,
    }

    for req in requests:
        status = (req.status or "open").lower()
        has_issue = status in BLOCKED_STATUSES or bool(_clean(req.blocked_reason))
        item = _move_item(req, now=now, has_issue=has_issue)
        items.append(item)

        bucket = _status_bucket(status)
        if bucket == "blocked":
            queue_summary["blocked_count"] += 1
        elif bucket == "waiting":
            queue_summary["waiting_count"] += 1
        elif bucket == "active":
            queue_summary["active_count"] += 1
        elif bucket == "completed":
            queue_summary["completed_count"] += 1
        else:
            queue_summary["open_count"] += 1
        if status not in {"completed", "cancelled"} and not (req.assigned_driver_id or _clean(req.assigned_driver_text)):
            queue_summary["unassigned_count"] += 1
        if has_issue:
            queue_summary["needs_attention_count"] += 1
        if status not in {"completed", "cancelled"} and not (req.linked_document_id or req.linked_plant_transfer_id):
            queue_summary["document_needed_count"] += 1
        if (req.priority or "").lower() in {"hot", "safety"}:
            queue_summary["hot_count"] += 1

        for label in (req.origin_location_text, req.destination_location_text):
            node = _node(nodes, label)
            if not node:
                continue
            _bump_status(node, status, has_issue=has_issue)
            _add_source(node["meta"], "MoveRequest")

        lane = _lane(lanes, req.origin_location_text, req.destination_location_text)
        if lane:
            _bump_status(lane, status)
            lane["linked_request_ids"].append(req.id)
            age = _age_minutes(req.requested_at, now=now)
            if age is not None:
                lane["oldest_age_minutes"] = age if lane["oldest_age_minutes"] is None else max(lane["oldest_age_minutes"], age)

    for log in logs:
        item = _route_item(log, now=now, issue_stop_ids=issue_stop_ids, damaged_stop_ids=damaged_stop_ids)
        items.append(item)
        node = _node(nodes, log.plant_name)
        if not node:
            continue
        _bump_status(node, "completed" if log.depart_time else "waiting", has_issue=log.id in issue_stop_ids or log.id in damaged_stop_ids)
        _add_source(node["meta"], "DriverLog")
        if getattr(log, "no_pickup", False):
            node["no_pickup_count"] += 1
        if (log.dock_wait_minutes or 0) >= DELAY_WAIT_THRESHOLD:
            node["delay_count"] += 1

    for transfer in transfers:
        item = _transfer_item(transfer)
        items.append(item)
        for label in (transfer.ship_from, transfer.ship_to):
            node = _node(nodes, label)
            if node:
                _bump_status(node, "completed")
                _add_source(node["meta"], "PlantTransfer")
        lane = _lane(lanes, transfer.ship_from, transfer.ship_to)
        if lane:
            _bump_status(lane, "completed")
            lane["linked_transfer_ids"].append(transfer.id)

    for report in damage_reports:
        item = _damage_item(report, now=now)
        items.append(item)
        node = _node(nodes, report.plant_name)
        if node:
            node["issue_count"] += 1
            node["blocked_count"] += 1
            node["damage_count"] += 1
            _add_source(node["meta"], "DamageReport")

    for event in issue_events:
        item = _exception_item(event, now=now)
        items.append(item)
        node = _node(nodes, event.plant_name)
        if node:
            node["issue_count"] += 1
            node["blocked_count"] += 1
            _add_source(node["meta"], "ExceptionEvent")

    for key, node in nodes.items():
        node["meta"]["timing"] = timing_by_node.get(key)
        node["worst_status"] = _worst_status(
            blocked_count=node["blocked_count"],
            waiting_count=node["waiting_count"],
            active_count=node["active_count"],
            open_count=node["open_count"],
            completed_count=node["completed_count"],
        )
        node["next_action"] = _node_next_action(node)

    for lane in lanes.values():
        lane["linked_request_ids"] = sorted(set(lane["linked_request_ids"]))
        lane["linked_driver_log_ids"] = sorted(set(lane["linked_driver_log_ids"]))
        lane["linked_transfer_ids"] = sorted(set(lane["linked_transfer_ids"]))
        lane["worst_status"] = _worst_status(
            blocked_count=lane["blocked_count"],
            waiting_count=lane["waiting_count"],
            active_count=lane["active_count"],
            open_count=lane["open_count"],
            completed_count=lane["completed_count"],
        )
        lane["lane_type"] = _lane_type(lane["worst_status"])

    flow_nodes = sorted(
        nodes.values(),
        key=lambda n: (-(n["blocked_count"] + n["waiting_count"] + n["active_count"] + n["open_count"]), n["label"]),
    )
    flow_lanes = sorted(
        lanes.values(),
        key=lambda l: (-(l["blocked_count"] + l["waiting_count"] + l["active_count"] + l["open_count"] + l["completed_count"]), l["origin_label"], l["destination_label"]),
    )
    items.sort(key=lambda item: (item["status"] not in {"blocked", "needs_review", "critical", "high"}, item["age_minutes"] is None, -(item["age_minutes"] or 0), item["label"]))

    floor_summary = {
        "active_stop_count": len([log for log in logs if not log.depart_time]),
        "completed_stop_count": len([log for log in logs if log.depart_time]),
        "active_driver_count": len({log.driver_id for log in logs if not log.depart_time}),
        "transfer_count": len(transfers),
        "issue_count": len(damage_reports) + len(issue_events),
        "node_count": len(flow_nodes),
        "lane_count": len(flow_lanes),
        "production_snapshot_available": False,
        "carrier_unit_snapshot": None,
        "rack_capacity_snapshot": None,
        "data_scope_note": DATA_SCOPE_EMPTY,
    }

    return {
        "mode": mode,
        "date": target,
        "flow_nodes": flow_nodes,
        "flow_lanes": flow_lanes,
        "flow_items": items,
        "queue_summary": queue_summary,
        "floor_summary": floor_summary,
        "selected_context": {
            "selected_plant": selected_plant,
            "selected_move_request_id": selected_move_request_id,
            "selected_stop_id": selected_stop_id,
            "selected_node_key": _location_key(selected_plant) if selected_plant else None,
        },
        "empty_states": {
            "no_flow_nodes": not bool(flow_nodes),
            "no_flow_lanes": not bool(flow_lanes),
            "no_flow_items": not bool(items),
            "no_move_requests": not bool(requests),
            "no_route_activity": not bool(logs),
            "no_transfer_data": not bool(transfers),
            "no_production_snapshot": True,
            "carrier_unit_snapshot": CARRIER_SNAPSHOT_EMPTY,
            "rack_capacity": RACK_SNAPSHOT_EMPTY,
            "data_scope": DATA_SCOPE_EMPTY,
        },
    }
