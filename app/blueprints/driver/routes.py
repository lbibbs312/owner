"""Driver-facing routes.

Holds the routes a driver hits during a shift: dashboard, pre-trip / post-trip
inspections, driver logs, shift start/end, end-of-day. Currently only the
pre-trip / post-trip family lives here; the rest will move in subsequent sub-
PRs of PR-5c.
"""
from datetime import datetime, date
from functools import wraps
import os
from uuid import uuid4

import pytz
from flask import abort, current_app, flash, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_
from werkzeug.utils import secure_filename

from app.blueprints.driver import bp
from app.extensions import db
from app.extensions import socketio
from app.forms.damage import DamageReportForm
from app.forms.log import DepartForm, DriverLogForm, TRUCK_ISSUE_CHOICES, TRUCK_ISSUE_LABELS
from app.forms.plant_transfer import PlantTransferForm
from app.forms.messaging import DirectMessageForm
from app.forms.shift import EndOfDayForm
from app.forms.trip import PostTripForm, PreTripForm
from app.forms.user import ProfileForm
from app.services.activity import record_activity
from app.services.audit import model_snapshot, record_audit_event
from app.services.evidence_packet import build_damage_evidence_packet
from app.services.document_numbers import (
    document_meta,
    eod_document_number,
    evidence_document_number,
    generated_at_label,
    pretrip_document_number,
    route_document_number,
    transfer_document_number,
)
from app.services.driver_wait import elapsed_wait_minutes, elapsed_wait_seconds, wait_label_for_log
from app.services.simple_pdf import LANDSCAPE_LETTER, LETTER, SimplePdf
from app.services.load_state import (
    MIN_PLANT_TRANSFER_MINUTES,
    SECONDARY_NOT_DROPPED_PREFIX,
    SECONDARY_NOT_DROPPED_PREFIXES,
    TRUCK_ISSUE_PREFIX,
    UNLOAD_NOT_COMPLETED_PREFIX,
    build_driver_log_route_context,
    cargo_display,
    current_load_after_logs,
    destination_from_load,
    destination_load_value,
    is_service_stop,
    is_load_for_plant,
    load_display,
    load_type_from_load,
    route_problem_reason,
    secondary_load_value,
    service_stop_label,
    truck_issue_reason,
)
from app.services.parts import record_part_scan as save_part_scan, scan_event_payload
from app.services.next_load_prediction import build_next_load_prediction
from app.services.route_context import build_route_context
from app.services.plant_time import forecast_for_stop, plant_time_forecast, route_stop_forecasts
from app.services.report_summary import damage_report_count_label, damage_report_detail_label
from app.services.hot_parts import (
    build_hot_part_proof,
    ensure_hot_move_for_task,
    hot_part_event_payload,
    record_hot_part_event,
    save_hot_part_photo,
)
from app.services.plant_addresses import PLANT_LABELS, plant_label as _plant_label
from app.services.role_session import restore_role_user
from app.services.search_corpus import ingest_driver_log
from app.models import (
    ActivityEvent,
    DamagePhoto,
    DamageReport,
    DirectMessage,
    HotMove,
    PartScanEvent,
    DriverLog,
    DriverLogPhoto,
    DraftEntry,
    PlantTransfer,
    PlantTransferLine,
    PostTrip,
    PreTrip,
    ShiftRecord,
    Task,
    User,
)


PLANT_TRANSFER_LINE_COUNT = 20
DRIVER_LOG_AUDIT_FIELDS = ["plant_name", "load_size", "depart_load_size", "secondary_load", "downtime_reason", "part_number", "hot_parts", "arrive_time", "depart_time", "dock_wait_minutes", "maintenance", "fuel", "fuel_mileage", "meeting"]
PLANT_TRANSFER_AUDIT_FIELDS = ["transfer_number", "transfer_date", "ship_to", "ship_from", "trailer_number", "driver_name", "driver_initials", "transfer_time", "loaded_by"]
RYDER_CLOSING_ACTIONS = {"fixed", "left", "rental"}


def _first_record_id(records):
    return records[0].id if records else None


def _truck_from_pretrips(pretrips):
    first = pretrips[0] if pretrips else None
    return first.truck_number if first else None


def _pretrip_document_meta(pretrip, page="1 of 1"):
    return document_meta("DAILY VEHICLE INSPECTION REPORT", pretrip_document_number(pretrip), page=page)


def _route_document_meta(route_date, driver, logs, pretrips, page="1 of 1"):
    return document_meta(
        "DRIVER ROUTE AUDIT SHEET",
        route_document_number(route_date, driver=driver, truck=_truck_from_pretrips(pretrips), route_id=_first_record_id(logs)),
        page=page,
    )


def _eod_document_meta(route_date, driver, logs, page="1 of 1"):
    return document_meta(
        "END OF DAY ROUTE RECORD",
        eod_document_number(route_date, driver=driver, route_id=_first_record_id(logs)),
        page=page,
    )


def _transfer_document_meta(transfer, page="1 of 1"):
    return document_meta("PLANT TRANSFER", transfer_document_number(transfer), page=page)


def _evidence_document_meta(report, page="1 of 1"):
    return document_meta("DAMAGE EVIDENCE PACKET", evidence_document_number(report), page=page)


def _draw_pdf_header(pdf, title, document_no, generated_at, page_label, *, driver=None, truck=None, date_value=None):
    pdf.text(36, 764, title, size=12, bold=True)
    pdf.text(36, 748, f"Document No: {document_no}", size=8, bold=True)
    pdf.text(260, 748, f"Generated: {generated_at}", size=8)
    pdf.text(500, 748, f"Page {page_label}", size=8)
    meta = []
    if driver:
        meta.append(f"Driver: {driver}")
    if truck:
        meta.append(f"Truck: {truck}")
    if date_value:
        meta.append(f"Date: {date_value}")
    if meta:
        pdf.text(36, 734, " | ".join(meta), size=8)
    pdf.line(36, 726, 576, 726, width=0.8)

RYDER_OUTCOME_LABELS = {
    "headed": "Headed to Ryder",
    "fixed": "Fixed at Ryder",
    "left": "Left at Ryder",
    "rental": "Rental picked up",
}


def _driver_route_guard(target_endpoint, page_label, retry_label="the mobile dashboard"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            try:
                return view_func(*args, **kwargs)
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Driver route failed: %s", request.path)
                flash(
                    f"We could not open {page_label}. Nothing was changed. Try again from {retry_label}.",
                    "danger",
                )
                return redirect(url_for(target_endpoint))
        return wrapped
    return decorator

DRIVER_ONLY_ENDPOINTS = {
    "dashboard",
    "mobile_dashboard",
    "mobile_ryder_service",
    "mobile_history",
    "mobile_day_report",
    "truck_maintenance_history",
    "list_pretrips",
    "new_pretrip",
    "do_posttrip",
    "view_pretrip",
    "edit_pretrip_entry",
    "delete_pretrip",
    "pretrip_printable",
    "pretrip_attachment",
    "mark_pretrip_printed",
    "plant_transfers",
    "new_plant_transfer",
    "view_plant_transfer",
    "edit_plant_transfer",
    "delete_plant_transfer",
    "plant_transfer_printable",
    "plant_transfer_attachment",
    "mark_plant_transfer_printed",
    "driver_logs",
    "new_driving_log",
    "add_stop",
    "edit_driver_log",
    "delete_driver_log",
    "clear_driver_log_hot_part",
    "depart_driver_log",
    "record_part_scan",
    "record_driver_log_photo",
    "driver_log_photo",
    "delete_driver_log_photo",
    "pickup_driver_log",
    "no_pickup_driver_log",
    "view_driver_log",
    "driver_logs_print",
    "driver_logs_attachment",
    "start_shift",
    "end_shift",
    "end_of_day_summary",
    "end_of_day_print",
    "end_of_day_attachment",
    "submit_end_of_day",
    "profile",
    "list_tasks",
    "view_task",
    "accept_task",
    "decline_task",
    "complete_task",
    "show_map",
    "damage_reports",
    "new_damage_report",
    "view_damage_report",
    "damage_photo",
    "record_hot_part_photo",
    "record_hot_part_proof",
    "edit_damage_report",
    "delete_damage_report",
    "submit_damage_report",
    "damage_evidence_packet",
}


def _requested_url():
    return request.full_path if request.query_string else request.path


@bp.before_request
def require_driver_role_for_driver_actions():
    endpoint = (request.endpoint or "").removeprefix("driver.")
    if endpoint not in DRIVER_ONLY_ENDPOINTS:
        return None
    if restore_role_user("driver"):
        return None
    flash("Driver credentials required.", "warning")
    return redirect(
        url_for("auth.login", next=_requested_url(), required_role="driver")
    )


def _today_local_date():
    return datetime.now(pytz.timezone("America/Detroit")).date()


def _selected_log_date_from_request():
    date_str = request.args.get("date")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    return _today_local_date()


def _can_driver_change_same_day(record_user_id, record_date, record_label, action):
    if current_user.role != "driver":
        flash("Driver credentials required.", "warning")
        return False
    if record_user_id != current_user.id:
        flash(f"Not authorized to {action} another driver's {record_label}.", "danger")
        return False
    if record_date != _today_local_date():
        flash(f"Only same-day {record_label} entries can be {action}d.", "warning")
        return False
    return True


def _driver_log_sort_key(log):
    return (log.date or date.min, log.arrive_time or "", log.created_at or datetime.min, log.id or 0)


def _driver_log_route_context(logs):
    return build_driver_log_route_context(logs)


def _active_driver_logs_query():
    return DriverLog.query.filter(DriverLog.deleted_at.is_(None))


def _current_driver_load(driver_id, route_date=None):
    route_date = route_date or _today_local_date()
    route_finalized = ActivityEvent.query.filter_by(
        user_id=driver_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(route_date))).first()
    if route_finalized:
        return current_load_after_logs([])
    logs = _active_driver_logs_query().filter_by(driver_id=driver_id, date=route_date).all()
    return current_load_after_logs(logs)


def _sync_next_open_stop_arrival_cargo(log):
    if not log or not log.driver_id or not log.date:
        return None
    logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=log.driver_id, date=log.date).all(),
        key=_driver_log_sort_key,
    )
    current_index = next((index for index, item in enumerate(logs) if item.id == log.id), None)
    if current_index is None or current_index + 1 >= len(logs):
        return None
    changed = []
    for next_index in range(current_index + 1, len(logs)):
        next_log = logs[next_index]
        if next_log.depart_time:
            continue
        expected = current_load_after_logs(logs[:next_index])
        expected_primary = expected.get("value") or "Empty"
        expected_secondary = expected.get("secondary_value") or None
        if next_log.load_size == expected_primary and (next_log.secondary_load or None) == expected_secondary:
            continue
        next_log.load_size = expected_primary
        next_log.secondary_load = expected_secondary
        changed.append(next_log)
    return changed[-1] if changed else None


def _driver_log_context_for(log):
    logs = _active_driver_logs_query().filter_by(
        driver_id=log.driver_id, date=log.date
    ).all()
    return _driver_log_route_context(logs).get(log.id, {})


def _active_pretrips_query():
    return PreTrip.query.filter(PreTrip.deleted_at.is_(None))


def _active_plant_transfers_query():
    return PlantTransfer.query.filter(PlantTransfer.deleted_at.is_(None))


def _open_shift_for_driver(driver_id):
    return (
        ShiftRecord.query.filter_by(user_id=driver_id, end_time=None)
        .order_by(ShiftRecord.start_time.desc())
        .first()
    )


def _shift_route_date(shift):
    if not shift:
        return None
    if shift.pretrip and shift.pretrip.pretrip_date:
        return shift.pretrip.pretrip_date
    if not shift.start_time:
        return None
    start_time = shift.start_time
    if start_time.tzinfo is None:
        start_time = pytz.utc.localize(start_time)
    return start_time.astimezone(pytz.timezone("America/Detroit")).date()


def _latest_open_pretrip(driver_id):
    pretrips = (
        _active_pretrips_query()
        .filter_by(user_id=driver_id)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .limit(20)
        .all()
    )
    return next((pretrip for pretrip in pretrips if not pretrip.posttrip), None)


def _active_route_date_for_driver(driver_id, today_local_date=None, open_shift=None):
    today_local_date = today_local_date or _today_local_date()
    open_shift = open_shift if open_shift is not None else _open_shift_for_driver(driver_id)
    shift_date = _shift_route_date(open_shift)
    if shift_date:
        return shift_date
    open_pretrip = _latest_open_pretrip(driver_id)
    if open_pretrip and open_pretrip.pretrip_date:
        return open_pretrip.pretrip_date
    return today_local_date


def _route_date_has_driver_records(driver_id, route_date):
    if not route_date:
        return False
    return any(
        [
            _active_driver_logs_query().filter_by(driver_id=driver_id, date=route_date).first(),
            _active_pretrips_query().filter_by(user_id=driver_id, pretrip_date=route_date).first(),
            _active_plant_transfers_query().filter_by(user_id=driver_id, transfer_date=route_date).first(),
        ]
    )


def _latest_driver_route_date(driver_id):
    latest_log = (
        _active_driver_logs_query()
        .with_entities(DriverLog.date)
        .filter_by(driver_id=driver_id)
        .order_by(DriverLog.date.desc(), DriverLog.id.desc())
        .first()
    )
    if latest_log and latest_log[0]:
        return latest_log[0]
    latest_pretrip = (
        _active_pretrips_query()
        .filter_by(user_id=driver_id)
        .order_by(PreTrip.pretrip_date.desc(), PreTrip.id.desc())
        .first()
    )
    if latest_pretrip and latest_pretrip.pretrip_date:
        return latest_pretrip.pretrip_date
    return None


def _dashboard_route_date_for_driver(driver_id, today_local_date=None, open_shift=None):
    today_local_date = today_local_date or _today_local_date()
    active_route_date = _active_route_date_for_driver(driver_id, today_local_date, open_shift)
    if open_shift or active_route_date != today_local_date:
        return active_route_date
    if _route_date_has_driver_records(driver_id, today_local_date):
        return today_local_date
    return _latest_driver_route_date(driver_id) or today_local_date


def _soft_delete_record(record):
    record.deleted_at = datetime.utcnow()
    record.deleted_by_id = current_user.id



def _active_driver_tasks_query():
    return Task.query.filter(
        Task.status.in_(["pending", "in-progress"]),
        (Task.assigned_to == current_user.id) | ((Task.assigned_to.is_(None)) & (Task.status == "pending")),
    )



def _task_sort_key(task):
    created = task.created_at or datetime.min
    return (
        task.status != "in-progress",
        task.assigned_to is None,
        not task.is_hot,
        -created.timestamp(),
    )


def _driver_task_query(driver_id):
    return Task.query.filter(
        Task.status.in_(["pending", "in-progress"]),
        or_(
            Task.assigned_to == driver_id,
            and_(Task.assigned_to.is_(None), Task.status == "pending"),
        ),
    )


def _driver_task_queue(driver_id):
    return sorted(_driver_task_query(driver_id).all(), key=_task_sort_key)


def _plant_code(value):
    wanted = (value or "").strip().lower()
    if not wanted:
        return ""
    for code, label in PLANT_LABELS.items():
        if wanted in {code.lower(), label.lower()}:
            return code
    return (value or "").strip()


def _task_route_codes(task):
    title = (task.title or "").strip()
    lowered = title.lower()
    marker = " to "
    split_at = lowered.find(marker)
    if split_at < 0:
        return "", ""
    return _plant_code(title[:split_at]), _plant_code(title[split_at + len(marker):])


def _task_part_label(task):
    return (task.part_number or task.title or f"Task {task.id}").strip()


def _task_matches_log(task, log):
    task_part = (task.part_number or "").strip().lower()
    log_part = (getattr(log, "part_number", None) or "").strip().lower()
    if task_part and log_part and task_part == log_part:
        return True

    origin, destination = _task_route_codes(task)
    plant = _plant_code(getattr(log, "plant_name", None))
    if not plant:
        return False
    if task.completed_at and destination and plant == destination:
        return True
    if task.accepted_at and origin and plant == origin:
        return True
    if task.status in {"pending", "in-progress"} and task.assigned_to == getattr(log, "driver_id", None):
        return plant in {origin, destination}
    return False


def _task_route_summary(task):
    if task.completed_at:
        status = "Unloaded"
    elif task.accepted_at or task.status == "in-progress":
        status = "Accepted"
    elif task.assigned_to:
        status = "Assigned"
    else:
        status = "Open"
    return {
        "id": task.id,
        "label": _task_part_label(task),
        "title": task.title,
        "is_hot": bool(task.is_hot),
        "kind_label": "Hot Part" if task.is_hot else "Part Move",
        "status": status,
        "accepted_at": task.accepted_at,
        "completed_at": task.completed_at,
    }


def _local_route_date_utc_bounds(route_date):
    local_tz = pytz.timezone("America/Detroit")
    start_local = local_tz.localize(datetime.combine(route_date, datetime.min.time()))
    end_local = local_tz.localize(datetime.combine(route_date, datetime.max.time()))
    return (
        start_local.astimezone(pytz.utc).replace(tzinfo=None),
        end_local.astimezone(pytz.utc).replace(tzinfo=None),
    )


def _driver_route_tasks(driver_id, route_date):
    day_start, day_end = _local_route_date_utc_bounds(route_date)
    return Task.query.filter(
        Task.status != "declined",
        or_(
            Task.assigned_to == driver_id,
            Task.accepted_by_id == driver_id,
            Task.completed_by_id == driver_id,
        ),
        or_(
            Task.status.in_(["pending", "in-progress"]),
            Task.created_at.between(day_start, day_end),
            Task.accepted_at.between(day_start, day_end),
            Task.completed_at.between(day_start, day_end),
        ),
    ).order_by(Task.created_at.desc()).all()


def _task_route_events_for_logs(logs, tasks=None):
    logs = list(logs or [])
    if not logs:
        return {}
    if tasks is None:
        grouped = {}
        for log in logs:
            grouped.setdefault((log.driver_id, log.date), None)
        tasks = []
        for driver_id, route_date in grouped:
            tasks.extend(_driver_route_tasks(driver_id, route_date))
    seen = set()
    unique_tasks = []
    for task in tasks:
        if task.id in seen:
            continue
        seen.add(task.id)
        unique_tasks.append(task)
    events = {log.id: [] for log in logs}
    for log in logs:
        for task in unique_tasks:
            if task.status == "declined":
                continue
            if _task_matches_log(task, log):
                events[log.id].append(_task_route_summary(task))
    return {log_id: items for log_id, items in events.items() if items}


def _next_load_eta_context(current_stop, current_stop_forecast, logs, route_date, now_local):
    if current_stop_forecast and current_stop_forecast.get("estimate_minutes") is not None:
        route = _driver_log_context_for(current_stop)
        label = current_stop_forecast.get("remaining_label") or current_stop_forecast.get("estimate_label")
        if current_stop.depart_time:
            label = current_stop_forecast.get("estimate_label")
        return {
            "plant": route.get("plant") or _plant_label(current_stop.plant_name),
            "estimate_label": label,
            "ready_at_label": current_stop_forecast.get("ready_at_label"),
            "status": current_stop_forecast.get("status"),
            "confidence": current_stop_forecast.get("confidence"),
        }

    latest_log = logs[-1] if logs else None
    if not latest_log:
        return None
    forecast = plant_time_forecast(latest_log.plant_name, anchor_date=route_date, now=now_local)
    if forecast.get("estimate_minutes") is None:
        return None
    route = _driver_log_context_for(latest_log)
    return {
        "plant": route.get("plant") or _plant_label(latest_log.plant_name),
        "estimate_label": forecast.get("estimate_label"),
        "ready_at_label": "",
        "status": None,
        "confidence": forecast.get("confidence"),
    }


