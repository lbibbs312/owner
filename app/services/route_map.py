"""Route-map view models derived from real MoveDefense records.

This module builds a display contract for the driver and manager dashboards.
It does not create GPS points, telemetry, synthetic stops, or new locations.
Every node, lane, stop, and move comes from DriverLog, MoveRequest,
PlantTransfer, DamageReport, and existing route/cargo/next-action helpers.
"""
from datetime import date as date_cls, datetime, timedelta
import re

from flask import has_request_context, url_for
import pytz
from werkzeug.routing import BuildError

from app.models import DamageReport, DriverLog, MoveRequest, PlantTransfer, User
from app.services.cargo_state import cargo_state_for_log, cargo_state_for_request
from app.services.driver_wait import wait_minutes_for_log
from app.services.floor_operations import (
    ACTIVE_STATUSES,
    next_action_for_request,
    route_next_action,
)
from app.services.load_state import (
    destination_from_load,
    is_empty_load,
    is_service_stop,
    load_display,
    service_stop_label,
)
from app.services.plant_addresses import PLANT_LABELS, plant_label
from app.services.route_context import build_route_context


SAFE_EMPTY = "No current data"
NOT_TRACKED = "Not tracked yet"
DOCUMENT_MISSING = "Document not attached"
DETROIT_TZ = pytz.timezone("America/Detroit")


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
    status = _clean(status).replace("_", " ").strip()
    return status.title() if status else SAFE_EMPTY


def _norm_key(value):
    return re.sub(r"[^a-z0-9]+", "_", _clean(value).lower()).strip("_") or "unspecified"


def _board_cargo_label(value):
    text = _clean(value)
    if not text or text == NOT_TRACKED:
        return "--"
    return load_display(text)


def _service_board_code(log):
    if getattr(log, "fuel", False):
        return "FUEL"
    plant_text = f"{getattr(log, 'plant_name', '')} {plant_label(getattr(log, 'plant_name', ''))}".lower()
    if "ryder" in plant_text:
        return "RYDR"
    if getattr(log, "maintenance", False):
        return "MTN"
    if getattr(log, "meeting", False):
        return "MTG"
    return "SRVC"


def _board_stop_code(log, sequence):
    if is_service_stop(log):
        return _service_board_code(log)
    return f"STP-{sequence or '?'}"


def _service_board_detail(log, label, route_pretrip=None):
    if getattr(log, "fuel", False) and getattr(log, "fuel_mileage", None) is not None:
        start_mileage = getattr(route_pretrip, "start_mileage", None)
        if start_mileage is not None:
            delta = log.fuel_mileage - start_mileage
            return f"+{delta:,} mi from pre-trip"
        return f"{log.fuel_mileage:,} mi recorded"
    return f"{label} - {service_stop_label(log).lower()}"


def _board_stop_detail(log, label, arrived_with, departed_with, wait_label="", route_pretrip=None):
    if is_service_stop(log):
        return _service_board_detail(log, label, route_pretrip=route_pretrip)

    arrived = _board_cargo_label(arrived_with)
    closed = bool(getattr(log, "depart_time", None))
    departed = _board_cargo_label(departed_with) if closed else "--"
    no_pickup = bool(getattr(log, "no_pickup", False))
    if closed and no_pickup and arrived == "Empty" and departed == "Empty":
        return f"{label} - empty return"

    detail = f"{label} - {arrived} -> {departed}"
    if wait_label and wait_label != NOT_TRACKED:
        detail = f"{detail} - {wait_label}"
    return detail


