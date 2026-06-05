from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app.blueprints.manager import bp
from app.extensions import db
from app.forms.move_request import MoveRequestForm
from app.models import ActivityEvent, DriverLog, ExternalDocument, MoveRequest, PlantTransfer, User
from app.services.activity import record_activity
from app.services.audit import model_snapshot, record_audit_event
from app.services.document_numbers import move_request_number
from app.services.flow_events import FlowEventService
from app.services.move_request_parser import parse_move_request_text
from app.services.plant_addresses import plant_label as _plant_label


MOVE_REQUEST_AUDIT_FIELDS = [
    "request_number",
    "source",
    "raw_text",
    "requested_by",
    "requested_at",
    "request_type",
    "priority",
    "origin_location_text",
    "destination_location_text",
    "cargo_text",
    "part_number",
    "quantity_value",
    "quantity_unit",
    "quantity_text",
    "due_at",
    "due_time_text",
    "notes",
    "status",
    "blocked_reason",
    "closed_reason",
    "assigned_driver_id",
    "assigned_driver_text",
    "equipment_id",
    "equipment_text",
    "linked_driver_log_id",
    "linked_route_id",
    "linked_plant_transfer_id",
    "linked_document_id",
    "parsed_confidence",
    "parse_warnings",
]

CLOSED_MOVE_REQUEST_STATUSES = {"completed", "cancelled"}
MOVE_REQUEST_LIFECYCLE_TRANSITIONS = {
    "assign": {
        "open": "assigned",
        "assigned": "assigned",
        "blocked": "assigned",
        "acknowledged": "acknowledged",
        "in_progress": "in_progress",
        "waiting": "waiting",
        "active": "active",
        "needs_review": "needs_review",
    },
    "acknowledge": {
        "open": "open",
        "assigned": "assigned",
        "blocked": "blocked",
        "acknowledged": "acknowledged",
        "in_progress": "in_progress",
        "waiting": "waiting",
        "active": "active",
        "needs_review": "needs_review",
    },
    "block": {
        "open": "blocked",
        "assigned": "blocked",
        "blocked": "blocked",
        "acknowledged": "blocked",
        "in_progress": "blocked",
        "waiting": "blocked",
        "active": "blocked",
        "needs_review": "blocked",
    },
    "complete": {
        "open": "completed",
        "assigned": "completed",
        "blocked": "completed",
        "acknowledged": "completed",
        "in_progress": "completed",
        "waiting": "completed",
        "active": "completed",
        "needs_review": "completed",
    },
    "cancel": {
        "open": "cancelled",
        "assigned": "cancelled",
        "blocked": "cancelled",
        "acknowledged": "cancelled",
        "in_progress": "cancelled",
        "waiting": "cancelled",
        "active": "cancelled",
        "needs_review": "cancelled",
    },
}
MOVE_REQUEST_LIFECYCLE_LABELS = {
    "assign": "assign this request",
    "acknowledge": "acknowledge this request",
    "block": "mark this request blocked",
    "complete": "mark this request completed",
    "cancel": "cancel this request",
}


def _clean_text(value):
    text = (value or "").strip()
    return text or None


def _zero_to_none(value):
    return value or None


def _normalized_status(value):
    return (value or "open").strip().lower()


def _move_request_lifecycle_target(move_request, action):
    status = _normalized_status(move_request.status)
    if status in CLOSED_MOVE_REQUEST_STATUSES:
        label = MOVE_REQUEST_LIFECYCLE_LABELS.get(action, "change this request")
        flash(
            f"{move_request.display_number} is {status.replace('_', ' ')} and cannot {label} without a correction/reopen action.",
            "danger",
        )
        return None
    target_status = MOVE_REQUEST_LIFECYCLE_TRANSITIONS.get(action, {}).get(status)
    if target_status is None:
        label = MOVE_REQUEST_LIFECYCLE_LABELS.get(action, "change this request")
        flash(f"{move_request.display_number} cannot {label} from {status.replace('_', ' ')}.", "danger")
        return None
    return target_status


def _require_lifecycle_reason(field_name, value):
    reason = _clean_text(value)
    if reason:
        return reason
    label = "Blocked reason" if field_name == "blocked_reason" else "Closed / cancel reason"
    flash(f"{label} is required for this move-request action.", "danger")
    return None


def _driver_choices():
    drivers = User.query.filter_by(role="driver").order_by(User.last_name, User.first_name, User.username).all()
    return drivers, [(0, "Unassigned")] + [(driver.id, driver.manager_label) for driver in drivers]