def _current_driver_task():
    return (
        _active_driver_tasks_query()
        .order_by(Task.assigned_to.is_(None), Task.is_hot.desc(), Task.created_at.desc())
        .first()
    )


def _prefill_log_form_from_task(form, task=None):
    task = task or _current_driver_task()
    if not task:
        return
    if task.part_number and not form.part_number.data:
        form.part_number.data = task.part_number
    if task.is_hot:
        form.hot_parts.data = True


def _form_hot_part_number(form):
    if not form.hot_parts.data:
        return None
    return (form.part_number.data or "").strip() or None


def _form_truck_issue_text(form):
    if not form.maintenance.data:
        return ""
    return _truck_issue_text(form.truck_issue.data, form.truck_issue_notes.data)


def _apply_log_part_fields(log, form):
    log.hot_parts = bool(form.hot_parts.data)
    log.part_number = _form_hot_part_number(form)


def _form_mileage_value(form):
    return form.fuel_mileage.data if (form.fuel.data or form.maintenance.data) else None


def _local_dt_for_hhmm(log_date, hhmm):
    if not log_date or not hhmm:
        return None
    try:
        parsed_time = datetime.strptime(hhmm, "%H:%M").time()
    except ValueError:
        return None
    return pytz.timezone("America/Detroit").localize(datetime.combine(log_date, parsed_time))


def _arrival_local_dt_for_log(log):
    value = (getattr(log, "arrive_time", None) or "").strip()
    if not value:
        return None
    try:
        utc_dt = pytz.utc.localize(datetime.strptime(value, "%Y-%m-%d %H:%M:%S"))
        return utc_dt.astimezone(pytz.timezone("America/Detroit"))
    except ValueError:
        normalized = _normalize_hhmm_time(value)
        if normalized is None:
            return None
        return _local_dt_for_hhmm(log.date, normalized)


def _depart_local_dt_for_log(log):
    return _local_dt_for_hhmm(getattr(log, "date", None), _normalize_hhmm_time(getattr(log, "depart_time", "")))


def _arrival_hhmm_for_log(log):
    return _normalize_hhmm_time(_arrival_utc_to_local_hhmm(log.arrive_time))


def _open_stop_for_driver(driver_id, log_date, exclude_log_id=None):
    query = _active_driver_logs_query().filter_by(driver_id=driver_id, date=log_date).filter(DriverLog.depart_time.is_(None))
    if exclude_log_id:
        query = query.filter(DriverLog.id != exclude_log_id)
    return query.order_by(DriverLog.created_at.desc()).first()


def _route_timing_errors(driver_id, log_date, plant_name, arrive_time, depart_time=None, exclude_log_id=None, check_previous=True):
    errors = []
    arrive_dt = _local_dt_for_hhmm(log_date, arrive_time) if arrive_time else None
    depart_dt = _local_dt_for_hhmm(log_date, depart_time) if depart_time else None
    if arrive_dt and depart_dt and depart_dt < arrive_dt:
        errors.append("Depart time cannot be before arrival time.")

    logs = (
        _active_driver_logs_query()
        .filter_by(driver_id=driver_id, date=log_date)
        .filter(DriverLog.id != exclude_log_id)
        .all()
    )
    previous = None
    next_log = None
    if arrive_dt:
        departed_before = [(log, _depart_local_dt_for_log(log)) for log in logs]
        departed_before = [(log, dt) for log, dt in departed_before if dt and dt <= arrive_dt]
        if departed_before:
            previous = max(departed_before, key=lambda item: item[1])

    compare_start = depart_dt or arrive_dt
    if compare_start:
        next_candidates = [log for log in logs if not exclude_log_id or log.id > exclude_log_id]
        arrivals_after = [(log, _arrival_local_dt_for_log(log)) for log in next_candidates]
        arrivals_after = [(log, dt) for log, dt in arrivals_after if dt and dt > compare_start]
        if arrivals_after:
            next_log = min(arrivals_after, key=lambda item: item[1])

    if check_previous and previous and arrive_dt:
        previous_log, previous_depart = previous
        minutes = int((arrive_dt - previous_depart).total_seconds() // 60)
        if minutes < 0:
            errors.append(f"Arrival is before departure from {_plant_label(previous_log.plant_name)}.")
        elif previous_log.plant_name != plant_name and minutes < MIN_PLANT_TRANSFER_MINUTES:
            errors.append(f"Only {minutes} min from {_plant_label(previous_log.plant_name)} to {_plant_label(plant_name)}. Fix the time or insert the missing stop in order.")

    if next_log and compare_start:
        following_log, next_arrival = next_log
        minutes = int((next_arrival - compare_start).total_seconds() // 60)
        if minutes < 0:
            errors.append(f"Next stop at {_plant_label(following_log.plant_name)} arrives before this departure.")
        elif following_log.plant_name != plant_name and minutes < MIN_PLANT_TRANSFER_MINUTES:
            errors.append(f"Only {minutes} min from {_plant_label(plant_name)} to {_plant_label(following_log.plant_name)}. Fix the time or insert the missing stop in order.")
    return errors


def _get_plant_transfer_or_redirect(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    if current_user.role == "driver" and transfer.user_id != current_user.id:
        flash("Not authorized to access that Plant Transfer.", "danger")
        return None
    return transfer


def _plant_transfer_line_from_request(index):
    part_number = request.form.get(f"part_number_{index}", "").strip()
    quantity = request.form.get(f"quantity_{index}", "").strip()
    skids = request.form.get(f"skids_{index}", "").strip()
    remarks = request.form.get(f"remarks_{index}", "").strip()
    if not any([part_number, quantity, skids, remarks]):
        return None
    return PlantTransferLine(
        line_number=index + 1,
        side="left" if index < 10 else "right",
        part_number=part_number,
        quantity=quantity,
        skids=skids,
        remarks=remarks,
    )


def _plant_transfer_form_lines(transfer=None):
    rows = []
    existing = {}
    if transfer is not None:
        existing = {line.line_number - 1: line for line in transfer.lines}
    for index in range(PLANT_TRANSFER_LINE_COUNT):
        line = existing.get(index)
        rows.append(
            {
                "index": index,
                "part_number": request.form.get(
                    f"part_number_{index}", line.part_number if line else ""
                ),
                "quantity": request.form.get(
                    f"quantity_{index}", line.quantity if line else ""
                ),
                "skids": request.form.get(f"skids_{index}", line.skids if line else ""),
                "remarks": request.form.get(
                    f"remarks_{index}", line.remarks if line else ""
                ),
            }
        )
    return rows


def _replace_plant_transfer_lines(transfer):
    transfer.lines.clear()
    for index in range(PLANT_TRANSFER_LINE_COUNT):
        line = _plant_transfer_line_from_request(index)
        if line is not None:
            transfer.lines.append(line)


def _get_today_eod_records():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    pretrips = _active_pretrips_query().filter_by(
        user_id=current_user.id, pretrip_date=today_local_date
    ).all()
    plant_transfers = _active_plant_transfers_query().filter_by(
        user_id=current_user.id, transfer_date=today_local_date
    ).all()
    return today_local_date, logs, pretrips, plant_transfers


def _shift_record_for_driver_date(driver_id, route_date, *, require_signature=False):
    def base_query():
        query = ShiftRecord.query.filter(ShiftRecord.user_id == driver_id)
        if require_signature:
            query = query.filter(ShiftRecord.driver_signature.isnot(None))
        return query

    by_pretrip = (
        base_query()
        .join(PreTrip, ShiftRecord.pretrip_id == PreTrip.id)
        .filter(PreTrip.pretrip_date == route_date)
        .order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc())
        .first()
    )
    if by_pretrip:
        return by_pretrip

    local_tz = pytz.timezone("America/Detroit")
    for shift in base_query().order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc()).limit(50).all():
        if not shift.start_time:
            continue
        start_time = shift.start_time
        if start_time.tzinfo is None:
            start_time = pytz.utc.localize(start_time)
        if start_time.astimezone(local_tz).date() == route_date:
            return shift
    return None


def _valid_signature_data(value):
    signature = (value or "").strip()
    return signature if signature.startswith("data:image/") else ""


def _end_of_day_draft_signature():
    draft_key = f"movedefense:draft:v1:{current_user.id}:/end_of_day_summary:end-of-day-{current_user.id}"
    draft = DraftEntry.query.filter_by(user_id=current_user.id, draft_key=draft_key).first()
    payload = draft.payload if draft else None
    if not isinstance(payload, dict):
        return ""

    for field_name in ("driver_signature", "driverSigData"):
        entry = payload.get(field_name)
        if isinstance(entry, dict):
            signature = _valid_signature_data(entry.get("value"))
            if signature:
                return signature
        else:
            signature = _valid_signature_data(entry)
            if signature:
                return signature

    for entry in payload.values():
        candidate = entry.get("value") if isinstance(entry, dict) else entry
        signature = _valid_signature_data(candidate)
        if signature:
            return signature
    return ""


def _record_eod_finalized(today_local_date, logs, pretrips, plant_transfers):
    record_activity(
        user_id=current_user.id,
        category="eod",
        action="finalized",
        title="End of day finalized",
        details=(
            f"Reviewed {len(logs)} driver log(s), "
            f"{len(pretrips)} pretrip(s), and "
            f"{len(plant_transfers)} plant transfer(s) for {today_local_date}."
        ),
        target_type="end_of_day",
    )



def _document_attachment_response(*, pdf_bytes, filename, target_type, target_id=None, title="PDF attachment downloaded"):
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    record_activity(
        user_id=current_user.id,
        category="download",
        action="pdf_attachment",
        title=title,
        details=f"Prepared {filename} as a PDF attachment.",
        target_type=target_type,
        target_id=target_id,
    )
    return response




def _reason_parts_from_text(value):
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _truck_issue_text(issue_code, notes):
    issue_code = (issue_code or "").strip()
    notes = (notes or "").strip()
    if not issue_code:
        return notes
    label = TRUCK_ISSUE_LABELS.get(issue_code, issue_code).strip()
    if label and notes:
        return f"{label}: {notes}"
    return label


def _split_truck_issue_text(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return "", ""
    lower = cleaned.lower()
    for code, label in TRUCK_ISSUE_CHOICES:
        if not code:
            continue
        label_lower = label.lower()
        if lower == label_lower:
            return code, ""
        prefix = f"{label_lower}:"
        if lower.startswith(prefix):
            return code, cleaned[len(label) + 1:].strip()
    keyword_map = {
        "cel": ("cel", "CEL light"),
        "check engine": ("cel", "CEL light"),
        "leak": ("leak", "Leak"),
        "overheat": ("overheat", "Overheat"),
        "flat": ("flat", "Flat tire"),
        "tow": ("tow", "Need tow"),
        "regen": ("regen", "Truck regen"),
    }
    for keyword, (code, label) in keyword_map.items():
        if keyword in lower:
            return code, cleaned if not lower.startswith(label.lower()) else cleaned[len(label):].lstrip(": ")
    return "", cleaned


def _compose_downtime_reason(reason_parts, truck_issue, maintenance=False):
    parts = [part for part in reason_parts if part]
    truck_issue = (truck_issue or "").strip()
    if truck_issue:
        parts.append(f"{TRUCK_ISSUE_PREFIX} {truck_issue}")
    elif maintenance:
        parts.append(f"{TRUCK_ISSUE_PREFIX} Truck issue reported")
    return "; ".join(parts) or None


def _preserved_non_truck_reasons(log):
    prefixes = (UNLOAD_NOT_COMPLETED_PREFIX,) + SECONDARY_NOT_DROPPED_PREFIXES
    return [part for part in _reason_parts_from_text(log.downtime_reason) if part.startswith(prefixes)]


def _preserved_non_unload_reasons(log):
    prefixes = (UNLOAD_NOT_COMPLETED_PREFIX,) + SECONDARY_NOT_DROPPED_PREFIXES
    return [part for part in _reason_parts_from_text(log.downtime_reason) if not part.startswith(prefixes)]


def _set_departure_unload_reasons(log, primary_reason=None, secondary_reason=None):
    reason_parts = _preserved_non_unload_reasons(log)
    if primary_reason:
        reason_parts.append(f"{UNLOAD_NOT_COMPLETED_PREFIX} {primary_reason}")
    if secondary_reason:
        reason_parts.append(f"{SECONDARY_NOT_DROPPED_PREFIX} {secondary_reason}")
    log.downtime_reason = "; ".join(reason_parts) or None


def _auto_wait_minutes_for_departure(log, now_local):
    return elapsed_wait_minutes(log, now=now_local)


def _save_damage_photo(report, uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None
    upload_root = current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos")
    upload_path = os.path.join(current_app.root_path, os.pardir, upload_root)
    os.makedirs(upload_path, exist_ok=True)
    original = secure_filename(uploaded_file.filename) or "damage-photo"
    filename = f"damage-{report.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{original}"
    uploaded_file.save(os.path.join(upload_path, filename))
    photo = DamagePhoto(
        damage_report_id=report.id,
        stage=report.stage,
        filename=filename,
        original_filename=original,
        content_type=uploaded_file.content_type,
    )
    db.session.add(photo)
    return photo


def _driver_log_photo_upload_path():
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    os.makedirs(upload_path, exist_ok=True)
    return upload_path


def _save_driver_log_photo(log, uploaded_file, *, source="gallery", note=None, uploaded_by_id=None):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("Choose a photo from your gallery or camera before saving proof.")
    original = secure_filename(uploaded_file.filename) or "stop-photo"
    name, ext = os.path.splitext(original)
    note_text = (note or "").strip()
    if not note_text:
        raise ValueError("Add a short reason for this stop photo before uploading.")
    filename = f"driver-log-{log.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext or '.jpg'}"
    uploaded_file.save(os.path.join(_driver_log_photo_upload_path(), filename))
    photo = DriverLogPhoto(
        driver_log_id=log.id,
        filename=filename,
        original_filename=original,
        content_type=getattr(uploaded_file, "mimetype", None) or getattr(uploaded_file, "content_type", None),
        source=(source or "gallery")[:40],
        note=note_text[:500],
        uploaded_by_id=uploaded_by_id,
        uploaded_at=datetime.utcnow(),
    )
    db.session.add(photo)
    db.session.flush()
    return photo


PHOTO_PROOF_CARGO_TERMS = ("cargo", "load", "skid", "pallet", "unbalanced", "un-balanced", "seal")


def _stop_photo_review_summary(log, plant_name=None):
    photos = list(getattr(log, "photos", []) or [])
    if not photos:
        return None
    latest = next((photo for photo in reversed(photos) if (photo.note or "").strip()), photos[-1])
    thumbnail = next((photo for photo in reversed(photos) if getattr(photo, "file_available", False)), None)
    joined_notes = " ".join((photo.note or "").lower() for photo in photos)
    label = "Cargo Photo Proof" if any(term in joined_notes for term in PHOTO_PROOF_CARGO_TERMS) else "Photo Proof"
    count = len(photos)
    proof_label = "stop photo proof" if count == 1 else "stop photo proofs"
    detail = f"{count} {proof_label} attached"
    if plant_name:
        detail += f" at {plant_name}"
    note = (latest.note or "").strip()
    if note:
        detail += f": {note}"
    missing_count = len([photo for photo in photos if not getattr(photo, "file_available", False)])
    if missing_count:
        file_label = "file" if missing_count == 1 else "files"
        detail += f" ({missing_count} photo {file_label} missing)"
    return {
        "label": label,
        "detail": detail,
        "count": count,
        "latest": latest,
        "thumbnail": thumbnail,
        "missing_count": missing_count,
    }


def _driver_log_photo_payload(photo):
    return {
        "id": photo.id,
        "url": url_for("driver.driver_log_photo", photo_id=photo.id),
        "delete_url": url_for("driver.delete_driver_log_photo", photo_id=photo.id),
        "original_filename": photo.original_filename or photo.filename,
        "source": (photo.source or "gallery").replace("_", " ").title(),
        "note": photo.note or "",
    }


def _photo_upload_wants_json():
    return "application/json" in (request.headers.get("Accept") or "") or request.headers.get("X-Requested-With") == "fetch"


def _save_pretrip_damage_report(pretrip, form):
    uploaded_file = request.files.get(form.damage_photo.name)
    if not uploaded_file or not uploaded_file.filename:
        return None
    description = (form.damage_report.data or "").strip() or "PreTrip damage photo."
    report = DamageReport(
        reported_by_id=current_user.id,
        truck_number=(pretrip.truck_number or "").strip() or None,
        trailer_number=(pretrip.trailer_number or "").strip() or None,
        plant_name="Other",
        stage="before",
        move_reference=f"PreTrip #{pretrip.id}",
        description=description,
    )
    db.session.add(report)
    db.session.flush()
    _save_damage_photo(report, uploaded_file)
    return report




def _pretrip_damage_reports(pretrip):
    if not pretrip or not getattr(pretrip, "id", None):
        return []
    return (
        DamageReport.query.filter(
            DamageReport.reported_by_id == pretrip.user_id,
            DamageReport.move_reference == f"PreTrip #{pretrip.id}",
        )
        .order_by(DamageReport.created_at.asc(), DamageReport.id.asc())
        .all()
    )


def _damage_photo_file_path(photo):
    if not photo:
        return None
    upload_root = current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos")
    path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, photo.filename))
    return path if os.path.isfile(path) else None



def _damage_report_date(report):
    stamp = report.damage_time or report.created_at or datetime.utcnow()
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    return stamp.astimezone(pytz.timezone("America/Detroit")).date()


def _is_damage_report_route_finalized(report):
    report_date = _damage_report_date(report)
    return ActivityEvent.query.filter_by(
        user_id=report.reported_by_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(report_date))).first() is not None


def _can_modify_damage_report(report):
    if current_user.role != "driver":
        return False
    if report.reported_by_id != current_user.id:
        return False
    if report.status != "open":
        return False
    return not _is_damage_report_route_finalized(report)


def _damage_report_or_404(report_id):
    report = DamageReport.query.get_or_404(report_id)
    if current_user.role == "driver" and report.reported_by_id != current_user.id:
        flash("Not authorized to access that damage report.", "danger")
        return None
    return report


def _today_damage_reports(driver_id, report_date):
    reports = DamageReport.query.filter_by(reported_by_id=driver_id).all()
    return [report for report in reports if _damage_report_date(report) == report_date]


def _total_miles_for_pretrips(pretrips):
    total = 0
    has_mileage = False
    for pretrip in pretrips:
        if pretrip.start_mileage is None or not pretrip.posttrip or pretrip.posttrip.end_mileage is None:
            continue
        total += pretrip.posttrip.end_mileage - pretrip.start_mileage
        has_mileage = True
    return total if has_mileage else None

def _yes_no(value):
    return "Yes" if value else "No"


PDF_ALERT_RED = (176, 0, 32)