def _date_label(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d %I:%M%p").replace(" 0", " ").lower()
    return _clean(value)


def _driver_name(driver_id=None, driver=None):
    if driver is None and driver_id:
        driver = User.query.get(driver_id)
    if driver is None:
        return NOT_TRACKED
    return getattr(driver, "display_name", None) or getattr(driver, "username", None) or NOT_TRACKED


def _quantity_text(req):
    return _clean(getattr(req, "quantity_display", "")) or _clean(getattr(req, "quantity_text", ""))


def _request_equipment(req):
    return _clean(getattr(req, "equipment_display", "")) or NOT_TRACKED


def _linked_stop_id(req):
    return getattr(req, "linked_driver_log_id", None)


def _damage_log_ids(log_ids):
    log_ids = [log_id for log_id in log_ids if log_id]
    if not log_ids:
        return set()
    reports = DamageReport.query.filter(
        DamageReport.status != "closed",
        DamageReport.driver_log_id.in_(log_ids),
    ).all()
    return {report.driver_log_id for report in reports}


def _open_issue_request_ids(requests):
    ids = set()
    for req in requests:
        status = (req.status or "").lower()
        if status in {"blocked", "needs_review"} or _clean(req.blocked_reason):
            ids.add(req.id)
    return ids


def _requests_for_view(*, driver_id=None, target=None, selected_move_request_id=None):
    target = target or date_cls.today()
    start, end = _day_bounds(target)
    requests = MoveRequest.query.filter(MoveRequest.status.in_(ACTIVE_STATUSES)).all()
    completed_today = MoveRequest.query.filter(
        MoveRequest.status == "completed",
        MoveRequest.updated_at >= start,
        MoveRequest.updated_at < end,
    ).all()
    request_by_id = {req.id: req for req in requests + completed_today}
    if selected_move_request_id and selected_move_request_id not in request_by_id:
        selected = MoveRequest.query.get(selected_move_request_id)
        if selected:
            request_by_id[selected.id] = selected

    rows = list(request_by_id.values())
    if driver_id:
        filtered = []
        for req in rows:
            linked_log = getattr(req, "linked_driver_log", None)
            if req.assigned_driver_id == driver_id or (
                linked_log is not None and linked_log.driver_id == driver_id
            ):
                filtered.append(req)
        rows = filtered

    rows.sort(
        key=lambda req: (
            getattr(req, "due_at", None) is None,
            getattr(req, "due_at", None) or datetime.max,
            getattr(req, "requested_at", None) or datetime.min,
        )
    )
    return rows


def _transfers_for_view(*, driver_id=None, target=None):
    target = target or date_cls.today()
    query = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date == target,
    )
    if driver_id:
        query = query.filter_by(user_id=driver_id)
    return query.order_by(PlantTransfer.created_at.desc()).all()


def _move_view_model(req, *, damaged_log_ids=frozenset(), issue_request_ids=frozenset(), role="driver"):
    log = getattr(req, "linked_driver_log", None)
    has_damage = bool(req.linked_driver_log_id and req.linked_driver_log_id in damaged_log_ids)
    cargo = cargo_state_for_request(req, log=log, has_open_damage=has_damage)
    has_issue = req.id in issue_request_ids or has_damage
    next_action = next_action_for_request(req, has_open_issue=has_issue, cargo=cargo)
    status = (req.status or "open").lower()
    priority = (req.priority or "normal").lower()
    origin = _location_label(req.origin_location_text) or NOT_TRACKED
    destination = _location_label(req.destination_location_text) or NOT_TRACKED
    edit_url = _safe_url("manager.edit_move_request", request_id=req.id)
    return {
        "move_request_id": req.id,
        "request_number": req.display_number,
        "raw_text": _clean(req.raw_text) or SAFE_EMPTY,
        "source": _clean(req.source) or NOT_TRACKED,
        "requested_by": _clean(req.requested_by) or NOT_TRACKED,
        "requested_at": _date_label(req.requested_at),
        "origin_location_text": origin,
        "destination_location_text": destination,
        "cargo_text": _clean(req.cargo_text) or SAFE_EMPTY,
        "part_number": _clean(req.part_number),
        "quantity_text": _quantity_text(req),
        "due_at": req.due_at,
        "due_time_text": _clean(req.due_time_text) or _date_label(req.due_at),
        "priority": priority,
        "priority_label": priority.title(),
        "status": status,
        "status_label": _status_label(status),
        "assigned_driver": _clean(req.assigned_display) or "Unassigned",
        "equipment": _request_equipment(req),
        "linked_stop_id": _linked_stop_id(req),
        "linked_route_id": _clean(req.linked_route_id),
        "linked_plant_transfer_id": req.linked_plant_transfer_id,
        "linked_document_id": req.linked_document_id,
        "document_summary": f"Document #{req.linked_document_id}" if req.linked_document_id else DOCUMENT_MISSING,
        "transfer_summary": (
            f"Plant Transfer {req.linked_plant_transfer.transfer_number or req.linked_plant_transfer_id}"
            if req.linked_plant_transfer_id and req.linked_plant_transfer
            else "No linked plant transfer"
        ),
        "cargo_status": cargo["label"],
        "has_damage": has_damage,
        "has_issue": has_issue,
        "next_action": next_action,
        "view_url": edit_url if role == "manager" else None,
        "actions": _move_actions(req, role=role, edit_url=edit_url),
    }


def _move_actions(req, *, role, edit_url=None):
    if role != "manager":
        return []
    actions = []
    status = (req.status or "open").lower()
    if status in {"open", "assigned"}:
        actions.append({
            "label": "Acknowledge",
            "url": _safe_url("manager.acknowledge_move_request", request_id=req.id),
            "method": "post",
        })
    actions.append({"label": "Assign driver", "url": edit_url, "method": "get"})
    actions.append({"label": "Start/link route", "url": edit_url, "method": "get"})
    if status != "blocked":
        actions.append({
            "label": "Mark blocked",
            "url": _safe_url("manager.mark_move_request_blocked", request_id=req.id),
            "method": "post",
        })
    if status != "completed":
        actions.append({
            "label": "Mark completed",
            "url": _safe_url("manager.mark_move_request_completed", request_id=req.id),
            "method": "post",
        })
    actions.append({"label": "Attach document", "url": edit_url, "method": "get"})
    actions.append({"label": "View audit/proof", "url": None, "method": "disabled"})
    return actions