def _driver_log_choices():
    logs = DriverLog.query.order_by(DriverLog.created_at.desc()).limit(100).all()
    choices = [(0, "No linked driver log")]
    for log in logs:
        driver = log.driver.display_name if log.driver else f"Driver {log.driver_id}"
        plant = _plant_label(log.plant_name)
        choices.append((log.id, f"Log #{log.id} / {log.date} / {driver} / {plant}"))
    return choices


def _plant_transfer_choices():
    transfers = (
        PlantTransfer.query.filter(PlantTransfer.deleted_at.is_(None))
        .order_by(PlantTransfer.created_at.desc())
        .limit(100)
        .all()
    )
    choices = [(0, "No linked plant transfer")]
    for transfer in transfers:
        transfer_no = transfer.transfer_number or transfer.id
        choices.append((transfer.id, f"Transfer {transfer_no} / {transfer.ship_from} to {transfer.ship_to}"))
    return choices


def _prepare_form_choices(form):
    drivers, driver_choices = _driver_choices()
    form.assigned_driver_id.choices = driver_choices
    form.linked_driver_log_id.choices = _driver_log_choices()
    form.linked_plant_transfer_id.choices = _plant_transfer_choices()
    if form.assigned_driver_id.data is None:
        form.assigned_driver_id.data = 0
    if form.linked_driver_log_id.data is None:
        form.linked_driver_log_id.data = 0
    if form.linked_plant_transfer_id.data is None:
        form.linked_plant_transfer_id.data = 0
    return drivers


def _latest_move_request_events(move_requests, action):
    request_ids = [move_request.id for move_request in move_requests]
    if not request_ids:
        return {}
    events = (
        ActivityEvent.query.filter(
            ActivityEvent.target_type == "move_request",
            ActivityEvent.action == action,
            ActivityEvent.target_id.in_(request_ids),
        )
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .all()
    )
    latest = {}
    for event in events:
        latest.setdefault(event.target_id, event)
    return latest


def _apply_suggestions(form, parse_result):
    for field_name, value in parse_result.get("suggestions", {}).items():
        if hasattr(form, field_name):
            getattr(form, field_name).data = value
    form.parsed_confidence.data = parse_result.get("confidence") or ""
    form.parse_warnings.data = "\n".join(parse_result.get("warnings") or [])


def _set_move_request_fields(move_request, form):
    move_request.source = form.source.data
    move_request.raw_text = form.raw_text.data.strip()
    move_request.requested_by = _clean_text(form.requested_by.data)
    move_request.requested_at = form.requested_at.data or datetime.utcnow()
    move_request.request_type = form.request_type.data
    move_request.priority = form.priority.data
    move_request.origin_location_text = _clean_text(form.origin_location_text.data)
    move_request.destination_location_text = _clean_text(form.destination_location_text.data)
    move_request.cargo_text = _clean_text(form.cargo_text.data)
    move_request.part_number = _clean_text(form.part_number.data)
    move_request.quantity_value = form.quantity_value.data
    move_request.quantity_unit = _clean_text(form.quantity_unit.data)
    move_request.quantity_text = _clean_text(form.quantity_text.data)
    move_request.due_at = form.due_at.data
    move_request.due_time_text = _clean_text(form.due_time_text.data)
    move_request.notes = _clean_text(form.notes.data)
    move_request.status = form.status.data
    move_request.blocked_reason = _clean_text(form.blocked_reason.data)
    move_request.closed_reason = _clean_text(form.closed_reason.data)
    move_request.assigned_driver_id = _zero_to_none(form.assigned_driver_id.data)
    move_request.assigned_driver_text = _clean_text(form.assigned_driver_text.data)
    move_request.equipment_id = _clean_text(form.equipment_id.data)
    move_request.equipment_text = _clean_text(form.equipment_text.data)
    move_request.linked_driver_log_id = _zero_to_none(form.linked_driver_log_id.data)
    move_request.linked_route_id = _clean_text(form.linked_route_id.data)
    move_request.linked_plant_transfer_id = _zero_to_none(form.linked_plant_transfer_id.data)
    move_request.linked_document_id = form.linked_document_id.data
    move_request.parsed_confidence = _clean_text(form.parsed_confidence.data)
    move_request.parse_warnings = _clean_text(form.parse_warnings.data)
    move_request.updated_by_id = current_user.id