_PRETRIP_DEFECT_FIELDS = [
    ("cab_doors_windows", "General - Cab/Doors/Windows"),
    ("body_doors", "General - Body/Doors"),
    ("oil_leak", "General - Oil Leak"),
    ("grease_leak", "General - Grease Leak"),
    ("coolant_leak", "General - Coolant Leak"),
    ("fuel_leak", "General - Fuel Leak"),
    ("gauges_warning", "In-Cab - Gauges/Warning Indicators"),
    ("wipers", "In-Cab - Windshield Wipers/Washers"),
    ("horn", "In-Cab - Horn"),
    ("heater_defroster", "In-Cab - Heater/Defroster"),
    ("mirrors", "In-Cab - Mirrors"),
    ("seat_belts_steering", "In-Cab - Seat Belts/Steering"),
    ("clutch", "In-Cab - Clutch"),
    ("service_brakes", "In-Cab - Service Brakes"),
    ("parking_brake", "In-Cab - Parking Brake"),
    ("emergency_brakes", "In-Cab - Emergency Brakes"),
    ("triangles", "In-Cab - Triangles"),
    ("fire_extinguisher", "In-Cab - Fire Extinguisher"),
    ("safety_equipment", "In-Cab - Safety Equipment"),
    ("oil_level", "Engine - Oil Level"),
    ("coolant_level", "Engine - Coolant Level"),
    ("belts", "Engine - Belts"),
    ("hoses", "Engine - Hoses"),
    ("lights_working", "Exterior - Lights Working"),
    ("reflectors", "Exterior - Reflectors"),
    ("suspension", "Exterior - Suspension"),
    ("tires", "Exterior - Tires"),
    ("wheels_rims", "Exterior - Wheels/Rims"),
    ("battery", "Exterior - Battery"),
    ("exhaust", "Exterior - Exhaust"),
    ("brakes", "Exterior - Brakes"),
    ("air_lines", "Exterior - Air Lines"),
    ("light_line", "Exterior - Light Line"),
    ("fifth_wheel", "Exterior - Fifth Wheel"),
    ("coupling", "Exterior - Coupling"),
    ("tie_downs", "Exterior - Tie Downs"),
    ("rear_end_protection", "Exterior - Rear End Protection"),
    ("towed_bodydoors", "Towed - Body/Doors"),
    ("towed_tiedowns", "Towed - Tie-Downs"),
    ("towed_lights", "Towed - Lights"),
    ("towed_reflectors", "Towed - Reflectors"),
    ("towed_suspension", "Towed - Suspension"),
    ("towed_tires", "Towed - Tires"),
    ("towed_wheels", "Towed - Wheels"),
    ("towed_brakes", "Towed - Brakes"),
    ("towed_landing_gear", "Towed - Landing Gear"),
    ("towed_kingpin", "Towed - Kingpin"),
    ("towed_fifthwheel", "Towed - Fifth Wheel"),
    ("towed_othercoupling", "Towed - Other Coupling"),
    ("towed_rearend", "Towed - Rear End"),
]


def _pretrip_marked_defects(pretrip):
    return [label for field, label in _PRETRIP_DEFECT_FIELDS if getattr(pretrip, field, False)]


def _normalize_hhmm_time(value):
    value = (value or "").strip().lower().replace(" ", "")
    if not value:
        return ""
    try:
        if value.endswith(("am", "pm")):
            parsed = datetime.strptime(value, "%I:%M%p")
        elif ":" in value:
            parsed = datetime.strptime(value, "%H:%M")
        elif value.isdigit() and len(value) in (3, 4):
            parsed = datetime.strptime(value.zfill(4), "%H%M")
        else:
            return None
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def _format_hhmm_12h(hhmm):
    if not hhmm:
        return ""
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M%p").lower().lstrip("0")
    except ValueError:
        return hhmm


def _format_display_time(value):
    normalized = _normalize_hhmm_time(value)
    if normalized is None:
        return value or ""
    return _format_hhmm_12h(normalized)