def _stop_actions(log, *, linked_move=None, role="driver"):
    actions = []
    view_endpoint = "manager.view_driver_log" if role == "manager" else "driver.view_driver_log"
    edit_endpoint = "driver.edit_driver_log"
    actions.append({"label": "Open stop", "url": _safe_url(view_endpoint, log_id=log.id), "method": "get"})
    if role == "driver":
        actions.append({"label": "Record arrival", "url": None, "method": "disabled"})
        if not log.depart_time:
            actions.append({"label": "Record departure", "url": _safe_url("driver.depart_driver_log", log_id=log.id), "method": "get"})
            actions.append({"label": "Confirm cargo", "url": _safe_url("driver.pickup_driver_log", log_id=log.id), "method": "get"})
        actions.append({"label": "Add note", "url": None, "method": "disabled"})
        actions.append({"label": "Add damage", "url": _safe_url("driver.new_damage_report"), "method": "get"})
        actions.append({"label": "Attach document", "url": _safe_url("driver.new_plant_transfer"), "method": "get"})
        actions.append({"label": "Verify suspicious time", "url": _safe_url(edit_endpoint, log_id=log.id), "method": "get"})
    if linked_move and role == "manager":
        actions.append({
            "label": "View linked move request",
            "url": _safe_url("manager.edit_move_request", request_id=linked_move.id),
            "method": "get",
        })
    return actions


def _stop_status(row, log, *, current_stop_id=None, has_issue=False, has_damage=False, linked_move=None):
    if linked_move is not None and (linked_move.status or "").lower() == "blocked":
        return "blocked"
    if has_damage or has_issue:
        return "needs_review"
    if current_stop_id and log.id == current_stop_id:
        return "active"
    if log.depart_time:
        return "completed"
    return "future"


def _stop_next_action(log, *, status, cargo, linked_move=None):
    if status == "blocked":
        return "Review blocker"
    if status == "needs_review":
        return "Review issue"
    if linked_move is not None:
        has_issue = (linked_move.status or "").lower() in {"blocked", "needs_review"}
        return next_action_for_request(linked_move, has_open_issue=has_issue)
    if not log.depart_time:
        if cargo["state"] == "unknown":
            return "Confirm cargo"
        return "Record departure"
    return "No action needed"


def _build_stops(route_context, *, role="driver", move_requests=None, route_pretrip=None):
    move_requests = move_requests or []
    linked_by_log = {req.linked_driver_log_id: req for req in move_requests if req.linked_driver_log_id}
    log_ids = [row["log"].id for row in getattr(route_context, "rows", []) if row.get("log")]
    damaged_log_ids = _damage_log_ids(log_ids)
    issue_stop_ids = set()
    for item in (getattr(route_context, "true_exceptions", None) or []) + (getattr(route_context, "review_items", None) or []):
        if item.get("stop_id"):
            issue_stop_ids.add(item["stop_id"])

    stops = []
    current_stop_id = getattr(getattr(route_context, "current_stop", None), "id", None)
    for row in getattr(route_context, "rows", []) or []:
        log = row.get("log")
        if not log:
            continue
        label = row.get("plant") or _location_label(log.plant_name) or SAFE_EMPTY
        linked_move = linked_by_log.get(log.id)
        cargo = cargo_state_for_log(log, has_open_damage=log.id in damaged_log_ids)
        has_issue = log.id in issue_stop_ids
        has_damage = log.id in damaged_log_ids
        status = _stop_status(
            row,
            log,
            current_stop_id=current_stop_id,
            has_issue=has_issue,
            has_damage=has_damage,
            linked_move=linked_move,
        )
        wait_minutes = wait_minutes_for_log(log, now=None) if not log.depart_time else (log.dock_wait_minutes or 0)
        sequence = row.get("index") or len(stops) + 1
        arrived_with = row.get("cargo_in") or log.load_size or NOT_TRACKED
        departed_with = row.get("cargo_out") or log.depart_load_size or NOT_TRACKED
        wait_label = f"{wait_minutes} min" if wait_minutes is not None else NOT_TRACKED
        stops.append({
            "stop_id": log.id,
            "sequence": sequence,
            "plant_name": label,
            "short_code": _short_code(log.plant_name or label),
            "board_code": _board_stop_code(log, sequence),
            "board_detail": _board_stop_detail(
                log,
                label,
                arrived_with,
                departed_with,
                wait_label=wait_label,
                route_pretrip=route_pretrip,
            ),
            "status": status,
            "status_label": _status_label(status),
            "arrival_at": log.arrive_time or "",
            "departure_at": log.depart_time or "",
            "wait_minutes": wait_minutes,
            "wait_label": wait_label,
            "arrived_with": arrived_with,
            "departed_with": departed_with,
            "no_pickup": bool(getattr(log, "no_pickup", False)),
            "cargo_status": cargo["label"],
            "linked_move_request_id": getattr(linked_move, "id", None),
            "linked_move_request_number": getattr(linked_move, "display_number", None),
            "linked_plant_transfer_id": getattr(linked_move, "linked_plant_transfer_id", None),
            "linked_document_id": getattr(linked_move, "linked_document_id", None),
            "document_summary": (
                f"Document #{linked_move.linked_document_id}"
                if linked_move is not None and linked_move.linked_document_id
                else DOCUMENT_MISSING
            ),
            "has_damage": has_damage,
            "has_issue": has_issue,
            "notes": row.get("note") or "",
            "next_action": _stop_next_action(log, status=status, cargo=cargo, linked_move=linked_move),
            "view_url": _safe_url("manager.view_driver_log" if role == "manager" else "driver.view_driver_log", log_id=log.id),
            "actions": _stop_actions(log, linked_move=linked_move, role=role),
        })
    return stops