def _record_move_request_activity(move_request, *, action, title, details, before_values):
    after_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    record_audit_event(
        user_id=current_user.id,
        target_type="move_request",
        target_id=move_request.id,
        action=action,
        reason=details,
        before_values=before_values,
        after_values=after_values,
        commit=False,
    )
    record_activity(
        user_id=current_user.id,
        category="move_request",
        action=action,
        title=title,
        details=details,
        target_type="move_request",
        target_id=move_request.id,
        commit=False,
    )


def _append_move_request_flow_event(move_request, event_type, *, notes=None, payload=None):
    FlowEventService.append_event(
        event_type=event_type,
        entity_type="move_request",
        entity_id=move_request.id,
        route_id=move_request.linked_route_id,
        stop_id=move_request.linked_driver_log_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        origin_node_id=move_request.origin_location_text,
        destination_node_id=move_request.destination_location_text,
        source="admin",
        payload_json={
            "request_number": move_request.request_number,
            "legacy_status_projection": move_request.status,
            "priority": move_request.priority,
            "cargo_text": move_request.cargo_text,
            "quantity_value": move_request.quantity_value,
            "quantity_unit": move_request.quantity_unit,
            **(payload or {}),
        },
        notes=notes,
        document_id=move_request.linked_document_id,
        commit=False,
    )


def _move_status_event_type(status):
    status = (status or "open").lower()
    if status in {"assigned", "acknowledged", "waiting"}:
        return "STAGED"
    if status in {"in_progress", "active"}:
        return "ASSIGNED_TO_TRAILER"
    if status in {"completed"}:
        return "RECONCILED"
    if status in {"blocked", "needs_review"}:
        return "DELAY_REPORTED"
    if status in {"cancelled"}:
        return "MANAGER_REJECTED"
    return "WIP_STARTED"


def _request_or_404(request_id):
    return MoveRequest.query.get_or_404(request_id)


@bp.route("/move-requests")
def move_requests():
    selected_status = request.args.get("status", "active")
    location_filter = (request.args.get("location") or request.args.get("plant") or "").strip()
    origin_filter = (request.args.get("origin") or "").strip()
    destination_filter = (request.args.get("destination") or "").strip()
    query = MoveRequest.query
    if selected_status == "active":
        query = query.filter(MoveRequest.status.notin_(["completed", "cancelled"]))
    elif selected_status != "all":
        query = query.filter_by(status=selected_status)
    if location_filter:
        like = f"%{location_filter}%"
        query = query.filter(
            or_(
                MoveRequest.origin_location_text.ilike(like),
                MoveRequest.destination_location_text.ilike(like),
            )
        )
    if origin_filter:
        query = query.filter(MoveRequest.origin_location_text.ilike(f"%{origin_filter}%"))
    if destination_filter:
        query = query.filter(MoveRequest.destination_location_text.ilike(f"%{destination_filter}%"))
    requests = query.order_by(MoveRequest.requested_at.desc(), MoveRequest.id.desc()).all()
    drivers, _ = _driver_choices()
    return render_template(
        "manager/move_requests.html",
        move_requests=requests,
        drivers=drivers,
        acknowledgements=_latest_move_request_events(requests, "acknowledged"),
        plant_transfer_choices=_plant_transfer_choices(),
        selected_status=selected_status,
        location_filter=location_filter,
        origin_filter=origin_filter,
        destination_filter=destination_filter,
    )


@bp.route("/move-requests/parse", methods=["POST"])
def parse_move_request():
    raw_text = request.form.get("raw_text") if request.form else None
    if request.is_json:
        raw_text = (request.get_json(silent=True) or {}).get("raw_text")
    return jsonify(parse_move_request_text(raw_text))


@bp.route("/move-requests/new", methods=["GET", "POST"])
def new_move_request():
    form = MoveRequestForm()
    _prepare_form_choices(form)
    parse_result = None

    if request.method == "POST" and request.form.get("form_action") == "parse":
        parse_result = parse_move_request_text(form.raw_text.data)
        _apply_suggestions(form, parse_result)
    elif form.validate_on_submit():
        move_request = MoveRequest(created_by_id=current_user.id)
        _set_move_request_fields(move_request, form)
        db.session.add(move_request)
        db.session.flush()
        move_request.request_number = move_request_number(move_request)
        _record_move_request_activity(
            move_request,
            action="created",
            title="Move request created",
            details=f"Created {move_request.display_number}.",
            before_values={},
        )
        _append_move_request_flow_event(
            move_request,
            _move_status_event_type(move_request.status),
            notes=f"Created {move_request.display_number}.",
        )
        db.session.commit()
        flash("Move request created.", "success")
        return redirect(url_for("manager.move_requests"))

    return render_template(
        "manager/move_request_form.html",
        form=form,
        move_request=None,
        parse_result=parse_result,
    )