def _arrival_utc_to_local_hhmm(arrive_time):
    if not arrive_time:
        return ""
    try:
        dt_utc = pytz.utc.localize(datetime.strptime(arrive_time, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return arrive_time
    local_tz = pytz.timezone("America/Detroit")
    return _format_hhmm_12h(dt_utc.astimezone(local_tz).strftime("%H:%M"))


def _local_hhmm_to_arrival_utc(hhmm, log_date):
    local_tz = pytz.timezone("America/Detroit")
    local_dt = local_tz.localize(
        datetime.combine(log_date, datetime.strptime(hhmm, "%H:%M").time())
    )
    return local_dt.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_local_and_utc():
    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    now_utc = datetime.utcnow()
    return now_local, now_utc.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(total_seconds):
    if total_seconds is None or total_seconds < 0:
        total_seconds = 0
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"


def _detail_value(details, key):
    prefix = f"{key}:"
    for part in (details or "").split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return part[len(prefix):].strip()
    return ""


def _open_ryder_event(user_id):
    headed = (
        ActivityEvent.query.filter_by(user_id=user_id, category="ryder", action="headed")
        .order_by(ActivityEvent.created_at.desc())
        .first()
    )
    if not headed:
        return None
    closed = (
        ActivityEvent.query.filter(
            ActivityEvent.user_id == user_id,
            ActivityEvent.category == "ryder",
            ActivityEvent.action.in_(RYDER_CLOSING_ACTIONS),
            ActivityEvent.created_at > headed.created_at,
        )
        .order_by(ActivityEvent.created_at.desc())
        .first()
    )
    return None if closed else headed


def _ryder_followup_context(user_id):
    event = _open_ryder_event(user_id)
    if not event:
        return {
            "pending_ryder_event": None,
            "pending_ryder_elapsed": None,
            "pending_ryder_truck": "",
            "pending_ryder_issue": "",
        }
    return {
        "pending_ryder_event": event,
        "pending_ryder_elapsed": _format_duration((datetime.utcnow() - event.created_at).total_seconds()),
        "pending_ryder_truck": _detail_value(event.details, "Truck"),
        "pending_ryder_issue": _detail_value(event.details, "Issue"),
    }


def _render_new_driving_log(form, current_load):
    has_today_logs = (
        _active_driver_logs_query()
        .filter_by(driver_id=current_user.id, date=_today_local_date())
        .first()
        is not None
    )
    return render_template(
        "new_driving_log.html",
        form=form,
        current_load=current_load,
        has_today_logs=has_today_logs,
        **_ryder_followup_context(current_user.id),
    )


def _shift_redirect():
    if request.args.get("next") == "mobile":
        return redirect(url_for("driver.mobile_dashboard"))
    return redirect(url_for("driver.dashboard"))


def _task_redirect():
    if request.args.get("next") == "mobile":
        return redirect(url_for("driver.mobile_dashboard"))
    return redirect(url_for("driver.list_tasks"))


def _emit_driver_log_updated(log, action="updated"):
    socketio.emit(
        "driver_log_updated",
        {
            "log_id": log.id,
            "driver_id": log.driver_id,
            "date": log.date.isoformat() if log.date else None,
            "plant_name": log.plant_name,
            "action": action,
            "departed": bool(log.depart_time),
        },
    )


def _mobile_report_days(limit=14):
    report_dates = set()
    for value, in _active_driver_logs_query().with_entities(DriverLog.date).filter_by(driver_id=current_user.id).all():
        if value:
            report_dates.add(value)
    for value, in _active_pretrips_query().with_entities(PreTrip.pretrip_date).filter_by(user_id=current_user.id).all():
        if value:
            report_dates.add(value)
    for value, in _active_plant_transfers_query().with_entities(PlantTransfer.transfer_date).filter_by(user_id=current_user.id).all():
        if value:
            report_dates.add(value)

    reports = []
    for report_date in sorted(report_dates, reverse=True)[:limit]:
        reports.append(
            {
                "date": report_date,
                "logs": _active_driver_logs_query().filter_by(driver_id=current_user.id, date=report_date).count(),
                "pretrips": _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=report_date).count(),
                "transfers": _active_plant_transfers_query().filter_by(user_id=current_user.id, transfer_date=report_date).count(),
            }
        )
    return reports


def _normalize_truck_number(value):
    return (value or "").strip()


def _same_truck_number(left, right):
    left_normalized = _normalize_truck_number(left).lower()
    right_normalized = _normalize_truck_number(right).lower()
    return bool(left_normalized and left_normalized == right_normalized)


def _truck_history_time_label(log):
    if not getattr(log, "arrive_time", None):
        return "time not set"
    return _format_display_time(_arrival_utc_to_local_hhmm(log.arrive_time)) or "time not set"


def _truck_history_fuel_entries(logs):
    entries = []
    for log in logs:
        if not log.fuel or log.fuel_mileage is None:
            continue
        entries.append(
            {
                "log": log,
                "mileage": log.fuel_mileage,
                "plant": _plant_label(log.plant_name),
                "time_label": _truck_history_time_label(log),
            }
        )
    return entries


def _truck_history_issue_entries(logs):
    entries = []
    for log in logs:
        issue = truck_issue_reason(log)
        if not issue and log.maintenance:
            issue = "Truck issue reported"
        issue = (issue or "").strip()
        if not issue:
            continue
        issue_code, _ = _split_truck_issue_text(issue)
        lowered_issue = issue.lower()
        entries.append(
            {
                "log": log,
                "label": issue,
                "is_regen": issue_code == "regen" or "regen" in lowered_issue,
                "mileage": log.fuel_mileage,
                "plant": _plant_label(log.plant_name),
                "opened_label": _truck_history_time_label(log),
            }
        )
    return entries


def _truck_maintenance_history(truck_number, *, current_pretrip_id=None, limit=8):
    truck_number = _normalize_truck_number(truck_number)
    if not truck_number:
        return []

    query = (
        _active_pretrips_query()
        .join(PostTrip, PostTrip.pretrip_id == PreTrip.id)
        .filter(func.lower(func.trim(PreTrip.truck_number)) == truck_number.lower())
    )
    if current_pretrip_id:
        query = query.filter(PreTrip.id != current_pretrip_id)

    pretrips = (
        query.order_by(PostTrip.created_at.desc(), PreTrip.pretrip_date.desc(), PreTrip.id.desc())
        .limit(limit)
        .all()
    )

    history = []
    for pretrip in pretrips:
        logs = sorted(
            _active_driver_logs_query()
            .filter_by(driver_id=pretrip.user_id, date=pretrip.pretrip_date)
            .all(),
            key=_driver_log_sort_key,
        )
        posttrip = pretrip.posttrip
        fuel_logs = _truck_history_fuel_entries(logs)
        issues = _truck_history_issue_entries(logs)
        history.append(
            {
                "pretrip": pretrip,
                "posttrip": posttrip,
                "driver": pretrip.driver,
                "driver_name": pretrip.driver.display_name if pretrip.driver else "Unknown driver",
                "date": pretrip.pretrip_date,
                "closed_at": posttrip.created_at if posttrip else None,
                "start_mileage": pretrip.start_mileage,
                "end_mileage": posttrip.end_mileage if posttrip else None,
                "miles_driven": posttrip.miles_driven if posttrip else None,
                "remarks": (posttrip.remarks or "").strip() if posttrip else "",
                "fuel_logs": fuel_logs,
                "fuel_count": len(fuel_logs),
                "issues": issues,
                "issue_count": len(issues),
                "regen_events": [issue for issue in issues if issue["is_regen"]],
                "status_label": "Closed on PostTrip" if posttrip else "Open",
            }
        )
    return history


def _parse_report_date(report_date):
    try:
        return datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        flash("Choose a valid report date.", "warning")
        return None


def _transfer_line_summary(transfer, limit=4):
    freight = []
    for line in transfer.lines:
        if not any([line.part_number, line.skids, line.quantity]):
            continue
        pieces = []
        if line.part_number:
            pieces.append(line.part_number)
        if line.skids:
            pieces.append(f"{line.skids} skid(s)")
        if line.quantity:
            pieces.append(f"qty {line.quantity}")
        freight.append(" / ".join(pieces))
    if len(freight) > limit:
        return freight[:limit] + [f"+{len(freight) - limit} more"]
    return freight


def _transfer_summary(transfer):
    lines = _transfer_line_summary(transfer)
    return {
        "route": f"{transfer.ship_from} to {transfer.ship_to}",
        "trailer": transfer.trailer_number or "not set",
        "parts": lines or ["No parts/skids recorded"],
        "transfer_number": transfer.transfer_number or transfer.id,
    }


def _log_freight_summary(log, transfers):
    plant = log.plant_name
    matches = [
        transfer
        for transfer in transfers
        if plant in {transfer.ship_from, transfer.ship_to}
    ]
    return [_transfer_summary(transfer) for transfer in matches]


def _build_pretrip_pdf(pretrip):
    evidence_reports = _pretrip_damage_reports(pretrip)
    total_pages = 2 if evidence_reports else 1
    meta = _pretrip_document_meta(pretrip, page=f"1 of {total_pages}")
    pdf = SimplePdf("PreTrip DVIR", LETTER)
    _draw_pdf_header(
        pdf,
        meta["title"],
        meta["document_no"],
        meta["generated_at"],
        meta["page"],
        driver=pretrip.driver.display_name if pretrip.driver else None,
        truck=pretrip.truck_number,
        date_value=pretrip.pretrip_date,
    )
    y = 704
    pdf.text(36, y, "1. Vehicle / Shift Info", size=10, bold=True)
    y -= 18
    pdf.text(36, y, f"Truck/Tractor No: {pretrip.truck_number or ''}", size=10, bold=True)
    pdf.text(265, y, f"Trailer No: {pretrip.trailer_number or ''}", size=10)
    pdf.text(445, y, f"Date: {pretrip.pretrip_date or ''}", size=10)
    y -= 18
    pdf.text(36, y, f"Shift: {pretrip.shift or ''}", size=10)
    pdf.text(160, y, f"Truck Type: {pretrip.truck_type or ''}", size=10)
    mileage = pretrip.start_mileage or 0
    if pretrip.posttrip and pretrip.posttrip.end_mileage is not None:
        total = pretrip.posttrip.end_mileage - (pretrip.start_mileage or 0)
        mileage = f"{pretrip.start_mileage or 0} - {pretrip.posttrip.end_mileage} (Total {total})"
    pdf.text(360, y, f"Mileage: {mileage}", size=10)
    y -= 25
    pdf.text(36, y, "2. Power Unit Inspection / 3. In-Cab Inspection / 4. Engine Compartment / 5. Exterior", size=9, bold=True)
    y -= 12
    rows = [
        ["Oil System", pretrip.oil_system_status or ""],
        ["Tires OK", _yes_no(pretrip.tires_ok)],
        ["Tires Status", pretrip.tires_status or ""],
        ["Oil Leak", _yes_no(pretrip.oil_leak)],
        ["Grease Leak", _yes_no(pretrip.grease_leak)],
        ["Coolant Leak", _yes_no(pretrip.coolant_leak)],
        ["Fuel Leak", _yes_no(pretrip.fuel_leak)],
        ["Cab/Doors/Windows", _yes_no(pretrip.cab_doors_windows)],
        ["Body Doors", _yes_no(pretrip.body_doors)],
        ["Gauges/Warning", _yes_no(pretrip.gauges_warning)],
        ["Wipers", _yes_no(pretrip.wipers)],
        ["Horn", _yes_no(pretrip.horn)],
        ["Heater/Defroster", _yes_no(pretrip.heater_defroster)],
        ["Mirrors", _yes_no(pretrip.mirrors)],
        ["Seat Belts/Steering", _yes_no(pretrip.seat_belts_steering)],
        ["Service Brakes", _yes_no(pretrip.service_brakes)],
        ["Parking Brake", _yes_no(pretrip.parking_brake)],
        ["Emergency Brakes", _yes_no(pretrip.emergency_brakes)],
        ["Safety Equipment", _yes_no(pretrip.safety_equipment)],
        ["Lights Working", _yes_no(pretrip.lights_working)],
        ["Reflectors", _yes_no(pretrip.reflectors)],
        ["Suspension", _yes_no(pretrip.suspension)],
        ["Wheels/Rims", _yes_no(pretrip.wheels_rims)],
        ["Brakes", _yes_no(pretrip.brakes)],
        ["Towed No Defects", _yes_no(pretrip.towed_no_defects)],
    ]
    numbered_rows = [[f"{idx}. {row[0]}", row[1]] for idx, row in enumerate(rows, start=1)]
    left = numbered_rows[:13]
    right = numbered_rows[13:]
    y = pdf.table(
        36,
        y,
        [150, 80, 150, 80],
        18,
        ["Item #", "Status", "Item #", "Status"],
        [l + r for l, r in zip(left, right)],
        font_size=8,
    )
    marked_defects = _pretrip_marked_defects(pretrip)
    if marked_defects:
        y -= 14
        pdf.text(36, y, "6. Defects / Remarks - Defects Marked", size=10, bold=True, color=PDF_ALERT_RED)
        pdf.multiline_text(
            42,
            y - 14,
            "; ".join(marked_defects),
            width_chars=105,
            size=8,
            leading=10,
            bold=True,
            max_lines=5,
            color=PDF_ALERT_RED,
        )

    y = 210
    remarks = (pretrip.damage_report or "").strip()
    remarks_color = PDF_ALERT_RED if remarks else None
    pdf.text(36, y, "6. Defects / Remarks", size=10, bold=True, color=remarks_color)
    pdf.rect(36, y - 70, 540, 60)
    pdf.multiline_text(
        42,
        y - 20,
        remarks,
        width_chars=95,
        size=9,
        bold=bool(remarks),
        max_lines=5,
        color=remarks_color,
    )
    pdf.text(36, 112, "7. Driver Signature", size=10, bold=True)
    pdf.text(36, 92, "Driver Signature: ____________________________", size=10)
    pdf.text(335, 92, "Date: __________________", size=10)

    if evidence_reports:
        pdf.add_page()
        meta = _pretrip_document_meta(pretrip, page=f"2 of {total_pages}")
        _draw_pdf_header(pdf, meta["title"], meta["document_no"], meta["generated_at"], meta["page"], driver=pretrip.driver.display_name if pretrip.driver else None, truck=pretrip.truck_number, date_value=pretrip.pretrip_date)
        y = 704
        pdf.text(36, y, "8. PreTrip Damage Evidence", size=14, bold=True)
        y -= 20
        pdf.text(36, y, f"PreTrip #{pretrip.id} / Truck {pretrip.truck_number or ''}", size=9)
        y -= 18
        for report in evidence_reports[:4]:
            pdf.text(36, y, f"Damage Report #{report.id}: {report.description}", size=9, bold=True, color=PDF_ALERT_RED)
            y -= 14
            if report.photos:
                for photo in report.photos[:2]:
                    image_y = y - 80
                    image_drawn = bool(_damage_photo_file_path(photo)) and pdf.image_file(_damage_photo_file_path(photo), 36, image_y, 120, 80)
                    if not image_drawn:
                        pdf.rect(36, image_y, 120, 80)
                        pdf.multiline_text(42, image_y + 48, "Photo record exists but file failed to render. Review in system before approval.", width_chars=28, size=7, leading=9, max_lines=4, bold=True)
                    pdf.text(170, y - 8, f"Photo ID #{photo.id}", size=8, bold=True)
                    pdf.text(170, y - 22, f"File: {photo.original_filename or photo.filename}", size=8)
                    pdf.text(170, y - 36, f"Uploaded: {photo.uploaded_at}", size=8)
                    y -= 98
                    if y < 120:
                        pdf.add_page()
                        y = 748
            else:
                pdf.text(44, y, "Damage report exists without photo attachment.", size=8, bold=True)
                y -= 18
            y -= 8
    return pdf.build()


def _signature_timestamp_label(signature_timestamp):
    if signature_timestamp:
        stamp = signature_timestamp
        if stamp.tzinfo is None:
            stamp = pytz.utc.localize(stamp)
        else:
            stamp = stamp.astimezone(pytz.utc)
        local_stamp = stamp.astimezone(pytz.timezone("America/Detroit"))
        return f"Signed {local_stamp.strftime('%Y-%m-%d %I:%M%p').lower().replace(' 0', ' ')} {local_stamp.strftime('%Z')}"
    return "Timestamp unavailable"


def _draw_signature_pdf_block(pdf, driver_signature=None, signature_timestamp=None):
    pdf.fill_rect(36, 34, 540, 94, gray=1)
    pdf.rect(36, 34, 540, 94)
    pdf.text(44, 112, "Driver Signature", size=9, bold=True)
    pdf.text(330, 112, "Manager / Auditor Signature", size=9, bold=True)

    if driver_signature:
        image_drawn = pdf.image_png_data_url(driver_signature, 44, 62, 190, 38)
        if not image_drawn:
            pdf.text(44, 80, "Driver e-signature captured", size=10, bold=True)
        pdf.line(44, 58, 252, 58)
        pdf.text(44, 44, _signature_timestamp_label(signature_timestamp), size=8)
    else:
        pdf.line(44, 74, 252, 74)
        pdf.text(44, 52, "Not yet signed", size=8)

    pdf.line(330, 74, 552, 74)
    pdf.text(330, 52, "Manager review signature", size=8)


def _build_driver_logs_pdf(logs, the_date, driver=None, driver_signature=None, signature_timestamp=None, route_context=None):
    route_context = route_context or build_route_context(driver_id=getattr(logs[0], "driver_id", None), route_date=getattr(logs[0], "date", None)) if logs else None
    routes = (route_context.log_routes if route_context else _driver_log_route_context(logs))
    pretrips = _active_pretrips_query().filter_by(user_id=getattr(driver, "id", None), pretrip_date=the_date).all() if driver else []
    truck = _truck_from_pretrips(pretrips)
    meta = _route_document_meta(the_date, driver, logs, pretrips)
    pdf = SimplePdf("Driver Route Sheet", LETTER)
    _draw_pdf_header(
        pdf,
        "DRIVER ROUTE AUDIT SHEET",
        meta["document_no"],
        meta["generated_at"],
        meta["page"],
        driver=driver.display_name if driver else None,
        truck=truck,
        date_value=the_date,
    )
    y = 710
    pdf.text(36, y, "1. Route Summary", size=11, bold=True)
    y -= 14
    if driver:
        info_parts = [driver.display_name]
        if driver.shift:
            info_parts.append(f"Shift: {driver.shift}")
        if driver.employee_id:
            info_parts.append(f"Badge: {driver.employee_id}")
        pdf.text(44, y, " | ".join(info_parts), size=8)
        y -= 14
    pdf.text(36, y, "2. Numbered Route Legs", size=11, bold=True)
    y -= 12
    snapshot_rows = {row.get("log_id"): row for row in (route_context.rows if route_context else [])}
    rows = []
    for idx, log in enumerate(logs, start=1):
        route = routes.get(log.id, {})
        snapshot = snapshot_rows.get(log.id, {})
        status = snapshot.get("note") or route.get("action") or ("Open" if not log.depart_time else "Complete")
        rows.append([
            str(idx),
            snapshot.get("plant") or route.get("plant") or log.plant_name,
            _arrival_utc_to_local_hhmm(log.arrive_time) or "--",
            _format_hhmm_12h(log.depart_time) or "--",
            snapshot.get("cargo_in") or route.get("arrive_cargo_desc") or route.get("arrive_desc") or load_display(log.load_size),
            snapshot.get("cargo_out") or (route.get("depart_cargo_desc") if route.get("depart_cargo_desc") is not None else "--"),
            wait_label_for_log(log) or "--",
            ("No Pickup " if log.no_pickup else "") + (("HOT " if log.hot_parts else "") + (log.part_number or "")).strip(),
            f"{snapshot.get('status', '')}: {status}" if snapshot else status,
        ])
    y = pdf.table(36, y, [28, 56, 44, 44, 78, 78, 54, 78, 72], 24, ["Leg #", "Plant", "Arrive", "Depart", "Cargo In", "Cargo Out", "Wait", "Parts", "Status"], rows or [["--", "No logs", "", "", "", "", "", "", ""]], font_size=6)
    y -= 18
    pdf.text(36, y, "3. Signatures", size=11, bold=True)
    _draw_signature_pdf_block(pdf, driver_signature, signature_timestamp)
    return pdf.build()


def _build_eod_pdf(the_date, logs, plant_transfers, driver_signature=None, signature_timestamp=None):
    meta = _eod_document_meta(the_date, current_user, logs)
    pdf = SimplePdf("End of Day", LETTER)
    _draw_pdf_header(pdf, "END OF DAY ROUTE RECORD", meta["document_no"], meta["generated_at"], meta["page"], driver=current_user.display_name, date_value=the_date)
    y = 710
    routes = _driver_log_route_context(logs)
    log_rows = []
    for idx, log in enumerate(logs, start=1):
        route = routes.get(log.id, {})
        cargo_out = route.get("depart_cargo_desc") if route.get("depart_cargo_desc") is not None else "--"
        if route.get("next_stop"):
            cargo_out = f"{cargo_out}; first stop {route.get('next_stop')}"
        log_rows.append([
            str(idx),
            route.get("plant") or log.plant_name,
            _arrival_utc_to_local_hhmm(log.arrive_time) or "--",
            _format_hhmm_12h(log.depart_time) or "--",
            route.get("arrive_cargo_desc") or route.get("arrive_desc") or load_display(log.load_size),
            cargo_out,
            wait_label_for_log(log) or "--",
            ("No Pickup " if log.no_pickup else "") + (("HOT " if log.hot_parts else "") + (log.part_number or "")).strip(),
        ])
    pdf.text(36, y, "1. Route Detail Table", size=11, bold=True)
    y -= 12
    y = pdf.table(36, y, [32, 58, 48, 48, 100, 108, 62, 92], 24, ["Stop #", "Plant", "Arrive", "Depart", "Cargo In", "Cargo Out", "Wait", "Parts"], log_rows or [["--", "No logs", "", "", "", "", "", ""]], font_size=7)
    y -= 34
    pdf.text(36, y, "2. Plant Transfers", size=12, bold=True)
    y -= 14
    transfer_rows = []
    for idx, transfer in enumerate(plant_transfers, start=1):
        transfer_rows.append([
            str(idx),
            transfer.transfer_number or transfer.id,
            transfer.ship_from,
            transfer.ship_to,
            transfer.trailer_number or "",
            transfer.driver_name or transfer.driver.display_name,
            len(transfer.lines),
        ])
    pdf.table(36, y, [35, 55, 75, 75, 75, 145, 50], 22, ["Item #", "No.", "From", "To", "Trailer", "Driver", "Lines"], transfer_rows or [["--", "No transfers", "", "", "", "", ""]], font_size=7)
    _draw_signature_pdf_block(pdf, driver_signature, signature_timestamp)
    return pdf.build()


def _plant_transfer_copy_sets(requested_copy):
    all_copy_sets = [
        {"key": "white", "label": "White - DATA INPUT", "class": "copy-white"},
        {"key": "canary", "label": "Canary - RECEIVING PLANT", "class": "copy-canary"},
        {"key": "pink", "label": "Pink - DRIVER", "class": "copy-pink"},
        {"key": "blue", "label": "Blue - SHIPPING PLANT", "class": "copy-blue"},
    ]
    if requested_copy == "all":
        return all_copy_sets, all_copy_sets, requested_copy
    copy_sets = [copy_set for copy_set in all_copy_sets if copy_set["key"] == requested_copy]
    if not copy_sets:
        requested_copy = "pink"
        copy_sets = [copy_set for copy_set in all_copy_sets if copy_set["key"] == "pink"]
    return all_copy_sets, copy_sets, requested_copy


def _build_plant_transfer_pdf(transfer, requested_copy):
    all_copy_sets, copy_sets, requested_copy = _plant_transfer_copy_sets(requested_copy)
    lines_by_number = {line.line_number: line for line in transfer.lines}
    rows = [(lines_by_number.get(i + 1), lines_by_number.get(i + 11)) for i in range(10)]
    pdf = SimplePdf("Plant Transfer", LANDSCAPE_LETTER)
    for idx, copy_set in enumerate(copy_sets):
        if idx:
            pdf.add_page(LANDSCAPE_LETTER)
        meta = _transfer_document_meta(transfer, page=f"{idx + 1} of {len(copy_sets)}")
        pdf.text(36, 588, f"Document No: {meta['document_no']}", size=8, bold=True)
        pdf.text(250, 588, f"Generated: {meta['generated_at']}", size=8)
        pdf.text(650, 588, f"Page {meta['page']}", size=8)
        pdf.text(340, 566, "LACKS INDUSTRIES INC.", size=8, bold=True)
        pdf.text(310, 548, "PLANT TRANSFER", size=18, bold=True)
        pdf.text(650, 552, f"No. {transfer.transfer_number or transfer.id}", size=10, bold=True)
        pdf.text(36, 530, f"SHIP TO: {transfer.ship_to}", size=9, bold=True)
        pdf.text(300, 530, f"SHIP FROM: {transfer.ship_from}", size=9, bold=True)
        pdf.text(610, 530, f"DATE: {transfer.transfer_date}", size=9, bold=True)
        pdf.text(620, 574, copy_set["label"], size=9, bold=True)
        table_rows = []
        for left, right in rows:
            table_rows.append([
                left.part_number if left else "",
                left.quantity if left else "",
                left.skids if left else "",
                left.remarks if left else "",
                right.part_number if right else "",
                right.quantity if right else "",
                right.skids if right else "",
                right.remarks if right else "",
            ])
        pdf.table(36, 505, [120, 52, 42, 150, 120, 52, 42, 150], 30, ["Part Number", "Qty", "Skids", "Remarks", "Part Number", "Qty", "Skids", "Remarks"], table_rows, font_size=7)
        pdf.text(36, 118, f"TRAILER NO.: {transfer.trailer_number or ''}", size=9, bold=True)
        pdf.text(230, 118, f"DRIVER: {transfer.driver_name or transfer.driver.display_name}", size=9, bold=True)
        pdf.text(410, 118, f"INITIALS: {transfer.driver_initials or ''}", size=9, bold=True)
        pdf.text(530, 118, f"TIME: {_format_display_time(transfer.transfer_time)}", size=9, bold=True)
        pdf.text(575, 118, f"LOADED BY: {transfer.loaded_by or ''}", size=9, bold=True)
        pdf.text(260, 82, "MAT-C - Plant Transfer | Ret: 1 mo. after creation | Effective Date: 1/1/10", size=7)
    return pdf.build(), requested_copy


@bp.route("/list_pretrips")
@login_required
def list_pretrips():
    if current_user.role == "management":
        pretrips = _active_pretrips_query().order_by(PreTrip.created_at.desc()).all()
    else:
        pretrips = (
            _active_pretrips_query().filter_by(user_id=current_user.id)
            .order_by(PreTrip.created_at.desc())
            .all()
        )
    return render_template(
        "list_pretrips.html",
        pretrips=pretrips,
        today_local_date=_today_local_date(),
    )


@bp.route("/new_pretrip", methods=["GET", "POST"])
@login_required
def new_pretrip():
    form = PreTripForm()
    if form.validate_on_submit():
        chosen_date = form.pretrip_date.data or date.today()

        new_pt = PreTrip(
            user_id=current_user.id,
            truck_number=form.truck_number.data,
            trailer_number=form.trailer_number.data,
            pretrip_date=chosen_date,
            shift=form.shift.data,
            start_mileage=form.start_mileage.data,
            truck_type=form.truck_type.data,
            oil_system_status=form.oil_system_status.data,
            tires_ok=form.tires_ok.data,
            tires_status=form.tires_status.data,
            cab_doors_windows=form.cab_doors_windows.data,
            body_doors=form.body_doors.data,
            oil_leak=form.oil_leak.data,
            grease_leak=form.grease_leak.data,
            coolant_leak=form.coolant_leak.data,
            fuel_leak=form.fuel_leak.data,
            gc_no_defects=form.gc_no_defects.data,
            gauges_warning=form.gauges_warning.data,
            wipers=form.wipers.data,
            horn=form.horn.data,
            heater_defroster=form.heater_defroster.data,
            mirrors=form.mirrors.data,
            seat_belts_steering=form.seat_belts_steering.data,
            clutch=form.clutch.data,
            service_brakes=form.service_brakes.data,
            parking_brake=form.parking_brake.data,
            emergency_brakes=form.emergency_brakes.data,
            triangles=form.triangles.data,
            fire_extinguisher=form.fire_extinguisher.data,
            safety_equipment=form.safety_equipment.data,
            incab_no_defects=form.incab_no_defects.data,
            oil_level=form.oil_level.data,
            coolant_level=form.coolant_level.data,
            belts=form.belts.data,
            hoses=form.hoses.data,
            ec_no_defects=form.ec_no_defects.data,
            lights_working=form.lights_working.data,
            reflectors=form.reflectors.data,
            suspension=form.suspension.data,
            tires=form.tires.data,
            wheels_rims=form.wheels_rims.data,
            battery=form.battery.data,
            exhaust=form.exhaust.data,
            brakes=form.brakes.data,
            air_lines=form.air_lines.data,
            light_line=form.light_line.data,
            fifth_wheel=form.fifth_wheel.data,
            coupling=form.coupling.data,
            tie_downs=form.tie_downs.data,
            rear_end_protection=form.rear_end_protection.data,
            exterior_no_defects=form.exterior_no_defects.data,
            towed_bodydoors=form.towed_bodydoors.data,
            towed_tiedowns=form.towed_tiedowns.data,
            towed_lights=form.towed_lights.data,
            towed_reflectors=form.towed_reflectors.data,
            towed_suspension=form.towed_suspension.data,
            towed_tires=form.towed_tires.data,
            towed_wheels=form.towed_wheels.data,
            towed_brakes=form.towed_brakes.data,
            towed_landing_gear=form.towed_landing_gear.data,
            towed_kingpin=form.towed_kingpin.data,
            towed_fifthwheel=form.towed_fifthwheel.data,
            towed_othercoupling=form.towed_othercoupling.data,
            towed_rearend=form.towed_rearend.data,
            towed_no_defects=form.towed_no_defects.data,
            damage_report=form.damage_report.data,
        )

        db.session.add(new_pt)
        db.session.flush()
        damage_report = _save_pretrip_damage_report(new_pt, form)
        existing_open_shift = ShiftRecord.query.filter_by(
            user_id=current_user.id, end_time=None
        ).first()
        if existing_open_shift is None:
            db.session.add(
                ShiftRecord(
                    user_id=current_user.id,
                    pretrip_id=new_pt.id,
                    start_time=datetime.utcnow(),
                    week_ending=None,
                )
            )
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="pretrip",
            action="created",
            title="PreTrip saved",
            details=f"Truck {new_pt.truck_number or 'unlisted'} for {chosen_date}.",
            target_type="pretrip",
            target_id=new_pt.id,
        )
        if damage_report:
            record_activity(
                user_id=current_user.id,
                category="damage",
                action="reported",
                title="PreTrip damage photo saved",
                details=f"Truck {new_pt.truck_number or 'unlisted'} pretrip damage photo.",
                target_type="damage_report",
                target_id=damage_report.id,
            )

        flash("PreTrip saved successfully!", "success")
        return redirect(url_for("driver.list_pretrips"))

    return render_template("new_pretrip.html", form=form)


@bp.route("/do_posttrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def do_posttrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to complete a PostTrip for someone else's PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))

    local_tz = pytz.timezone("America/Detroit")
    today_date = datetime.now(local_tz).date()
    fuel_logs = (
        _active_driver_logs_query()
        .filter_by(driver_id=current_user.id, date=today_date, fuel=True)
        .filter(DriverLog.fuel_mileage.isnot(None))
        .order_by(DriverLog.arrive_time)
        .all()
    )

    form = PostTripForm()
    if form.validate_on_submit():
        end_mileage_val = form.end_mileage.data
        if pt.start_mileage is not None and end_mileage_val < pt.start_mileage:
            flash("End mileage cannot be lower than start mileage.", "danger")
            return render_template("posttrip.html", form=form, pretrip=pt, fuel_logs=fuel_logs)
        if pt.start_mileage is not None:
            miles_val = end_mileage_val - pt.start_mileage
        else:
            miles_val = None

        new_posttrip = PostTrip(
            pretrip_id=pretrip_id,
            end_mileage=end_mileage_val,
            remarks=form.remarks.data,
            miles_driven=miles_val,
        )
        db.session.add(new_posttrip)
        db.session.commit()

        shift = ShiftRecord.query.filter_by(pretrip_id=pretrip_id).first()
        if shift and shift.end_time is None:
            shift.end_time = datetime.utcnow()
            shift.total_hours = (
                shift.end_time - shift.start_time
            ).total_seconds() / 3600.0
            db.session.commit()

        record_activity(
            user_id=current_user.id,
            category="posttrip",
            action="completed",
            title="PostTrip completed",
            details=f"PreTrip #{pt.id}; miles driven: {miles_val if miles_val is not None else 'not calculated'}.",
            target_type="posttrip",
            target_id=new_posttrip.id,
        )

        flash("PostTrip completed successfully and shift clock ended!", "success")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pretrip_id))
    return render_template("posttrip.html", form=form, pretrip=pt, fuel_logs=fuel_logs)