def _detail_flags(log, row, route):
    text = " ".join(
        _clean(value)
        for value in (
            getattr(log, "downtime_reason", ""),
            row.get("note"),
            " ".join(route.get("warnings") or []),
        )
    ).lower()
    flags = []
    if getattr(log, "hot_parts", False):
        flags.append("Hot")
    if getattr(log, "no_pickup", False):
        flags.append("No pickup")
    if "hold" in text or "held" in text or "blocked" in text:
        flags.append("Hold")
    if "scrap" in text:
        flags.append("Scrap")
    if route.get("unload_blocked") or route.get("secondary_drop_blocked"):
        flags.append("Needs review")
    if route.get("deviation"):
        flags.append("Verify route")
    if getattr(log, "maintenance", False):
        flags.append("Maintenance")
    if getattr(log, "fuel", False):
        flags.append("Fuel")
    if getattr(log, "meeting", False):
        flags.append("Meeting")
    return tuple(dict.fromkeys(flags))


def _part_labels(log, *extra_parts):
    labels = []
    part = _clean(getattr(log, "part_number", ""))
    if part:
        labels.append(f"HOT {part}" if getattr(log, "hot_parts", False) else part)
    elif getattr(log, "hot_parts", False):
        labels.append("Hot part")
    for item in extra_parts:
        text = _clean(item)
        if text and text not in labels:
            labels.append(text)
    return labels


def _delivery_destination(load_label, fallback_plant):
    destination = destination_from_load(load_label)
    if destination:
        return plant_label(destination), destination
    return _location_label(fallback_plant) or SAFE_EMPTY, _location_key(fallback_plant)


def _load_count_label(count):
    return f"{count} load{'s' if count != 1 else ''}"


def _stop_count_label(count):
    return f"{count} stop{'s' if count != 1 else ''}"


def _new_narrative_group(kind, *, title, route_line, board_detail=None, origin_label=None, destination_label=None):
    return {
        "key": _norm_key(f"{kind}:{title}:{origin_label}:{destination_label}"),
        "kind": kind,
        "tone": "empty" if kind == "empty" else ("delivery" if kind == "delivery" else "pickup"),
        "title": title,
        "route_line": route_line,
        "board_detail": board_detail or route_line,
        "origin_label": origin_label,
        "destination_label": destination_label,
        "count": 0,
        "load_count_label": "",
        "stop_count_label": "",
        "parts": [],
        "flags": [],
        "details": [],
        "latest_departure_at": "",
    }


def _add_narrative_detail(groups, key, group, detail):
    if key not in groups:
        groups[key] = group
    target = groups[key]
    target["count"] += 1
    target["load_count_label"] = _load_count_label(target["count"])
    target["stop_count_label"] = _stop_count_label(len(target["details"]) + 1)
    target["latest_departure_at"] = detail.get("departure_at") or target["latest_departure_at"]
    for part in detail.get("parts") or []:
        if part not in target["parts"]:
            target["parts"].append(part)
    for flag in detail.get("flags") or []:
        if flag not in target["flags"]:
            target["flags"].append(flag)
    target["details"].append(detail)