@bp.route("/move-requests/<int:request_id>/edit", methods=["GET", "POST"])
def edit_move_request(request_id):
    move_request = _request_or_404(request_id)
    form = MoveRequestForm(obj=move_request if request.method == "GET" else None)
    _prepare_form_choices(form)
    parse_result = None

    if request.method == "POST" and request.form.get("form_action") == "parse":
        parse_result = parse_move_request_text(form.raw_text.data)
        _apply_suggestions(form, parse_result)
    elif form.validate_on_submit():
        before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
        _set_move_request_fields(move_request, form)
        _record_move_request_activity(
            move_request,
            action="updated",
            title="Move request updated",
            details=f"Updated {move_request.display_number}.",
            before_values=before_values,
        )
        before_status = before_values.get("status")
        if before_status != move_request.status:
            _append_move_request_flow_event(
                move_request,
                _move_status_event_type(move_request.status),
                notes=f"Updated {move_request.display_number} status from {before_status or 'unknown'} to {move_request.status}.",
                payload={"previous_legacy_status_projection": before_status},
            )
        db.session.commit()
        flash("Move request updated.", "success")
        return redirect(url_for("manager.move_requests"))

    return render_template(
        "manager/move_request_form.html",
        form=form,
        move_request=move_request,
        parse_result=parse_result,
    )


@bp.route("/move-requests/<int:request_id>/assign", methods=["POST"])
def assign_move_request(request_id):
    move_request = _request_or_404(request_id)
    target_status = _move_request_lifecycle_target(move_request, "assign")
    if target_status is None:
        return redirect(url_for("manager.move_requests"))
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    driver_id = request.form.get("assigned_driver_id", type=int) or None
    move_request.assigned_driver_id = driver_id
    move_request.assigned_driver_text = _clean_text(request.form.get("assigned_driver_text"))
    move_request.equipment_id = _clean_text(request.form.get("equipment_id"))
    move_request.equipment_text = _clean_text(request.form.get("equipment_text"))
    move_request.status = target_status
    move_request.updated_by_id = current_user.id
    _record_move_request_activity(
        move_request,
        action="assigned",
        title="Move request assigned",
        details=f"Assigned {move_request.display_number}.",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "STAGED",
        notes=f"Assigned {move_request.display_number}.",
        payload={"assigned_driver_id": move_request.assigned_driver_id, "equipment_id": move_request.equipment_id},
    )
    db.session.commit()
    flash("Move request assigned.", "success")
    return redirect(url_for("manager.move_requests"))


@bp.route("/move-requests/<int:request_id>/acknowledge", methods=["POST"])
def acknowledge_move_request(request_id):
    move_request = _request_or_404(request_id)
    target_status = _move_request_lifecycle_target(move_request, "acknowledge")
    if target_status is None:
        return redirect(url_for("manager.move_requests"))
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    acknowledged_by_text = _clean_text(request.form.get("acknowledged_by_text")) or current_user.display_name
    move_request.status = target_status
    move_request.updated_by_id = current_user.id
    _record_move_request_activity(
        move_request,
        action="acknowledged",
        title="Move request acknowledged",
        details=f"Acknowledged {move_request.display_number} by {acknowledged_by_text}.",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "MANAGER_APPROVED",
        notes=f"Acknowledged {move_request.display_number} by {acknowledged_by_text}.",
        payload={"acknowledged_by_text": acknowledged_by_text},
    )
    db.session.commit()
    flash("Move request acknowledged.", "success")
    return redirect(url_for("manager.move_requests"))