@bp.route("/view_pretrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def view_pretrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to view that PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))
    return render_template(
        "view_pretrip.html",
        pretrip=pt,
        readonly=(current_user.role == "management"),
        today_local_date=_today_local_date(),
        pretrip_damage_reports=_pretrip_damage_reports(pt),
        document_meta=_pretrip_document_meta(pt),
    )


@bp.route("/edit_pretrip_entry/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def edit_pretrip_entry(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for("driver.list_pretrips"))
    if current_user.role == "management":
        flash("Managers have read-only access to driver pretrip data.", "warning")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pt.id))

    form = PreTripForm(obj=pt)
    if form.validate_on_submit():
        pt.pretrip_date = form.pretrip_date.data
        pt.shift = form.shift.data
        pt.truck_type = form.truck_type.data
        pt.truck_number = form.truck_number.data
        pt.trailer_number = form.trailer_number.data
        pt.start_mileage = form.start_mileage.data
        pt.oil_system_status = form.oil_system_status.data
        pt.tires_ok = form.tires_ok.data
        pt.tires_status = form.tires_status.data
        pt.cab_doors_windows = form.cab_doors_windows.data
        pt.body_doors = form.body_doors.data
        pt.oil_leak = form.oil_leak.data
        pt.grease_leak = form.grease_leak.data
        pt.coolant_leak = form.coolant_leak.data
        pt.fuel_leak = form.fuel_leak.data
        pt.gc_no_defects = form.gc_no_defects.data
        pt.gauges_warning = form.gauges_warning.data
        pt.wipers = form.wipers.data
        pt.horn = form.horn.data
        pt.heater_defroster = form.heater_defroster.data
        pt.mirrors = form.mirrors.data
        pt.seat_belts_steering = form.seat_belts_steering.data
        pt.clutch = form.clutch.data
        pt.service_brakes = form.service_brakes.data
        pt.parking_brake = form.parking_brake.data
        pt.emergency_brakes = form.emergency_brakes.data
        pt.triangles = form.triangles.data
        pt.fire_extinguisher = form.fire_extinguisher.data
        pt.safety_equipment = form.safety_equipment.data
        pt.incab_no_defects = form.incab_no_defects.data
        pt.oil_level = form.oil_level.data
        pt.coolant_level = form.coolant_level.data
        pt.belts = form.belts.data
        pt.hoses = form.hoses.data
        pt.ec_no_defects = form.ec_no_defects.data
        pt.lights_working = form.lights_working.data
        pt.reflectors = form.reflectors.data
        pt.suspension = form.suspension.data
        pt.tires = form.tires.data
        pt.wheels_rims = form.wheels_rims.data
        pt.battery = form.battery.data
        pt.exhaust = form.exhaust.data
        pt.brakes = form.brakes.data
        pt.air_lines = form.air_lines.data
        pt.light_line = form.light_line.data
        pt.fifth_wheel = form.fifth_wheel.data
        pt.coupling = form.coupling.data
        pt.tie_downs = form.tie_downs.data
        pt.rear_end_protection = form.rear_end_protection.data
        pt.exterior_no_defects = form.exterior_no_defects.data
        pt.towed_bodydoors = form.towed_bodydoors.data
        pt.towed_tiedowns = form.towed_tiedowns.data
        pt.towed_lights = form.towed_lights.data
        pt.towed_reflectors = form.towed_reflectors.data
        pt.towed_suspension = form.towed_suspension.data
        pt.towed_tires = form.towed_tires.data
        pt.towed_wheels = form.towed_wheels.data
        pt.towed_brakes = form.towed_brakes.data
        pt.towed_landing_gear = form.towed_landing_gear.data
        pt.towed_kingpin = form.towed_kingpin.data
        pt.towed_fifthwheel = form.towed_fifthwheel.data
        pt.towed_othercoupling = form.towed_othercoupling.data
        pt.towed_rearend = form.towed_rearend.data
        pt.towed_no_defects = form.towed_no_defects.data
        pt.damage_report = form.damage_report.data
        damage_report = _save_pretrip_damage_report(pt, form)

        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="pretrip",
            action="updated",
            title="PreTrip updated",
            details=f"Truck {pt.truck_number or 'unlisted'} for {pt.pretrip_date}.",
            target_type="pretrip",
            target_id=pt.id,
        )
        if damage_report:
            record_activity(
                user_id=current_user.id,
                category="damage",
                action="reported",
                title="PreTrip damage photo saved",
                details=f"Truck {pt.truck_number or 'unlisted'} pretrip damage photo.",
                target_type="damage_report",
                target_id=damage_report.id,
            )

        session["reviewing_driver"] = request.form.get("reviewing_driver")
        session["reviewing_date"] = request.form.get("reviewing_date")

        flash("PreTrip updated!", "success")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pt.id))

    return render_template("edit_pretrip_entry.html", form=form, pretrip=pt)


@bp.route("/pretrips/<int:pretrip_id>/delete", methods=["POST"])
@login_required
def delete_pretrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if not _can_driver_change_same_day(pt.user_id, pt.pretrip_date, "PreTrip", "delete"):
        return redirect(url_for("driver.list_pretrips"))

    truck_number = pt.truck_number or "unlisted"
    report_date = pt.pretrip_date
    _soft_delete_record(pt)
    record_activity(
        user_id=current_user.id,
        category="pretrip",
        action="deleted",
        title="PreTrip deleted",
        details=f"Truck {truck_number} for {report_date}.",
        target_type="pretrip",
        target_id=pretrip_id,
    )
    db.session.commit()
    flash("PreTrip deleted.", "success")
    return redirect(url_for("driver.list_pretrips"))