def _base_stop_detail(log, row, route, *, cargo_label, pickup=None):
    flags = list(_detail_flags(log, row, route))
    parts = _part_labels(log, *((pickup or {}).get("parts") or ()))
    wait_minutes = wait_minutes_for_log(log, now=None) if not getattr(log, "depart_time", None) else (getattr(log, "dock_wait_minutes", None) or 0)
    wait_label = f"Wait {wait_minutes} min" if wait_minutes else ""
    pickup_label = ""
    if pickup:
        pickup_label = f"Picked up at {pickup['plant_label']}"
        if pickup.get("departure_at"):
            pickup_label = f"{pickup_label} before stop {row.get('index')}"
        for flag in pickup.get("flags") or []:
            if flag not in flags:
                flags.append(flag)
    return {
        "stop_id": getattr(log, "id", None),
        "sequence": row.get("index"),
        "board_code": _board_stop_code(log, row.get("index")),
        "board_detail": _board_stop_detail(
            log,
            row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
            row.get("cargo_in") or route.get("arrive_cargo_desc") or load_display(getattr(log, "load_size", "")),
            row.get("cargo_out") or route.get("depart_cargo_desc") or load_display(getattr(log, "depart_load_size", "")),
            wait_label=wait_label.replace("Wait ", "", 1) if wait_label else "",
        ),
        "plant": row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
        "arrival_at": getattr(log, "arrive_time", ""),
        "departure_at": getattr(log, "depart_time", ""),
        "cargo_label": cargo_label,
        "arrived_with": row.get("cargo_in") or route.get("arrive_cargo_desc") or load_display(getattr(log, "load_size", "")),
        "departed_with": row.get("cargo_out") or route.get("depart_cargo_desc") or load_display(getattr(log, "depart_load_size", "")),
        "no_pickup": bool(getattr(log, "no_pickup", False)),
        "parts": parts,
        "flags": tuple(dict.fromkeys(flags)),
        "wait_label": wait_label,
        "note": row.get("note") or "",
        "pickup_label": pickup_label,
        "view_url": _safe_url("driver.view_driver_log", log_id=getattr(log, "id", None)),
    }


def _pickup_info(log, row, route, cargo_label):
    return {
        "plant_label": row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
        "stop_id": getattr(log, "id", None),
        "sequence": row.get("index"),
        "departure_at": getattr(log, "depart_time", ""),
        "parts": _part_labels(log),
        "flags": _detail_flags(log, row, route),
        "cargo_label": cargo_label,
    }


def _build_delivery_narratives(route_context):
    """Aggregate completed route work into readable delivery and empty-load cards."""
    groups = {}
    pending_by_cargo = {}
    pending_by_destination = {}

    for row in getattr(route_context, "rows", []) or []:
        log = row.get("log")
        route = row.get("route") or {}
        if not log or not getattr(log, "depart_time", None):
            continue

        plant_label_text = row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY
        removed = [load_display(item) for item in row.get("cargo_removed") or () if not is_empty_load(item)]
        added = [load_display(item) for item in row.get("cargo_added") or () if not is_empty_load(item)]

        for cargo_label in removed:
            cargo_key = _norm_key(cargo_label)
            destination_label, destination_key = _delivery_destination(cargo_label, plant_label_text)
            pickup = pending_by_cargo.pop(cargo_key, None)
            if pickup and pending_by_destination.get(destination_key) is pickup:
                pending_by_destination.pop(destination_key, None)
            if pickup is None:
                pickup = pending_by_destination.pop(destination_key, None)
            origin_label = (pickup or {}).get("plant_label") or "Earlier stop"
            key = _norm_key(f"delivery:{origin_label}:{destination_label}")
            group = _new_narrative_group(
                "delivery",
                title=f"{destination_label} delivery from {origin_label}",
                route_line=f"{cargo_label} delivered from {origin_label} to {destination_label}",
                board_detail=f"{origin_label} -> {destination_label} - {cargo_label}",
                origin_label=origin_label,
                destination_label=destination_label,
            )
            detail = _base_stop_detail(log, row, route, cargo_label=cargo_label, pickup=pickup)
            _add_narrative_detail(groups, key, group, detail)

        arrived_empty = is_empty_load(row.get("cargo_in")) or is_empty_load(route.get("arrive_cargo_desc")) or is_empty_load(getattr(log, "load_size", None))
        departed_empty = is_empty_load(row.get("cargo_out")) or is_empty_load(route.get("depart_cargo_desc")) or is_empty_load(getattr(log, "depart_load_size", None))
        if not removed and not added and arrived_empty and departed_empty:
            key = _norm_key(f"empty:{plant_label_text}")
            group = _new_narrative_group(
                "empty",
                title=f"{plant_label_text} empty load",
                route_line=f"Arrived empty and departed empty at {plant_label_text}",
                board_detail=f"{plant_label_text} - empty return",
                destination_label=plant_label_text,
            )
            detail = _base_stop_detail(log, row, route, cargo_label="Empty load")
            _add_narrative_detail(groups, key, group, detail)

        for cargo_label in added:
            destination_label, destination_key = _delivery_destination(cargo_label, plant_label_text)
            info = _pickup_info(log, row, route, cargo_label)
            pending_by_cargo[_norm_key(cargo_label)] = info
            pending_by_destination[destination_key] = info

    return sorted(
        groups.values(),
        key=lambda item: (
            item.get("count") or 0,
            item.get("kind") == "delivery",
            item.get("latest_departure_at") or "",
        ),
        reverse=True,
    )