@bp.route("/move-requests/<int:request_id>/link-evidence", methods=["POST"])
def link_move_request_evidence(request_id):
    move_request = _request_or_404(request_id)
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    plant_transfer_id = request.form.get("linked_plant_transfer_id", type=int) or None
    linked_document_id = request.form.get("linked_document_id", type=int) or None

    transfer = None
    if plant_transfer_id:
        transfer = (
            PlantTransfer.query.filter(
                PlantTransfer.deleted_at.is_(None),
                PlantTransfer.id == plant_transfer_id,
            )
            .first()
        )
        if not transfer:
            flash("Selected plant transfer was not found.", "danger")
            return redirect(url_for("manager.move_requests"))

    document = None
    if linked_document_id:
        document = ExternalDocument.query.get(linked_document_id)
        if not document:
            flash("Selected document was not found.", "danger")
            return redirect(url_for("manager.move_requests"))

    move_request.linked_plant_transfer_id = plant_transfer_id
    move_request.linked_document_id = linked_document_id
    move_request.updated_by_id = current_user.id

    linked_labels = []
    if transfer:
        linked_labels.append(f"Plant Transfer {transfer.transfer_number or transfer.id}")
    if document:
        linked_labels.append(f"Document #{document.id}")
    if not linked_labels:
        linked_labels.append("No linked evidence")

    _record_move_request_activity(
        move_request,
        action="evidence_linked",
        title="Move request evidence linked",
        details=f"Linked evidence for {move_request.display_number}: {', '.join(linked_labels)}.",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "PROOF_ATTACHED" if (transfer or document) else "MANAGER_REJECTED",
        notes=f"Linked evidence for {move_request.display_number}: {', '.join(linked_labels)}.",
        payload={"linked_plant_transfer_id": plant_transfer_id, "linked_document_id": linked_document_id},
    )
    db.session.commit()
    flash("Move request evidence link updated.", "success")
    return redirect(url_for("manager.move_requests"))


@bp.route("/move-requests/<int:request_id>/mark-blocked", methods=["POST"])
def mark_move_request_blocked(request_id):
    move_request = _request_or_404(request_id)
    target_status = _move_request_lifecycle_target(move_request, "block")
    if target_status is None:
        return redirect(url_for("manager.move_requests"))
    blocked_reason = _require_lifecycle_reason("blocked_reason", request.form.get("blocked_reason"))
    if blocked_reason is None:
        return redirect(url_for("manager.move_requests"))
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    move_request.status = target_status
    move_request.blocked_reason = blocked_reason
    move_request.updated_by_id = current_user.id
    _record_move_request_activity(
        move_request,
        action="blocked",
        title="Move request blocked",
        details=f"Blocked {move_request.display_number}: {move_request.blocked_reason}",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "DELAY_REPORTED",
        notes=move_request.blocked_reason,
        payload={"blocked_reason": move_request.blocked_reason},
    )
    db.session.commit()
    flash("Move request marked blocked.", "warning")
    return redirect(url_for("manager.move_requests"))


@bp.route("/move-requests/<int:request_id>/mark-completed", methods=["POST"])
def mark_move_request_completed(request_id):
    move_request = _request_or_404(request_id)
    target_status = _move_request_lifecycle_target(move_request, "complete")
    if target_status is None:
        return redirect(url_for("manager.move_requests"))
    closed_reason = _require_lifecycle_reason("closed_reason", request.form.get("closed_reason"))
    if closed_reason is None:
        return redirect(url_for("manager.move_requests"))
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    move_request.status = target_status
    move_request.closed_reason = closed_reason
    move_request.updated_by_id = current_user.id
    _record_move_request_activity(
        move_request,
        action="completed",
        title="Move request completed",
        details=f"Completed {move_request.display_number}: {move_request.closed_reason}",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "RECONCILED",
        notes=move_request.closed_reason,
        payload={"closed_reason": move_request.closed_reason},
    )
    db.session.commit()
    flash("Move request marked completed.", "success")
    return redirect(url_for("manager.move_requests"))


@bp.route("/move-requests/<int:request_id>/cancel", methods=["POST"])
def cancel_move_request(request_id):
    move_request = _request_or_404(request_id)
    target_status = _move_request_lifecycle_target(move_request, "cancel")
    if target_status is None:
        return redirect(url_for("manager.move_requests"))
    closed_reason = _require_lifecycle_reason("closed_reason", request.form.get("closed_reason"))
    if closed_reason is None:
        return redirect(url_for("manager.move_requests"))
    before_values = model_snapshot(move_request, MOVE_REQUEST_AUDIT_FIELDS)
    move_request.status = target_status
    move_request.closed_reason = closed_reason
    move_request.updated_by_id = current_user.id
    _record_move_request_activity(
        move_request,
        action="cancelled",
        title="Move request cancelled",
        details=f"Cancelled {move_request.display_number}: {move_request.closed_reason}",
        before_values=before_values,
    )
    _append_move_request_flow_event(
        move_request,
        "MANAGER_REJECTED",
        notes=move_request.closed_reason,
        payload={"closed_reason": move_request.closed_reason},
    )
    db.session.commit()
    flash("Move request cancelled.", "warning")
    return redirect(url_for("manager.move_requests"))