@bp.route("/pretrip_printable/<int:pretrip_id>")
@login_required
def pretrip_printable(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to print another driver's PreTrip!", "danger")
        return redirect(url_for("driver.list_pretrips"))

    ephemeral_driver = session.get("reviewing_driver")
    ephemeral_date = session.get("reviewing_date")

    return render_template(
        "pretrip_printable.html",
        pretrip=pt,
        ephemeral_driver=ephemeral_driver,
        ephemeral_date=ephemeral_date,
        email_mode=False,
        pretrip_damage_reports=_pretrip_damage_reports(pt),
        document_meta=_pretrip_document_meta(pt),
    )


@bp.route("/pretrip_printable/<int:pretrip_id>/attachment")
@login_required
def pretrip_attachment(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to download another driver's PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))
    return _document_attachment_response(
        pdf_bytes=_build_pretrip_pdf(pt),
        filename=f"pretrip-{pt.id}.pdf",
        target_type="pretrip",
        target_id=pt.id,
        title="PreTrip PDF downloaded",
    )

@bp.route("/pretrip_printable/<int:pretrip_id>/mark_printed", methods=["POST"])
@login_required
def mark_pretrip_printed(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and pt.user_id != current_user.id:
        return jsonify({"ok": False, "error": "not_authorized"}), 403
    record_activity(
        user_id=current_user.id,
        category="print",
        action="pretrip_printed",
        title="PreTrip printed",
        details=f"Printed DVIR for truck {pt.truck_number or 'unlisted'}.",
        target_type="pretrip",
        target_id=pt.id,
    )
    return jsonify({"ok": True})


@bp.route("/plant_transfers")
@login_required
def plant_transfers():
    if current_user.role == "management":
        transfers = _active_plant_transfers_query().order_by(PlantTransfer.created_at.desc()).all()
    else:
        transfers = (
            _active_plant_transfers_query().filter_by(user_id=current_user.id)
            .order_by(PlantTransfer.created_at.desc())
            .all()
        )
    return render_template(
        "plant_transfers.html",
        transfers=transfers,
        today_local_date=_today_local_date(),
    )


@bp.route("/plant_transfers/new", methods=["GET", "POST"])
@login_required
def new_plant_transfer():
    form = PlantTransferForm()
    if request.method == "GET" and not form.driver_name.data:
        form.driver_name.data = current_user.display_name
    lines = _plant_transfer_form_lines()
    if form.validate_on_submit():
        if not any(_plant_transfer_line_from_request(i) for i in range(PLANT_TRANSFER_LINE_COUNT)):
            flash("Add at least one part line before saving the Plant Transfer.", "danger")
            return render_template(
                "plant_transfer_form.html", form=form, lines=lines, transfer=None
            )
        transfer = PlantTransfer(
            user_id=current_user.id,
            transfer_number=form.transfer_number.data,
            transfer_date=form.transfer_date.data,
            ship_to=form.ship_to.data,
            ship_from=form.ship_from.data,
            trailer_number=form.trailer_number.data,
            driver_name=form.driver_name.data,
            driver_initials=(form.driver_initials.data or "").strip().upper() or None,
            transfer_time=_normalize_hhmm_time(form.transfer_time.data) or form.transfer_time.data,
            loaded_by=form.loaded_by.data,
        )
        _replace_plant_transfer_lines(transfer)
        db.session.add(transfer)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="transfer",
            action="created",
            title="Plant Transfer saved",
            details=f"{transfer.ship_from} to {transfer.ship_to}; {len(transfer.lines)} line(s).",
            target_type="plant_transfer",
            target_id=transfer.id,
        )
        flash("Plant Transfer saved.", "success")
        return redirect(url_for("driver.view_plant_transfer", transfer_id=transfer.id))
    return render_template("plant_transfer_form.html", form=form, lines=lines, transfer=None)


@bp.route("/plant_transfers/<int:transfer_id>")
@login_required
def view_plant_transfer(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return redirect(url_for("driver.plant_transfers"))
    return render_template(
        "view_plant_transfer.html",
        transfer=transfer,
        today_local_date=_today_local_date(),
    )


@bp.route("/plant_transfers/<int:transfer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_plant_transfer(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return redirect(url_for("driver.plant_transfers"))
    if current_user.role == "management":
        flash("Managers have read-only access to driver Plant Transfers.", "warning")
        return redirect(url_for("driver.view_plant_transfer", transfer_id=transfer.id))
    form = PlantTransferForm(obj=transfer)
    if request.method == "GET":
        form.transfer_time.data = _format_display_time(transfer.transfer_time)
    lines = _plant_transfer_form_lines(transfer)
    if form.validate_on_submit():
        if not any(_plant_transfer_line_from_request(i) for i in range(PLANT_TRANSFER_LINE_COUNT)):
            flash("Add at least one part line before saving the Plant Transfer.", "danger")
            return render_template(
                "plant_transfer_form.html", form=form, lines=lines, transfer=transfer
            )
        before_values = model_snapshot(transfer, PLANT_TRANSFER_AUDIT_FIELDS)
        transfer.transfer_number = form.transfer_number.data
        transfer.transfer_date = form.transfer_date.data
        transfer.ship_to = form.ship_to.data
        transfer.ship_from = form.ship_from.data
        transfer.trailer_number = form.trailer_number.data
        transfer.driver_name = form.driver_name.data
        transfer.driver_initials = (form.driver_initials.data or "").strip().upper() or None
        transfer.transfer_time = _normalize_hhmm_time(form.transfer_time.data) or form.transfer_time.data
        transfer.loaded_by = form.loaded_by.data
        _replace_plant_transfer_lines(transfer)
        after_values = model_snapshot(transfer, PLANT_TRANSFER_AUDIT_FIELDS)
        record_audit_event(
            user_id=current_user.id,
            target_type="plant_transfer",
            target_id=transfer.id,
            action="updated",
            reason=form.edit_reason.data,
            before_values=before_values,
            after_values=after_values,
            commit=False,
        )
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="transfer",
            action="updated",
            title="Plant Transfer updated",
            details=f"{transfer.ship_from} to {transfer.ship_to}; {len(transfer.lines)} line(s).",
            target_type="plant_transfer",
            target_id=transfer.id,
        )
        flash("Plant Transfer updated.", "success")
        return redirect(url_for("driver.view_plant_transfer", transfer_id=transfer.id))
    return render_template(
        "plant_transfer_form.html", form=form, lines=lines, transfer=transfer
    )


@bp.route("/plant_transfers/<int:transfer_id>/delete", methods=["POST"])
@login_required
def delete_plant_transfer(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    if not _can_driver_change_same_day(
        transfer.user_id, transfer.transfer_date, "Plant Transfer", "delete"
    ):
        return redirect(url_for("driver.plant_transfers"))

    transfer_number = transfer.transfer_number or transfer.id
    route = f"{transfer.ship_from} to {transfer.ship_to}"
    _soft_delete_record(transfer)
    record_activity(
        user_id=current_user.id,
        category="transfer",
        action="deleted",
        title="Plant Transfer deleted",
        details=f"{transfer_number}: {route}.",
        target_type="plant_transfer",
        target_id=transfer_id,
    )
    db.session.commit()
    flash("Plant Transfer deleted.", "success")
    return redirect(url_for("driver.plant_transfers"))


@bp.route("/plant_transfers/<int:transfer_id>/print")
@login_required
def plant_transfer_printable(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return redirect(url_for("driver.plant_transfers"))
    lines_by_number = {line.line_number: line for line in transfer.lines}
    print_rows = [
        (lines_by_number.get(i + 1), lines_by_number.get(i + 11)) for i in range(10)
    ]
    all_copy_sets = [
        {"key": "white", "label": "White - DATA INPUT", "class": "copy-white"},
        {"key": "canary", "label": "Canary - RECEIVING PLANT", "class": "copy-canary"},
        {"key": "pink", "label": "Pink - DRIVER", "class": "copy-pink"},
        {"key": "blue", "label": "Blue - SHIPPING PLANT", "class": "copy-blue"},
    ]
    requested_copy = request.args.get("copy", "pink").lower()
    if requested_copy == "all":
        copy_sets = all_copy_sets
    else:
        copy_sets = [
            copy_set for copy_set in all_copy_sets if copy_set["key"] == requested_copy
        ]
        if not copy_sets:
            copy_sets = [copy_set for copy_set in all_copy_sets if copy_set["key"] == "pink"]
            requested_copy = "pink"
    return render_template(
        "plant_transfer_printable.html",
        transfer=transfer,
        print_rows=print_rows,
        copy_sets=copy_sets,
        all_copy_sets=all_copy_sets,
        requested_copy=requested_copy,
        email_mode=False,
        document_meta=_transfer_document_meta(transfer, page=f"1 of {len(copy_sets)}"),
    )


@bp.route("/plant_transfers/<int:transfer_id>/attachment")
@login_required
def plant_transfer_attachment(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return redirect(url_for("driver.plant_transfers"))
    requested_copy = request.args.get("copy", "pink")
    pdf_bytes, requested_copy = _build_plant_transfer_pdf(transfer, requested_copy)
    return _document_attachment_response(
        pdf_bytes=pdf_bytes,
        filename=f"plant-transfer-{transfer.transfer_number or transfer.id}-{requested_copy}.pdf",
        target_type="plant_transfer",
        target_id=transfer.id,
        title="Plant Transfer PDF downloaded",
    )

@bp.route("/plant_transfers/<int:transfer_id>/mark_printed", methods=["POST"])
@login_required
def mark_plant_transfer_printed(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return jsonify({"ok": False, "error": "not_authorized"}), 403
    record_activity(
        user_id=current_user.id,
        category="print",
        action="plant_transfer_printed",
        title="Plant Transfer printed",
        details=(
            f"{transfer.ship_from} to {transfer.ship_to}; "
            f"copy: {request.args.get('copy', 'selected')}."
        ),
        target_type="plant_transfer",
        target_id=transfer.id,
    )
    return jsonify({"ok": True})


@bp.route("/driver_logs", methods=["GET"])
@login_required
def driver_logs():
    search_date = _selected_log_date_from_request()

    if current_user.role == "management":
        all_drivers = User.query.filter_by(role="driver").all()
        selected_driver_id = request.args.get("driver_id", type=int)
        query = _active_driver_logs_query().filter(DriverLog.date == search_date).order_by(
            DriverLog.created_at.desc()
        )
        if selected_driver_id:
            query = query.filter_by(driver_id=selected_driver_id)
        logs = query.all()
        return render_template(
            "driver_logs.html",
            logs=logs,
            log_routes=_driver_log_route_context(logs),
            route_task_events=_task_route_events_for_logs(logs),
            all_drivers=all_drivers,
            selected_driver_id=selected_driver_id,
            search_date=search_date,
            today_local_date=_today_local_date(),
        )
    else:
        logs = (
            _active_driver_logs_query().filter_by(driver_id=current_user.id, date=search_date)
            .order_by(DriverLog.created_at.desc())
            .all()
        )
        return render_template(
            "driver_logs.html",
            logs=logs,
            log_routes=_driver_log_route_context(logs),
            route_task_events=_task_route_events_for_logs(logs),
            search_date=search_date,
            today_local_date=_today_local_date(),
        )


@bp.route("/new_driving_log", methods=["GET", "POST"])
@login_required
@_driver_route_guard("driver.mobile_dashboard", "the driver log page")
def new_driving_log():
    form = DriverLogForm()
    pending_ryder_event = _open_ryder_event(current_user.id)
    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    open_shift = _open_shift_for_driver(current_user.id)
    local_date = _active_route_date_for_driver(current_user.id, now_local.date(), open_shift=open_shift)
    current_load = _current_driver_load(current_user.id, route_date=local_date)
    current_load_value = current_load["value"] or "Empty"
    current_secondary_value = current_load.get("secondary_value") or ""

    if form.validate_on_submit():
        if pending_ryder_event:
            flash("Close the Ryder status before entering the next stop.", "warning")
            return _render_new_driving_log(form, current_load)
        if not form.plant_name.data:
            flash("Please select the plant you arrived at.", "danger")
            return redirect(url_for("driver.new_driving_log"))
        open_stop = _open_stop_for_driver(current_user.id, local_date)
        if open_stop:
            flash(f"Close the open stop at {_plant_label(open_stop.plant_name)} before creating the next stop.", "warning")
            return redirect(url_for("driver.driver_logs"))

        arrival_load = current_load_value or "Empty"
        arrival_secondary_load = current_secondary_value or None

        now_utc = datetime.utcnow()
        arrive_time_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=arrival_load,
            secondary_load=arrival_secondary_load,
            downtime_reason=_compose_downtime_reason([], _form_truck_issue_text(form), form.maintenance.data),
            part_number=_form_hot_part_number(form),
            hot_parts=bool(form.hot_parts.data),
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            fuel_mileage=_form_mileage_value(form),
            meeting=form.meeting.data,
            date=local_date,
        )
        db.session.add(newlog)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="submitted",
            title="Driver log submitted",
            details=f"{newlog.plant_name} arrival with {cargo_display(newlog.load_size, newlog.secondary_load)} for {newlog.date}.",
            target_type="driver_log",
            target_id=newlog.id,
        )
        ingest_driver_log(newlog, commit=True)
        _emit_driver_log_updated(newlog, "submitted")
        flash("Arrival recorded.", "success")
        return redirect(url_for("driver.driver_logs"))

    _prefill_log_form_from_task(form)
    form.load_size.data = current_load_value if current_load_value != "Empty" else "Empty"
    form.secondary_load.data = current_secondary_value
    return _render_new_driving_log(form, current_load)


@bp.route("/add_stop", methods=["GET", "POST"])
@login_required
def add_stop():
    """Retroactively add a missed stop with a manually-entered arrive time.
    Optional ?from_log_id=<id> pre-fills cargo and date from that stop's departure."""
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    active_log_date = _active_route_date_for_driver(
        current_user.id,
        today_local_date,
        open_shift=_open_shift_for_driver(current_user.id),
    )

    # Resolve the source log (GET or hidden POST field).
    from_log_id_raw = request.values.get("from_log_id", "")
    source_log = None
    if from_log_id_raw:
        source_log = (
            _active_driver_logs_query()
            .filter_by(id=from_log_id_raw, driver_id=current_user.id)
            .first()
        )

    log_date = source_log.date if source_log else active_log_date

    form = DriverLogForm()

    if form.validate_on_submit():
        if not form.plant_name.data:
            flash("Please select the plant.", "danger")
            return render_template("add_stop.html", form=form, source_log=source_log, from_log_id=from_log_id_raw)

        arrive_time_raw = (form.arrive_time.data or "").strip()
        if not arrive_time_raw:
            flash("Arrival time is required — enter the time you arrived at this stop.", "danger")
            return render_template("add_stop.html", form=form, source_log=source_log, from_log_id=from_log_id_raw)

        arrive_time_norm = _normalize_hhmm_time(arrive_time_raw)
        if arrive_time_norm is None:
            flash("Arrival time must be a valid time like 5:45am or 1:05pm.", "danger")
            return render_template("add_stop.html", form=form, source_log=source_log, from_log_id=from_log_id_raw)

        timing_errors = _route_timing_errors(current_user.id, log_date, form.plant_name.data, arrive_time_norm)
        if timing_errors:
            flash(timing_errors[0], "danger")
            return render_template("add_stop.html", form=form, source_log=source_log, from_log_id=from_log_id_raw)

        arrive_time_str = _local_hhmm_to_arrival_utc(arrive_time_norm, log_date)

        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=form.load_size.data or "Empty",
            secondary_load=None,
            downtime_reason=_compose_downtime_reason(
                [],
                _form_truck_issue_text(form),
                form.maintenance.data,
            ),
            part_number=_form_hot_part_number(form),
            hot_parts=bool(form.hot_parts.data),
            dock_wait_minutes=form.dock_wait_minutes.data,
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            fuel_mileage=_form_mileage_value(form),
            meeting=form.meeting.data,
            date=log_date,
        )
        db.session.add(newlog)

        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="submitted",
            title="Additional stop added",
            details=f"{newlog.plant_name} added retroactively for {newlog.date}.",
            target_type="driver_log",
            target_id=newlog.id,
        )
        ingest_driver_log(newlog, commit=True)
        _emit_driver_log_updated(newlog, "added_stop")
        flash("Additional stop added.", "success")
        return redirect(url_for("driver.driver_logs"))

    # GET: pre-fill load and time from the source log's departure.
    if request.method == "GET" and source_log:
        form.load_size.data = source_log.depart_load_size or "Empty"
        if source_log.depart_time:
            form.arrive_time.data = _format_hhmm_12h(source_log.depart_time)

    return render_template("add_stop.html", form=form, source_log=source_log, from_log_id=from_log_id_raw)


@bp.route("/edit_driver_log/<int:log_id>", methods=["GET", "POST"])
@login_required
def edit_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to edit someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))

    form = DriverLogForm(obj=log)
    if request.method == "GET":
        form.arrive_time.data = _arrival_utc_to_local_hhmm(log.arrive_time)
        issue_code, issue_notes = _split_truck_issue_text(truck_issue_reason(log) or route_problem_reason(log))
        form.truck_issue.data = issue_code
        form.truck_issue_notes.data = issue_notes
        form.departure_destination.data = destination_from_load(log.depart_load_size) or ""
        form.secondary_departure_dest.data = destination_from_load(log.secondary_load) or ""
        form.secondary_departure_type.data = load_type_from_load(log.secondary_load)
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("driver.edit_driver_log", log_id=log.id))

        arrive_time_raw = request.form.get("arrive_time", "")
        arrive_time = _normalize_hhmm_time(arrive_time_raw)
        if arrive_time_raw and arrive_time is None:
            flash("Arrival time must be a valid Detroit local time like 5:45am or 1:05pm.", "danger")
            return render_template("edit_driver_log.html", form=form, log=log)

        depart_time_raw = request.form.get("depart_time", "")
        depart_time = _normalize_hhmm_time(depart_time_raw)
        if depart_time_raw and depart_time is None:
            flash("Depart time must be a valid Detroit local time like 5:45am or 1:05pm.", "danger")
            return render_template("edit_driver_log.html", form=form, log=log)

        proposed_arrive = arrive_time or _normalize_hhmm_time(_arrival_utc_to_local_hhmm(log.arrive_time))
        proposed_depart = depart_time or _normalize_hhmm_time(log.depart_time or "")
        timing_errors = _route_timing_errors(log.driver_id, log.date, form.plant_name.data, proposed_arrive, proposed_depart, exclude_log_id=log.id)
        if timing_errors:
            flash(timing_errors[0], "danger")
            return render_template("edit_driver_log.html", form=form, log=log)

        before_values = model_snapshot(log, DRIVER_LOG_AUDIT_FIELDS)
        log.plant_name = form.plant_name.data
        log.load_size = form.load_size.data
        _apply_log_part_fields(log, form)
        log.dock_wait_minutes = form.dock_wait_minutes.data
        log.maintenance = form.maintenance.data
        log.downtime_reason = _compose_downtime_reason(_preserved_non_truck_reasons(log), _form_truck_issue_text(form), form.maintenance.data)
        log.fuel = form.fuel.data
        log.fuel_mileage = _form_mileage_value(form)
        log.meeting = form.meeting.data
        departure_dest = form.departure_destination.data
        sec_dest = form.secondary_departure_dest.data
        log.secondary_load = secondary_load_value(sec_dest, form.secondary_departure_type.data) if sec_dest else None

        if arrive_time:
            log.arrive_time = _local_hhmm_to_arrival_utc(arrive_time, log.date)
        if depart_time:
            log.depart_time = depart_time
        if log.depart_time:
            log.depart_load_size = destination_load_value(departure_dest) if departure_dest else "Empty"
            log.no_pickup = log.depart_load_size == "Empty" and not log.secondary_load
            _sync_next_open_stop_arrival_cargo(log)

        after_values = model_snapshot(log, DRIVER_LOG_AUDIT_FIELDS)
        record_audit_event(
            user_id=current_user.id,
            target_type="driver_log",
            target_id=log.id,
            action="updated",
            reason=form.edit_reason.data,
            before_values=before_values,
            after_values=after_values,
            commit=False,
        )
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="updated",
            title="Driver log updated",
            details=f"{log.plant_name} / {log.load_size} load for {log.date}.",
            target_type="driver_log",
            target_id=log.id,
        )
        ingest_driver_log(log, commit=True)
        _emit_driver_log_updated(log, "updated")
        flash(f"Driving log updated (ID: {log.id}).", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_template("edit_driver_log.html", form=form, log=log)


@bp.route("/edit_driving_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_edit_driving_log(log_id):
    return redirect(url_for("driver.edit_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)


@bp.route("/view_driving_log/<int:log_id>", methods=["GET"], strict_slashes=False)
@login_required
def legacy_view_driving_log(log_id):
    return redirect(url_for("driver.view_driver_log", log_id=log_id))


@bp.route("/depart_driver_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_depart_driver_log(log_id):
    return redirect(url_for("driver.depart_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)


@bp.route("/pickup_driver_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_pickup_driver_log(log_id):
    return redirect(url_for("driver.depart_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)


@bp.route("/no_pickup_driver_log/<int:log_id>", methods=["POST"], strict_slashes=False)
@login_required
def legacy_no_pickup_driver_log(log_id):
    return redirect(url_for("driver.no_pickup_driver_log", log_id=log_id), code=307)


@bp.route("/driver_logs/<int:log_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
def delete_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if not _can_driver_change_same_day(log.driver_id, log.date, "driver log", "delete"):
        return redirect(url_for("driver.driver_logs"))

    details = f"{log.plant_name} / {log.load_size} load for {log.date}."
    _soft_delete_record(log)
    record_activity(
        user_id=current_user.id,
        category="log",
        action="deleted",
        title="Driver log deleted",
        details=details,
        target_type="driver_log",
        target_id=log_id,
    )
    db.session.commit()
    _emit_driver_log_updated(log, "deleted")
    flash("Driver log deleted.", "success")
    return redirect(url_for("driver.driver_logs"))


@bp.route("/driver_logs/<int:log_id>/clear-hot", methods=["POST"], strict_slashes=False)
@login_required
def clear_driver_log_hot_part(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if not _can_driver_change_same_day(log.driver_id, log.date, "driver log", "clear hot part"):
        return redirect(url_for("driver.driver_logs"))
    if not log.hot_parts and not log.part_number:
        flash("That stop is not marked as a hot part.", "info")
        return redirect(url_for("driver.driver_logs"))

    before_values = model_snapshot(log, DRIVER_LOG_AUDIT_FIELDS)
    log.hot_parts = False
    log.part_number = None
    after_values = model_snapshot(log, DRIVER_LOG_AUDIT_FIELDS)
    record_audit_event(
        user_id=current_user.id,
        target_type="driver_log",
        target_id=log.id,
        action="updated",
        reason="Driver cleared an accidental hot-part flag.",
        before_values=before_values,
        after_values=after_values,
        commit=False,
    )
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="log",
        action="updated",
        title="Hot part flag cleared",
        details=f"{_plant_label(log.plant_name)} stop no longer marked hot.",
        target_type="driver_log",
        target_id=log.id,
    )
    ingest_driver_log(log, commit=True)
    _emit_driver_log_updated(log, "updated")
    flash("Hot part flag cleared for this stop.", "success")
    return redirect(url_for("driver.driver_logs"))


@bp.route("/driver_logs/photos/<int:photo_id>")
@login_required
def driver_log_photo(photo_id):
    photo = DriverLogPhoto.query.get_or_404(photo_id)
    if not photo.log or photo.log.driver_id != current_user.id:
        abort(403)
    return send_from_directory(_driver_log_photo_upload_path(), photo.filename)


def _delete_driver_log_photo_file(photo):
    path = os.path.join(_driver_log_photo_upload_path(), photo.filename)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        current_app.logger.warning("Unable to remove driver log photo %s", path, exc_info=True)


@bp.route("/driver_logs/photos/<int:photo_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
def delete_driver_log_photo(photo_id):
    photo = DriverLogPhoto.query.get_or_404(photo_id)
    log = photo.log
    if not log or log.driver_id != current_user.id:
        abort(403)
    photo_label = photo.original_filename or photo.filename
    note = photo.note
    _delete_driver_log_photo_file(photo)
    record_activity(
        user_id=current_user.id,
        category="log_photo",
        action="deleted",
        title="Stop photo proof deleted",
        details=f"Deleted stop photo {photo_label}. Reason was: {note or 'No reason recorded'}",
        target_type="driver_log",
        target_id=log.id,
        commit=False,
    )
    db.session.delete(photo)
    db.session.commit()
    flash("Stop photo proof deleted.", "success")
    return redirect(request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id))


@bp.route("/driver_logs/<int:log_id>/photos", methods=["POST"], strict_slashes=False)
@login_required
def record_driver_log_photo(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        if _photo_upload_wants_json():
            return jsonify({"error": "Not authorized to upload proof for this stop."}), 403
        flash("Not authorized to upload proof for this stop.", "danger")
        return redirect(url_for("driver.driver_logs"))

    try:
        photo = _save_driver_log_photo(
            log,
            request.files.get("photo"),
            source=request.form.get("source") or "gallery",
            note=request.form.get("note"),
            uploaded_by_id=current_user.id,
        )
    except ValueError as exc:
        db.session.rollback()
        if _photo_upload_wants_json():
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "danger")
        return redirect(request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id))

    record_activity(
        user_id=current_user.id,
        category="log_photo",
        action="created",
        title="Stop photo proof uploaded",
        details=f"{_plant_label(log.plant_name)} stop photo: {photo.original_filename or photo.filename}. Reason: {photo.note}",
        target_type="driver_log_photo",
        target_id=photo.id,
        commit=False,
    )
    db.session.commit()
    if _photo_upload_wants_json():
        return jsonify({"photo": _driver_log_photo_payload(photo)})
    flash("Stop photo proof saved.", "success")
    return redirect(request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id))


@bp.route("/driver_logs/<int:log_id>/part-scans", methods=["POST"], strict_slashes=False)
@login_required
def record_part_scan(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        return jsonify({"error": "Not authorized to scan against this stop."}), 403
    payload = request.get_json(silent=True) or request.form

    def payload_float(name):
        value = payload.get(name)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    raw_value = payload.get("raw_value") or payload.get("value")
    try:
        event = save_part_scan(
            log=log,
            route=_driver_log_context_for(log),
            raw_value=raw_value,
            scan_context=payload.get("scan_context"),
            barcode_format=payload.get("barcode_format"),
            device_id=payload.get("device_id"),
            gps_lat=payload_float("gps_lat"),
            gps_lng=payload_float("gps_lng"),
            created_offline=str(payload.get("created_offline") or "").lower() in {"1", "true", "yes"},
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="part_scan",
        action="created",
        title="Cargo scan recorded",
        details=f"{event.scan_context}: {event.normalized_value} at {_plant_label(log.plant_name)}",
        target_type="part_scan_event",
        target_id=event.id,
    )
    return jsonify({"scan": scan_event_payload(event)})


@bp.route("/driver_logs/<int:log_id>/depart", methods=["GET", "POST"], strict_slashes=False)
@login_required
@_driver_route_guard("driver.driver_logs", "that departure page", "Driver Logs")
def depart_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to depart someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    form = DepartForm()
    route = _driver_log_context_for(log)
    service_stop = is_service_stop(log)
    service_label = service_stop_label(log) if service_stop else ""

    def render_depart_page():
        now_local = datetime.now(pytz.timezone("America/Detroit"))
        auto_wait_seconds = elapsed_wait_seconds(log, now=now_local)
        auto_wait_minutes = None if auto_wait_seconds is None else auto_wait_seconds // 60
        part_scan_events = (
            PartScanEvent.query
            .filter_by(stop_id=log.id)
            .order_by(PartScanEvent.timestamp.asc(), PartScanEvent.id.asc())
            .all()
        )
        return render_template(
            "depart_driver_log.html",
            form=form,
            log=log,
            route=route,
            auto_wait_minutes=auto_wait_minutes,
            auto_wait_seconds=auto_wait_seconds,
            service_stop=service_stop,
            service_stop_label=service_label,
            part_scan_events=part_scan_events,
        )

    if form.validate_on_submit():
        primary_unloaded = None
        primary_unload_reason = None
        if not service_stop and route.get("arrived_at_primary_destination"):
            primary_unloaded = form.unloaded_on_departure.data
            if primary_unloaded not in {"yes", "no"}:
                flash("Please answer whether you got unloaded.", "danger")
                return render_depart_page()
            if primary_unloaded == "no":
                primary_unload_reason = (form.unload_reason.data or "").strip()
                if not primary_unload_reason:
                    flash("Please enter why the load was not unloaded.", "danger")
                    return render_depart_page()

        secondary_dropped = None
        secondary_drop_reason = None
        if not service_stop and route.get("arrived_at_secondary_destination"):
            secondary_dropped = form.secondary_dropped_on_departure.data
            if secondary_dropped not in {"yes", "no"}:
                flash("Please answer whether you dropped off the second-stop cargo.", "danger")
                return render_depart_page()
            if secondary_dropped == "no":
                secondary_drop_reason = (form.secondary_unload_reason.data or "").strip()
                if not secondary_drop_reason:
                    flash("Please enter why the second-stop cargo was not dropped off.", "danger")
                    return render_depart_page()

        after_unload_primary = route.get("after_arrival_primary") or "Empty"
        if primary_unloaded == "yes":
            after_unload_primary = "Empty"

        if service_stop:
            departure_load = route.get("after_arrival_primary") or load_display(log.load_size) or "Empty"
        elif form.got_loaded.data == "yes":
            if not form.destination.data:
                flash("Please select where the primary load is going.", "danger")
                return render_depart_page()
            departure_load = destination_load_value(form.destination.data)
        elif form.got_loaded.data == "no":
            departure_load = after_unload_primary
        else:
            flash("Please answer whether you got loaded.", "danger")
            return render_depart_page()

        secondary_load = route.get("after_arrival_secondary") or None
        if not service_stop:
            if secondary_dropped == "yes":
                secondary_load = None
            if form.secondary_destination.data:
                secondary_load = secondary_load_value(form.secondary_destination.data, form.secondary_load_type.data)

        unresolved_scan = (
            PartScanEvent.query
            .filter_by(stop_id=log.id)
            .filter(PartScanEvent.validation_status.in_(["unexpected", "missing", "missed_drop", "needs_review", "pending_part"]))
            .first()
        )
        override_reason = (request.form.get("cargo_override_reason") or "").strip()
        if unresolved_scan:
            if override_reason:
                record_activity(
                    user_id=current_user.id,
                    category="part_scan",
                    action="override",
                    title="Cargo scan override recorded",
                    details=f"{unresolved_scan.normalized_value}: {override_reason}",
                    target_type="part_scan_event",
                    target_id=unresolved_scan.id,
                    commit=False,
                )
            else:
                detail = unresolved_scan.validation_message or unresolved_scan.validation_status
                record_activity(
                    user_id=current_user.id,
                    category="part_scan",
                    action="needs_review",
                    title="Cargo scan needs manager review",
                    details=f"{unresolved_scan.normalized_value}: {detail}",
                    target_type="part_scan_event",
                    target_id=unresolved_scan.id,
                    commit=False,
                )

        local_tz = pytz.timezone("America/Detroit")
        now_local = datetime.now(local_tz)
        depart_time = now_local.strftime("%H:%M")
        timing_errors = _route_timing_errors(log.driver_id, log.date, log.plant_name, _arrival_hhmm_for_log(log), depart_time, exclude_log_id=log.id, check_previous=False)
        if timing_errors:
            flash(timing_errors[0], "danger")
            return render_depart_page()
        log.depart_time = depart_time
        log.dock_wait_minutes = _auto_wait_minutes_for_departure(log, now_local)
        log.depart_load_size = departure_load
        log.secondary_load = secondary_load or None
        _set_departure_unload_reasons(log, primary_unload_reason, secondary_drop_reason)
        log.no_pickup = False if service_stop else departure_load == "Empty" and not log.secondary_load
        _sync_next_open_stop_arrival_cargo(log)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="departed",
            title="Driver log departed",
            details=f"{log.plant_name} departed at {_format_display_time(log.depart_time)} with {cargo_display(log.depart_load_size, log.secondary_load)}.",
            target_type="driver_log",
            target_id=log.id,
        )
        ingest_driver_log(log, commit=True)
        _emit_driver_log_updated(log, "departed")
        flash(f"Departed {log.plant_name} with {cargo_display(log.depart_load_size, log.secondary_load)}.", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_depart_page()




@bp.route("/driver_logs/<int:log_id>/no_pickup", methods=["POST"], strict_slashes=False)
@login_required
def no_pickup_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to update someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    depart_time = now_local.strftime("%H:%M")
    timing_errors = _route_timing_errors(log.driver_id, log.date, log.plant_name, _arrival_hhmm_for_log(log), depart_time, exclude_log_id=log.id, check_previous=False)
    if timing_errors:
        flash(timing_errors[0], "danger")
        return redirect(url_for("driver.driver_logs"))
    log.no_pickup = True
    log.depart_load_size = "Empty"
    log.depart_time = depart_time
    log.dock_wait_minutes = _auto_wait_minutes_for_departure(log, now_local)
    _sync_next_open_stop_arrival_cargo(log)
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="log",
        action="no_pickup",
        title="No pickup recorded",
        details=f"{log.plant_name} had no pickup at {_format_display_time(log.depart_time)}.",
        target_type="driver_log",
        target_id=log.id,
    )
    ingest_driver_log(log, commit=True)
    _emit_driver_log_updated(log, "no_pickup")
    flash(f"No pickup recorded for log #{log.id}.", "success")
    return redirect(url_for("driver.driver_logs"))


@bp.route("/driver_logs/<int:log_id>/pickup", methods=["GET", "POST"], strict_slashes=False)
@login_required
def pickup_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to pick up from someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    form = DriverLogForm()
    _prefill_log_form_from_task(form)
    if form.validate_on_submit():
        if not form.plant_name.data:
            flash("Please select where the load is going.", "danger")
            return render_template("pickup_driver_log.html", form=form, log=log)

        now_local = datetime.now(pytz.timezone("America/Detroit"))
        depart_time = now_local.strftime("%H:%M")
        timing_errors = _route_timing_errors(log.driver_id, log.date, log.plant_name, _arrival_hhmm_for_log(log), depart_time, exclude_log_id=log.id, check_previous=False)
        if timing_errors:
            flash(timing_errors[0], "danger")
            return render_template("pickup_driver_log.html", form=form, log=log)
        log.depart_time = depart_time
        log.depart_load_size = destination_load_value(form.plant_name.data)
        log.hot_parts = bool(form.hot_parts.data)
        log.part_number = _form_hot_part_number(form) or (log.part_number if log.hot_parts else None)
        log.dock_wait_minutes = _auto_wait_minutes_for_departure(log, now_local)
        log.maintenance = form.maintenance.data
        log.downtime_reason = _compose_downtime_reason(_preserved_non_truck_reasons(log), _form_truck_issue_text(form), form.maintenance.data)
        log.fuel = form.fuel.data
        log.fuel_mileage = _form_mileage_value(form)
        log.meeting = form.meeting.data
        _sync_next_open_stop_arrival_cargo(log)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="pickup",
            title="Pickup recorded",
            details=f"{log.plant_name}: departed with {load_display(log.depart_load_size)}.",
            target_type="driver_log",
            target_id=log.id,
        )
        ingest_driver_log(log, commit=True)
        _emit_driver_log_updated(log, "pickup")
        flash(f"Load recorded at {log.plant_name}; departing with {load_display(log.depart_load_size)}.", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_template("pickup_driver_log.html", form=form, log=log)


@bp.route("/view_driver_log/<int:log_id>")
@login_required
def view_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to view someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    return render_template(
        "view_driver_log.html",
        log=log,
        today_local_date=_today_local_date(),
        driver_log_photos=list(log.photos),
    )


@bp.route("/driver_logs_print")
@login_required
def driver_logs_print():
    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    selected_date = _selected_log_date_from_request()
    logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=current_user.id, date=selected_date).all(),
        key=_driver_log_sort_key,
    )
    pretrips = _active_pretrips_query().filter_by(
        user_id=current_user.id, pretrip_date=selected_date
    ).all()
    route_context = build_route_context(driver_id=current_user.id, route_date=selected_date, now=now_local)
    log_routes = route_context.log_routes if route_context else _driver_log_route_context(logs)
    damage_reports_today = _today_damage_reports(current_user.id, selected_date)
    parts_carried = sorted({log.part_number for log in logs if log.part_number})
    exception_notes = []
    log_issue_details = {}
    for log in logs:
        route = log_routes.get(log.id, {})
        plant_name = route.get("plant") or _plant_label(log.plant_name)
        truck_issue = truck_issue_reason(log)
        route_problem = route_problem_reason(log)
        log_issue_details[log.id] = {"truck": truck_issue, "route": route_problem}
        if log.maintenance or truck_issue:
            exception_notes.append(f"Truck issue at {plant_name}: {truck_issue or 'Maintenance marked'}")
        if route.get("unload_blocked"):
            exception_notes.append(f"Unload issue at {plant_name}: {route.get('unload_reason')}")
        elif route.get("secondary_drop_blocked"):
            exception_notes.append(f"Second-stop cargo issue at {plant_name}: {route.get('secondary_drop_reason')}")
        elif route_problem:
            exception_notes.append(f"Route issue at {plant_name}: {route_problem}")
        photo_review = _stop_photo_review_summary(log, plant_name)
        if photo_review:
            exception_notes.append(f"{photo_review['label']}: {photo_review['detail']}")
    for issue in route_context.true_exceptions or []:
        label = issue.get("label") or "Route review item"
        detail = issue.get("detail") or ""
        note = f"{label}: {detail}" if detail else label
        if note not in exception_notes:
            exception_notes.append(note)
    route_finalized = ActivityEvent.query.filter_by(
        user_id=current_user.id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(selected_date))).first() is not None
    record_activity(
        user_id=current_user.id,
        category="print",
        action="logs_printed",
        title="Driver logs printed",
        details=f"Printed {len(logs)} log(s) for {selected_date}.",
        target_type="driver_log",
    )
    shift_record = _shift_record_for_driver_date(current_user.id, selected_date, require_signature=True)
    return render_template(
        "driver_logs_print.html",
        logs=logs,
        log_routes=log_routes,
        the_date=selected_date,
        pretrips=pretrips,
        damage_reports=damage_reports_today,
        damage_report_summary=damage_report_count_label(damage_reports_today),
        damage_report_details=[damage_report_detail_label(report) for report in damage_reports_today],
        total_miles=_total_miles_for_pretrips(pretrips),
        parts_carried=parts_carried,
        exception_notes=exception_notes,
        log_issue_details=log_issue_details,
        route_task_events=_task_route_events_for_logs(logs),
        stop_forecasts=route_context.stop_timing,
        route_state=route_context.route_state,
        route_context=route_context,
        route_finalized=route_finalized,
        driver_signature=shift_record.driver_signature if shift_record else None,
        signature_timestamp=shift_record.signature_timestamp if shift_record else None,
        document_meta=_route_document_meta(selected_date, current_user, logs, pretrips),
        attachment_url=url_for("driver.driver_logs_attachment", date=selected_date.isoformat()),
        email_mode=False,
    )


@bp.route("/driver_logs_print/attachment")
@login_required
def driver_logs_attachment():
    selected_date = _selected_log_date_from_request()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=selected_date
    ).all()
    shift_record = _shift_record_for_driver_date(current_user.id, selected_date, require_signature=True)
    route_context = build_route_context(driver_id=current_user.id, route_date=selected_date)
    return _document_attachment_response(
        pdf_bytes=_build_driver_logs_pdf(
            logs,
            selected_date,
            driver=current_user,
            driver_signature=shift_record.driver_signature if shift_record else None,
            signature_timestamp=shift_record.signature_timestamp if shift_record else None,
            route_context=route_context,
        ),
        filename=f"driver-logs-{selected_date}.pdf",
        target_type="driver_log",
        title="Driver Logs PDF downloaded",
    )

@bp.route("/start_shift", methods=["GET", "POST"])
@login_required
def start_shift():
    existing_open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if existing_open_shift:
        flash("You already have a shift in progress!", "warning")
        return _shift_redirect()

    new_shift = ShiftRecord(
        user_id=current_user.id,
        pretrip_id=None,
        start_time=datetime.utcnow(),
        week_ending=None,
    )
    db.session.add(new_shift)
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="shift",
        action="started",
        title="Shift started",
        details="Manual shift timer started.",
        target_type="shift",
        target_id=new_shift.id,
    )

    flash("Shift started!", "success")
    return _shift_redirect()


@bp.route("/end_shift", methods=["GET", "POST"])
@login_required
def end_shift():
    open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if not open_shift:
        flash("No open shift found!", "warning")
        return _shift_redirect()

    open_shift.end_time = datetime.utcnow()
    open_shift.total_hours = (
        open_shift.end_time - open_shift.start_time
    ).total_seconds() / 3600
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="shift",
        action="ended",
        title="Shift ended",
        details=f"Total hours: {open_shift.total_hours:.2f}.",
        target_type="shift",
        target_id=open_shift.id,
    )

    flash("Shift ended!", "success")
    return _shift_redirect()


@bp.route("/end_of_day_summary", methods=["GET", "POST"])
@login_required
def end_of_day_summary():
    form = EndOfDayForm()
    today_local_date, logs, pretrips_today, plant_transfers_today = _get_today_eod_records()
    if form.validate_on_submit():
        signature_shift = None
        sig_data = _valid_signature_data(form.driver_signature.data) or _end_of_day_draft_signature()
        if not sig_data:
            signature_shift = _shift_record_for_driver_date(current_user.id, today_local_date, require_signature=True)
            sig_data = _valid_signature_data(signature_shift.driver_signature if signature_shift else None)

        if sig_data:
            signature_shift = signature_shift or (
                ShiftRecord.query.filter_by(user_id=current_user.id, end_time=None)
                .order_by(ShiftRecord.start_time.desc())
                .first()
            ) or _shift_record_for_driver_date(current_user.id, today_local_date)
            if signature_shift is None:
                signature_shift = ShiftRecord(
                    user_id=current_user.id,
                    pretrip_id=pretrips_today[0].id if pretrips_today else None,
                    start_time=datetime.utcnow(),
                    week_ending=None,
                )
                db.session.add(signature_shift)
            signature_shift.driver_signature = sig_data
            signature_shift.signature_timestamp = datetime.utcnow()
            flash("Route signed and finalized. Review the signed printout before saving or printing.", "success")
        else:
            current_app.logger.warning("EOD finalized without captured driver signature for user_id=%s", current_user.id)
            flash("Route finalized. Driver signature was not captured and remains pending for manager review.", "warning")

        db.session.commit()
        _record_eod_finalized(today_local_date, logs, pretrips_today, plant_transfers_today)
        return redirect(url_for("driver.driver_logs_print"))

    drivers_logs = {current_user.display_name: logs}
    drivers_pretrips = {current_user.display_name: pretrips_today}
    drivers_plant_transfers = {current_user.display_name: plant_transfers_today}

    return render_template(
        "end_of_day_summary.html",
        form=form,
        the_date=today_local_date,
        drivers_logs=drivers_logs,
        drivers_pretrips=drivers_pretrips,
        drivers_plant_transfers=drivers_plant_transfers,
        log_routes=_driver_log_route_context(logs),
    )


@bp.route("/end_of_day_print")
@login_required
def end_of_day_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    plant_transfers = _active_plant_transfers_query().filter_by(
        user_id=current_user.id, transfer_date=today_local_date
    ).all()
    pretrips_today = _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=today_local_date).all()
    drivers_logs = {current_user.display_name: logs}
    drivers_plant_transfers = {current_user.display_name: plant_transfers}
    drivers_pretrips = {current_user.display_name: pretrips_today}
    record_activity(
        user_id=current_user.id,
        category="print",
        action="eod_printed",
        title="End of day print generated",
        details=f"Printed EOD packet for {today_local_date}.",
        target_type="end_of_day",
    )

    signature_shift = _shift_record_for_driver_date(current_user.id, today_local_date, require_signature=True)
    return render_template(
        "end_of_day_print.html",
        the_date=today_local_date,
        drivers_logs=drivers_logs,
        drivers_plant_transfers=drivers_plant_transfers,
        drivers_pretrips=drivers_pretrips,
        log_routes=_driver_log_route_context(logs),
        driver_signature=signature_shift.driver_signature if signature_shift else None,
        signature_timestamp=signature_shift.signature_timestamp if signature_shift else None,
        document_meta=_eod_document_meta(today_local_date, current_user, logs),
        email_mode=False,
    )


@bp.route("/end_of_day_print/attachment")
@login_required
def end_of_day_attachment():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    plant_transfers = _active_plant_transfers_query().filter_by(
        user_id=current_user.id, transfer_date=today_local_date
    ).all()
    drivers_logs = {current_user.display_name: logs}
    drivers_plant_transfers = {current_user.display_name: plant_transfers}
    signature_shift = _shift_record_for_driver_date(current_user.id, today_local_date, require_signature=True)
    return _document_attachment_response(
        pdf_bytes=_build_eod_pdf(
            today_local_date,
            logs,
            plant_transfers,
            driver_signature=signature_shift.driver_signature if signature_shift else None,
            signature_timestamp=signature_shift.signature_timestamp if signature_shift else None,
        ),
        filename=f"end-of-day-{today_local_date}.pdf",
        target_type="end_of_day",
        title="End of Day PDF downloaded",
    )

@bp.route("/submit_end_of_day", methods=["POST"])
@login_required
def submit_end_of_day():
    today_local_date, logs, pretrips_today, plant_transfers_today = _get_today_eod_records()
    _record_eod_finalized(today_local_date, logs, pretrips_today, plant_transfers_today)
    flash("End of Day finalized and added to activity history.", "success")
    return redirect(url_for("driver.dashboard"))


@bp.route("/damage_reports")
@login_required
def damage_reports():
    if current_user.role == "management":
        reports = DamageReport.query.order_by(DamageReport.created_at.desc()).all()
    else:
        reports = DamageReport.query.filter_by(reported_by_id=current_user.id).order_by(DamageReport.created_at.desc()).all()
    return render_template(
        "damage_reports.html",
        reports=reports,
        can_modify_damage_report=_can_modify_damage_report,
        route_finalized_for_report=_is_damage_report_route_finalized,
    )


@bp.route("/damage_reports/new", methods=["GET", "POST"])
@login_required
def new_damage_report():
    form = DamageReportForm()
    if form.validate_on_submit():
        report = DamageReport(
            reported_by_id=current_user.id,
            truck_number=(form.truck_number.data or "").strip() or None,
            trailer_number=(form.trailer_number.data or "").strip() or None,
            plant_name=form.plant_name.data,
            stage=form.stage.data,
            move_reference=(form.move_reference.data or "").strip() or None,
            description=form.description.data,
        )
        db.session.add(report)
        db.session.flush()
        _save_damage_photo(report, request.files.get(form.photo.name))
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="damage",
            action="reported",
            title="Damage report saved",
            details=f"{report.plant_name}; {report.truck_number or 'truck not set'} / {report.trailer_number or 'trailer not set'}.",
            target_type="damage_report",
            target_id=report.id,
        )
        flash("Damage report saved. You can edit or delete it until the route is finalized or you submit it.", "success")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))
    return render_template("damage_report_form.html", form=form, report=None, is_edit=False)