def _plant_seed(plants, label, *, role="driver"):
    label = _location_label(label)
    if not label:
        return None
    key = _location_key(label)
    if key not in plants:
        plants[key] = {
            "plant_key": key,
            "label": label,
            "short_code": _short_code(label),
            "active_stop_count": 0,
            "open_request_count": 0,
            "blocked_count": 0,
            "waiting_count": 0,
            "completed_today_count": 0,
            "related_move_request_ids": [],
            "related_stop_ids": [],
            "related_plant_transfer_ids": [],
            "worst_status": "none",
            "move_queue_url": _safe_url("manager.move_requests", location=label) if role == "manager" else None,
            "active_moves_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes") if role == "manager" else None,
            "timing_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes") if role == "manager" else None,
        }
    return plants[key]


def _lane_seed(lanes, origin, destination, *, role="driver"):
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
            "status": "none",
            "open_count": 0,
            "active_count": 0,
            "completed_count": 0,
            "blocked_count": 0,
            "linked_move_request_ids": [],
            "linked_stop_ids": [],
            "linked_plant_transfer_ids": [],
            "view_url": _safe_url("manager.move_requests", origin=origin, destination=destination) if role == "manager" else None,
        }
    return lanes[key]


def _worst_status(*, blocked=0, waiting=0, active=0, open_=0, completed=0):
    if blocked:
        return "blocked"
    if waiting:
        return "waiting"
    if active:
        return "active"
    if open_:
        return "open"
    if completed:
        return "completed"
    return "none"


def _build_plants_and_lanes(stops, moves, transfers, *, role="driver"):
    plants = {}
    lanes = {}

    for stop in stops:
        plant = _plant_seed(plants, stop["plant_name"], role=role)
        if not plant:
            continue
        plant["related_stop_ids"].append(stop["stop_id"])
        if stop["status"] == "completed":
            plant["completed_today_count"] += 1
        elif stop["status"] == "blocked":
            plant["blocked_count"] += 1
            plant["active_stop_count"] += 1
        elif stop["status"] == "needs_review":
            plant["blocked_count"] += 1
            plant["active_stop_count"] += 1
        elif stop["status"] == "active":
            plant["active_stop_count"] += 1
            plant["waiting_count"] += 1

    for prev, nxt in zip(stops, stops[1:]):
        lane = _lane_seed(lanes, prev["plant_name"], nxt["plant_name"], role=role)
        if not lane:
            continue
        lane["linked_stop_ids"].extend([prev["stop_id"], nxt["stop_id"]])
        if nxt["status"] in {"active", "needs_review"}:
            lane["active_count"] += 1
        elif nxt["status"] == "blocked":
            lane["blocked_count"] += 1
        elif nxt["status"] == "completed":
            lane["completed_count"] += 1
        else:
            lane["open_count"] += 1

    for move in moves:
        origin = _plant_seed(plants, move["origin_location_text"], role=role)
        destination = _plant_seed(plants, move["destination_location_text"], role=role)
        for plant in (origin, destination):
            if not plant:
                continue
            plant["related_move_request_ids"].append(move["move_request_id"])
            if move["status"] == "completed":
                plant["completed_today_count"] += 1
            else:
                plant["open_request_count"] += 1
            if move["status"] == "blocked" or move["has_issue"]:
                plant["blocked_count"] += 1
            if move["status"] in {"assigned", "in_progress", "waiting"}:
                plant["active_stop_count"] += 1
            if move["status"] == "waiting":
                plant["waiting_count"] += 1

        lane = _lane_seed(lanes, move["origin_location_text"], move["destination_location_text"], role=role)
        if lane:
            lane["linked_move_request_ids"].append(move["move_request_id"])
            if move["status"] == "completed":
                lane["completed_count"] += 1
            elif move["status"] == "blocked" or move["has_issue"]:
                lane["blocked_count"] += 1
            elif move["status"] in {"assigned", "in_progress", "waiting"}:
                lane["active_count"] += 1
            else:
                lane["open_count"] += 1

    for transfer in transfers:
        origin = _plant_seed(plants, transfer.ship_from, role=role)
        destination = _plant_seed(plants, transfer.ship_to, role=role)
        for plant in (origin, destination):
            if plant:
                plant["related_plant_transfer_ids"].append(transfer.id)
                plant["completed_today_count"] += 1
        lane = _lane_seed(lanes, transfer.ship_from, transfer.ship_to, role=role)
        if lane:
            lane["linked_plant_transfer_ids"].append(transfer.id)
            lane["completed_count"] += 1

    for plant in plants.values():
        plant["related_move_request_ids"] = sorted(set(plant["related_move_request_ids"]))
        plant["related_stop_ids"] = sorted(set(plant["related_stop_ids"]))
        plant["related_plant_transfer_ids"] = sorted(set(plant["related_plant_transfer_ids"]))
        plant["worst_status"] = _worst_status(
            blocked=plant["blocked_count"],
            waiting=plant["waiting_count"],
            active=plant["active_stop_count"],
            open_=plant["open_request_count"],
            completed=plant["completed_today_count"],
        )

    for lane in lanes.values():
        lane["linked_move_request_ids"] = sorted(set(lane["linked_move_request_ids"]))
        lane["linked_stop_ids"] = sorted(set(lane["linked_stop_ids"]))
        lane["linked_plant_transfer_ids"] = sorted(set(lane["linked_plant_transfer_ids"]))
        lane["status"] = _worst_status(
            blocked=lane["blocked_count"],
            active=lane["active_count"],
            open_=lane["open_count"],
            completed=lane["completed_count"],
        )

    return (
        sorted(plants.values(), key=lambda p: (-p["active_stop_count"], -p["open_request_count"], p["label"])),
        sorted(lanes.values(), key=lambda l: (-(l["open_count"] + l["active_count"] + l["completed_count"]), l["origin_label"], l["destination_label"])),
    )


def _route_summary(route_context, *, moves, stops, driver=None):
    current_stop = getattr(route_context, "current_stop", None)
    current_stop_id = getattr(current_stop, "id", None)
    current_location = (
        plant_label(current_stop.plant_name)
        if current_stop is not None
        else (stops[-1]["plant_name"] if stops else SAFE_EMPTY)
    )
    issue_count = len([s for s in stops if s["has_issue"] or s["has_damage"]]) + len([m for m in moves if m["has_issue"] or m["has_damage"]])
    document_needed = len([m for m in moves if not m["linked_document_id"] and not m["linked_plant_transfer_id"]])
    next_action = route_next_action(
        route_context,
        has_high_issue=bool(issue_count),
        missing_document=bool(document_needed and stops),
    )
    return {
        "route_id": getattr(route_context, "route_id", None),
        "driver_name": _driver_name(getattr(route_context, "driver_id", None), driver=driver),
        "truck": getattr(route_context, "truck_id", None) or NOT_TRACKED,
        "equipment": getattr(route_context, "truck_id", None) or NOT_TRACKED,
        "status": getattr(route_context, "route_status", None) or ("active" if stops else "no_route"),
        "current_stop_id": current_stop_id,
        "current_location": current_location,
        "next_action": next_action,
        "issue_summary": f"{issue_count} issue{'s' if issue_count != 1 else ''}" if issue_count else "No open issues",
        "document_summary": f"{document_needed} document needed" if document_needed else "Documents current",
    }


def _empty_states(route, stops, moves, lanes):
    return {
        "no_route": not bool(stops),
        "no_stops": not bool(stops),
        "no_move_requests": not bool(moves),
        "no_lane_data": not bool(lanes),
    }


def build_driver_map_mode_context(route_context, route_map=None, production_flow_context=None, *, route_date=None, today_local_date=None, route_is_active=False):
    """Choose the driver map mode without requiring active driving."""
    route_map = route_map or {}
    production_flow_context = production_flow_context or {}
    stops = route_map.get("stops") or []
    has_route_history = bool(stops)
    has_production = bool(
        production_flow_context.get("flow_nodes")
        or production_flow_context.get("flow_lanes")
        or production_flow_context.get("flow_items")
    )
    current_stop = getattr(route_context, "current_stop", None)
    is_today = bool(route_date and today_local_date and route_date == today_local_date)

    if current_stop is not None or (route_is_active and has_route_history):
        mode = "live_current_work"
        label = "Active Route Map"
        empty = ""
    elif has_route_history:
        mode = "route_replay"
        label = "Last Route Replay" if not is_today else "Route Replay"
        empty = ""
    elif has_production:
        mode = "production_flow"
        label = "Production Flow"
        empty = ""
    else:
        mode = "no_current_activity"
        label = "No Current Activity"
        empty = "No route stops logged for this date."

    return {
        "map_mode": mode,
        "map_label": label,
        "map_empty_message": empty,
        "has_route_history": has_route_history,
        "has_production_flow": has_production,
    }