@bp.route("/damage_reports/photos/<int:photo_id>")
@login_required
def damage_photo(photo_id):
    photo = DamagePhoto.query.get_or_404(photo_id)
    report = photo.damage_report
    if current_user.role == "driver" and report.reported_by_id != current_user.id:
        flash("Not authorized to access that damage photo.", "danger")
        return redirect(url_for("driver.damage_reports"))
    upload_root = current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    return send_from_directory(upload_path, photo.filename)

@bp.route("/damage_reports/<int:report_id>")
@login_required
def view_damage_report(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    return render_template(
        "view_damage_report.html",
        report=report,
        can_modify=_can_modify_damage_report(report),
        route_finalized=_is_damage_report_route_finalized(report),
    )


@bp.route("/damage_reports/<int:report_id>/evidence_packet")
@login_required
def damage_evidence_packet(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="evidence_packet_generated",
        title="Evidence packet generated",
        details=f"Generated damage evidence packet #{report.id}.",
        target_type="damage_report",
        target_id=report.id,
    )
    packet = build_damage_evidence_packet(report, generated_by=current_user)
    return render_template(
        "damage_evidence_packet.html",
        packet=packet,
        manager_view=False,
        document_meta=_evidence_document_meta(report, page="1 of 5"),
        back_url=url_for("driver.view_damage_report", report_id=report.id),
    )


@bp.route("/damage_reports/<int:report_id>/edit", methods=["GET", "POST"])
@login_required
def edit_damage_report(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    if not _can_modify_damage_report(report):
        flash("This damage report is locked because it was submitted or the route was finalized.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    form = DamageReportForm(obj=report)
    if form.validate_on_submit():
        before = model_snapshot(report, ["truck_number", "trailer_number", "plant_name", "stage", "move_reference", "description", "status"])
        report.truck_number = (form.truck_number.data or "").strip() or None
        report.trailer_number = (form.trailer_number.data or "").strip() or None
        report.plant_name = form.plant_name.data
        report.stage = form.stage.data
        report.move_reference = (form.move_reference.data or "").strip() or None
        report.description = form.description.data
        _save_damage_photo(report, request.files.get(form.photo.name))
        after = model_snapshot(report, ["truck_number", "trailer_number", "plant_name", "stage", "move_reference", "description", "status"])
        record_audit_event(
            user_id=current_user.id,
            target_type="damage_report",
            target_id=report.id,
            action="edited",
            reason="Driver updated open damage report before route finalization.",
            before_values=before,
            after_values=after,
            commit=False,
        )
        record_activity(
            user_id=current_user.id,
            category="damage",
            action="edited",
            title="Damage report edited",
            details=f"Damage report #{report.id} updated for {report.plant_name}.",
            target_type="damage_report",
            target_id=report.id,
        )
        db.session.commit()
        flash("Damage report updated.", "success")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    return render_template("damage_report_form.html", form=form, report=report, is_edit=True)


@bp.route("/damage_reports/<int:report_id>/submit", methods=["POST"])
@login_required
def submit_damage_report(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    if not _can_modify_damage_report(report):
        flash("This damage report is already locked.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    report.status = "submitted"
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="submitted",
        title="Damage report submitted",
        details=f"Damage report #{report.id} submitted and locked.",
        target_type="damage_report",
        target_id=report.id,
    )
    db.session.commit()
    flash("Damage report submitted and locked.", "success")
    return redirect(url_for("driver.view_damage_report", report_id=report.id))


@bp.route("/damage_reports/<int:report_id>/delete", methods=["POST"])
@login_required
def delete_damage_report(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    if not _can_modify_damage_report(report):
        flash("This damage report is locked because it was submitted or the route was finalized.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    details = f"Damage report #{report.id} deleted for {report.plant_name}."
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="deleted",
        title="Damage report deleted",
        details=details,
        target_type="damage_report",
        target_id=report.id,
    )
    db.session.delete(report)
    db.session.commit()
    flash("Damage report deleted.", "success")
    return redirect(url_for("driver.damage_reports"))


@bp.route("/mobile/history")
@login_required
def mobile_history():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return render_template("mobile_history.html", reports=_mobile_report_days(30))


@bp.route("/truck-maintenance-history")
@login_required
def truck_maintenance_history():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))

    today_local_date = _today_local_date()
    todays_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=today_local_date)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    latest_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    truck_number = _normalize_truck_number(request.args.get("truck_number"))
    if not truck_number:
        source_pretrip = todays_pretrip or latest_pretrip
        truck_number = _normalize_truck_number(source_pretrip.truck_number if source_pretrip else "")

    current_pretrip_id = None
    if todays_pretrip and _same_truck_number(todays_pretrip.truck_number, truck_number):
        current_pretrip_id = todays_pretrip.id

    return render_template(
        "truck_maintenance_history.html",
        truck_number=truck_number,
        history=_truck_maintenance_history(
            truck_number,
            current_pretrip_id=current_pretrip_id,
            limit=25,
        ),
        todays_pretrip=todays_pretrip,
    )


@bp.route("/mobile/history/<report_date>")
@login_required
def mobile_day_report(report_date):
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    parsed_date = _parse_report_date(report_date)
    if parsed_date is None:
        return redirect(url_for("driver.mobile_history"))

    logs = (
        _active_driver_logs_query().filter_by(driver_id=current_user.id, date=parsed_date)
        .order_by(DriverLog.created_at.desc())
        .all()
    )
    pretrips = (
        _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=parsed_date)
        .order_by(PreTrip.created_at.desc())
        .all()
    )
    transfers = (
        _active_plant_transfers_query().filter_by(user_id=current_user.id, transfer_date=parsed_date)
        .order_by(PlantTransfer.created_at.desc())
        .all()
    )
    log_routes = _driver_log_route_context(logs)
    route_task_events = _task_route_events_for_logs(logs, _driver_route_tasks(current_user.id, parsed_date))
    log_reports = [
        {"log": log, "route": log_routes.get(log.id), "freight": _log_freight_summary(log, transfers)}
        for log in logs
    ]
    transfer_reports = [_transfer_summary(transfer) for transfer in transfers]
    today_local_date = _today_local_date()
    return render_template(
        "mobile_day_report.html",
        report_date=parsed_date,
        today_local_date=today_local_date,
        logs=logs,
        log_reports=log_reports,
        log_routes=log_routes,
        route_task_events=route_task_events,
        pretrips=pretrips,
        transfers=transfers,
        transfer_reports=transfer_reports,
    )


@bp.route("/mobile")
@login_required
def mobile_dashboard():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))

    now_local, _ = _now_local_and_utc()
    today_local_date = now_local.date()
    open_shift = _open_shift_for_driver(current_user.id)
    route_date = _dashboard_route_date_for_driver(current_user.id, today_local_date, open_shift=open_shift)
    shift_elapsed = None
    if open_shift:
        shift_elapsed = _format_duration((datetime.utcnow() - open_shift.start_time).total_seconds())

    tasks = _driver_task_queue(current_user.id)
    active_task = tasks[0] if tasks else None
    task_queue = [task for task in tasks if not active_task or task.id != active_task.id]
    queued_tasks = task_queue[:3]
    hot_task_count = len([task for task in tasks if task.is_hot])

    latest_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    todays_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=today_local_date)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    route_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=route_date)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    route_is_active = bool(open_shift or (route_pretrip and not route_pretrip.posttrip))
    active_pretrip = todays_pretrip or (route_pretrip if route_is_active else None)
    pending_posttrip = bool(active_pretrip and not active_pretrip.posttrip)
    latest_transfer = (
        _active_plant_transfers_query().filter_by(user_id=current_user.id)
        .order_by(PlantTransfer.created_at.desc())
        .first()
    )

    recent_ryder_events = (
        ActivityEvent.query.filter_by(
            user_id=current_user.id,
            category="ryder",
        )
        .order_by(ActivityEvent.created_at.desc())
        .limit(3)
        .all()
    )

    todays_logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=current_user.id, date=route_date).all(),
        key=_driver_log_sort_key,
    )
    route_context = build_route_context(driver_id=current_user.id, route_date=route_date, now=now_local)
    todays_log_routes = route_context.log_routes
    route_task_events = _task_route_events_for_logs(todays_logs, _driver_route_tasks(current_user.id, route_date))
    current_stop = route_context.current_stop
    current_stop_forecast = (
        forecast_for_stop(current_stop, now=now_local)
        if current_stop and not current_stop.depart_time
        else None
    )
    stop_forecasts = route_context.stop_timing
    next_load_prediction = route_context.next_load_prediction or build_next_load_prediction(
        current_stop=current_stop,
        driver_id=current_user.id,
        current_cargo_state=current_load_after_logs(todays_logs),
        active_dispatch_task=active_task,
        route_date=route_date,
        timing_forecast=current_stop_forecast,
        now=now_local,
    ).to_dict() if current_stop else None
    next_load_eta = next_load_prediction
    if route_context.route_status == "completed" and route_date == today_local_date:
        route_panel_title = "Route Complete"
    elif route_context.route_status == "finalized" and route_date == today_local_date:
        route_panel_title = "Route Finalized"
    elif route_date == today_local_date:
        route_panel_title = "Today's Route"
    elif route_is_active:
        route_panel_title = "Active Route"
    else:
        route_panel_title = "Last Route"
    truck_source_pretrip = active_pretrip or route_pretrip or latest_pretrip
    current_truck_number = _normalize_truck_number(
        truck_source_pretrip.truck_number if truck_source_pretrip else ""
    )
    truck_maintenance_history = _truck_maintenance_history(
        current_truck_number,
        current_pretrip_id=active_pretrip.id if active_pretrip else None,
        limit=6,
    )
    ryder_context = _ryder_followup_context(current_user.id)

    return render_template(
        "driver_mobile.html",
        active_task=active_task,
        queued_tasks=queued_tasks,
        task_queue=task_queue,
        hot_task_count=hot_task_count,
        latest_pretrip=latest_pretrip,
        todays_pretrip=todays_pretrip,
        route_pretrip=route_pretrip,
        active_pretrip=active_pretrip,
        pending_posttrip=pending_posttrip,
        latest_transfer=latest_transfer,
        recent_ryder_events=recent_ryder_events,
        open_shift=open_shift,
        shift_elapsed=shift_elapsed,
        today_local_date=today_local_date,
        route_date=route_date,
        route_panel_title=route_panel_title,
        route_is_active=route_is_active,
        todays_logs=todays_logs,
        todays_log_routes=todays_log_routes,
        route_task_events=route_task_events,
        current_stop=current_stop,
        route_state=route_context.route_state,
        route_context=route_context,
        stop_forecasts=stop_forecasts,
        current_stop_forecast=current_stop_forecast,
        next_load_eta=next_load_eta,
        next_load_prediction=next_load_prediction,
        current_truck_number=current_truck_number,
        truck_maintenance_history=truck_maintenance_history,
        truck_issue_choices=TRUCK_ISSUE_CHOICES,
        **ryder_context,
    )


@bp.route("/mobile/ryder-service", methods=["POST"])
@login_required
def mobile_ryder_service():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))

    pending_ryder_event = _open_ryder_event(current_user.id)
    truck_number = (request.form.get("truck_number") or "").strip()
    issue_code = (request.form.get("issue") or "").strip()
    outcome = (request.form.get("outcome") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    next_target = (request.form.get("next") or "mobile").strip()

    if pending_ryder_event:
        truck_number = truck_number or _detail_value(pending_ryder_event.details, "Truck")
        issue_code = issue_code or _detail_value(pending_ryder_event.details, "Issue")
    truck_number = truck_number or "Truck not set"
    issue = TRUCK_ISSUE_LABELS.get(issue_code, issue_code).strip()

    if not issue or outcome not in RYDER_OUTCOME_LABELS:
        flash("Choose what is wrong with the truck and the Ryder status.", "warning")
        return redirect(url_for("driver.new_driving_log" if next_target == "new_log" else "driver.mobile_dashboard"))

    details = f"Truck: {truck_number}; Issue: {issue}; Outcome: {RYDER_OUTCOME_LABELS[outcome]}"
    if pending_ryder_event and outcome in RYDER_CLOSING_ACTIONS:
        details = f"{details}; Ryder time: {_format_duration((datetime.utcnow() - pending_ryder_event.created_at).total_seconds())}"
    if notes:
        details = f"{details}; Notes: {notes}"
    record_activity(
        user_id=current_user.id,
        category="ryder",
        action=outcome,
        title=RYDER_OUTCOME_LABELS[outcome],
        details=details,
        target_type="ryder_service",
        target_id=pending_ryder_event.id if pending_ryder_event and outcome in RYDER_CLOSING_ACTIONS else None,
    )
    flash("Ryder service status saved.", "success")
    return redirect(url_for("driver.new_driving_log" if next_target == "new_log" else "driver.mobile_dashboard"))


@bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if current_user.role == "driver":
        return redirect(url_for("driver.mobile_dashboard"))

    logs = (
        _active_driver_logs_query().filter_by(driver_id=current_user.id)
        .order_by(DriverLog.created_at.desc())
        .limit(5)
        .all()
    )
    pretrips = (
        _active_pretrips_query().filter_by(user_id=current_user.id)
        .order_by(PreTrip.created_at.desc())
        .limit(5)
        .all()
    )
    tasks = (
        Task.query.filter_by(assigned_to=current_user.id)
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    plant_transfers = (
        _active_plant_transfers_query().filter_by(user_id=current_user.id)
        .order_by(PlantTransfer.created_at.desc())
        .limit(5)
        .all()
    )

    dm_form = DirectMessageForm()
    all_users = User.query.filter(User.id != current_user.id).all()
    dm_form.receiver_id.choices = [(u.id, u.username) for u in all_users]

    if dm_form.validate_on_submit():
        new_dm = DirectMessage(
            sender_id=current_user.id,
            receiver_id=dm_form.receiver_id.data,
            content=dm_form.content.data,
        )
        db.session.add(new_dm)
        db.session.commit()
        socketio.emit(
            "new_direct_message",
            {
                "sender": current_user.username,
                "receiver_id": dm_form.receiver_id.data,
                "content": dm_form.content.data,
            },
        )
        flash("Message sent!", "success")
        return redirect(url_for("driver.dashboard"))

    inbox = (
        DirectMessage.query.filter_by(receiver_id=current_user.id)
        .order_by(DirectMessage.timestamp.desc())
        .all()
    )
    outbox = (
        DirectMessage.query.filter_by(sender_id=current_user.id)
        .order_by(DirectMessage.timestamp.desc())
        .all()
    )

    return render_template(
        "dashboard.html",
        logs=logs,
        pretrips=pretrips,
        tasks=tasks,
        plant_transfers=plant_transfers,
        dm_form=dm_form,
        inbox=inbox,
        outbox=outbox,
    )


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.employee_id = form.employee_id.data
        current_user.department = form.department.data
        current_user.email = form.email.data
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="profile",
            action="updated",
            title="Profile updated",
            details="Account profile information changed.",
            target_type="user",
            target_id=current_user.id,
        )
        flash("Profile updated!", "success")
        return redirect(url_for("driver.profile"))
    return render_template("profile.html", profile_form=form)


@bp.route("/tasks")
@bp.route("/list_tasks")
@login_required
def list_tasks():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
    else:
        tasks = (
            _active_driver_tasks_query()
            .order_by(Task.created_at.desc())
            .all()
        )
    return render_template("list_tasks.html", tasks=tasks)


def _get_driver_task_or_redirect(task_id, *, allow_open=True):
    task = Task.query.get_or_404(task_id)
    if current_user.role != "driver":
        flash("Driver credentials required.", "warning")
        return None
    if task.assigned_to == current_user.id:
        return task
    if allow_open and task.assigned_to is None and task.status == "pending":
        return task
    flash("That task is not assigned to you.", "danger")
    return None


def _current_hot_part_stop_context(driver_id):
    route_date = _active_route_date_for_driver(driver_id)
    open_log = (
        _active_driver_logs_query()
        .filter_by(driver_id=driver_id, date=route_date)
        .filter(DriverLog.depart_time.is_(None))
        .order_by(DriverLog.created_at.desc(), DriverLog.id.desc())
        .first()
    )
    if open_log:
        return open_log
    return (
        _active_driver_logs_query()
        .filter_by(driver_id=driver_id, date=route_date)
        .order_by(DriverLog.created_at.desc(), DriverLog.id.desc())
        .first()
    )


def _claim_hot_task_for_driver(task):
    changed = False
    now = datetime.utcnow()
    if task.assigned_to is None:
        task.assigned_to = current_user.id
        changed = True
    if task.status == "pending":
        task.status = "in-progress"
        changed = True
    if not task.accepted_at:
        task.accepted_at = now
        task.accepted_by_id = current_user.id
        changed = True
    return changed


def _task_socket_payload(task):
    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "assigned_driver_id": task.assigned_to,
        "accepted_by_id": task.accepted_by_id,
        "completed_by_id": task.completed_by_id,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _hot_part_context(task):
    stop = _current_hot_part_stop_context(current_user.id)
    hot_move = ensure_hot_move_for_task(task, driver_id=current_user.id)
    return hot_move, stop


@bp.route("/tasks/<int:task_id>")
@login_required
def view_task(task_id):
    task = _get_driver_task_or_redirect(task_id)
    if task is None:
        return _task_redirect()
    task_events = (
        ActivityEvent.query.filter_by(target_type="task", target_id=task.id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(20)
        .all()
    )
    hot_part_query = _active_driver_logs_query().filter_by(driver_id=current_user.id)
    if task.part_number:
        hot_part_query = hot_part_query.filter(DriverLog.part_number == task.part_number)
    else:
        hot_part_query = hot_part_query.filter(DriverLog.hot_parts.is_(True))
    hot_part_logs = hot_part_query.order_by(DriverLog.created_at.desc()).limit(8).all()
    hot_move = None
    hot_part_proof = None
    if task.is_hot:
        hot_move = HotMove.query.filter_by(move_id=task.id).order_by(HotMove.id.asc()).first()
        hot_part_proof = build_hot_part_proof(hot_move, task=task)
    return render_template(
        "driver_task_detail.html",
        task=task,
        task_events=task_events,
        hot_part_logs=hot_part_logs,
        hot_move=hot_move,
        hot_part_proof=hot_part_proof,
    )


@bp.route("/tasks/<int:task_id>/hot-proof", methods=["POST"])
@login_required
def record_hot_part_proof(task_id):
    task = _get_driver_task_or_redirect(task_id)
    if task is None:
        return jsonify({"error": "That hot move is not assigned to you."}), 403
    if not task.is_hot:
        return jsonify({"error": "Hot part proof is only available for hot moves."}), 400

    payload = request.get_json(silent=True) or request.form
    event_type = (payload.get("event_type") or payload.get("action") or "").strip()
    allowed = {"label_scanned", "picked_up", "dropped_off", "cant_find_part", "wrong_part", "delay_reported"}
    if event_type not in allowed:
        return jsonify({"error": "Choose a hot part proof action."}), 400

    _claim_hot_task_for_driver(task)
    if event_type == "dropped_off":
        task.status = "completed"
        task.completed_at = task.completed_at or datetime.utcnow()
        task.completed_by_id = current_user.id

    hot_move, stop = _hot_part_context(task)
    try:
        event = record_hot_part_event(
            hot_move,
            event_type,
            driver_id=current_user.id,
            stop_id=getattr(stop, "id", None),
            plant_id=getattr(stop, "plant_name", None),
            raw_scan_value=payload.get("raw_scan_value") or payload.get("value"),
            barcode_format=payload.get("barcode_format"),
            created_offline=str(payload.get("created_offline") or "").lower() in {"1", "true", "yes"},
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    record_activity(
        user_id=current_user.id,
        category="hot_part",
        action=event_type,
        title="Hot part proof recorded",
        details=f"{task.part_number or task.title}: {event_type.replace('_', ' ')}",
        target_type="hot_move",
        target_id=hot_move.id,
        commit=False,
    )
    db.session.commit()
    socketio.emit("task_updated", _task_socket_payload(task))
    proof = build_hot_part_proof(hot_move, task=task)
    proof_payload = {
        "hot_part_number": proof["hot_part_number"],
        "current_status": proof["current_status"],
        "has_scan_proof": proof["has_scan_proof"],
        "has_photo_proof": proof["has_photo_proof"],
        "proof_sentence": proof["proof_sentence"],
        "narrative": proof["narrative"],
        "open_exception": proof["open_exception"],
    }
    return jsonify({"event": hot_part_event_payload(event), "proof": proof_payload})


@bp.route("/tasks/<int:task_id>/hot-proof-photo", methods=["POST"])
@login_required
def record_hot_part_photo(task_id):
    task = _get_driver_task_or_redirect(task_id)
    if task is None:
        flash("That hot move is not assigned to you.", "danger")
        return _task_redirect()
    if not task.is_hot:
        flash("Hot part photos are only available for hot moves.", "warning")
        return _task_redirect()

    _claim_hot_task_for_driver(task)
    hot_move, stop = _hot_part_context(task)
    try:
        photo, event = save_hot_part_photo(
            hot_move,
            request.files.get("photo"),
            uploaded_by_id=current_user.id,
            stop_id=getattr(stop, "id", None),
            plant_id=getattr(stop, "plant_name", None),
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("driver.view_task", task_id=task.id))

    record_activity(
        user_id=current_user.id,
        category="hot_part",
        action="photo_added",
        title="Hot part photo proof recorded",
        details=f"{task.part_number or task.title}: photo {photo.id}",
        target_type="hot_move",
        target_id=hot_move.id,
        commit=False,
    )
    db.session.commit()
    socketio.emit("task_updated", _task_socket_payload(task))
    flash("Hot part photo proof saved.", "success")
    return redirect(url_for("driver.view_task", task_id=task.id))


@bp.route("/tasks/<int:task_id>/accept", methods=["POST"])
@login_required
def accept_task(task_id):
    task = _get_driver_task_or_redirect(task_id)
    if task is None:
        return _task_redirect()
    if task.status != "pending":
        flash("Only pending tasks can be accepted.", "warning")
    else:
        task.assigned_to = current_user.id
        task.status = "in-progress"
        task.accepted_at = datetime.utcnow()
        task.accepted_by_id = current_user.id
        if task.is_hot:
            hot_move, stop = _hot_part_context(task)
            record_hot_part_event(
                hot_move,
                "driver_accepted",
                driver_id=current_user.id,
                stop_id=getattr(stop, "id", None),
                plant_id=getattr(stop, "plant_name", None),
            )
        record_activity(
            user_id=current_user.id,
            category="task",
            action="accepted",
            title="Task accepted",
            details=task.title,
            target_type="task",
            target_id=task.id,
        )
        socketio.emit(
            "task_updated",
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "assigned_driver_id": task.assigned_to,
                "accepted_by_id": task.accepted_by_id,
                "completed_by_id": task.completed_by_id,
            },
        )
        flash("Task accepted.", "success")
    return _task_redirect()


@bp.route("/tasks/<int:task_id>/decline", methods=["POST"])
@login_required
def decline_task(task_id):
    task = _get_driver_task_or_redirect(task_id, allow_open=False)
    if task is None:
        return _task_redirect()
    if task.status == "completed":
        flash("Completed tasks cannot be declined.", "warning")
    else:
        task.status = "declined"
        task.assigned_to = None
        record_activity(
            user_id=current_user.id,
            category="task",
            action="declined",
            title="Task declined",
            details=task.title,
            target_type="task",
            target_id=task.id,
        )
        socketio.emit(
            "task_updated",
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "assigned_driver_id": task.assigned_to,
                "accepted_by_id": task.accepted_by_id,
                "completed_by_id": task.completed_by_id,
            },
        )
        flash("Task declined.", "warning")
    return _task_redirect()


@bp.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    task = _get_driver_task_or_redirect(task_id)
    if task is None:
        return _task_redirect()
    if task.status not in {"pending", "in-progress"}:
        flash("Only active tasks can be completed.", "warning")
    else:
        task.assigned_to = current_user.id
        if not task.accepted_at:
            task.accepted_at = datetime.utcnow()
            task.accepted_by_id = current_user.id
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.completed_by_id = current_user.id
        if task.is_hot:
            hot_move, stop = _hot_part_context(task)
            if not any(event.event_type == "dropped_off" for event in hot_move.events):
                record_hot_part_event(
                    hot_move,
                    "dropped_off",
                    driver_id=current_user.id,
                    stop_id=getattr(stop, "id", None),
                    plant_id=getattr(stop, "plant_name", None),
                )
        record_activity(
            user_id=current_user.id,
            category="task",
            action="completed",
            title="Task completed",
            details=task.title,
            target_type="task",
            target_id=task.id,
        )
        socketio.emit(
            "task_updated",
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "assigned_driver_id": task.assigned_to,
                "accepted_by_id": task.accepted_by_id,
                "completed_by_id": task.completed_by_id,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            },
        )
        flash("Task completed.", "success")
    return _task_redirect()


@bp.route("/map")
@login_required
def show_map():
    return render_template("map.html", google_api_key="YOUR_GOOGLE_MAPS_API_KEY")