def build_driver_route_map_context(
    driver_log=None,
    driver=None,
    date=None,
    selected_stop_id=None,
    selected_plant=None,
    selected_move_request_id=None,
    route_pretrip=None,
):
    """Build the driver route-map context from the driver's real work."""
    driver_id = getattr(driver, "id", None) or getattr(driver_log, "driver_id", None)
    target = _target_date(date or getattr(driver_log, "date", None))
    route_context = build_route_context(
        driver_log_id=getattr(driver_log, "id", None),
        driver_id=driver_id,
        route_date=target,
        selected_log_id=selected_stop_id,
    )
    requests = _requests_for_view(
        driver_id=driver_id,
        target=target,
        selected_move_request_id=selected_move_request_id,
    )
    request_log_ids = [req.linked_driver_log_id for req in requests if req.linked_driver_log_id]
    damaged_log_ids = _damage_log_ids(request_log_ids)
    issue_request_ids = _open_issue_request_ids(requests)
    moves = [
        _move_view_model(req, damaged_log_ids=damaged_log_ids, issue_request_ids=issue_request_ids, role="driver")
        for req in requests
    ]
    stops = _build_stops(route_context, role="driver", move_requests=requests, route_pretrip=route_pretrip)
    delivery_narratives = _build_delivery_narratives(route_context)
    transfers = _transfers_for_view(driver_id=driver_id, target=target)
    plants, lanes = _build_plants_and_lanes(stops, moves, transfers, role="driver")
    route = _route_summary(route_context, moves=moves, stops=stops, driver=driver)
    return {
        "map_mode": "live_current_work" if stops or moves or plants else "no_current_activity",
        "map_label": "Active Route Map" if stops or moves or plants else "No Current Activity",
        "map_empty_message": "No route stops logged for this date." if not stops else "",
        "route": route,
        "stops": stops,
        "delivery_narratives": delivery_narratives,
        "moves": moves,
        "plants": plants,
        "lanes": lanes,
        "selected": {
            "selected_stop_id": selected_stop_id,
            "selected_plant": selected_plant,
            "selected_move_request_id": selected_move_request_id,
        },
        "empty_states": _empty_states(route, stops, moves, lanes),
    }


def build_manager_route_map_context(date=None, selected_plant=None, selected_driver_id=None):
    """Build the manager route-map context across today's real routes/requests."""
    target = _target_date(date)
    log_query = DriverLog.query.filter(DriverLog.deleted_at.is_(None), DriverLog.date == target)
    if selected_driver_id:
        log_query = log_query.filter_by(driver_id=selected_driver_id)
    logs = log_query.order_by(DriverLog.driver_id.asc(), DriverLog.created_at.asc(), DriverLog.id.asc()).all()
    driver_ids = sorted({log.driver_id for log in logs})
    if selected_driver_id and selected_driver_id not in driver_ids:
        driver_ids = [selected_driver_id]

    requests = _requests_for_view(
        driver_id=selected_driver_id,
        target=target,
        selected_move_request_id=None,
    )
    request_log_ids = [req.linked_driver_log_id for req in requests if req.linked_driver_log_id]
    damaged_log_ids = _damage_log_ids(request_log_ids)
    issue_request_ids = _open_issue_request_ids(requests)
    moves = [
        _move_view_model(req, damaged_log_ids=damaged_log_ids, issue_request_ids=issue_request_ids, role="manager")
        for req in requests
    ]

    stops = []
    route_contexts = []
    for driver_id in driver_ids:
        route_context = build_route_context(driver_id=driver_id, route_date=target)
        route_contexts.append(route_context)
        stops.extend(_build_stops(route_context, role="manager", move_requests=requests))

    transfers = _transfers_for_view(driver_id=selected_driver_id, target=target)
    plants, lanes = _build_plants_and_lanes(stops, moves, transfers, role="manager")

    selected_driver = User.query.get(selected_driver_id) if selected_driver_id else None
    primary_context = route_contexts[0] if len(route_contexts) == 1 else None
    if primary_context:
        route = _route_summary(primary_context, moves=moves, stops=stops, driver=selected_driver)
    else:
        active_count = len([stop for stop in stops if stop["status"] in {"active", "needs_review", "blocked"}])
        issue_count = len([s for s in stops if s["has_issue"] or s["has_damage"]]) + len([m for m in moves if m["has_issue"] or m["has_damage"]])
        route = {
            "route_id": None,
            "driver_name": f"{len(driver_ids)} driver{'s' if len(driver_ids) != 1 else ''}" if driver_ids else NOT_TRACKED,
            "truck": NOT_TRACKED,
            "equipment": NOT_TRACKED,
            "status": "active" if active_count or moves else "no_route",
            "current_stop_id": next((stop["stop_id"] for stop in stops if stop["status"] == "active"), None),
            "current_location": next((stop["plant_name"] for stop in stops if stop["status"] == "active"), SAFE_EMPTY),
            "next_action": "Review issue" if issue_count else ("Assign driver" if moves else "No action needed"),
            "issue_summary": f"{issue_count} issue{'s' if issue_count != 1 else ''}" if issue_count else "No open issues",
            "document_summary": "Documents current",
        }

    return {
        "route": route,
        "stops": stops,
        "moves": moves,
        "plants": plants,
        "lanes": lanes,
        "selected": {
            "selected_stop_id": None,
            "selected_plant": selected_plant,
            "selected_move_request_id": None,
        },
        "empty_states": _empty_states(route, stops, moves, lanes),
    }
