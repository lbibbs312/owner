"""Driver-facing routes.

Holds the routes a driver hits during a shift: dashboard, pre-trip / post-trip
inspections, driver logs, shift start/end, end-of-day. Currently only the
pre-trip / post-trip family lives here; the rest will move in subsequent sub-
PRs of PR-5c.
"""
from datetime import datetime, date, timedelta
from functools import wraps
import io
import mimetypes
import os
import re
import shutil
import textwrap
from uuid import uuid4

import pytz
from flask import abort, current_app, flash, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_
from werkzeug.datastructures import CombinedMultiDict, MultiDict
from werkzeug.utils import secure_filename

from app.blueprints.driver import bp
from app.extensions import db
from app.extensions import socketio
from app.models.case import ExceptionEvent
from app.forms.damage import DamageReportForm
from app.forms.log import DepartForm, DriverLogForm, TRUCK_ISSUE_CHOICES, TRUCK_ISSUE_LABELS, ensure_legacy_plant_choice
from app.forms.plant_transfer import PlantTransferForm
from app.forms.shift import EndOfDayForm
from app.forms.trip import PostTripForm, PreTripForm
from app.forms.user import ProfileForm
from app.models.duty import DutyStatusEvent
from app.services import duty_log as duty_log_service
from app.services import hos as hos_service
from app.services.activity import record_activity
from app.services.audit import model_snapshot, record_audit_event
from app.services.accident_packets import (
    accident_form_required,
    accident_media_path,
    build_accident_packet,
    create_accident_report_from_form,
    save_packet_media,
)
from app.services.evidence_packet import build_damage_evidence_packet
from app.services.file_integrity import sha256_file
from app.services.ifta_worksheets import build_ifta_packet, create_ifta_worksheet_from_form, ifta_receipt_available, ifta_receipt_path
from app.services.packet_classification import (
    PacketClassification,
    classify_damage_report,
    classify_packet_text,
    packet_label_for_report,
)
from app.services.report_context import build_report_context
from app.services.autolog import remember_place
from app.services.google_places import lookup_destination_place, nearby_place_candidates
from app.services.document_numbers import (
    document_meta,
    eod_document_number,
    evidence_document_number,
    generated_at_label,
    pretrip_document_number,
    route_document_number,
    transfer_document_number,
)
from app.services.driver_wait import elapsed_wait_minutes, elapsed_wait_seconds, wait_label_for_log, wait_minutes_for_log
from app.services.simple_pdf import LANDSCAPE_LETTER, LETTER, SimplePdf
from app.services.route_documents import collect_route_documents, render_document_appendix
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
    freight_cargo_text,
    freight_load_destined_here,
    is_empty_load,
    is_freight_load,
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
from app.services.route_context import build_route_context, build_route_cta_context, route_finalization_event, unresolved_departure_logs
from app.services.flow_events import FlowEventService
from app.services.route_map import build_driver_route_map_context, build_driver_map_mode_context
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
    AccidentIncidentReport,
    IftaFuelRecord,
    IftaWorksheet,
    DamagePhoto,
    DamageReport,
    HotMove,
    PartScanEvent,
    PlaceMemory,
    DriverLog,
    DriverLogPhoto,
    DraftEntry,
    PlantTransfer,
    PlantTransferLine,
    PostTrip,
    ProofMediaFile,
    PreTrip,
    RouteBreak,
    ShiftRecord,
    Task,
    User,
)


PLANT_TRANSFER_LINE_COUNT = 20
DRIVER_LOG_AUDIT_FIELDS = ["plant_name", "load_size", "depart_load_size", "secondary_load", "downtime_reason", "part_number", "hot_parts", "arrive_time", "depart_time", "dock_wait_minutes", "maintenance", "fuel", "fuel_mileage", "meeting", "location_address", "destination_address", "gps_latitude", "gps_longitude", "gps_accuracy_m"]
PLANT_TRANSFER_AUDIT_FIELDS = ["transfer_number", "transfer_date", "ship_to", "ship_from", "trailer_number", "driver_name", "driver_initials", "transfer_time", "loaded_by"]
DAMAGE_REPORT_AUDIT_FIELDS = [
    "reported_by_id",
    "task_id",
    "driver_log_id",
    "plant_transfer_id",
    "truck_number",
    "trailer_number",
    "plant_name",
    "damage_time",
    "stage",
    "move_reference",
    "description",
    "status",
    "created_at",
    "resolved_at",
]
RYDER_CLOSING_ACTIONS = {"fixed", "left", "rental"}
MAX_REASONABLE_DAILY_ROUTE_MILES = 1000


def _append_driver_log_flow_event(log, event_type, *, notes=None, payload=None, source="mobile"):
    FlowEventService.append_event(
        event_type=event_type,
        entity_type="route_stop",
        entity_id=log.id,
        route_id=f"driver:{log.driver_id}:date:{log.date}" if log.driver_id and log.date else None,
        stop_id=log.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        origin_node_id=log.plant_name,
        destination_node_id=destination_from_load(log.depart_load_size) or log.plant_name,
        source=source,
        payload_json={
            "plant_name": log.plant_name,
            "arrive_time": log.arrive_time,
            "depart_time": log.depart_time,
            "arrival_load": log.load_size,
            "departure_load": log.depart_load_size,
            "secondary_load": log.secondary_load,
            "commodity": log.commodity,
            "weight": log.weight,
            "location_address": getattr(log, "location_address", None),
            "destination_address": getattr(log, "destination_address", None),
            "gps_latitude": getattr(log, "gps_latitude", None),
            "gps_longitude": getattr(log, "gps_longitude", None),
            "gps_accuracy_m": getattr(log, "gps_accuracy_m", None),
            "no_pickup": bool(log.no_pickup),
            **(payload or {}),
        },
        notes=notes,
        commit=False,
    )


def _first_record_id(records):
    return records[0].id if records else None


def _truck_from_pretrips(pretrips):
    first = pretrips[0] if pretrips else None
    return first.truck_number if first else None


def _pretrip_document_meta(pretrip, page="1 of 1"):
    return document_meta("DAILY VEHICLE INSPECTION REPORT", pretrip_document_number(pretrip), page=page)


def _route_document_meta(route_date, driver, logs, pretrips, page="1 of 1"):
    return document_meta(
        "DRIVER LOG SHEET",
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
    return document_meta(packet_label_for_report(report), evidence_document_number(report), page=page)


def _draw_pdf_header(pdf, title, document_no, generated_at, page_label, *, driver=None, truck=None, date_value=None):
    pdf.brand_signature()
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


def _draw_route_sheet_pdf_header(pdf, meta, *, driver=None, truck=None, date_value=None, page_label=None):
    date_label = date_value.strftime("%b %d, %Y") if hasattr(date_value, "strftime") else str(date_value or "")
    truck_date = f"{truck or 'Truck not set'} \xb7 {date_label}"
    pdf.text(36, 764, "DRIVER", size=8, bold=True)
    pdf.text(36, 748, (driver or "").upper(), size=15, bold=True)
    pdf.text(36, 732, truck_date, size=8, bold=True)
    pdf.text(420, 748, f"Route Sheet No: {meta['document_no']}", size=8, bold=True)
    pdf.text(420, 734, f"Generated: {meta['generated_at']}", size=8)
    pdf.text(420, 720, f"Page: {page_label or meta['page']}", size=8)
    pdf.line(36, 712, 576, 712, width=1.0)
    pdf.text(36, 694, "DRIVER LOG SHEET", size=12, bold=True)

RYDER_OUTCOME_LABELS = {
    "headed": "Headed to shop",
    "fixed": "Fixed at shop",
    "left": "Shop kept it",
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
    "driver_reports",
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
    "mobile_end_route",
    "request_manager_review",
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
    "new_ifta_worksheet",
    "view_ifta_worksheet",
    "ifta_worksheet_packet",
    "ifta_receipt",
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
    flash("Driver access required. Sign in to continue.", "warning")
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
            current_app.logger.warning("Invalid driver log date query: %s", date_str)
    return _today_local_date()


def _can_driver_change_same_day(record_user_id, record_date, record_label, action):
    if current_user.role != "driver":
        flash("Driver access required.", "warning")
        return False
    if record_user_id != current_user.id:
        flash(f"Not authorized to {action} another driver's {record_label}.", "danger")
        return False
    if record_date != _today_local_date():
        flash(f"Only same-day {record_label} entries can be changed.", "warning")
        return False
    if _driver_route_record_finalized(record_user_id, record_date):
        flash(f"That route is finalized. {record_label.title()} entries cannot be changed.", "warning")
        return False
    return True


def _driver_route_record_finalized(driver_id, route_date):
    return _route_finalized_for_driver_date(driver_id, route_date)


def _can_driver_mutate_route_record(record_user_id, record_date, record_label, action):
    return _can_driver_change_same_day(record_user_id, record_date, record_label, action)


def _guard_route_record_mutation(record_user_id, record_date, record_label, action, *, wants_json=False, next_url=None):
    if _can_driver_mutate_route_record(record_user_id, record_date, record_label, action):
        return None
    if wants_json:
        if _driver_route_record_finalized(record_user_id, record_date):
            message = f"That route is finalized. {record_label.title()} entries cannot be changed."
        else:
            message = f"Not authorized to {action} this {record_label}."
        return jsonify({"ok": False, "error": message}), 403
    return redirect(next_url or _driver_logs_url_for_date(record_date))


def _guard_driver_log_mutation(log, action, *, wants_json=False, next_url=None):
    return _guard_route_record_mutation(
        log.driver_id,
        log.date,
        "driver log",
        action,
        wants_json=wants_json,
        next_url=next_url,
    )


def _driver_log_sort_key(log):
    return (log.date or date.min, log.arrive_time or "", log.created_at or datetime.min, log.id or 0)


def _driver_log_route_context(logs):
    return build_driver_log_route_context(logs)


def _route_finalized_for_driver_date(driver_id, route_date):
    return route_finalization_event(driver_id, route_date) is not None


def _active_driver_logs_query():
    return DriverLog.query.filter(DriverLog.deleted_at.is_(None))


def _current_driver_load(driver_id, route_date=None, *, route_context=None):
    route_date = route_date or _today_local_date()
    open_shift = _open_shift_for_driver(driver_id)
    open_shift_route_date = _shift_route_date(open_shift)
    route_still_active = bool(open_shift and (not open_shift_route_date or open_shift_route_date == route_date))
    route_context = route_context or build_route_context(driver_id=driver_id, route_date=route_date)
    if route_context.route_finalized and not route_still_active:
        return current_load_after_logs([])
    cargo = route_context.current_cargo
    # Freight loads are freeform strings the plant-destination tracker can't
    # parse, so it reports Empty mid-haul. For day drivers the truth is simple:
    # the truck carries whatever the latest closed stop departed with.
    if (
        getattr(current_user, "is_day_driver", False)
        and getattr(current_user, "id", None) == driver_id
        and (not cargo or is_empty_load((cargo or {}).get("value")))
    ):
        last = (
            _active_driver_logs_query()
            .filter(DriverLog.driver_id == driver_id, DriverLog.depart_time.isnot(None))
            .order_by(DriverLog.id.desc())
            .first()
        )
        if last and not is_empty_load(last.depart_load_size):
            cargo = dict(cargo or {})
            label = (last.commodity or last.depart_load_size or "").strip()
            if last.weight:
                label = f"{label} · {last.weight} lbs"
            cargo["value"] = freight_cargo_text(last.depart_load_size)
            cargo["cargo_display"] = freight_cargo_text(label)
            if last.destination:
                cargo["destination"] = last.destination
    return cargo


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
    departed_empty = (log.depart_load_size or "").strip().lower() in {"", "empty"}
    onboard_commodity = None if departed_empty else (log.commodity or None)
    onboard_weight = None if departed_empty else (log.weight or None)
    changed = []
    for next_index in range(current_index + 1, len(logs)):
        next_log = logs[next_index]
        if next_log.depart_time:
            continue
        expected = current_load_after_logs(logs[:next_index])
        expected_primary = expected.get("value") or "Empty"
        expected_secondary = expected.get("secondary_value") or None
        log_changed = False
        if next_log.load_size != expected_primary or (next_log.secondary_load or None) != expected_secondary:
            next_log.load_size = expected_primary
            next_log.secondary_load = expected_secondary
            log_changed = True
        # Day-driver freight detail carries forward with the load until it changes.
        if (next_log.commodity or None) != onboard_commodity:
            next_log.commodity = onboard_commodity
            log_changed = True
        if (next_log.weight or None) != onboard_weight:
            next_log.weight = onboard_weight
            log_changed = True
        if log_changed:
            changed.append(next_log)
    return changed[-1] if changed else None


def _onboard_day_cargo(driver_id, route_date):
    """Most-recent commodity/weight still onboard for a day driver.

    Returns ``(None, None)`` once the latest departure left empty (unloaded).
    """
    logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=driver_id, date=route_date).all(),
        key=_driver_log_sort_key,
    )
    for log in reversed(logs):
        if log.depart_time and (log.depart_load_size or "").strip().lower() in {"", "empty"}:
            return (None, None)
        if log.commodity or log.weight:
            return (log.commodity, log.weight)
    return (None, None)


def _prefill_day_driver_cargo(form, driver_id, route_date):
    """Auto-fill the arrival form's commodity/weight from what is still onboard."""
    commodity, weight = _onboard_day_cargo(driver_id, route_date)
    if commodity and not (form.commodity.data or "").strip():
        form.commodity.data = commodity
    if weight and not (form.weight.data or "").strip():
        form.weight.data = weight


def _driver_log_context_for(log):
    route_context = build_route_context(
        driver_id=log.driver_id,
        route_date=log.date,
        selected_log_id=log.id,
    )
    return route_context.log_routes.get(log.id, {})


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


def _open_shifts_for_driver(driver_id):
    return (
        ShiftRecord.query.filter_by(user_id=driver_id, end_time=None)
        .order_by(ShiftRecord.start_time.asc(), ShiftRecord.id.asc())
        .all()
    )


def _close_shift_record(shift, ended_at):
    shift.end_time = ended_at
    elapsed_hours = (shift.end_time - shift.start_time).total_seconds() / 3600.0
    shift.total_hours = max(0, elapsed_hours)


def _end_open_shifts_for_driver(driver_id, ended_at=None):
    ended_at = ended_at or datetime.utcnow()
    open_shifts = _open_shifts_for_driver(driver_id)
    for shift in open_shifts:
        _close_shift_record(shift, ended_at)
    # Ending the shift also ends any break the driver forgot to close —
    # otherwise it keeps "running" on the board and prints as "in progress"
    # on documents generated after release.
    open_breaks = RouteBreak.query.filter_by(user_id=driver_id, end_time=None).all()
    for brk in open_breaks:
        brk.end_time = max(brk.start_time or ended_at, ended_at)
    return open_shifts


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


def _shift_elapsed_hours(shift, now_utc=None):
    if not shift or not shift.start_time:
        return 0
    now_utc = now_utc or datetime.utcnow()
    start_time = shift.start_time
    if start_time.tzinfo is not None:
        start_time = start_time.astimezone(pytz.utc).replace(tzinfo=None)
    return max(0, (now_utc - start_time).total_seconds() / 3600.0)


def _is_stale_open_shift(shift, today_local_date=None, *, stale_after_hours=18):
    if not shift:
        return False
    today_local_date = today_local_date or _today_local_date()
    shift_date = _shift_route_date(shift)
    if not shift_date or shift_date >= today_local_date:
        return False
    return _shift_elapsed_hours(shift) >= stale_after_hours


def _driver_logs_url_for_date(route_date):
    if route_date:
        return url_for("driver.driver_logs", date=route_date.isoformat())
    return url_for("driver.driver_logs")


def _latest_open_pretrip(driver_id):
    pretrips = (
        _active_pretrips_query()
        .filter_by(user_id=driver_id)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .limit(20)
        .all()
    )
    return next((pretrip for pretrip in pretrips if not pretrip.posttrip), None)


def _is_stale_open_pretrip(pretrip, today_local_date=None, open_shift=None):
    if not pretrip or getattr(pretrip, "posttrip", None):
        return False
    today_local_date = today_local_date or _today_local_date()
    pretrip_date = getattr(pretrip, "pretrip_date", None)
    if not pretrip_date or pretrip_date >= today_local_date:
        return False
    if open_shift and getattr(open_shift, "pretrip_id", None) == getattr(pretrip, "id", None):
        return _is_stale_open_shift(open_shift, today_local_date)
    return True


def _active_route_date_for_driver(driver_id, today_local_date=None, open_shift=None):
    today_local_date = today_local_date or _today_local_date()
    open_shift = open_shift if open_shift is not None else _open_shift_for_driver(driver_id)
    shift_date = _shift_route_date(open_shift)
    if shift_date and not _is_stale_open_shift(open_shift, today_local_date):
        return shift_date
    open_pretrip = _latest_open_pretrip(driver_id)
    if open_pretrip and open_pretrip.pretrip_date and not _is_stale_open_pretrip(
        open_pretrip,
        today_local_date,
        open_shift=open_shift,
    ):
        return open_pretrip.pretrip_date
    return today_local_date


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
    return today_local_date


def _requested_mobile_route_date():
    date_str = request.args.get("date")
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _mobile_route_date_options(driver_id, route_date, today_local_date):
    options = [
        {
            "label": "Today",
            "date": today_local_date,
            "active": route_date == today_local_date,
            "url": url_for("driver.mobile_dashboard", date=today_local_date.isoformat()),
        }
    ]
    previous = _latest_driver_route_date(driver_id)
    if previous and previous != today_local_date:
        options.append(
            {
                "label": "Previous Route",
                "date": previous,
                "active": route_date == previous,
                "url": url_for("driver.mobile_dashboard", date=previous.isoformat()),
            }
        )
    if route_date and route_date not in {item["date"] for item in options}:
        options.append(
            {
                "label": "Selected Date",
                "date": route_date,
                "active": True,
                "url": url_for("driver.mobile_dashboard", date=route_date.isoformat()),
            }
        )
    return options


def _route_cta_urls(route_date, current_stop=None, active_pretrip=None, pending_posttrip=False, route_context=None):
    date_value = route_date.isoformat() if route_date else _today_local_date().isoformat()
    add_stop_args = {"next": "mobile"}
    next_stop_context = getattr(route_context, "next_stop_context", None) or {}
    if next_stop_context.get("source_log_id"):
        add_stop_args["from_log_id"] = next_stop_context["source_log_id"]
    if next_stop_context.get("destination"):
        add_stop_args["expected_destination"] = next_stop_context["destination"]
    urls = {
        "add_damage": url_for("driver.new_damage_report"),
        "add_note": url_for("driver.new_damage_report"),
        "add_stop": url_for("driver.new_driving_log", **add_stop_args),
        "end_route": url_for("driver.mobile_end_route"),
        "attach_document": url_for("driver.new_plant_transfer"),
        "finalize_route": url_for("driver.end_of_day_summary"),
        "print_route": url_for("driver.driver_logs_print", date=date_value),
        "route_history": url_for("driver.mobile_history"),
        "start_shift": url_for("driver.new_pretrip"),
        "view_route": url_for("driver.driver_logs", date=date_value),
    }
    if current_stop:
        urls["confirm_cargo"] = url_for("driver.pickup_driver_log", log_id=current_stop.id)
        urls["record_departure"] = url_for("driver.depart_driver_log", log_id=current_stop.id)
    if (pending_posttrip or (active_pretrip and not active_pretrip.posttrip)) and active_pretrip:
        urls["posttrip"] = url_for("driver.do_posttrip", pretrip_id=active_pretrip.id)
    return urls


def _route_has_in_transit_cargo(route_context):
    current_cargo = getattr(route_context, "current_cargo", None)
    if not isinstance(current_cargo, dict):
        return False
    cargo_value = current_cargo.get("cargo_display") or current_cargo.get("value")
    return bool(
        current_cargo.get("destination")
        or current_cargo.get("destination_label")
        or current_cargo.get("secondary_destination")
        or current_cargo.get("secondary_destination_label")
        or not is_empty_load(cargo_value)
    )


def _route_can_finish_after_closed_stops(route_context, route_date, today_local_date):
    if not route_date or not today_local_date or route_date != today_local_date:
        return False
    if getattr(route_context, "route_finalized", False):
        return False
    if getattr(route_context, "current_stop", None) is not None:
        return False
    if not getattr(route_context, "all_departed", False):
        return False
    if _route_has_in_transit_cargo(route_context):
        return False
    return bool(getattr(route_context, "rows", None))


def _route_can_end_at_current_stop(route_context, route_date, today_local_date):
    current_stop = getattr(route_context, "current_stop", None)
    if not current_stop or getattr(current_stop, "depart_time", None):
        return False
    if not route_date or not today_local_date or route_date != today_local_date:
        return False
    if getattr(route_context, "route_finalized", False):
        return False
    logs = [row.get("log") for row in (getattr(route_context, "rows", None) or []) if row.get("log")]
    if not logs or logs[-1].id != current_stop.id:
        return False
    return not unresolved_departure_logs(logs, route_finalized=True)


def _route_has_completed_posttrip(route_context, active_pretrip):
    if active_pretrip and active_pretrip.posttrip:
        return True
    return getattr(route_context, "posttrip_status", None) == "complete"


def _apply_route_end_cta(route_cta, route_context, active_pretrip, route_date, today_local_date):
    posttrip_complete = _route_has_completed_posttrip(route_context, active_pretrip)
    if posttrip_complete and _route_can_end_at_current_stop(route_context, route_date, today_local_date):
        patched = dict(route_cta or {})
        route_message = "Use the current stop as the route end. No departure will be created."
        patched.update(
            {
                "route_display_mode": "route_end_ready",
                "next_action": "End Route Here",
                "primary_cta": {"label": "End Route Here", "action": "end_route", "style": "primary"},
                "secondary_cta": {"label": "View Route Sheet", "action": "view_route", "style": "ghost"},
                "allowed_actions": ["end_route", "view_route", "print_route", "attach_document"],
                "route_state_message": route_message,
                "show_finalize_button": True,
                "show_posttrip_button": False,
            }
        )
        return patched
    if _route_can_finish_after_closed_stops(route_context, route_date, today_local_date):
        patched = dict(route_cta or {})
        proof_missing = bool(patched.get("proof_missing"))
        if not _route_has_completed_posttrip(route_context, active_pretrip):
            return route_cta
        route_message = "All recorded stops are closed. Finalize the route to lock the route sheet."
        if proof_missing:
            route_message = (
                "Document proof is missing. Attach it if required by your company, "
                "or finalize the route if the record is ready."
            )
        patched.update(
            {
                "route_display_mode": "route_end_ready",
                "next_action": "Finalize Route",
                "primary_cta": {"label": "Finalize Route", "action": "end_route", "style": "primary"},
                "secondary_cta": {"label": "View Route Sheet", "action": "view_route", "style": "ghost"},
                "allowed_actions": ["end_route", "view_route", "print_route", "attach_document"],
                "route_state_message": route_message,
                "show_finalize_button": True,
                "show_posttrip_button": False,
            }
        )
        return patched
    return route_cta


def _posttrip_due_for_route(active_pretrip, route_context, *, route_is_active=False, finalizing=False):
    if getattr(route_context, "posttrip_status", None) == "complete":
        return False
    if getattr(route_context, "route_finalized", False):
        return False
    if not active_pretrip or active_pretrip.posttrip:
        return False
    if finalizing:
        return True
    if route_is_active:
        return False
    return getattr(route_context, "route_status", None) in {"completed", "finalized"}


def _route_pretrips_for_driver_date(driver_id, route_date):
    if not driver_id or not route_date:
        return []
    return (
        _active_pretrips_query()
        .filter_by(user_id=driver_id, pretrip_date=route_date)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .all()
    )


def _select_route_pretrip(pretrips, *, route_context=None, open_shift=None):
    pretrips = list(pretrips or [])
    if not pretrips:
        return None
    posttrip_complete = getattr(route_context, "posttrip_status", None) == "complete"
    route_status = getattr(route_context, "route_status", None)
    open_shift_pretrip_id = getattr(open_shift, "pretrip_id", None)

    if route_status == "active" and open_shift_pretrip_id:
        for pretrip in pretrips:
            if pretrip.id == open_shift_pretrip_id:
                return pretrip

    if posttrip_complete:
        completed = [pretrip for pretrip in pretrips if pretrip.posttrip]
        if completed:
            return completed[0]

    if route_status in {"completed", "finalized"}:
        open_pretrip = next((pretrip for pretrip in pretrips if not pretrip.posttrip), None)
        if open_pretrip:
            return open_pretrip

    return pretrips[0]


def _pretrips_with_route_record_first(pretrips, *, route_context=None, open_shift=None):
    pretrips = list(pretrips or [])
    selected = _select_route_pretrip(pretrips, route_context=route_context, open_shift=open_shift)
    if not selected:
        return pretrips
    return [selected] + [pretrip for pretrip in pretrips if pretrip.id != selected.id]


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


def _optional_float_from_form(name, *, minimum=None, maximum=None):
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


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


def _repair_today_driver_log_dates(driver_id, today_local_date):
    """Recover live stop entries saved under a stale route date.

    This only moves rows whose stored UTC arrival timestamp resolves to today's
    Detroit date, so retroactive add-stop entries with old arrival dates stay put.
    """
    if not driver_id or not today_local_date:
        return 0
    candidates = (
        _active_driver_logs_query()
        .filter(DriverLog.driver_id == driver_id, DriverLog.date != today_local_date)
        .order_by(DriverLog.created_at.desc(), DriverLog.id.desc())
        .limit(50)
        .all()
    )
    changed = 0
    for log in candidates:
        arrival_dt = _arrival_local_dt_for_log(log)
        if not arrival_dt or arrival_dt.date() != today_local_date:
            continue
        log.date = today_local_date
        changed += 1
    if changed:
        db.session.commit()
    return changed


def _repair_today_pretrip_dates(driver_id, today_local_date):
    """Recover PreTrips saved under tomorrow's UTC date during today's local shift."""
    if not driver_id or not today_local_date:
        return 0
    existing_today = (
        _active_pretrips_query()
        .filter_by(user_id=driver_id, pretrip_date=today_local_date)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .limit(20)
        .all()
    )
    if any(not pretrip.posttrip for pretrip in existing_today):
        return 0

    day_start, day_end = _local_route_date_utc_bounds(today_local_date)
    future_date = today_local_date + timedelta(days=1)
    candidates = (
        _active_pretrips_query()
        .filter(
            PreTrip.user_id == driver_id,
            PreTrip.pretrip_date == future_date,
            PreTrip.created_at >= day_start,
            PreTrip.created_at <= day_end,
        )
        .order_by(PreTrip.created_at.asc(), PreTrip.id.asc())
        .all()
    )
    changed = 0
    for pretrip in candidates:
        pretrip.pretrip_date = today_local_date
        changed += 1
    if changed:
        db.session.commit()
    return changed


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
            errors.append(f"Following stop at {_plant_label(following_log.plant_name)} arrives before this departure.")
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
    lp_ids = request.form.get(f"lp_ids_{index}", "").strip()
    if lp_ids:
        remarks = f"{remarks} | LP IDs: {lp_ids}" if remarks else f"LP IDs: {lp_ids}"
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


def _split_transfer_line_remarks(raw):
    remarks = (raw or "").strip()
    lp_ids = ""
    marker = "LP IDs:"
    if marker in remarks:
        before, after = remarks.split(marker, 1)
        remarks = before.rstrip(" |").strip()
        lp_ids = after.strip()
    return remarks, lp_ids


def _plant_transfer_form_lines(transfer=None):
    rows = []
    existing = {}
    if transfer is not None:
        existing = {line.line_number - 1: line for line in transfer.lines}
    for index in range(PLANT_TRANSFER_LINE_COUNT):
        line = existing.get(index)
        stored_remarks, stored_lp_ids = _split_transfer_line_remarks(line.remarks if line else "")
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
                    f"remarks_{index}", stored_remarks
                ),
                "lp_ids": request.form.get(
                    f"lp_ids_{index}", stored_lp_ids
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
    _repair_today_pretrip_dates(current_user.id, today_local_date)
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
    if _route_finalized_for_driver_date(current_user.id, today_local_date):
        return None
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
    # Always regenerate — never serve a stale cached PDF (e.g. after a deploy).
    response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    response.headers["Pragma"] = "no-cache"
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
    stored_path = os.path.join(upload_path, filename)
    uploaded_file.save(stored_path)
    photo = DamagePhoto(
        damage_report_id=report.id,
        stage=report.stage,
        filename=filename,
        original_filename=original,
        content_type=uploaded_file.content_type,
        sha256_hash=sha256_file(stored_path),
    )
    db.session.add(photo)
    return photo


def _driver_log_photo_upload_path():
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    os.makedirs(upload_path, exist_ok=True)
    return upload_path


def _driver_log_photo_default_note(source):
    source_text = (source or "").replace("_", " ").strip().lower()
    if any(term in source_text for term in ("bol", "manifest", "shipper")):
        return "BOL and manifest paperwork"
    if "transfer" in source_text:
        return "Transfer sheet paperwork"
    if "route_sheet" in source_text or "route packet" in source_text:
        return "Route sheet"
    if "proof_photo" in source_text or "proof photo" in source_text:
        return "Proof photo"
    if "driver_credential" in source_text:
        return "Driver credential"
    if "truck_document" in source_text:
        return "Truck document"
    if "manager_note" in source_text:
        return "Manager note"
    if "inspection" in source_text:
        return "Inspection record"
    if "route" in source_text and ("paperwork" in source_text or "document" in source_text):
        return "Route paperwork"
    if "paperwork" in source_text or "document" in source_text:
        return "Paperwork photo"
    if "damage" in source_text:
        return "Damage photo"
    if "seal" in source_text:
        return "Seal photo"
    return "Stop photo proof"


def _save_driver_log_photo(log, uploaded_file, *, source="gallery", note=None, uploaded_by_id=None):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("Choose a photo from your gallery or camera before saving proof.")
    original = secure_filename(uploaded_file.filename) or "stop-photo"
    name, ext = os.path.splitext(original)
    source_text = (source or "gallery").strip() or "gallery"
    note_text = (note or "").strip() or _driver_log_photo_default_note(source_text)
    filename = f"driver-log-{log.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext or '.jpg'}"
    stored_path = os.path.join(_driver_log_photo_upload_path(), filename)
    uploaded_file.save(stored_path)
    photo = DriverLogPhoto(
        driver_log_id=log.id,
        filename=filename,
        original_filename=original,
        content_type=getattr(uploaded_file, "mimetype", None) or getattr(uploaded_file, "content_type", None),
        sha256_hash=sha256_file(stored_path),
        source=source_text[:40],
        note=note_text[:500],
        uploaded_by_id=uploaded_by_id,
        uploaded_at=datetime.utcnow(),
    )
    db.session.add(photo)
    db.session.flush()
    return photo


def _first_uploaded_file(files):
    """Return the first FileStorage that actually carries a file.

    The workspace attach-document control exposes two inputs named ``photo``
    (Take Photo / Upload File). Browsers submit both, so ``request.files.get``
    can return the empty one. Pick the first part that has a filename.
    """
    for candidate in files or []:
        if candidate and getattr(candidate, "filename", ""):
            return candidate
    return None


def _document_attached_toast(log, photo):
    """Build (title, detail) lines for the document-attached toast.

    Capture-and-attach is the core workflow; no extraction runs, so the detail
    line states fields were not extracted and review is optional (never blocking).
    """
    plant = _plant_label(log.plant_name) or "this stop"
    day_logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=log.driver_id, date=log.date).all(),
        key=_driver_log_sort_key,
    )
    sequence = next((index + 1 for index, item in enumerate(day_logs) if item.id == log.id), None)
    context = f"Stop {sequence} · {plant}" if sequence else plant
    code = photo.resolved_document_type
    if code == "bol_manifest":
        return ("BOL ATTACHED", f"{context} · fields not extracted · review optional")
    if code == "transfer_sheet":
        return ("TRANSFER SHEET ATTACHED", f"{context} · fields not extracted · review optional")
    return ("DOCUMENT ATTACHED", f"{photo.document_type_label} · {context}")


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


def _save_pretrip_evidence_photo(pretrip, form):
    uploaded_file = request.files.get(getattr(form.fuel_level_photo, "name", "fuel_level_photo"))
    if not uploaded_file or not uploaded_file.filename:
        return None
    note = f"Fuel level proof: {pretrip.start_fuel_level or 'not recorded'}"
    return save_packet_media(
        uploaded_file,
        packet_type=PacketClassification.PRETRIP_DVIR_ISSUE.value,
        owner_type="pretrip",
        owner_id=pretrip.id,
        category="pretrip_fuel_level",
        uploaded_by=current_user,
        related={
            "truck": pretrip.truck_number,
            "trailer": pretrip.trailer_number,
        },
        note=note,
    )


def _pretrip_evidence_media(pretrip):
    if not pretrip or not getattr(pretrip, "id", None):
        return []
    return (
        ProofMediaFile.query.filter_by(owner_type="pretrip", owner_id=pretrip.id)
        .order_by(ProofMediaFile.uploaded_at.asc(), ProofMediaFile.id.asc())
        .all()
    )


def _pretrip_evidence_counts(pretrips):
    pretrip_ids = [pretrip.id for pretrip in pretrips or [] if getattr(pretrip, "id", None)]
    counts = {pretrip_id: 0 for pretrip_id in pretrip_ids}
    if not pretrip_ids:
        return counts
    rows = (
        db.session.query(ProofMediaFile.owner_id, func.count(ProofMediaFile.id))
        .filter(ProofMediaFile.owner_type == "pretrip", ProofMediaFile.owner_id.in_(pretrip_ids))
        .group_by(ProofMediaFile.owner_id)
        .all()
    )
    for owner_id, count in rows:
        counts[owner_id] = int(count or 0)
    return counts


def _pretrip_from_damage_report(report):
    reference = (getattr(report, "move_reference", "") or "").strip()
    match = re.search(r"\bPreTrip\s*#\s*(\d+)\b", reference, re.IGNORECASE)
    if not match:
        return None
    pretrip = _active_pretrips_query().filter_by(id=int(match.group(1))).first()
    if not pretrip:
        return None
    if current_user.role != "management" and pretrip.user_id != current_user.id:
        return None
    return pretrip


def _copy_damage_photos_to_pretrip_evidence(report, pretrip):
    upload_root = current_app.config.get("PACKET_UPLOAD_FOLDER", "uploads/packet_media")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    os.makedirs(upload_path, exist_ok=True)
    moved_media = []
    for photo in report.photos or []:
        source_path = _damage_photo_file_path(photo)
        if not source_path:
            continue
        original = secure_filename(photo.original_filename or photo.filename or "pretrip-evidence") or "pretrip-evidence"
        ext = os.path.splitext(original)[1] or os.path.splitext(photo.filename or "")[1] or ".bin"
        filename = (
            f"{PacketClassification.PRETRIP_DVIR_ISSUE.value}-pretrip-{pretrip.id}-"
            f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext}"
        )
        destination_path = os.path.join(upload_path, filename)
        shutil.copy2(source_path, destination_path)
        media = ProofMediaFile(
            packet_type=PacketClassification.PRETRIP_DVIR_ISSUE.value,
            owner_type="pretrip",
            owner_id=pretrip.id,
            category="pretrip_fuel_level",
            filename=filename,
            original_filename=original,
            content_type=photo.content_type,
            sha256_hash=sha256_file(destination_path),
            uploaded_by_id=report.reported_by_id,
            uploaded_at=photo.uploaded_at or datetime.utcnow(),
            related_truck=pretrip.truck_number,
            related_trailer=pretrip.trailer_number,
            manager_note=f"Moved from damage report #{report.id}: {report.description or 'PreTrip inspection proof'}",
        )
        db.session.add(media)
        moved_media.append(media)
    return moved_media




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


def _pretrip_damage_evidence_counts(pretrips):
    refs = {f"PreTrip #{pretrip.id}": pretrip.id for pretrip in pretrips or [] if getattr(pretrip, "id", None)}
    counts = {pretrip_id: {"reports": 0, "photos": 0} for pretrip_id in refs.values()}
    if not refs:
        return counts
    reports = (
        DamageReport.query.filter(DamageReport.move_reference.in_(refs.keys()))
        .order_by(DamageReport.created_at.asc(), DamageReport.id.asc())
        .all()
    )
    for report in reports:
        pretrip_id = refs.get(report.move_reference)
        if not pretrip_id:
            continue
        counts.setdefault(pretrip_id, {"reports": 0, "photos": 0})
        counts[pretrip_id]["reports"] += 1
        counts[pretrip_id]["photos"] += len(report.photos or [])
    return counts


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


def _is_reasonable_daily_route_miles(value):
    return value is not None and 0 <= value <= MAX_REASONABLE_DAILY_ROUTE_MILES


def _route_miles_from_values(start_mileage, end_mileage, miles_driven, *, allow_odometer_fallback=True):
    if _is_reasonable_daily_route_miles(miles_driven):
        return miles_driven
    if not allow_odometer_fallback or start_mileage is None or end_mileage is None:
        return None
    odometer_delta = end_mileage - start_mileage
    if _is_reasonable_daily_route_miles(odometer_delta):
        return odometer_delta
    return None


def _tracked_miles_for_pretrip(pretrip, *, allow_odometer_fallback=True):
    posttrip = pretrip.posttrip if pretrip else None
    if not posttrip:
        return None
    return _route_miles_from_values(
        pretrip.start_mileage,
        posttrip.end_mileage,
        posttrip.miles_driven,
        allow_odometer_fallback=allow_odometer_fallback,
    )


def _total_miles_for_pretrips(pretrips):
    total = 0
    has_mileage = False
    for pretrip in pretrips:
        miles = _tracked_miles_for_pretrip(pretrip)
        if miles is None:
            continue
        total += miles
        has_mileage = True
    return total if has_mileage else None


def _route_sheet_wait_minutes(logs, *, now=None):
    total = 0
    has_wait = False
    for log in logs or []:
        minutes = wait_minutes_for_log(log, now=now)
        if minutes is None:
            continue
        total += minutes
        has_wait = True
    return total if has_wait else 0


def _route_sheet_supporting_data(driver_id, route_date, logs, log_routes, route_context, *, now=None):
    raw_damage_reports = _today_damage_reports(driver_id, route_date) if driver_id else []
    damage_reports = [report for report in raw_damage_reports if not _sheet_pretrip_support_report_label(report)]
    support_document_notes = [
        label for label in (_sheet_pretrip_support_report_label(report) for report in raw_damage_reports) if label
    ]
    exception_notes = []
    log_issue_details = {}
    for log in logs or []:
        route = (log_routes or {}).get(log.id, {})
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
    for issue in (getattr(route_context, "true_exceptions", None) or []):
        label = issue.get("label") or "Route review item"
        detail = issue.get("detail") or ""
        note = f"{label}: {detail}" if detail else label
        if note not in exception_notes:
            exception_notes.append(note)
    route_pretrips = (
        _active_pretrips_query().filter_by(user_id=driver_id, pretrip_date=route_date).all()
        if driver_id and route_date
        else []
    )
    support_document_notes.extend(_sheet_pretrip_media_notes(route_pretrips))
    total_miles = _total_miles_for_pretrips(route_pretrips) if route_pretrips else None
    return {
        "damage_reports": damage_reports,
        "damage_report_details": [damage_report_detail_label(report) for report in damage_reports],
        "parts_carried": sorted({log.part_number for log in logs or [] if log.part_number}),
        "exception_notes": exception_notes,
        "log_issue_details": log_issue_details,
        "route_documents": collect_route_documents(logs, plant_label=_plant_label),
        "support_document_notes": _dedupe_sheet_lines(support_document_notes),
        "summary": {
            "total_stops": (getattr(route_context, "route_summary", {}) or {}).get("total_stops", len(logs or [])),
            "open_stops": (getattr(route_context, "route_summary", {}) or {}).get(
                "open_stops",
                sum(1 for log in logs or [] if not getattr(log, "depart_time", None)),
            ),
            "total_miles": total_miles,
            "total_wait_minutes": _route_sheet_wait_minutes(logs, now=now),
            "route_status": getattr(route_context, "route_status", None),
            "route_finalized_at": (getattr(route_context, "route_summary", {}) or {}).get("route_finalized_at"),
            "route_document_count": (getattr(route_context, "route_summary", {}) or {}).get("route_document_count"),
            "damage_count": (getattr(route_context, "route_summary", {}) or {}).get("damage_count", len(damage_reports)),
            "issue_count": (getattr(route_context, "route_summary", {}) or {}).get("issue_count", len(exception_notes)),
        },
    }


def _driver_mileage_totals_by_date(driver_id, *, before_date=None, through_date=None):
    query = (
        _active_pretrips_query()
        .join(PostTrip, PostTrip.pretrip_id == PreTrip.id)
        .filter(
            PreTrip.user_id == driver_id,
        )
    )
    if before_date is not None:
        query = query.filter(PreTrip.pretrip_date < before_date)
    if through_date is not None:
        query = query.filter(PreTrip.pretrip_date <= through_date)

    totals = {}
    for route_date, start_mileage, end_mileage, miles_driven in query.with_entities(
        PreTrip.pretrip_date,
        PreTrip.start_mileage,
        PostTrip.end_mileage,
        PostTrip.miles_driven,
    ):
        miles = _route_miles_from_values(start_mileage, end_mileage, miles_driven)
        if route_date is None or miles is None:
            continue
        totals[route_date] = totals.get(route_date, 0) + miles
    return totals


def _driver_mileage_performance(driver_id, route_date, current_total):
    previous_date = route_date - timedelta(days=1)
    previous_total = _driver_mileage_totals_by_date(
        driver_id,
        through_date=previous_date,
    ).get(previous_date)
    history_totals = _driver_mileage_totals_by_date(driver_id, before_date=route_date)
    historical_values = list(history_totals.values())
    average_miles = round(sum(historical_values) / len(historical_values)) if historical_values else None
    variance = current_total - previous_total if current_total is not None and previous_total is not None else None
    return {
        "previous_date": previous_date,
        "previous_total_miles": previous_total,
        "mileage_variance": variance,
        "average_miles": average_miles,
        "average_days": len(historical_values),
    }


def _route_pretrip_sort_key(pretrip):
    return (
        pretrip.pretrip_date or date.min,
        pretrip.created_at or datetime.min,
        pretrip.id or 0,
    )


def _previous_posttrip_fuel_level(driver_id, before_date, truck_number=None, before_pretrip=None):
    query = (
        _active_pretrips_query()
        .join(PostTrip, PostTrip.pretrip_id == PreTrip.id)
    )
    truck_number = _normalize_truck_number(truck_number)
    if truck_number:
        query = query.filter(func.lower(func.trim(PreTrip.truck_number)) == truck_number.lower())
    else:
        query = query.filter(PreTrip.user_id == driver_id)
    if before_pretrip is not None:
        query = query.filter(PreTrip.id != before_pretrip.id)
        if before_pretrip.created_at:
            query = query.filter(PostTrip.created_at < before_pretrip.created_at)
        else:
            query = query.filter(PreTrip.pretrip_date <= before_date)
    else:
        query = query.filter(PreTrip.pretrip_date < before_date)

    previous_pretrips = (
        query.order_by(PostTrip.created_at.desc(), PreTrip.pretrip_date.desc(), PreTrip.id.desc())
        .limit(20)
        .all()
    )
    for previous_pretrip in previous_pretrips:
        previous_posttrip = previous_pretrip.posttrip
        previous_fuel = (getattr(previous_posttrip, "end_fuel_level", None) or "").strip() if previous_posttrip else ""
        if previous_fuel:
            return previous_fuel, previous_pretrip
    return "", None


def _driver_route_audit_summary(driver_id, route_date, logs, route_map_ctx=None, pretrips=None):
    pretrips = list(pretrips) if pretrips is not None else (
        _active_pretrips_query()
        .filter_by(user_id=driver_id, pretrip_date=route_date)
        .order_by(PreTrip.created_at.asc(), PreTrip.id.asc())
        .all()
    )
    pretrips = sorted(pretrips, key=_route_pretrip_sort_key)
    route_stops_by_id = {
        stop.get("stop_id"): stop
        for stop in ((route_map_ctx or {}).get("stops") or [])
        if stop.get("stop_id")
    }
    first_pretrip = pretrips[0] if pretrips else None
    last_pretrip = pretrips[-1] if pretrips else None
    last_posttrip = next((pretrip.posttrip for pretrip in reversed(pretrips) if pretrip.posttrip), None)
    start_mileage = first_pretrip.start_mileage if first_pretrip else None
    end_mileage = last_posttrip.end_mileage if last_posttrip else None
    start_fuel_level = (getattr(last_pretrip, "start_fuel_level", None) or "").strip() if last_pretrip else ""
    start_fuel_source = "PreTrip" if start_fuel_level else ""
    if not start_fuel_level:
        start_fuel_level, previous_fuel_pretrip = _previous_posttrip_fuel_level(
            driver_id,
            route_date,
            truck_number=getattr(last_pretrip, "truck_number", None) if last_pretrip else None,
            before_pretrip=last_pretrip,
        )
        if previous_fuel_pretrip:
            start_fuel_source = (
                f"Previous PostTrip truck {previous_fuel_pretrip.truck_number}"
                if getattr(previous_fuel_pretrip, "truck_number", None)
                else "Previous PostTrip"
            )
    fuel_events = []
    for log in sorted([item for item in logs if item.fuel], key=_driver_log_sort_key):
        stop_vm = route_stops_by_id.get(log.id) or {}
        delta = None
        if log.fuel_mileage is not None and start_mileage is not None:
            delta = log.fuel_mileage - start_mileage
        fuel_events.append(
            {
                "log_id": log.id,
                "sequence": stop_vm.get("sequence"),
                "plant": stop_vm.get("plant_name") or log.plant_name,
                "mileage": log.fuel_mileage,
                "delta_from_start": delta,
            }
        )
    total_miles = _total_miles_for_pretrips(pretrips)
    mileage_performance = _driver_mileage_performance(driver_id, route_date, total_miles)
    # Fuel bought through the Fuel page lives on IFTA records, not DriverLog
    # fuel flags — the route fuel card must count both or it claims "No fuel
    # stop" on days the driver did buy fuel.
    fuel_purchase_records = _same_day_ifta_fuel_records(driver_id, route_date)
    return {
        "pretrip_count": len(pretrips),
        "route_pretrip": last_pretrip,
        "truck_number": last_pretrip.truck_number if last_pretrip else "",
        "trailer_number": last_pretrip.trailer_number if last_pretrip else "",
        "start_mileage": start_mileage,
        "end_mileage": end_mileage,
        "total_miles": total_miles,
        **mileage_performance,
        "posttrip_complete": bool(last_posttrip),
        "start_fuel_level": start_fuel_level,
        "start_fuel_source": start_fuel_source,
        "end_fuel_level": (getattr(last_posttrip, "end_fuel_level", None) or "").strip() if last_posttrip else "",
        "fuel_events": fuel_events,
        "fuel_purchase_count": len(fuel_purchase_records),
        "fuel_purchase_labels": [_fuel_record_label(record) for record in fuel_purchase_records],
    }


def _sheet_clean(value):
    return str(value or "").strip()


def _dedupe_sheet_lines(lines):
    seen = set()
    cleaned = []
    for line in lines or []:
        text = _sheet_clean(line)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _sheet_positive_weight_label(value):
    text = _sheet_clean(value)
    if not text:
        return ""
    match = re.search(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", text)
    if not match:
        return ""
    try:
        amount = float(match.group(0).replace(",", ""))
    except ValueError:
        return ""
    if amount <= 0:
        return ""
    return f"{amount:g} lbs"


def _sheet_strip_weight(text, *, keep_positive=True):
    def convert(match):
        try:
            amount = float(match.group(1).replace(",", ""))
        except ValueError:
            return ""
        return f" ({amount:g} lbs)" if keep_positive and amount > 0 else ""

    return re.sub(r"\s*\(\s*(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)\s*lbs?\s*\)", convert, text, flags=re.I)


def _sheet_load_text(value, *, include_weight=True):
    text = load_display(value) if value is not None else ""
    text = freight_cargo_text(text)
    text = _sheet_strip_weight(text, keep_positive=include_weight)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sheet_load_commodity(value):
    return _sheet_load_text(value, include_weight=False)


def _sheet_join_flow(parts, *, pdf=False):
    cleaned = _dedupe_sheet_lines(parts)
    return (" to " if pdf else " \u2192 ").join(cleaned)


def _sheet_flow_item(label, parts):
    cleaned = _dedupe_sheet_lines(parts)
    return {"label": label, "value": _sheet_join_flow(cleaned), "pdf_value": _sheet_join_flow(cleaned, pdf=True), "kind": "flow", "parts": cleaned}


def _sheet_item_label_value(item):
    if isinstance(item, dict):
        return item.get("label", ""), item.get("value", ""), item
    label, value = item
    return label, value, None


def _sheet_item_real(item):
    label, value, meta = _sheet_item_label_value(item)
    if meta and meta.get("kind") == "flow":
        return bool(meta.get("parts"))
    return _sheet_real(value)


def _sheet_pretrip_support_report_label(report):
    move_reference = _sheet_clean(getattr(report, "move_reference", ""))
    if not move_reference.lower().startswith("pretrip #"):
        return ""
    text = " ".join(
        _sheet_clean(value).lower()
        for value in (
            getattr(report, "description", ""),
            getattr(report, "plant_name", ""),
            getattr(report, "stage", ""),
            move_reference,
        )
    )
    fuel_level_words = ("fuel level", "fuel gauge", "low fuel", "fuel tank", "full fuel", "fuel proof")
    damage_words = ("damage", "dent", "scratch", "scrape", "broken", "crack", "leak", "rejection", "shortage")
    if any(word in text for word in fuel_level_words) and not any(word in text for word in damage_words):
        return "Pretrip fuel level photo attached."
    return ""


def _sheet_pretrip_media_notes(pretrips):
    notes = []
    pretrip_ids = [pretrip.id for pretrip in pretrips or [] if getattr(pretrip, "id", None)]
    if not pretrip_ids:
        return notes
    media_rows = (
        ProofMediaFile.query.filter(ProofMediaFile.owner_type == "pretrip", ProofMediaFile.owner_id.in_(pretrip_ids))
        .order_by(ProofMediaFile.uploaded_at.asc(), ProofMediaFile.id.asc())
        .all()
    )
    for media in media_rows:
        category = _sheet_clean(getattr(media, "category", "")).lower()
        note = _sheet_clean(getattr(media, "manager_note", ""))
        if category == "pretrip_fuel_level":
            notes.append("Pretrip fuel level photo attached.")
        elif "inspection" in category or "pretrip" in category:
            notes.append("Pretrip photo attached.")
        elif note:
            notes.append("Supporting document attached.")
    return notes


def _sheet_location_key(value):
    return re.sub(r"[^a-z0-9]+", "", _sheet_clean(value).lower())


def _sheet_same_location(left, right):
    return bool(left and right and _sheet_location_key(left) == _sheet_location_key(right))


def _sheet_stop_location_lines(log, plant_name):
    label = _sheet_clean(plant_name) or _plant_label(getattr(log, "plant_name", None))
    address = _sheet_clean(getattr(log, "location_address", None))
    if not label and address:
        return [address]
    if address and not _sheet_same_location(label, address):
        return [label, address]
    return [label or "Stop"]


def _sheet_stop_location_display(log, plant_name):
    return " · ".join(_sheet_stop_location_lines(log, plant_name))


def _sheet_blank(value):
    text = _sheet_clean(value)
    return text if text else ""


def _sheet_not_recorded(value):
    text = _sheet_clean(value)
    return text if text else "Not recorded"


def _sheet_int(value):
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _sheet_miles(value):
    text = _sheet_int(value)
    return f"{text} mi" if text else ""


def _sheet_minutes(value):
    if value is None:
        return ""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return str(value)
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} hr {remainder} min" if remainder else f"{hours} hr"


def _sheet_local_datetime(stamp):
    if not stamp:
        return None
    if isinstance(stamp, str):
        try:
            stamp = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    return stamp.astimezone(pytz.timezone("America/Detroit"))


def _sheet_datetime_label(stamp):
    local = _sheet_local_datetime(stamp)
    if not local:
        return ""
    return local.strftime("%b %d, %Y %-I:%M %p %Z") if os.name != "nt" else local.strftime("%b %d, %Y %#I:%M %p %Z")


def _sheet_first_departure_label(logs):
    for log in logs or []:
        if log.depart_time:
            return _format_hhmm_12h(log.depart_time)
    return ""


def _sheet_last_arrival_label(logs):
    for log in reversed(logs or []):
        label = _arrival_utc_to_local_hhmm(log.arrive_time)
        if label:
            return label
    return ""


def _sheet_elapsed_minutes(start_dt, end_dt):
    if not start_dt or not end_dt:
        return None
    if start_dt.tzinfo is None:
        start_dt = pytz.utc.localize(start_dt)
    if end_dt.tzinfo is None:
        end_dt = pytz.utc.localize(end_dt)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _route_drive_minutes(logs):
    """Total drive time from depart->next-arrive segments (driver-entered events)."""
    logs = list(logs or [])
    total = 0
    captured = False
    for depart_log, arrive_log in zip(logs, logs[1:]):
        if not depart_log.depart_time or not arrive_log.arrive_time:
            continue
        depart_dt = _local_dt_for_hhmm(depart_log.date, depart_log.depart_time)
        arrive_dt = _arrival_local_dt_for_log(arrive_log)
        minutes = _sheet_elapsed_minutes(depart_dt, arrive_dt)
        if minutes is not None:
            total += minutes
            captured = True
    return total if captured else None


def _sheet_route_minutes(logs, shift_record=None, *, now=None):
    local_tz = pytz.timezone("America/Detroit")
    now_local = now or datetime.now(local_tz)
    start_dt = None
    end_dt = None
    if shift_record and shift_record.start_time:
        start_dt = _sheet_local_datetime(shift_record.start_time)
        end_dt = _sheet_local_datetime(shift_record.end_time) if shift_record.end_time else now_local
    if start_dt is None and logs:
        start_dt = _arrival_local_dt_for_log(logs[0])
    if end_dt is None and logs:
        last_departed = next((log for log in reversed(logs) if log.depart_time), None)
        end_dt = _local_dt_for_hhmm(last_departed.date, last_departed.depart_time) if last_departed else _arrival_local_dt_for_log(logs[-1])
    return _sheet_elapsed_minutes(start_dt, end_dt)


def _sheet_route_status_label(route_context, logs):
    status = getattr(route_context, "route_status", None)
    if status == "finalized":
        return "Route finalized"
    if status == "completed":
        return "Route completed and awaiting final review"
    if logs:
        return "Route open and not finalized"
    return "No route recorded"


# Values that mean "we have nothing real to print here" — the log sheet omits
# these entirely rather than showing placeholder filler.
_SHEET_PLACEHOLDERS = {
    "",
    "empty",
    "not recorded",
    "none recorded",
    "not started",
    "no issues recorded",
    "none",
    "pending",
    "pending posttrip",
    "--",
    "—",
}


def _sheet_real(value):
    """True when a value is a captured fact worth printing (not placeholder filler)."""
    if value is None:
        return False
    return str(value).strip().lower() not in _SHEET_PLACEHOLDERS


def _sheet_card(title, items, *, show=True):
    """Build a card containing only items with real values; return None if empty."""
    if not show:
        return None
    real_items = [item for item in items if _sheet_item_real(item)]
    return {"title": title, "items": real_items} if real_items else None


def _sheet_load_label(value):
    text = _sheet_load_text(value)
    return text or "Empty"


def _sheet_cargo_label(log, route, row_state, key):
    if key == "in":
        value = (row_state or {}).get("cargo_in") or (route or {}).get("arrive_cargo_desc") or (route or {}).get("arrive_desc") or _sheet_load_label(log.load_size)
    else:
        if not log.depart_time:
            return "Pending departure"
        value = (row_state or {}).get("cargo_out") or (route or {}).get("depart_cargo_desc")
        if not value:
            value = _sheet_load_label(log.depart_load_size)
    if value in {"--", "Pending"}:
        return "Pending departure" if key == "out" else ""
    return _sheet_load_text(value) or "Empty"


_SHEET_NOTE_NOISE = {"stop complete", "picked up load", "departed empty", "unloaded, departed empty"}


def _sheet_note_is_noise(line):
    """Drop flow narration already conveyed by Time / Wait and Load Flow columns."""
    low = (line or "").strip().lower().rstrip(".")
    if low in _SHEET_NOTE_NOISE:
        return True
    if low.startswith("dock time"):
        return True
    if low.endswith(": pickup") or low.endswith(": delivery") or low.endswith(": shift start"):
        return True
    return False


def _sheet_polish_note(line, plant_name):
    """Turn a raw stop-summary line into a polished, human note (or None to drop it)."""
    text = (line or "").strip()
    if not text:
        return None
    low = text.lower().rstrip(".")
    # Drop location-prefixed system narration ("Customer Dock: Shift start.").
    if plant_name and low.startswith(plant_name.strip().lower() + ":"):
        return None
    if _sheet_note_is_noise(text):
        return None
    if low.startswith("loaded "):
        cargo = _sheet_load_commodity(text[len("Loaded "):]).rstrip(".")
        return f"Picked up {cargo}." if cargo else "Picked up load."
    if low.startswith("delivered "):
        cargo = _sheet_load_commodity(text[len("Delivered "):]).rstrip(".")
        return f"Delivered {cargo}." if cargo else "Delivered load."
    if low.startswith("unloaded "):
        cargo = _sheet_load_commodity(text[len("Unloaded "):]).rstrip(".")
        return f"Delivered {cargo}." if cargo else "Delivered load."
    if low.startswith("continuing with "):
        cargo = _sheet_load_commodity(text[len("Continuing with "):]).rstrip(".")
        return f"Continued with {cargo} onboard." if cargo else "Continued with load onboard."
    return text


def _sheet_stop_notes(log, route, issue, route_task_events, row_state, plant_name, *, index, is_last=False, route_context=None):
    # Notes carry only meaningful, polished facts. The routine flow narrative
    # (dock time, plant pickup/delivery labels, "Stop complete") lives in the
    # Time / Wait and Load Flow columns and is dropped/deduplicated here.
    notes = []
    finalized = getattr(route_context, "route_status", None) == "finalized"
    if not log.depart_time:
        notes.append(f"Route End: {plant_name}" if finalized else "Departure pending.")
    elif index == 1:
        notes.append("Shift start.")
    for line in (route or {}).get("summary_lines") or []:
        polished = _sheet_polish_note(line, plant_name)
        if polished and polished not in notes:
            notes.append(polished)
    if (route or {}).get("unload_blocked"):
        notes.append(f"Not unloaded: {(route or {}).get('unload_reason') or 'reason not recorded'}")
    if (route or {}).get("secondary_drop_blocked"):
        notes.append(f"Second stop not unloaded: {(route or {}).get('secondary_drop_reason') or 'reason not recorded'}")
    if (route or {}).get("deviation_reason"):
        notes.append(f"Deviation: {(route or {}).get('deviation_reason')}")
    if log.no_pickup:
        no_pickup_note = "No pickup."
        if no_pickup_note not in notes:
            notes.append(no_pickup_note)
    if log.hot_parts or log.part_number:
        notes.append((("Hot part " if log.hot_parts else "") + (log.part_number or "")).strip())
    if log.maintenance or (issue or {}).get("truck"):
        notes.append(f"Truck issue: {(issue or {}).get('truck') or 'Maintenance marked'}")
    if (issue or {}).get("route"):
        notes.append(f"Route issue: {(issue or {}).get('route')}")
    if log.downtime_reason and log.downtime_reason not in notes:
        notes.append(log.downtime_reason)
    if log.fuel and "Fuel stop." not in notes:
        notes.append("Fuel stop.")
    for event in route_task_events or []:
        notes.append(f"{event.kind_label} {event.label}: {event.status}")
    if is_last and log.depart_time and finalized and "Route completed." not in notes:
        notes.append("Route completed.")
    return [note for note in notes if note]


def _same_day_ifta_fuel_records(driver_id, route_date):
    if not driver_id or not route_date:
        return []
    return (
        IftaFuelRecord.query.join(IftaWorksheet, IftaFuelRecord.worksheet_id == IftaWorksheet.id)
        .filter(
            or_(IftaWorksheet.driver_id == driver_id, IftaWorksheet.created_by_id == driver_id),
            IftaFuelRecord.purchase_date == route_date,
        )
        .order_by(IftaFuelRecord.id.asc())
        .all()
    )


def _fuel_record_label(record):
    # Only captured facts — never "amount not recorded" filler.
    seller = _sheet_clean(record.seller_name)
    parts = []
    if record.gallons_or_liters is not None:
        parts.append(f"{record.gallons_or_liters:g} gal")
    if record.total_sale_amount is not None:
        parts.append(f"${record.total_sale_amount:,.2f}")
    fuel_type = _sheet_clean(record.fuel_type)
    if fuel_type:
        parts.append(fuel_type)
    if seller and parts:
        return f"{seller}: {' '.join(parts)}"
    if seller:
        return seller
    if parts:
        return " ".join(parts)
    return "Fuel purchase"


def _fuel_type_from_text(*parts):
    text = " ".join(str(part or "") for part in parts).lower()
    if "def" in text:
        return "DEF"
    if "diesel" in text:
        return "Diesel"
    if "gasoline" in text or re.search(r"\bgas\b", text):
        return "Gas"
    if "fuel" in text or "full" in text or "tank" in text:
        return "Fuel level"
    return ""


def _fuel_form_from_damage_form(form):
    plant_name = _sheet_clean(form.plant_name.data)
    move_reference = _sheet_clean(form.move_reference.data)
    seller_name = "" if plant_name.lower() in {"", "other"} else plant_name
    if not seller_name and move_reference and len(move_reference) <= 80:
        seller_name = move_reference
    description = _sheet_clean(form.description.data)
    truck_number = _sheet_clean(form.truck_number.data)
    trailer_number = _sheet_clean(form.trailer_number.data)
    fuel_type = _fuel_type_from_text(description, move_reference, plant_name)
    return MultiDict(
        {
            "purchase_date": _today_local_date().isoformat(),
            "seller_name": seller_name,
            "fuel_type": fuel_type,
            "trip_notes": description,
            "truck": truck_number,
            "trailer": trailer_number,
            "vehicle_unit_number": truck_number,
        }
    )


def _driver_log_sheet_model(driver, route_date, logs, pretrips, log_routes, route_context, route_sheet_data, route_task_events, shift_record, *, now=None):
    logs = list(logs or [])
    pretrips = sorted(pretrips or [], key=_route_pretrip_sort_key)
    first_pretrip = pretrips[0] if pretrips else None
    last_pretrip = pretrips[-1] if pretrips else None
    completed_pretrips = [pretrip for pretrip in pretrips if pretrip.posttrip]
    last_posttrip = completed_pretrips[-1].posttrip if completed_pretrips else None
    selected_pretrip = completed_pretrips[-1] if completed_pretrips else (last_pretrip or first_pretrip)
    truck = getattr(selected_pretrip, "truck_number", None) or getattr(route_context, "truck_id", None) or ""
    trailer = getattr(selected_pretrip, "trailer_number", None) or ""

    route_minutes = _sheet_route_minutes(logs, shift_record, now=now)
    total_wait_minutes = (route_sheet_data.get("summary") or {}).get("total_wait_minutes")
    service_minutes = max(0, route_minutes - total_wait_minutes) if route_minutes is not None and total_wait_minutes is not None else None
    total_miles = _total_miles_for_pretrips(pretrips)
    avg_miles = round(total_miles / len(logs), 1) if total_miles is not None and logs else None
    fuel_records = _same_day_ifta_fuel_records(getattr(driver, "id", None), route_date)
    total_fuel = sum(record.gallons_or_liters or 0 for record in fuel_records)
    has_fuel_amount = any(record.gallons_or_liters is not None for record in fuel_records)
    avg_fuel = round(total_fuel / len(logs), 2) if has_fuel_amount and logs else None
    fuel_events = [
        {
            "stop": item.get("sequence"),
            "plant": item.get("plant"),
            "mileage": _sheet_miles(item.get("mileage")),
            "delta": _sheet_miles(item.get("delta_from_start")),
        }
        for item in _driver_route_audit_summary(getattr(driver, "id", None), route_date, logs, pretrips=pretrips).get("fuel_events", [])
    ]

    row_states = {row.get("log_id"): row for row in (getattr(route_context, "rows", None) or [])}
    timeline_rows = []
    previous_mileage = getattr(first_pretrip, "start_mileage", None)
    for index, log in enumerate(logs, start=1):
        route = (log_routes or {}).get(log.id, {})
        row_state = row_states.get(log.id, {})
        plant_name = row_state.get("plant") or route.get("plant") or _plant_label(log.plant_name)
        location_lines = _sheet_stop_location_lines(log, plant_name)
        location_display = " · ".join(location_lines)
        inbound = _sheet_cargo_label(log, route, row_state, "in")
        outbound = _sheet_cargo_label(log, route, row_state, "out")
        miles_since = None
        if log.fuel_mileage is not None and previous_mileage is not None and log.fuel_mileage >= previous_mileage:
            miles_since = log.fuel_mileage - previous_mileage
        if log.fuel_mileage is not None:
            previous_mileage = log.fuel_mileage
        timeline_rows.append(
            {
                "stop_no": index,
                "stop_label": plant_name,
                "location": location_display,
                "location_lines": location_lines,
                "location_address": _sheet_clean(getattr(log, "location_address", None)),
                "arrive": _arrival_utc_to_local_hhmm(log.arrive_time),
                "depart": _format_hhmm_12h(log.depart_time) if log.depart_time else "Pending",
                "wait": wait_label_for_log(log) or "",
                "load_in": inbound,
                "load_out": outbound,
                "miles_since": _sheet_miles(miles_since),
                "fuel": "",  # real per-stop fuel amounts (gallons) are not captured today; odometer goes to mileage
                "notes": _sheet_stop_notes(
                    log,
                    route,
                    (route_sheet_data.get("log_issue_details") or {}).get(log.id, {}),
                    (route_task_events or {}).get(log.id, []),
                    row_state,
                    plant_name,
                    index=index,
                    is_last=index == len(logs),
                    route_context=route_context,
                ),
            }
        )

    current_cargo = getattr(route_context, "current_cargo", {}) or {}
    current_load = _sheet_load_commodity(current_cargo.get("cargo_display") or current_cargo.get("value") or "")
    current_load_status = ""
    open_stop = next((log for log in reversed(logs) if not log.depart_time), None)
    if open_stop and is_freight_load(getattr(open_stop, "load_size", None)) and freight_load_destined_here(
        open_stop.load_size, open_stop.plant_name, getattr(open_stop, "location_address", None)
    ):
        current_load = _sheet_load_commodity(open_stop.load_size)
        current_load_status = f"Delivered at {_plant_label(open_stop.plant_name)}, departure pending"
    load_labels = []
    weight_labels = []
    for log in logs:
        if log.commodity:
            label = _sheet_load_commodity(log.commodity)
            if label not in load_labels:
                load_labels.append(label)
            weight = _sheet_positive_weight_label(log.weight)
            if weight and weight not in weight_labels:
                weight_labels.append(weight)
    if not load_labels:
        for row in timeline_rows:
            for value in (row["load_in"], row["load_out"]):
                label = _sheet_load_commodity(value)
                if label and label not in {"Empty", "Pending departure"} and label not in load_labels:
                    load_labels.append(label)
    unload_blocked = [
        f"{row['stop_label']}: {note}"
        for row in timeline_rows
        for note in row["notes"]
        if note.startswith("Not unloaded") or note.startswith("Second stop not unloaded")
    ]
    # Compact location chain (the per-stop IN/OUT detail already lives in the
    # timeline's Load Flow column); collapse immediate repeats so it stays one line.
    route_history = []
    for row in timeline_rows:
        location = row["stop_label"]
        if location and (not route_history or route_history[-1] != location):
            route_history.append(location)

    load_flow_history = []
    if timeline_rows and timeline_rows[0]["load_in"] == "Empty":
        load_flow_history.append("Empty")
    for log, row in zip(logs, timeline_rows):
        route = (log_routes or {}).get(log.id, {})
        stop = row["stop_label"]
        delivered_primary = bool(route.get("unloaded_on_arrival")) or bool(
            not log.depart_time
            and is_freight_load(getattr(log, "load_size", None))
            and freight_load_destined_here(log.load_size, log.plant_name, getattr(log, "location_address", None))
        )
        if delivered_primary:
            cargo = _sheet_load_commodity(route.get("arrive_desc") or log.load_size)
            if cargo and cargo != "Empty":
                load_flow_history.append(f"Delivered {cargo} at {stop}")
        if route.get("secondary_dropped_on_arrival"):
            cargo = _sheet_load_commodity(route.get("arrive_secondary_desc") or getattr(log, "secondary_load", None))
            if cargo and cargo != "Empty":
                load_flow_history.append(f"Delivered {cargo} at {stop}")
        if log.depart_time and not log.no_pickup:
            outbound = _sheet_load_commodity(route.get("depart_desc") or log.depart_load_size)
            inbound = _sheet_load_commodity(route.get("arrive_desc") or log.load_size)
            if outbound and outbound not in {"Empty", inbound}:
                load_flow_history.append(f"Picked up {outbound} at {stop}")

    issue_lines = []
    issue_lines.extend(route_sheet_data.get("exception_notes") or [])
    for log in logs:
        if log.downtime_reason:
            issue_lines.append(f"{_plant_label(log.plant_name)}: {log.downtime_reason}")
    document_lines = [
        f"{doc.get('doc_label')} - {doc.get('owner_label')}" + (f" - {doc.get('note')}" if doc.get("note") else "")
        for doc in route_sheet_data.get("route_documents") or []
    ]

    posttrip_remarks = _sheet_clean(getattr(last_posttrip, "remarks", None))
    maintenance_notes = []
    if getattr(first_pretrip, "damage_report", None):
        maintenance_notes.append(first_pretrip.damage_report)
    if posttrip_remarks:
        maintenance_notes.append(posttrip_remarks)
    for item in issue_lines:
        if "Truck issue" in item or "Maintenance" in item:
            maintenance_notes.append(item)

    start_mileage = getattr(first_pretrip, "start_mileage", None)
    last_odometer = getattr(last_posttrip, "end_mileage", None) or (previous_mileage if previous_mileage != start_mileage else None)
    miles_by_stop = "; ".join(f"Stop {row['stop_no']}: {row['miles_since']}" for row in timeline_rows if row["miles_since"])
    # Odometer readings logged at fuel stops are MILEAGE facts, not fuel amounts.
    fuel_stop_odometer = "; ".join(f"{event['plant']}: {event['mileage']}" for event in fuel_events)
    show_miles_col = any(row["miles_since"] for row in timeline_rows)
    has_mileage = show_miles_col or total_miles is not None or start_mileage is not None or last_odometer is not None or bool(fuel_stop_odometer)

    fuel_purchases = "; ".join(_fuel_record_label(record) for record in fuel_records)
    # Fuel means real fuel (gallons/levels). The per-stop Fuel column only shows
    # when an actual fuel amount was captured per stop (odometer never qualifies).
    show_fuel_col = any(row["fuel"] for row in timeline_rows)
    has_fuel = show_fuel_col or has_fuel_amount or bool(fuel_records)

    status_label = _sheet_route_status_label(route_context, logs)
    summary = route_sheet_data.get("summary") or {}
    total_stops = summary.get("total_stops", len(logs))
    open_stops = summary.get("open_stops", 0)

    weights = "; ".join(weight_labels)
    commodity = "; ".join(load_labels)
    damage_text = "; ".join(route_sheet_data.get("damage_report_details") or [])
    delay_reasons = "; ".join(log.downtime_reason for log in logs if log.downtime_reason)
    not_unloaded = "; ".join(unload_blocked)
    problem_events = "; ".join(issue_lines)
    maintenance_text = "; ".join(maintenance_notes)
    pickup_stop = next((row["stop_label"] for row in timeline_rows if row["load_out"] not in {"", "Empty", "Pending", "Pending departure"}), "")
    delivery_stop = next((event.rsplit(" at ", 1)[1] for event in load_flow_history if event.startswith("Delivered ") and " at " in event), "")
    if unload_blocked:
        unloaded_status = "; ".join(unload_blocked)
    elif current_load_status:
        unloaded_status = ""
    elif current_load and current_load != "Empty":
        unloaded_status = "In truck"
    else:
        unloaded_status = ""
    service_start = _sheet_datetime_label(getattr(shift_record, "start_time", None)) or (_arrival_utc_to_local_hhmm(logs[0].arrive_time) if logs else "")
    posttrip_release = _sheet_datetime_label(getattr(last_posttrip, "created_at", None)) if last_posttrip else ""

    raw_tiles = [
        ("stops", "Total Stops", str(total_stops)),
        ("open", "Open Stops", str(open_stops)),
        ("status", "Route Status", status_label),
        ("hours", "Total Service Hours", _sheet_minutes(route_minutes)),
        ("wait", "Total Wait Time", _sheet_minutes(total_wait_minutes)),
    ]
    if has_mileage:
        raw_tiles.append(("miles", "Total Miles", _sheet_miles(total_miles)))
        raw_tiles.append(("avg_miles", "Avg Mi / Stop", _sheet_miles(avg_miles) if avg_miles is not None else ""))
    if has_fuel:
        raw_tiles.append(("fuel", "Total Fuel Used", f"{total_fuel:g} gal" if has_fuel_amount else ""))
        raw_tiles.append(("avg_fuel", "Avg Fuel / Stop", f"{avg_fuel:g} gal" if avg_fuel is not None else ""))
    summary_tiles = [
        {"icon": icon, "label": label, "value": value}
        for icon, label, value in raw_tiles
        if _sheet_real(value)
    ]

    drive_minutes = _route_drive_minutes(logs)
    route_breaks = _route_breaks_for_driver_date(getattr(driver, "id", None), route_date)
    # Hours Check display follows the day-driver route type unless HOS Companion is
    # explicitly enabled: General Freight / owner-operator shows hours facts only.
    driver_route_type = getattr(driver, "day_driver_route_type", None) or "local_short_haul"
    shift_hos_mode = getattr(shift_record, "hos_mode", None)
    if shift_hos_mode == hos_service.HOS_COMPANION:
        effective_hos_mode = hos_service.HOS_COMPANION
    elif driver_route_type == "general_freight":
        effective_hos_mode = hos_service.HOURS_ONLY
    else:
        effective_hos_mode = hos_service.SHORT_HAUL
    hours = hos_service.build_hours_summary(
        mode=effective_hos_mode,
        shift_start=getattr(shift_record, "start_time", None),
        release_time=getattr(last_posttrip, "created_at", None) or getattr(shift_record, "end_time", None),
        on_duty_minutes=route_minutes,
        drive_minutes=drive_minutes,
        wait_minutes=total_wait_minutes,
        first_departure=_sheet_first_departure_label(logs),
        last_arrival=_sheet_last_arrival_label(logs),
        report_start_label=service_start,
        release_label=posttrip_release,
        breaks=route_breaks,
        now=now,
    )

    cards = [card for card in [
        _sheet_card("Mileage Summary", [
            ("Starting odometer", _sheet_miles(start_mileage)),
            ("Last recorded odometer", _sheet_miles(last_odometer)),
            ("Total route miles", _sheet_miles(total_miles)),
            ("Miles by stop", miles_by_stop),
            ("Odometer recorded at", fuel_stop_odometer),
        ], show=has_mileage),
        _sheet_card("Fuel Summary", [
            ("Starting fuel", _sheet_clean(getattr(first_pretrip, "start_fuel_level", None))),
            ("Fuel purchases", fuel_purchases),
            ("Last / remaining fuel", _sheet_clean(getattr(last_posttrip, "end_fuel_level", None))),
            ("Estimated fuel used", f"{total_fuel:g} gal" if has_fuel_amount else ""),
        ], show=has_fuel),
        _sheet_card("Duty / Hours", [
            ("Shift start / report time", service_start),
            ("First departure", _sheet_first_departure_label(logs)),
            ("Last arrival", _sheet_last_arrival_label(logs)),
            ("Total on-duty", _sheet_minutes(route_minutes)),
            ("Total drive time", hos_service.format_minutes(drive_minutes)),
            ("Total wait / dock time", _sheet_minutes(total_wait_minutes)),
            ("Total service time", _sheet_minutes(service_minutes)),
            ("Posttrip / release time", posttrip_release),
        ]),
        _sheet_card("Breaks", [(f"Break {i}", line) for i, line in enumerate(hours["breaks"], 1)]),
        _sheet_card("Short-Haul Check", hours["short_haul"]),
        _sheet_card("HOS Companion", hours["companion"]),
        _sheet_card("Vehicle / Maintenance", [
            ("Truck", truck),
            ("Trailer", trailer),
            ("Pretrip status", "Completed" if first_pretrip else ""),
            ("Posttrip status", "Completed" if last_posttrip else ""),
            ("Maintenance notes", maintenance_text),
        ]),
        _sheet_card("What Was Hauled / Load", [
            ("Current load", current_load),
            ("Status", current_load_status),
            ("Commodity", commodity),
            ("Weight", weights),
            ("Pickup stop", pickup_stop),
            ("Delivery / unload stop", delivery_stop),
            ("Unloaded status", unloaded_status),
        ]),
        _sheet_card("Route Flow", [
            _sheet_flow_item("Route history", route_history),
        ]),
        _sheet_card("Load Flow History", [
            _sheet_flow_item("Load movement", load_flow_history),
        ], show=bool(load_flow_history)),
        _sheet_card("Damage / Shortage / Rejection", [
            ("Reports", damage_text),
        ], show=bool(damage_text)),
        _sheet_card("Attached Photos / Documents", [
            ("Supporting documents", "; ".join(_dedupe_sheet_lines((route_sheet_data.get("support_document_notes") or []) + document_lines))),
        ], show=bool((route_sheet_data.get("support_document_notes") or []) or document_lines)),
        _sheet_card("Notes / Events", [
            ("Delay reasons", delay_reasons),
            ("Not unloaded reasons", not_unloaded),
            ("Route issues", problem_events),
        ]),
    ] if card]

    return {
        "title": "DRIVER LOG SHEET",
        "driver_name": getattr(driver, "display_name", None) or "",
        "route_date": route_date,
        "route_date_label": route_date.strftime("%b %d, %Y") if route_date else "",
        "route_label": getattr(route_context, "route_label", "") or "",
        "truck": truck,
        "trailer": trailer,
        "route_id": getattr(route_context, "route_id", "") or "",
        "route_status": status_label,
        "has_mileage": has_mileage,
        "has_fuel": has_fuel,
        "show_miles_col": show_miles_col,
        "show_fuel_col": show_fuel_col,
        "summary_tiles": summary_tiles,
        "timeline_rows": timeline_rows,
        "cards": cards,
        "hours": hours,
    }


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


def _freight_stop_memory(driver_id, limit=40):
    """The driver's own recent locations, commodities, and commodity->weight
    pairs, so the freight stop form remembers instead of re-asking."""
    rows = (
        _active_driver_logs_query()
        .filter_by(driver_id=driver_id)
        .order_by(DriverLog.id.desc())
        .limit(limit)
        .all()
    )
    learned_places = (
        PlaceMemory.query.filter_by(user_id=driver_id)
        .order_by(PlaceMemory.last_visited_at.desc(), PlaceMemory.id.desc())
        .limit(limit)
        .all()
    )
    locations, destinations, commodities, weight_map, places = [], [], [], {}, []

    def add_location(label):
        label = (label or "").strip()
        if label and label != "Day Route" and label not in locations:
            locations.append(label)

    def add_destination(name="", address=""):
        name = (name or "").strip()
        address = (address or "").strip()
        if not name and not address:
            return
        key = (name.lower(), address.lower())
        if key not in {(item["name"].lower(), item["address"].lower()) for item in destinations}:
            destinations.append({"name": name, "address": address})
        add_location(name or address)

    def secondary_destination_label(value):
        value = (value or "").strip()
        if " -> " not in value:
            return ""
        return value.rsplit(" -> ", 1)[1].strip()

    for place in learned_places:
        label = (place.label or "").strip()
        add_destination(label)
        if label and place.center_latitude is not None and place.center_longitude is not None:
            places.append(
                {
                    "label": label,
                    "lat": place.center_latitude,
                    "lng": place.center_longitude,
                    "radius_m": min(place.radius_m or 90, 90),
                }
            )
    for log in rows:
        add_destination(getattr(log, "destination", None), getattr(log, "destination_address", None))
        add_destination(secondary_destination_label(getattr(log, "secondary_load", None)))
        add_location(log.plant_name)
        commodity = (log.commodity or "").strip()
        if commodity:
            if commodity not in commodities:
                commodities.append(commodity)
            weight = (log.weight or "").strip()
            if weight and commodity.lower() not in weight_map:
                weight_map[commodity.lower()] = weight
    return {
        "locations": locations[:8],
        "destinations": destinations[:8],
        "places": places[:20],
        "commodities": commodities[:5],
        "weight_map": weight_map,
    }


def _freight_departure_label(commodity, weight="", destination="", *, fallback="Loaded", limit=80):
    commodity = (commodity or "").strip() or fallback
    weight = (weight or "").strip()
    destination = (destination or "").strip()
    label = commodity
    try:
        numeric_weight = float(weight.replace(",", "")) if weight else None
    except ValueError:
        numeric_weight = None
    if weight and numeric_weight != 0:
        label = f"{label} ({weight} lbs)"
    if destination:
        label = f"{label} -> {destination}"
    return label[:limit]


def _bounded_float_arg(name, *, minimum, maximum):
    raw_value = (request.args.get(name) or "").strip()
    try:
        value = float(raw_value)
    except ValueError:
        return None
    if value < minimum or value > maximum:
        return None
    return value


@bp.route("/gps/place-candidates")
@login_required
@_driver_route_guard("driver.mobile_dashboard", "the driver GPS place lookup")
def gps_place_candidates():
    # Every driver-facing location field (fuel, duty status, stops) offers the
    # GPS fill button, so this is not day-driver gated — only driver gated.
    lat = _bounded_float_arg("lat", minimum=-90, maximum=90)
    lng = _bounded_float_arg("lng", minimum=-180, maximum=180)
    accuracy = _bounded_float_arg("accuracy", minimum=0, maximum=50000)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "bad_coordinates", "places": []}), 400
    hint = (request.args.get("hint") or "").strip()[:80]
    try:
        payload = nearby_place_candidates(lat, lng, accuracy_m=accuracy, hint=hint)
    except Exception:
        current_app.logger.exception(
            "Google place lookup failed for user_id=%s lat=%s lng=%s",
            current_user.id,
            lat,
            lng,
        )
        payload = {"ok": False, "error": "lookup_failed", "places": []}
    return jsonify(payload)


@bp.route("/gps/destination-lookup")
@login_required
@_driver_route_guard("driver.mobile_dashboard", "the driver destination place lookup")
def gps_destination_lookup():
    if not getattr(current_user, "is_day_driver", False):
        return jsonify({"ok": False, "error": "day_driver_required", "place": None, "places": []}), 403
    query = (request.args.get("query") or "").strip()[:255]
    if len(query) < 4:
        return jsonify({"ok": False, "error": "short_query", "place": None, "places": []}), 400
    bias_lat = _bounded_float_arg("lat", minimum=-90, maximum=90)
    bias_lng = _bounded_float_arg("lng", minimum=-180, maximum=180)
    near = (request.args.get("near") or "").strip()[:255]
    try:
        payload = lookup_destination_place(query, bias_lat=bias_lat, bias_lng=bias_lng, near=near)
    except Exception:
        current_app.logger.exception(
            "Google destination lookup failed for user_id=%s query_present=%s",
            current_user.id,
            bool(query),
        )
        payload = {"ok": False, "error": "lookup_failed", "place": None, "places": []}
    return jsonify(payload)


def _render_new_driving_log(form, current_load, *, route_context=None, return_to_mobile=False):
    route_date = getattr(route_context, "route_date", None) or _today_local_date()
    has_today_logs = bool(getattr(route_context, "rows", None)) if route_context else (
        _active_driver_logs_query()
        .filter_by(driver_id=current_user.id, date=route_date)
        .first()
        is not None
    )
    freight_memory = (
        _freight_stop_memory(current_user.id)
        if getattr(current_user, "is_day_driver", False)
        else None
    )
    return render_template(
        "new_driving_log.html",
        form=form,
        current_load=current_load,
        has_today_logs=has_today_logs,
        route_context=route_context,
        next_stop_context=getattr(route_context, "next_stop_context", None),
        return_to_mobile=return_to_mobile,
        freight_memory=freight_memory,
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


def _truck_pretrips_for_number(truck_number, limit=30):
    truck_number = _normalize_truck_number(truck_number)
    if not truck_number:
        return []
    query = (
        _active_pretrips_query()
        .filter(func.lower(func.trim(PreTrip.truck_number)) == truck_number.lower())
        .order_by(PreTrip.pretrip_date.desc(), PreTrip.created_at.desc(), PreTrip.id.desc())
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def _driver_inspection_truck_choices(driver_id, *, include_closed=False):
    today_local_date = _today_local_date()
    driver_pretrips = (
        _active_pretrips_query()
        .filter(
            PreTrip.user_id == driver_id,
            PreTrip.truck_number.isnot(None),
            func.trim(PreTrip.truck_number) != "",
        )
        .order_by(PreTrip.pretrip_date.desc(), PreTrip.created_at.desc(), PreTrip.id.desc())
        .limit(40)
        .all()
    )
    choices = {}

    def add_choice(pretrip):
        truck_number = _normalize_truck_number(pretrip.truck_number)
        if not truck_number:
            return
        key = truck_number.lower()
        if key not in choices:
            choices[key] = {
                "truck_number": truck_number,
                "latest_pretrip": pretrip,
                "latest_date": pretrip.pretrip_date,
                "has_open": not bool(pretrip.posttrip),
            }
        else:
            choices[key]["has_open"] = choices[key]["has_open"] or not bool(pretrip.posttrip)

    # include_closed (the driver's own inspection list) offers every truck the
    # driver has recently inspected so closed, past-day PreTrip/PostTrip records
    # stay reachable. Other callers -- cross-driver view authorization and the
    # standalone maintenance-history page -- stay scoped to the truck the driver
    # is currently on (today-dated or still-open) so they don't widen access.
    for pretrip in driver_pretrips:
        if include_closed or pretrip.pretrip_date == today_local_date or not pretrip.posttrip:
            add_choice(pretrip)
    if not choices and driver_pretrips:
        add_choice(driver_pretrips[0])
    return list(choices.values())


def _driver_selected_inspection_truck(driver_id, requested_truck_number=None, *, include_closed=False):
    truck_choices = _driver_inspection_truck_choices(driver_id, include_closed=include_closed)
    selected_truck = None
    requested_truck_number = _normalize_truck_number(requested_truck_number)
    if requested_truck_number:
        selected_truck = next(
            (truck for truck in truck_choices if _same_truck_number(truck["truck_number"], requested_truck_number)),
            None,
        )
    if selected_truck is None and truck_choices:
        selected_truck = truck_choices[0]
    return selected_truck, truck_choices


def _driver_can_view_inspection_pretrip(pretrip):
    if current_user.role != "driver" or pretrip.user_id == current_user.id:
        return True
    _, truck_choices = _driver_selected_inspection_truck(current_user.id)
    return any(_same_truck_number(pretrip.truck_number, truck["truck_number"]) for truck in truck_choices)


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
                "start_fuel_level": pretrip.start_fuel_level or "",
                "end_fuel_level": posttrip.end_fuel_level if posttrip else "",
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
        freight.append(" - ".join(pieces))
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
    inspection_media = _pretrip_evidence_media(pretrip)
    total_pages = 2 if evidence_reports or inspection_media else 1
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
    pdf.text(36, y, "1. Vehicle and Shift Info", size=10, bold=True)
    y -= 18
    pdf.text(36, y, f"Truck and Tractor No: {pretrip.truck_number or ''}", size=10, bold=True)
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
    y -= 18
    fuel_level = f"Start: {pretrip.start_fuel_level or 'Not recorded'}"
    if pretrip.posttrip:
        fuel_level = f"{fuel_level} - End: {pretrip.posttrip.end_fuel_level or 'Not recorded'}"
    pdf.text(36, y, f"Fuel Level: {fuel_level}", size=10)
    y -= 25
    pdf.text(36, y, "2. Power Unit Inspection, 3. In-Cab Inspection, 4. Engine Compartment, 5. Exterior", size=9, bold=True)
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
        pdf.text(36, y, "6. Defects and Remarks - Defects Marked", size=10, bold=True, color=PDF_ALERT_RED)
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
    pretrip_remarks = (pretrip.damage_report or "").strip()
    remarks_lines = []
    if pretrip_remarks:
        remarks_lines.append(pretrip_remarks)
    if pretrip.posttrip:
        posttrip_parts = [
            f"PostTrip: End mileage {pretrip.posttrip.end_mileage if pretrip.posttrip.end_mileage is not None else 'not recorded'}",
            f"miles driven {pretrip.posttrip.miles_driven if pretrip.posttrip.miles_driven is not None else 'not calculated'}",
            f"ending fuel {pretrip.posttrip.end_fuel_level or 'not recorded'}",
        ]
        posttrip_remarks = (pretrip.posttrip.remarks or "").strip()
        if posttrip_remarks:
            posttrip_parts.append(f"remarks: {posttrip_remarks}")
        remarks_lines.append("; ".join(posttrip_parts))
    remarks = "\n".join(remarks_lines)
    remarks_color = PDF_ALERT_RED if pretrip_remarks else None
    pdf.text(36, y, "6. Defects and Remarks", size=10, bold=True, color=remarks_color)
    pdf.rect(36, y - 70, 540, 60)
    pdf.multiline_text(
        42,
        y - 20,
        remarks,
        width_chars=95,
        size=9,
        bold=bool(pretrip_remarks),
        max_lines=6,
        color=remarks_color,
    )
    pdf.text(36, 112, "7. Driver Signature", size=10, bold=True)
    pdf.text(36, 92, "Driver Signature: ____________________________", size=10)
    pdf.text(335, 92, "Date: __________________", size=10)

    if inspection_media or evidence_reports:
        pdf.add_page()
        meta = _pretrip_document_meta(pretrip, page=f"2 of {total_pages}")
        _draw_pdf_header(pdf, meta["title"], meta["document_no"], meta["generated_at"], meta["page"], driver=pretrip.driver.display_name if pretrip.driver else None, truck=pretrip.truck_number, date_value=pretrip.pretrip_date)
        y = 704
        if inspection_media:
            pdf.text(36, y, "8. PreTrip Inspection Evidence", size=14, bold=True)
            y -= 20
            pdf.text(36, y, f"PreTrip #{pretrip.id} - Truck {pretrip.truck_number or ''}", size=9)
            y -= 18
            for media in inspection_media[:4]:
                image_y = y - 80
                media_path = accident_media_path(media)
                image_drawn = bool(media_path) and pdf.image_file(media_path, 36, image_y, 120, 80)
                if not image_drawn:
                    pdf.rect(36, image_y, 120, 80)
                    pdf.multiline_text(42, image_y + 48, "Evidence file exists in the record but could not render. Review in system before approval.", width_chars=28, size=7, leading=9, max_lines=4, bold=True)
                pdf.text(170, y - 8, f"Evidence #{media.id}", size=8, bold=True)
                pdf.text(170, y - 22, f"Type: {media.category.replace('_', ' ').title()}", size=8)
                pdf.text(170, y - 36, f"File: {media.original_filename or media.filename}", size=8)
                y -= 98
                if y < 120:
                    pdf.add_page()
                    y = 748
            y -= 8
        if evidence_reports:
            pdf.text(36, y, f"{'9' if inspection_media else '8'}. PreTrip Damage Evidence", size=14, bold=True)
            y -= 20
            pdf.text(36, y, f"PreTrip #{pretrip.id} - Truck {pretrip.truck_number or ''}", size=9)
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
    pdf.text(330, 112, "Manager and Reviewer Signature", size=9, bold=True)

    if driver_signature and not pdf.image_png_data_url(driver_signature, 44, 64, 190, 38):
        pdf.text(44, 80, "Driver e-signature captured", size=10, bold=True)
    pdf.line(44, 58, 252, 58)
    if driver_signature:
        pdf.text(44, 46, _signature_timestamp_label(signature_timestamp), size=7)
    pdf.text(186, 46, "Date: __________", size=7)
    pdf.line(330, 58, 552, 58)
    pdf.text(470, 46, "Date: __________", size=7)


MD_PDF_BLUE = (31, 78, 163)
MD_PDF_INK = (26, 34, 48)
MD_PDF_MUTED = (91, 102, 117)
MD_PDF_WHITE = (255, 255, 255)


def _draw_branded_log_sheet_header(pdf, log_sheet, meta, the_date, *, page_label=None):
    """Branded DRIVER LOG SHEET header — matches the HTML print layout, only real facts."""
    logo_path = os.path.join(current_app.static_folder or "", "brand", "movedefense_stripe_brand_icon_200x200.png")
    if os.path.exists(logo_path):
        pdf.fill_rect(36, 726, 26, 26, rgb=(13, 19, 32))
        pdf.image_file(logo_path, 37, 727, 24, 24)
    pdf.text(70, 742, "MoveDefense", size=12, bold=True, color=MD_PDF_INK)
    pdf.text(36, 714, "DRIVER", size=7, bold=True, color=MD_PDF_MUTED)
    pdf.text(36, 700, (log_sheet.get("driver_name") or "").upper(), size=15, bold=True)
    date_label = log_sheet.get("route_date_label") or (the_date.strftime("%b %d, %Y") if hasattr(the_date, "strftime") else "")
    route_label = log_sheet.get("route_label") or ""
    pdf.text(36, 688, (f"{route_label} \xb7 {date_label}" if route_label else date_label), size=8, bold=True, color=MD_PDF_MUTED)
    clean_no = f"LOG-{the_date.strftime('%Y-%m-%d')}" if hasattr(the_date, "strftime") else (meta.get("document_no") or "")
    rx = 400
    pdf.text(rx, 742, f"Driver Log No: {clean_no}", size=8, bold=True)
    pdf.text(rx, 730, f"Generated: {meta.get('generated_at', '')}", size=8)
    truck = log_sheet.get("truck")
    trailer = log_sheet.get("trailer")
    if truck:
        pdf.text(rx, 718, f"Truck / Trailer: {truck}" + (f" / {trailer}" if trailer else ""), size=8)
    elif trailer:
        pdf.text(rx, 718, f"Trailer: {trailer}", size=8)
    if page_label:
        pdf.text(rx, 706, f"Page: {page_label}", size=8)
    pdf.fill_rect(36, 682, 540, 2, rgb=MD_PDF_BLUE)
    pdf.text(36, 666, log_sheet.get("title") or "DRIVER LOG SHEET", size=15, bold=True, color=MD_PDF_INK)
    return 648


def _draw_log_sheet_tiles(pdf, tiles, y):
    if not tiles:
        return y
    pdf.text(36, y, "ROUTE SUMMARY", size=9, bold=True, color=MD_PDF_BLUE)
    y -= 14
    tile_w, tile_h, per_row = 180, 26, 3
    for index, tile in enumerate(tiles):
        col, row = index % per_row, index // per_row
        tx = 36 + col * tile_w
        ty = y - row * (tile_h + 5)
        pdf.rect(tx, ty - tile_h, tile_w - 8, tile_h)
        pdf.fill_rect(tx, ty - tile_h, 3, tile_h, rgb=MD_PDF_BLUE)
        pdf.text(tx + 9, ty - 9, (tile.get("label") or "").upper(), size=5.5, bold=True, color=MD_PDF_MUTED)
        pdf.multiline_text(tx + 9, ty - 19, tile.get("value") or "", max(6, int((tile_w - 18) / 4.0)), size=8.5, bold=True, leading=9, max_lines=1)
    rows_used = (len(tiles) + per_row - 1) // per_row
    return y - rows_used * (tile_h + 5) - 8


def _pdf_wrapped_lines(value, width_chars, *, max_lines=None):
    chunks = value if isinstance(value, (list, tuple)) else [value]
    lines = []
    for chunk in chunks:
        text = (
            _sheet_clean(chunk)
            .replace("\u2014", " - ")
            .replace("\u2013", " - ")
            .replace("\u2192", " to ")
            .replace("\xa0", " ")
        )
        if not text:
            continue
        wrapped = textwrap.wrap(
            text,
            width=max(8, int(width_chars)),
            break_long_words=False,
            replace_whitespace=False,
        )
        lines.extend(wrapped or [text])
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        if len(lines[-1]) > 3:
            lines[-1] = lines[-1].rstrip(" .;") + "..."
    return lines


def _draw_sheet_table_header(pdf, x, y, widths, headers):
    header_h = 26
    total_width = sum(widths)
    pdf.fill_rect(x, y - header_h, total_width, header_h, rgb=MD_PDF_BLUE)
    pdf.rect(x, y - header_h, total_width, header_h)
    cx = x
    for idx, width in enumerate(widths):
        pdf.line(cx, y, cx, y - header_h)
        pdf.multiline_text(
            cx + 3,
            y - 10,
            headers[idx],
            max(6, int(width / 4.5)),
            size=6,
            bold=True,
            leading=7,
            max_lines=2,
            color=MD_PDF_WHITE,
        )
        cx += width
    pdf.line(cx, y, cx, y - header_h)
    return y - header_h


def _draw_log_sheet_timeline_table(pdf, log_sheet, y):
    show_miles = log_sheet["show_miles_col"]
    show_fuel = log_sheet["show_fuel_col"]
    headers = ["Stop #", "Location / Stop", "Time / Wait", "Load Flow"]
    widths = [28, 106, 82, 96]
    if show_miles:
        headers.append("Miles Since Last Stop")
        widths.append(54)
    if show_fuel:
        headers.append("Fuel Used / Recorded")
        widths.append(62)
    headers.append("Notes")
    widths.append(524 - sum(widths))

    x = 36
    y = _draw_sheet_table_header(pdf, x, y, widths, headers)
    for row_index, row in enumerate(log_sheet["timeline_rows"]):
        time_wait = [f"Arrive: {row['arrive'] or '--'}", f"Depart: {row['depart'] or '--'}"]
        if row["wait"]:
            time_wait.append(row["wait"])
        load_flow = [f"In: {row['load_in'] or '--'}", f"Out: {row['load_out'] or '--'}"]
        cells = [str(row["stop_no"]), row.get("location_lines") or row["location"] or "--", time_wait, load_flow]
        if show_miles:
            cells.append(row["miles_since"])
        if show_fuel:
            cells.append(row["fuel"])
        cells.append("; ".join(row["notes"]) if row["notes"] else "")

        wrapped = [
            _pdf_wrapped_lines(value, max(7, int(width / 3.7)), max_lines=6)
            for value, width in zip(cells, widths)
        ]
        row_h = max(34, 12 + max((len(lines) or 1) * 8 for lines in wrapped))
        if y - row_h < 150:
            pdf.add_page()
            y = _draw_sheet_table_header(pdf, x, 748, widths, headers)
        if row_index % 2:
            pdf.fill_rect(x, y - row_h, sum(widths), row_h, rgb=(247, 249, 253))
        pdf.rect(x, y - row_h, sum(widths), row_h)
        cx = x
        for idx, width in enumerate(widths):
            pdf.line(cx, y, cx, y - row_h)
            for line_idx, line in enumerate(wrapped[idx]):
                pdf.text(cx + 3, y - 10 - line_idx * 8, line, size=6.2, bold=(idx == 0))
            cx += width
        pdf.line(cx, y, cx, y - row_h)
        y -= row_h
    return y - 10


def _pdf_card_item_height(item, col_w):
    label, value, meta = _sheet_item_label_value(item)
    display_value = meta.get("pdf_value") if meta else value
    max_lines = 4 if meta and meta.get("kind") == "flow" else 3
    lines = _pdf_wrapped_lines(display_value, max(12, int((col_w - 18) / 3.7)), max_lines=max_lines)
    return 10 + max(1, len(lines)) * 8, lines


def _draw_log_sheet_cards(pdf, cards, y):
    if not cards:
        return y
    pdf.text(36, y, "DRIVER LOG SUMMARY", size=9, bold=True, color=MD_PDF_BLUE)
    y -= 14
    col_w, gap = 264, 12
    cols_x = [36, 36 + col_w + gap]
    index = 0
    while index < len(cards):
        pair = cards[index:index + 2]
        measured = []
        for card in pair:
            item_measurements = [_pdf_card_item_height(item, col_w) for item in card["items"]]
            measured.append((card, item_measurements, 24 + sum(height for height, _lines in item_measurements)))
        row_h = max(height for _card, _items, height in measured)
        if y - row_h < 150:
            pdf.add_page()
            y = 748
        for col, (card, item_measurements, ch) in enumerate(measured):
            cx = cols_x[col]
            pdf.rect(cx, y - ch, col_w, ch)
            pdf.fill_rect(cx, y - 3, col_w, 3, rgb=MD_PDF_BLUE)
            pdf.text(cx + 7, y - 13, (card.get("title") or "").upper(), size=7, bold=True, color=MD_PDF_INK)
            iy = y - 26
            for item, (item_h, value_lines) in zip(card["items"], item_measurements):
                label, value, meta = _sheet_item_label_value(item)
                pdf.text(cx + 7, iy, str(label).upper(), size=5.6, bold=True, color=MD_PDF_MUTED)
                for line_idx, line in enumerate(value_lines or [""]):
                    pdf.text(cx + 7, iy - 8 - line_idx * 8, line, size=7.1, bold=True, color=MD_PDF_INK)
                iy -= item_h
        y -= row_h + 8
        index += 2
    return y


def _build_driver_logs_pdf(logs, the_date, driver=None, driver_signature=None, signature_timestamp=None, route_context=None):
    route_context = route_context or build_route_context(driver_id=getattr(logs[0], "driver_id", None), route_date=getattr(logs[0], "date", None)) if logs else None
    routes = (route_context.log_routes if route_context else _driver_log_route_context(logs))
    pretrips = _active_pretrips_query().filter_by(user_id=getattr(driver, "id", None), pretrip_date=the_date).all() if driver else []
    truck = _truck_from_pretrips(pretrips)
    meta = _route_document_meta(the_date, driver, logs, pretrips)
    support = _route_sheet_supporting_data(getattr(driver, "id", None), the_date, logs, routes, route_context)
    summary = support["summary"]
    pdf = SimplePdf("Driver Log Sheet", LETTER)
    route_task_events = _task_route_events_for_logs(logs)
    shift_record = _shift_record_for_driver_date(getattr(driver, "id", None), the_date) if driver else None
    log_sheet = _driver_log_sheet_model(
        driver,
        the_date,
        logs,
        pretrips,
        routes,
        route_context,
        support,
        route_task_events,
        shift_record,
    )
    # Same branded layout and view model as the HTML Print Document.
    y = _draw_branded_log_sheet_header(pdf, log_sheet, meta, the_date)
    y = _draw_log_sheet_tiles(pdf, log_sheet["summary_tiles"], y)
    pdf.text(36, y, "1. STOP TIMELINE", size=9, bold=True, color=MD_PDF_BLUE)
    y -= 12
    if log_sheet["timeline_rows"]:
        y = _draw_log_sheet_timeline_table(pdf, log_sheet, y)
    else:
        pdf.text(44, y, "No stops for selected date.", size=8)
        y -= 18
    # Lower branded summary cards (damage/notes/documents now live inside these,
    # so no separate placeholder sections are drawn).
    y = _draw_log_sheet_cards(pdf, log_sheet["cards"], y)
    y = max(y - 14, 136)
    pdf.text(36, y, "SIGNATURES", size=10, bold=True, color=MD_PDF_BLUE)
    _draw_signature_pdf_block(pdf, driver_signature, signature_timestamp)
    pdf.text(150, 22, "Thank you for driving safe and delivering excellence.", size=7, color=MD_PDF_MUTED)

    def _start_document_page():
        pdf.add_page()
        _draw_branded_log_sheet_header(pdf, log_sheet, meta, the_date, page_label="Documents")
        return 648

    render_document_appendix(
        pdf,
        support["route_documents"],
        start_new_page=_start_document_page,
        title="Documents Attached",
    )
    return pdf.build()


def _build_eod_pdf(the_date, logs, plant_transfers, driver_signature=None, signature_timestamp=None, pretrips=None):
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
    y = pdf.table(36, y, [32, 58, 48, 48, 100, 108, 86, 68], 24, ["Stop #", "Plant", "Arrive", "Depart", "Cargo In", "Cargo Out", "Wait", "Parts"], log_rows or [["--", "No logs", "", "", "", "", "", ""]], font_size=7)
    y -= 34
    pretrips = list(pretrips or [])
    route_pretrip = pretrips[0] if pretrips else None
    route_posttrip = getattr(route_pretrip, "posttrip", None) if route_pretrip else None
    fuel_logs = [log for log in logs if getattr(log, "fuel", False) and getattr(log, "fuel_mileage", None) is not None]
    mileage_rows = []
    start_mileage = getattr(route_pretrip, "start_mileage", None) if route_pretrip else None
    start_fuel = (getattr(route_pretrip, "start_fuel_level", None) or "").strip() if route_pretrip else ""
    end_mileage = getattr(route_posttrip, "end_mileage", None) if route_posttrip else None
    end_fuel = (getattr(route_posttrip, "end_fuel_level", None) or "").strip() if route_posttrip else ""
    if start_mileage is not None or start_fuel:
        mileage_rows.append([
            "Pre-Trip Start",
            f"{start_mileage:,} mi" if start_mileage is not None else "--",
            f"Start Fuel: {start_fuel}" if start_fuel else "",
        ])
    for fuel_log in fuel_logs:
        note = f"+{fuel_log.fuel_mileage - start_mileage:,} from start" if start_mileage is not None else ""
        mileage_rows.append(["Fuel Stop", f"{fuel_log.fuel_mileage:,} mi", note])
    if route_posttrip:
        total_note = f" - {end_mileage - start_mileage:,} total mi" if end_mileage is not None and start_mileage is not None else ""
        mileage_rows.append([
            "Post-Trip End",
            f"{end_mileage:,} mi" if end_mileage is not None else "--",
            f"End Fuel: {end_fuel or 'Not recorded'}{total_note}",
        ])
    if mileage_rows:
        pdf.text(36, y, "2. Mileage and Fuel Summary", size=12, bold=True)
        y -= 14
        y = pdf.table(36, y, [110, 95, 220], 22, ["Checkpoint", "Odometer", "Notes"], mileage_rows, font_size=7)
        y -= 24
    pdf.text(36, y, "3. Plant Transfers", size=12, bold=True)
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
        pdf.brand_signature(36, 570)
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
        selected_truck_number = ""
        inspection_trucks = []
        truck_history = []
    else:
        selected_truck, inspection_trucks = _driver_selected_inspection_truck(
            current_user.id,
            request.args.get("truck_number"),
            include_closed=True,
        )
        selected_truck_number = selected_truck["truck_number"] if selected_truck else ""
        current_pretrip = selected_truck["latest_pretrip"] if selected_truck else None
        current_pretrip_id = current_pretrip.id if current_pretrip and not current_pretrip.posttrip else None
        pretrips = _truck_pretrips_for_number(selected_truck_number, limit=30)
        truck_history = _truck_maintenance_history(
            selected_truck_number,
            current_pretrip_id=current_pretrip_id,
            limit=8,
        )
    return render_template(
        "list_pretrips.html",
        pretrips=pretrips,
        selected_truck_number=selected_truck_number,
        inspection_trucks=inspection_trucks,
        truck_history=truck_history,
        pretrip_damage_evidence_by_id=_pretrip_damage_evidence_counts(pretrips),
        pretrip_evidence_by_id=_pretrip_evidence_counts(pretrips),
        today_local_date=_today_local_date(),
        route_finalized_by_pretrip_id={
            pretrip.id: build_route_context(driver_id=pretrip.user_id, route_date=pretrip.pretrip_date).route_finalized
            for pretrip in pretrips
        },
    )


@bp.route("/new_pretrip", methods=["GET", "POST"])
@login_required
def new_pretrip():
    today_local_date = _today_local_date()
    formdata = None
    if request.method == "POST" and not (request.form.get("pretrip_date") or "").strip():
        posted = MultiDict(request.form)
        posted["pretrip_date"] = today_local_date.isoformat()
        formdata = CombinedMultiDict((posted, request.files))
    form = PreTripForm(formdata=formdata) if formdata is not None else PreTripForm()
    if request.method == "GET":
        if not form.pretrip_date.data:
            form.pretrip_date.data = today_local_date
        previous_fuel, _ = _previous_posttrip_fuel_level(current_user.id, today_local_date)
        if previous_fuel and not form.start_fuel_level.data:
            form.start_fuel_level.data = previous_fuel
    if form.validate_on_submit():
        chosen_date = form.pretrip_date.data or today_local_date

        new_pt = PreTrip(
            user_id=current_user.id,
            truck_number=form.truck_number.data,
            trailer_number=form.trailer_number.data,
            pretrip_date=chosen_date,
            shift=form.shift.data,
            start_mileage=form.start_mileage.data,
            start_fuel_level=form.start_fuel_level.data,
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
        pretrip_evidence = _save_pretrip_evidence_photo(new_pt, form)
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
        elif existing_open_shift.pretrip_id is None:
            existing_open_shift.pretrip_id = new_pt.id
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
        if pretrip_evidence:
            record_activity(
                user_id=current_user.id,
                category="pretrip",
                action="evidence_uploaded",
                title="PreTrip fuel evidence saved",
                details=f"Truck {new_pt.truck_number or 'unlisted'} fuel level photo.",
                target_type="pretrip",
                target_id=new_pt.id,
            )

        flash(
            (
                "PreTrip saved with fuel evidence and damage photo attached."
                if pretrip_evidence and damage_report
                else "PreTrip saved with fuel evidence attached."
                if pretrip_evidence
                else "PreTrip saved with damage photo attached."
                if damage_report
                else "PreTrip saved successfully!"
            ),
            "success",
        )
        return redirect(url_for("driver.list_pretrips"))
    elif request.method == "POST":
        current_app.logger.warning(
            "PreTrip validation failed for user_id=%s: %s",
            current_user.id,
            form.errors,
        )
        flash("PreTrip was not saved. Check the highlighted fields and try again.", "danger")

    return render_template("new_pretrip.html", form=form, today_local_date=today_local_date)


@bp.route("/do_posttrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def do_posttrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    route_context = build_route_context(driver_id=pt.user_id, route_date=pt.pretrip_date)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        if request.method == "GET" and pt.posttrip and _driver_can_view_inspection_pretrip(pt):
            return redirect(url_for("driver.pretrip_printable", pretrip_id=pt.id, _anchor="posttrip-closeout"))
        flash("Not authorized to complete a PostTrip for someone else's PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))
    if route_context.route_finalized:
        if request.method == "GET" and pt.posttrip and _driver_can_view_inspection_pretrip(pt):
            return redirect(url_for("driver.pretrip_printable", pretrip_id=pt.id, _anchor="posttrip-closeout"))
        flash("That route is finalized. PostTrip entries cannot be changed.", "warning")
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

    posttrip = (
        PostTrip.query.filter_by(pretrip_id=pretrip_id)
        .order_by(PostTrip.created_at.asc(), PostTrip.id.asc())
        .first()
    )
    form = PostTripForm(obj=posttrip)
    if form.validate_on_submit():
        end_mileage_val = form.end_mileage.data
        if pt.start_mileage is not None and end_mileage_val < pt.start_mileage:
            flash("End mileage cannot be lower than start mileage.", "danger")
            return render_template("posttrip.html", form=form, pretrip=pt, posttrip=posttrip, fuel_logs=fuel_logs, route_context=route_context, route_summary=route_context.route_summary)
        if pt.start_mileage is not None:
            miles_val = end_mileage_val - pt.start_mileage
        else:
            miles_val = None

        if posttrip is None:
            posttrip = PostTrip(pretrip_id=pretrip_id)
            db.session.add(posttrip)
        posttrip.end_mileage = end_mileage_val
        posttrip.end_fuel_level = form.end_fuel_level.data
        posttrip.remarks = form.remarks.data
        posttrip.miles_driven = miles_val

        _end_open_shifts_for_driver(pt.user_id)
        db.session.commit()

        record_activity(
            user_id=current_user.id,
            category="posttrip",
            action="completed",
            title="PostTrip completed",
            details=f"PreTrip #{pt.id}; miles driven: {miles_val if miles_val is not None else 'not calculated'}.",
            target_type="posttrip",
            target_id=posttrip.id,
        )

        flash("PostTrip completed successfully and shift clock ended!", "success")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pretrip_id))
    return render_template("posttrip.html", form=form, pretrip=pt, posttrip=posttrip, fuel_logs=fuel_logs, route_context=route_context, route_summary=route_context.route_summary)


@bp.route("/view_pretrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def view_pretrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver":
        if not _driver_can_view_inspection_pretrip(pt):
            flash("Not authorized to view that PreTrip.", "danger")
            return redirect(url_for("driver.list_pretrips"))
        return redirect(url_for("driver.pretrip_printable", pretrip_id=pt.id))
    return render_template(
        "view_pretrip.html",
        pretrip=pt,
        readonly=True,
        today_local_date=_today_local_date(),
        pretrip_damage_reports=_pretrip_damage_reports(pt),
        pretrip_evidence_media=_pretrip_evidence_media(pt),
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
        if not _can_driver_mutate_route_record(pt.user_id, pt.pretrip_date, "PreTrip", "update"):
            return redirect(url_for("driver.list_pretrips"))
        pt.pretrip_date = form.pretrip_date.data
        pt.shift = form.shift.data
        pt.truck_type = form.truck_type.data
        pt.truck_number = form.truck_number.data
        pt.trailer_number = form.trailer_number.data
        pt.start_mileage = form.start_mileage.data
        pt.start_fuel_level = form.start_fuel_level.data
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
        pretrip_evidence = _save_pretrip_evidence_photo(pt, form)
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
        if pretrip_evidence:
            record_activity(
                user_id=current_user.id,
                category="pretrip",
                action="evidence_uploaded",
                title="PreTrip fuel evidence saved",
                details=f"Truck {pt.truck_number or 'unlisted'} fuel level photo.",
                target_type="pretrip",
                target_id=pt.id,
            )

        session["reviewing_driver"] = request.form.get("reviewing_driver")
        session["reviewing_date"] = request.form.get("reviewing_date")

        flash(
            (
                "PreTrip updated with fuel evidence and damage photo attached."
                if pretrip_evidence and damage_report
                else "PreTrip updated with fuel evidence attached."
                if pretrip_evidence
                else "PreTrip updated with damage photo attached."
                if damage_report
                else "PreTrip updated!"
            ),
            "success",
        )
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
    if current_user.role == "driver" and not _driver_can_view_inspection_pretrip(pt):
        flash("Not authorized to print that PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))

    ephemeral_driver = session.get("reviewing_driver")
    ephemeral_date = session.get("reviewing_date")
    route_context = build_route_context(driver_id=pt.user_id, route_date=pt.pretrip_date)

    return render_template(
        "pretrip_printable.html",
        pretrip=pt,
        ephemeral_driver=ephemeral_driver,
        ephemeral_date=ephemeral_date,
        email_mode=False,
        pretrip_damage_reports=_pretrip_damage_reports(pt),
        pretrip_evidence_media=_pretrip_evidence_media(pt),
        route_context=route_context,
        route_summary=route_context.route_summary,
        document_meta=_pretrip_document_meta(pt),
    )


@bp.route("/pretrip_printable/<int:pretrip_id>/attachment")
@login_required
def pretrip_attachment(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver" and not _driver_can_view_inspection_pretrip(pt):
        flash("Not authorized to download that PreTrip.", "danger")
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
    if request.method == "GET":
        guard = _guard_route_record_mutation(
            current_user.id,
            _today_local_date(),
            "Plant Transfer",
            "create",
            next_url=url_for("driver.plant_transfers"),
        )
        if guard:
            return guard
    elif request.method == "POST":
        guard = _guard_route_record_mutation(
            current_user.id,
            form.transfer_date.data or _today_local_date(),
            "Plant Transfer",
            "create",
            next_url=url_for("driver.plant_transfers"),
        )
        if guard:
            return guard
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
    guard = _guard_route_record_mutation(
        transfer.user_id,
        transfer.transfer_date,
        "Plant Transfer",
        "update",
        next_url=url_for("driver.view_plant_transfer", transfer_id=transfer.id),
    )
    if guard:
        return guard
    if request.method == "GET":
        form.transfer_time.data = _format_display_time(transfer.transfer_time)
    lines = _plant_transfer_form_lines(transfer)
    if form.validate_on_submit():
        if not _can_driver_mutate_route_record(transfer.user_id, transfer.transfer_date, "Plant Transfer", "update"):
            return redirect(url_for("driver.plant_transfers"))
        if not _can_driver_mutate_route_record(transfer.user_id, form.transfer_date.data, "Plant Transfer", "move"):
            return redirect(url_for("driver.view_plant_transfer", transfer_id=transfer.id))
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
    if current_user.role == "driver" and search_date == _today_local_date():
        _repair_today_driver_log_dates(current_user.id, search_date)

    if current_user.role == "management":
        all_drivers = User.query.filter_by(role="driver").all()
        selected_driver_id = request.args.get("driver_id", type=int)
        query = _active_driver_logs_query().filter(DriverLog.date == search_date).order_by(
            DriverLog.created_at.desc()
        )
        if selected_driver_id:
            query = query.filter_by(driver_id=selected_driver_id)
        logs = query.all()
        selected_driver = User.query.get(selected_driver_id) if selected_driver_id else None
        route_map_stops_by_id = {}
        route_map_ctx = {}
        route_context = None
        if selected_driver:
            route_context = build_route_context(driver_id=selected_driver.id, route_date=search_date)
            route_map_ctx = build_driver_route_map_context(driver=selected_driver, date=search_date)
            route_map_stops_by_id = {stop["stop_id"]: stop for stop in route_map_ctx.get("stops", [])}
        return render_template(
            "driver_logs.html",
            logs=logs,
            log_routes=route_context.log_routes if route_context else _driver_log_route_context(logs),
            route_context=route_context,
            route_summary=getattr(route_context, "route_summary", None),
            route_map=route_map_ctx,
            route_map_stops_by_id=route_map_stops_by_id,
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
        pretrips = (
            _active_pretrips_query()
            .filter_by(user_id=current_user.id, pretrip_date=search_date)
            .order_by(PreTrip.created_at.asc(), PreTrip.id.asc())
            .all()
        )
        route_pretrip = sorted(pretrips, key=_route_pretrip_sort_key)[-1] if pretrips else None
        route_context = build_route_context(driver_id=current_user.id, route_date=search_date)
        route_map_ctx = build_driver_route_map_context(
            driver=current_user,
            date=search_date,
            route_pretrip=route_pretrip,
        )
        return render_template(
            "driver_logs.html",
            logs=logs,
            log_routes=route_context.log_routes,
            route_context=route_context,
            route_summary=route_context.route_summary,
            route_map=route_map_ctx,
            route_map_stops_by_id={stop["stop_id"]: stop for stop in route_map_ctx.get("stops", [])},
            route_audit_summary=_driver_route_audit_summary(
                current_user.id,
                search_date,
                logs,
                route_map_ctx=route_map_ctx,
                pretrips=pretrips,
            ),
            route_task_events=_task_route_events_for_logs(logs),
            route_finalized=route_context.route_finalized,
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
    try:
        route_context = build_route_context(driver_id=current_user.id, route_date=local_date, now=now_local)
        current_load = _current_driver_load(current_user.id, local_date, route_context=route_context)
    except Exception:
        current_app.logger.exception("Driver log route context could not be resolved for user_id=%s", current_user.id)
        flash("Driver log could not be opened. Try again from Mobile Dashboard.", "danger")
        return redirect(url_for("driver.mobile_dashboard"))
    current_load_value = current_load["value"] or "Empty"
    current_secondary_value = current_load.get("secondary_value") or ""
    return_to_mobile = request.values.get("next") == "mobile"
    next_url = url_for("driver.mobile_dashboard") if return_to_mobile else _driver_logs_url_for_date(local_date)
    guard = _guard_route_record_mutation(
        current_user.id,
        local_date,
        "driver log",
        "create",
        next_url=next_url,
    )
    if guard:
        return guard

    if form.validate_on_submit():
        if pending_ryder_event:
            flash("Close the open service status before entering the next stop.", "warning")
            return _render_new_driving_log(form, current_load, route_context=route_context, return_to_mobile=return_to_mobile)
        is_day_driver = getattr(current_user, "is_day_driver", False)
        if not form.plant_name.data and not is_day_driver:
            flash("Please select the plant you arrived at.", "danger")
            return _render_new_driving_log(form, current_load, route_context=route_context, return_to_mobile=return_to_mobile)
        stop_name = (form.location.data or "").strip()
        stop_address = (form.location_address.data or "").strip()
        if is_day_driver and not form.plant_name.data:
            # Day drivers describe stops by where they are (free-text location),
            # falling back to the address/commodity so old habits still produce a label.
            form.plant_name.data = (
                stop_name[:120]
                or stop_address[:120]
                or (form.commodity.data or "").strip()[:120]
                or "Day Route"
            )
        open_stop = _open_stop_for_driver(current_user.id, local_date)
        if open_stop:
            flash(f"Close the open stop at {_plant_label(open_stop.plant_name)} before creating the next stop.", "warning")
            return redirect(next_url)

        arrival_load = current_load_value or "Empty"
        arrival_secondary_load = current_secondary_value or None

        now_utc = datetime.utcnow()
        arrive_time_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        carried_commodity = (form.commodity.data or "").strip() or None
        carried_weight = (form.weight.data or "").strip() or None
        gps_latitude = _optional_float_from_form("gps_latitude", minimum=-90, maximum=90) if is_day_driver else None
        gps_longitude = _optional_float_from_form("gps_longitude", minimum=-180, maximum=180) if is_day_driver else None
        gps_accuracy_m = _optional_float_from_form("gps_accuracy_m", minimum=0, maximum=50000) if is_day_driver else None
        if is_day_driver and not carried_commodity:
            # Cargo is described once, at the pickup's departure. If the latest
            # closed stop left loaded, that load is what's arriving here.
            prev_departed = (
                _active_driver_logs_query()
                .filter(
                    DriverLog.driver_id == current_user.id,
                    DriverLog.depart_time.isnot(None),
                )
                .order_by(DriverLog.id.desc())
                .first()
            )
            if prev_departed and not is_empty_load(prev_departed.depart_load_size):
                carried_commodity = prev_departed.commodity
                carried_weight = prev_departed.weight
                if is_empty_load(arrival_load):
                    arrival_load = prev_departed.depart_load_size
        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=arrival_load,
            secondary_load=arrival_secondary_load,
            commodity=carried_commodity,
            weight=carried_weight,
            location_address=stop_address[:255] if is_day_driver and stop_address else None,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_accuracy_m=gps_accuracy_m,
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
        try:
            db.session.add(newlog)
            db.session.flush()
            if (
                is_day_driver
                and gps_latitude is not None
                and gps_longitude is not None
                and (newlog.plant_name or "").strip()
            ):
                remember_place(
                    current_user.id,
                    newlog.plant_name,
                    gps_latitude,
                    gps_longitude,
                    place_type="unknown",
                    usual_load=carried_commodity or (None if is_empty_load(arrival_load) else arrival_load),
                    now=now_utc,
                )
            _append_driver_log_flow_event(
                newlog,
                "ARRIVED_DESTINATION",
                notes=f"Arrived at {_plant_label(newlog.plant_name)}.",
                payload={"driver_action": "arrive"},
            )
            record_activity(
                user_id=current_user.id,
                category="log",
                action="submitted",
                title="Driver log submitted",
                details=f"{newlog.plant_name} arrival with {cargo_display(newlog.load_size, newlog.secondary_load)} for {newlog.date}.",
                target_type="driver_log",
                target_id=newlog.id,
                commit=False,
            )
            ingest_driver_log(newlog, commit=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Driver arrival could not be saved for user_id=%s", current_user.id)
            flash("Arrival could not be saved. Try again.", "danger")
            return _render_new_driving_log(form, current_load, route_context=route_context, return_to_mobile=return_to_mobile)
        _emit_driver_log_updated(newlog, "submitted")
        flash("Arrival recorded.", "success")
        return redirect(url_for("driver.mobile_dashboard") if return_to_mobile else _driver_logs_url_for_date(newlog.date))

    _prefill_log_form_from_task(form)
    expected_destination = (
        (request.args.get("expected_destination") or "").strip()
        or ((route_context.next_stop_context or {}).get("destination") or "")
    )
    # Day-driver customer names must remain editable discovery fields. Keep the
    # expected destination as a GPS/search hint in the template instead of
    # pre-filling stale text that blocks suggestions.
    if expected_destination and not getattr(current_user, "is_day_driver", False) and not form.plant_name.data:
        ensure_legacy_plant_choice(form.plant_name, expected_destination)
        form.plant_name.data = expected_destination
    form.load_size.data = current_load_value if current_load_value != "Empty" else "Empty"
    form.secondary_load.data = current_secondary_value
    if getattr(current_user, "is_day_driver", False):
        _prefill_day_driver_cargo(form, current_user.id, local_date)
        if not _open_stop_for_driver(current_user.id, local_date):
            last_loaded = (
                DriverLog.query.filter(
                    DriverLog.driver_id == current_user.id,
                    DriverLog.date == local_date,
                    DriverLog.deleted_at.is_(None),
                    DriverLog.depart_time.isnot(None),
                    DriverLog.destination.isnot(None),
                )
                .order_by(DriverLog.id.desc())
                .first()
            )
            if last_loaded and not is_empty_load(last_loaded.depart_load_size):
                # In transit: arriving means landing at the destination typed on
                # the last loaded departure. Keep the customer name blank so GPS
                # and Google suggestions show immediately; address can still be
                # prefilled because it is the stronger physical stop fact.
                if not form.location_address.data:
                    form.location_address.data = last_loaded.destination_address
    if request.args.get("report_type") == "truck_issue":
        form.maintenance.data = True
    elif request.args.get("report_type") == "route_note":
        form.meeting.data = True
    elif request.args.get("report_type") == "fuel":
        # Quick-log "Fuel": open the existing per-stop fuel capture with the
        # fuel flag pre-checked so the driver just confirms the stop + odometer.
        form.fuel.data = True
    return _render_new_driving_log(form, current_load, route_context=route_context, return_to_mobile=return_to_mobile)


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
    if current_user.role != "driver":
        flash("Driver access required.", "warning")
        return redirect(url_for("driver.dashboard"))
    if _driver_route_record_finalized(current_user.id, log_date):
        flash("That route is finalized. Driver Log entries cannot be changed.", "warning")
        return redirect(_driver_logs_url_for_date(log_date))

    if form.validate_on_submit():
        if getattr(current_user, "is_day_driver", False) and not form.plant_name.data:
            form.plant_name.data = (form.commodity.data or "").strip() or "Day Route"
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
        db.session.flush()
        _append_driver_log_flow_event(
            newlog,
            "ARRIVED_DESTINATION",
            notes=f"Retroactive arrival at {_plant_label(newlog.plant_name)}.",
            payload={"driver_action": "add_stop"},
        )

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
        return redirect(_driver_logs_url_for_date(newlog.date))

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
    guard = _guard_driver_log_mutation(log, "edit", next_url=_driver_logs_url_for_date(log.date))
    if guard:
        return guard

    form = DriverLogForm(obj=log)
    ensure_legacy_plant_choice(form.plant_name, log.plant_name)
    if request.method == "GET":
        form.arrive_time.data = _arrival_utc_to_local_hhmm(log.arrive_time)
        issue_code, issue_notes = _split_truck_issue_text(truck_issue_reason(log) or route_problem_reason(log))
        form.truck_issue.data = issue_code
        form.truck_issue_notes.data = issue_notes
        form.departure_destination.data = destination_from_load(log.depart_load_size) or ""
        form.secondary_departure_dest.data = destination_from_load(log.secondary_load) or ""
        form.secondary_departure_type.data = load_type_from_load(log.secondary_load)
    if form.validate_on_submit():
        guard = _guard_driver_log_mutation(log, "update")
        if guard:
            return guard
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
    guard = _guard_driver_log_mutation(
        log,
        "delete proof from",
        next_url=request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id),
    )
    if guard:
        return guard
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
    next_url = request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id)
    guard = _guard_driver_log_mutation(
        log,
        "attach a document to",
        wants_json=_photo_upload_wants_json(),
        next_url=next_url,
    )
    if guard:
        if not _photo_upload_wants_json():
            flash("UPLOAD FAILED\nNot authorized to attach a document to this stop.", "danger")
        return guard

    document_type = (request.form.get("document_type") or "").strip()
    capture_source = (request.form.get("source") or "gallery").strip() or "gallery"
    owner_type = (request.form.get("owner_type") or "").strip()
    owner_id = (request.form.get("owner_id") or "").strip()
    upload_source = f"{document_type}_{capture_source}" if document_type else capture_source

    try:
        photo = _save_driver_log_photo(
            log,
            _first_uploaded_file(request.files.getlist("photo")),
            source=upload_source,
            note=request.form.get("note"),
            uploaded_by_id=current_user.id,
        )
    except ValueError as exc:
        db.session.rollback()
        message = str(exc) or "File was not saved. Try again."
        if _photo_upload_wants_json():
            return jsonify({"error": message}), 400
        flash(f"UPLOAD FAILED\n{message}", "danger")
        return redirect(next_url)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Driver log document upload failed for log_id=%s", log.id)
        if _photo_upload_wants_json():
            return jsonify({"error": "Upload failed. Try again."}), 500
        flash("UPLOAD FAILED\nUpload failed. Try again.", "danger")
        return redirect(next_url)

    if document_type:
        photo.document_type = document_type[:40]
    photo.owner_type = (owner_type or "stop")[:30]
    photo.owner_id = (owner_id or str(log.id))[:40]

    record_activity(
        user_id=current_user.id,
        category="log_photo",
        action="created",
        title="Stop document uploaded",
        details=f"{_plant_label(log.plant_name)} {photo.document_type_label}: {photo.original_filename or photo.filename}. Note: {photo.note}",
        target_type="driver_log_photo",
        target_id=photo.id,
        commit=False,
    )
    db.session.commit()
    if _photo_upload_wants_json():
        return jsonify({"photo": _driver_log_photo_payload(photo)})
    toast_title, toast_detail = _document_attached_toast(log, photo)
    flash(f"{toast_title}\n{toast_detail}", "success")
    return redirect(next_url)


@bp.route("/driver_logs/<int:log_id>/part-scans", methods=["POST"], strict_slashes=False)
@login_required
def record_part_scan(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    guard = _guard_driver_log_mutation(log, "scan against", wants_json=True)
    if guard:
        return guard
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
    quick_depart = (
        request.form.get("next") == "mobile"
        or request.args.get("next") == "mobile"
        or request.form.get("source") == "live_flow"
    )
    quick_fetch = quick_depart and request.headers.get("X-Requested-With") == "fetch"

    def depart_redirect():
        return redirect(url_for("driver.mobile_dashboard" if quick_depart else "driver.driver_logs"))

    def quick_depart_error(message, status=400):
        if quick_fetch:
            return jsonify({"ok": False, "error": message}), status
        flash(message, "danger")
        if quick_depart:
            return depart_redirect()
        return render_depart_page()

    def quick_depart_success(message):
        if quick_fetch:
            return jsonify({"ok": True, "message": message, "redirect": url_for("driver.mobile_dashboard")})
        flash(message, "success")
        return depart_redirect()

    if current_user.role == "driver" and log.driver_id != current_user.id:
        if quick_fetch:
            return jsonify({"ok": False, "error": "Not authorized to depart someone else's log!"}), 403
        flash("Not authorized to depart someone else's log!", "danger")
        return depart_redirect()
    guard = _guard_driver_log_mutation(
        log,
        "depart",
        wants_json=quick_fetch,
        next_url=url_for("driver.mobile_dashboard" if quick_depart else "driver.driver_logs"),
    )
    if guard:
        return guard
    if log.depart_time:
        if quick_fetch:
            return jsonify({"ok": False, "error": "That log already has a departure time."}), 409
        flash("That log already has a departure time.", "warning")
        return depart_redirect()

    form = DepartForm()
    route = _driver_log_context_for(log)
    service_stop = is_service_stop(log)
    service_label = service_stop_label(log) if service_stop else ""

    def render_depart_page():
        if quick_depart:
            if quick_fetch:
                error = next(
                    (
                        f"{field.label.text}: {messages[0]}"
                        for field in form
                        if getattr(field, "errors", None)
                        for messages in [field.errors]
                        if messages
                    ),
                    "Departure could not be saved. Check the required answers and try again.",
                )
                return jsonify({"ok": False, "error": error, "errors": form.errors}), 400
            return redirect(url_for("driver.mobile_dashboard"))
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
        is_day_driver = getattr(current_user, "is_day_driver", False)
        primary_destination_address = (request.form.get("destination_address") or "").strip()[:255]
        primary_destination_text = (request.form.get("destination_text") or "").strip()[:120]
        primary_destination_label = primary_destination_text or primary_destination_address[:120]
        posted_primary_commodity = (form.commodity.data or "").strip()
        posted_primary_weight = (form.weight.data or "").strip()
        primary_commodity = posted_primary_commodity or (log.commodity or "").strip()
        primary_weight = posted_primary_weight or (log.weight or "").strip()
        secondary_commodity = (request.form.get("secondary_commodity") or "").strip()[:120]
        secondary_weight = (request.form.get("secondary_weight") or "").strip()[:40]
        secondary_destination_address = (request.form.get("secondary_destination_address") or "").strip()[:255]
        secondary_destination_text = (request.form.get("secondary_destination_text") or "").strip()[:120]
        secondary_destination_label = secondary_destination_text or secondary_destination_address[:120]
        primary_unloaded = None
        primary_unload_reason = None
        day_driver_carrying = is_day_driver and (
            bool(log.commodity) or not is_empty_load(getattr(log, "load_size", None))
        )
        freight_primary_aboard = is_day_driver and is_freight_load(getattr(log, "load_size", None))
        freight_primary_destined_here = freight_primary_aboard and freight_load_destined_here(
            log.load_size, log.plant_name, getattr(log, "location_address", None)
        )
        if not service_stop and (route.get("arrived_at_primary_destination") or day_driver_carrying):
            primary_unloaded = form.unloaded_on_departure.data
            if primary_unloaded not in {"yes", "no"}:
                return quick_depart_error("Please answer whether you got unloaded.")
            if primary_unloaded == "no":
                primary_unload_reason = (form.unload_reason.data or "").strip()
                # A reason is only demanded when refusing a drop AT the load's
                # destination; "No" elsewhere just means it rides along.
                needs_reason = route.get("arrived_at_primary_destination") or freight_primary_destined_here
                if not primary_unload_reason and needs_reason:
                    return quick_depart_error("Please enter why the load was not unloaded.")

        secondary_dropped = None
        secondary_drop_reason = None
        freight_secondary_aboard = is_day_driver and not service_stop and is_freight_load(getattr(log, "secondary_load", None))
        if not service_stop and (route.get("arrived_at_secondary_destination") or freight_secondary_aboard):
            secondary_dropped = form.secondary_dropped_on_departure.data
            if secondary_dropped not in {"yes", "no"}:
                if freight_secondary_aboard:
                    return quick_depart_error("Please answer whether you dropped off the second load.")
                return quick_depart_error("Please answer whether you dropped off the second-stop cargo.")
            if secondary_dropped == "no":
                secondary_drop_reason = (form.secondary_unload_reason.data or "").strip()
                needs_reason = route.get("arrived_at_secondary_destination") or (
                    freight_secondary_aboard
                    and freight_load_destined_here(log.secondary_load, log.plant_name, getattr(log, "location_address", None))
                )
                if not secondary_drop_reason and needs_reason:
                    return quick_depart_error("Please enter why the second load was not dropped off.")

        new_pickup_keeps_old = (
            is_day_driver
            and not service_stop
            and form.got_loaded.data == "yes"
            and primary_unloaded == "no"
            and freight_primary_aboard
        )

        after_unload_primary = route.get("after_arrival_primary") or "Empty"
        if primary_unloaded == "yes":
            after_unload_primary = "Empty"
            if not posted_primary_commodity:
                primary_commodity = ""
            if not posted_primary_weight:
                primary_weight = ""

        if service_stop:
            departure_load = route.get("after_arrival_primary") or load_display(log.load_size) or "Empty"
        elif form.got_loaded.data == "yes":
            if form.destination.data:
                departure_load = destination_load_value(form.destination.data)
            elif is_day_driver:
                # Freight: the truck carries a commodity, not a plant load. The
                # free-text destination is stored on the log at save time below.
                # When the old load stays aboard, the new label comes from what
                # was typed for the new pickup — never the kept load's details.
                commodity_for_label = posted_primary_commodity if new_pickup_keeps_old else primary_commodity
                weight_for_label = posted_primary_weight if new_pickup_keeps_old else primary_weight
                if not commodity_for_label and not primary_destination_label:
                    return quick_depart_error("Enter the load or destination before departing loaded.")
                departure_load = _freight_departure_label(
                    commodity_for_label,
                    weight_for_label,
                    primary_destination_label,
                )
            else:
                return quick_depart_error("Please select where the primary load is going.")
        elif form.got_loaded.data == "no":
            departure_load = after_unload_primary
        else:
            return quick_depart_error("Please answer whether you picked up a load here.")

        secondary_load = route.get("after_arrival_secondary") or None
        if not service_stop:
            if secondary_dropped == "yes":
                secondary_load = None
            if form.secondary_destination.data:
                secondary_load = secondary_load_value(form.secondary_destination.data, form.secondary_load_type.data)
            if is_day_driver and (secondary_commodity or secondary_weight or secondary_destination_label):
                if secondary_load and secondary_dropped != "yes" and freight_secondary_aboard:
                    return quick_depart_error("Two loads max - drop the second load here before adding another.")
                secondary_load = _freight_departure_label(
                    secondary_commodity,
                    secondary_weight,
                    secondary_destination_label,
                    fallback="Second load",
                )

        if new_pickup_keeps_old:
            # Keeping the old load while picking up a new one: the kept load
            # moves to the second slot; the truck tracks two loads max.
            if secondary_load:
                return quick_depart_error("Two loads max - record a drop here before picking up another load.")
            secondary_load = (log.load_size or "").strip()

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
            return quick_depart_error(timing_errors[0])
        try:
            log.depart_time = depart_time
            log.dock_wait_minutes = _auto_wait_minutes_for_departure(log, now_local)
            log.depart_load_size = departure_load
            log.secondary_load = secondary_load or None
            if is_day_driver:
                log.destination = primary_destination_label or secondary_destination_label or None
                log.destination_address = primary_destination_address or secondary_destination_address or None
            # Day-driver: capture commodity + weight when a load is picked up here;
            # clear it when the truck leaves empty so nothing lingers onboard.
            if form.got_loaded.data == "yes":
                log.commodity = primary_commodity or ("Loaded" if is_day_driver else log.commodity)
                log.weight = primary_weight or log.weight
            elif primary_unloaded == "yes" or (departure_load == "Empty" and not (secondary_load or None)):
                log.commodity = None
                log.weight = None
            _set_departure_unload_reasons(log, primary_unload_reason, secondary_drop_reason)
            log.no_pickup = False if service_stop else departure_load == "Empty" and not log.secondary_load
            _sync_next_open_stop_arrival_cargo(log)
            _append_driver_log_flow_event(
                log,
                "DEPARTED_ORIGIN",
                notes=f"Departed {_plant_label(log.plant_name)} with {cargo_display(log.depart_load_size, log.secondary_load)}.",
                payload={"driver_action": "depart", "service_stop": bool(service_stop)},
            )
            record_activity(
                user_id=current_user.id,
                category="log",
                action="departed",
                title="Driver log departed",
                details=f"{log.plant_name} departed at {_format_display_time(log.depart_time)} with {cargo_display(log.depart_load_size, log.secondary_load)}.",
                target_type="driver_log",
                target_id=log.id,
                commit=False,
            )
            ingest_driver_log(log, commit=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Driver departure could not be saved for log_id=%s", log.id)
            return quick_depart_error("Departure could not be saved. Try again.", 500)
        _emit_driver_log_updated(log, "departed")
        success_message = f"Departed {log.plant_name} with {cargo_display(log.depart_load_size, log.secondary_load)}."
        if getattr(current_user, "is_day_driver", False):
            if log.destination:
                success_message = (
                    f"Departed {log.plant_name} with "
                    f"{cargo_display(log.depart_load_size, log.secondary_load)}, headed to {log.destination}."
                )
        elif quick_depart and form.got_loaded.data == "yes" and not form.secondary_destination.data:
            success_message = f"{success_message} No second stop selected."
        return quick_depart_success(success_message)

    return render_depart_page()




@bp.route("/driver_logs/<int:log_id>/no_pickup", methods=["POST"], strict_slashes=False)
@login_required
def no_pickup_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    guard = _guard_driver_log_mutation(log, "update")
    if guard:
        return guard
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
    _append_driver_log_flow_event(
        log,
        "DEPARTED_ORIGIN",
        notes=f"No pickup at {_plant_label(log.plant_name)}.",
        payload={"driver_action": "no_pickup"},
    )
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
    guard = _guard_driver_log_mutation(log, "pick up from")
    if guard:
        return guard
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
        log.commodity = (form.commodity.data or "").strip() or log.commodity
        log.weight = (form.weight.data or "").strip() or log.weight
        log.hot_parts = bool(form.hot_parts.data)
        log.part_number = _form_hot_part_number(form) or (log.part_number if log.hot_parts else None)
        log.dock_wait_minutes = _auto_wait_minutes_for_departure(log, now_local)
        log.maintenance = form.maintenance.data
        log.downtime_reason = _compose_downtime_reason(_preserved_non_truck_reasons(log), _form_truck_issue_text(form), form.maintenance.data)
        log.fuel = form.fuel.data
        log.fuel_mileage = _form_mileage_value(form)
        log.meeting = form.meeting.data
        _sync_next_open_stop_arrival_cargo(log)
        _append_driver_log_flow_event(
            log,
            "DEPARTED_ORIGIN",
            notes=f"Pickup recorded at {_plant_label(log.plant_name)} with {load_display(log.depart_load_size)}.",
            payload={"driver_action": "pickup"},
        )
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
    issue_review = None
    issue_closeout = (
        ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_resolved",
            ExceptionEvent.stop_id == log.id,
        )
        .order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc())
        .first()
    )
    route_map_context = build_driver_route_map_context(driver=log.driver, date=log.date)
    for stop in route_map_context.get("stops", []):
        if stop.get("stop_id") == log.id:
            issue_review = stop
            break
    return render_template(
        "view_driver_log.html",
        log=log,
        today_local_date=_today_local_date(),
        driver_log_photos=list(log.photos),
        issue_review=issue_review,
        issue_closeout=issue_closeout,
        route_finalized=_driver_route_record_finalized(log.driver_id, log.date),
    )


@bp.route("/driver_logs_print")
@login_required
def driver_logs_print():
    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    selected_date = _selected_log_date_from_request()
    today_local_date = _today_local_date()
    if selected_date == today_local_date:
        _repair_today_pretrip_dates(current_user.id, today_local_date)
    logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=current_user.id, date=selected_date).all(),
        key=_driver_log_sort_key,
    )
    pretrips = _active_pretrips_query().filter_by(
        user_id=current_user.id, pretrip_date=selected_date
    ).all()
    route_context = build_route_context(driver_id=current_user.id, route_date=selected_date, now=now_local)
    log_routes = route_context.log_routes if route_context else _driver_log_route_context(logs)
    route_sheet_data = _route_sheet_supporting_data(current_user.id, selected_date, logs, log_routes, route_context, now=now_local)
    record_activity(
        user_id=current_user.id,
        category="print",
        action="logs_printed",
        title="Driver logs printed",
        details=f"Printed {len(logs)} log(s) for {selected_date}.",
        target_type="driver_log",
    )
    route_task_events = _task_route_events_for_logs(logs)
    shift_record = _shift_record_for_driver_date(current_user.id, selected_date, require_signature=True)
    shift_timing_record = _shift_record_for_driver_date(current_user.id, selected_date)
    log_sheet = _driver_log_sheet_model(
        current_user,
        selected_date,
        logs,
        pretrips,
        log_routes,
        route_context,
        route_sheet_data,
        route_task_events,
        shift_timing_record,
        now=now_local,
    )
    return render_template(
        "driver_logs_print.html",
        logs=logs,
        log_routes=log_routes,
        the_date=selected_date,
        pretrips=pretrips,
        damage_reports=route_sheet_data["damage_reports"],
        damage_report_summary=damage_report_count_label(route_sheet_data["damage_reports"]),
        damage_report_details=route_sheet_data["damage_report_details"],
        total_miles=_total_miles_for_pretrips(pretrips),
        parts_carried=route_sheet_data["parts_carried"],
        exception_notes=route_sheet_data["exception_notes"],
        log_issue_details=route_sheet_data["log_issue_details"],
        route_documents=route_sheet_data["route_documents"],
        route_sheet_summary=route_sheet_data["summary"],
        route_task_events=route_task_events,
        log_sheet=log_sheet,
        stop_forecasts=route_context.stop_timing,
        route_state=route_context.route_state,
        route_context=route_context,
        route_finalized=route_context.route_finalized,
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
    if request.method == "GET":
        flash("Use the shift button to start a shift.", "info")
        return _shift_redirect()

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
    if request.method == "GET":
        flash("Use the shift button to end a shift.", "info")
        return _shift_redirect()

    ended_at = datetime.utcnow()
    closed_shifts = _end_open_shifts_for_driver(current_user.id, ended_at)
    if not closed_shifts:
        flash("No open shift found!", "warning")
        return _shift_redirect()

    db.session.commit()
    for shift in closed_shifts:
        record_activity(
            user_id=current_user.id,
            category="shift",
            action="ended",
            title="Shift ended",
            details=f"Total hours: {shift.total_hours:.2f}.",
            target_type="shift",
            target_id=shift.id,
            commit=False,
        )
    db.session.commit()

    flash("Shift ended!", "success")
    return _shift_redirect()


@bp.route("/mobile/end-route", methods=["GET", "POST"])
@login_required
def mobile_end_route():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    if request.method == "GET":
        flash("Use Finalize Route from the mobile board to close the route.", "info")
        return redirect(url_for("driver.mobile_dashboard"))

    now_local, _ = _now_local_and_utc()
    today_local_date, logs, pretrips_today, plant_transfers_today = _get_today_eod_records()
    logs = sorted(logs, key=_driver_log_sort_key)
    open_shift = _open_shift_for_driver(current_user.id)
    route_context = build_route_context(driver_id=current_user.id, route_date=today_local_date, now=now_local)
    active_pretrip = _select_route_pretrip(pretrips_today, route_context=route_context, open_shift=open_shift)

    can_finish_closed_route = _route_can_finish_after_closed_stops(
        route_context,
        today_local_date,
        today_local_date,
    )
    can_end_current_stop = _route_can_end_at_current_stop(
        route_context,
        today_local_date,
        today_local_date,
    )
    if (can_finish_closed_route or can_end_current_stop) and not _route_has_completed_posttrip(route_context, active_pretrip):
        if not active_pretrip:
            flash("Complete PostTrip before finishing the route.", "warning")
            return redirect(url_for("driver.mobile_dashboard"))
        flash("Complete PostTrip before finishing the route.", "warning")
        return redirect(url_for("driver.do_posttrip", pretrip_id=active_pretrip.id))

    if not can_finish_closed_route and not can_end_current_stop:
        flash("Complete PostTrip first, or record departure if this stop continues the route.", "warning")
        return redirect(url_for("driver.mobile_dashboard"))

    unresolved_departures = unresolved_departure_logs(logs, route_finalized=True)
    if unresolved_departures:
        stop = unresolved_departures[0]
        flash(f"Correct departure for {_plant_label(stop.plant_name)} before ending the route.", "warning")
        return redirect(url_for("driver.view_driver_log", log_id=stop.id))

    _end_open_shifts_for_driver(current_user.id)
    db.session.commit()
    _record_eod_finalized(today_local_date, logs, pretrips_today, plant_transfers_today)
    for log in logs[-1:]:
        _emit_driver_log_updated(log, "route_finished")
    flash("Route finished. The route sheet is finalized.", "success")
    return redirect(url_for("driver.mobile_dashboard"))


@bp.route("/end_of_day_summary", methods=["GET", "POST"])
@login_required
def end_of_day_summary():
    form = EndOfDayForm()
    now_local, _ = _now_local_and_utc()
    today_local_date, logs, pretrips_today, plant_transfers_today = _get_today_eod_records()
    open_shift = _open_shift_for_driver(current_user.id)
    route_context = build_route_context(driver_id=current_user.id, route_date=today_local_date, now=now_local)
    active_pretrip = _select_route_pretrip(pretrips_today, route_context=route_context, open_shift=open_shift)
    pending_posttrip = _posttrip_due_for_route(active_pretrip, route_context, finalizing=True)
    if form.validate_on_submit():
        if _driver_route_record_finalized(current_user.id, today_local_date):
            flash("That route is finalized. Route closeout cannot be changed.", "warning")
            return redirect(url_for("driver.driver_logs_print"))
        if pending_posttrip:
            flash("Complete PostTrip before final route closeout.", "warning")
            return redirect(url_for("driver.do_posttrip", pretrip_id=active_pretrip.id))
        unresolved_departures = unresolved_departure_logs(
            sorted(logs, key=_driver_log_sort_key),
            route_finalized=True,
        )
        if unresolved_departures:
            stop = unresolved_departures[0]
            flash(f"Correct departure for {_plant_label(stop.plant_name)} before ending the route.", "warning")
            return redirect(url_for("driver.view_driver_log", log_id=stop.id))

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

        _end_open_shifts_for_driver(current_user.id)
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
        pending_posttrip=pending_posttrip,
        pending_posttrip_pretrip=active_pretrip if pending_posttrip else None,
    )


@bp.route("/end_of_day_print")
@login_required
def end_of_day_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    _repair_today_pretrip_dates(current_user.id, today_local_date)
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    plant_transfers = _active_plant_transfers_query().filter_by(
        user_id=current_user.id, transfer_date=today_local_date
    ).all()
    route_context = build_route_context(driver_id=current_user.id, route_date=today_local_date)
    open_shift = _open_shift_for_driver(current_user.id)
    pretrips_today = _pretrips_with_route_record_first(
        _route_pretrips_for_driver_date(current_user.id, today_local_date),
        route_context=route_context,
        open_shift=open_shift,
    )
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
    _repair_today_pretrip_dates(current_user.id, today_local_date)
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    plant_transfers = _active_plant_transfers_query().filter_by(
        user_id=current_user.id, transfer_date=today_local_date
    ).all()
    route_context = build_route_context(driver_id=current_user.id, route_date=today_local_date)
    open_shift = _open_shift_for_driver(current_user.id)
    pretrips_today = _pretrips_with_route_record_first(
        _route_pretrips_for_driver_date(current_user.id, today_local_date),
        route_context=route_context,
        open_shift=open_shift,
    )
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
            pretrips=pretrips_today,
        ),
        filename=f"end-of-day-{today_local_date}.pdf",
        target_type="end_of_day",
        title="End of Day PDF downloaded",
    )

@bp.route("/submit_end_of_day", methods=["POST"])
@login_required
def submit_end_of_day():
    today_local_date, logs, pretrips_today, plant_transfers_today = _get_today_eod_records()
    if _driver_route_record_finalized(current_user.id, today_local_date):
        flash("That route is finalized. Route closeout cannot be changed.", "warning")
        return redirect(url_for("driver.dashboard"))
    now_local, _ = _now_local_and_utc()
    open_shift = _open_shift_for_driver(current_user.id)
    route_context = build_route_context(driver_id=current_user.id, route_date=today_local_date, now=now_local)
    active_pretrip = _select_route_pretrip(pretrips_today, route_context=route_context, open_shift=open_shift)
    if _posttrip_due_for_route(active_pretrip, route_context, finalizing=True):
        flash("Complete PostTrip before final route closeout.", "warning")
        return redirect(url_for("driver.do_posttrip", pretrip_id=active_pretrip.id))
    unresolved_departures = unresolved_departure_logs(
        sorted(logs, key=_driver_log_sort_key),
        route_finalized=True,
    )
    if unresolved_departures:
        stop = unresolved_departures[0]
        flash(f"Correct departure for {_plant_label(stop.plant_name)} before ending the route.", "warning")
        return redirect(url_for("driver.view_driver_log", log_id=stop.id))

    _end_open_shifts_for_driver(current_user.id)
    db.session.commit()
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


@bp.route("/reports")
@login_required
def driver_reports():
    report_context = build_report_context(
        user=current_user,
        selected_report_type=request.args.get("report_type"),
        driver_log_id=request.args.get("driver_log_id", type=int),
        stop_id=request.args.get("stop_id", type=int),
    )
    report_choices = [
        {
            "label": "Fuel / Low Fuel",
            "meta": "Fuel purchase, low fuel, receipt, odometer, and IFTA support details.",
            "url": url_for("driver.new_ifta_worksheet"),
        },
        {
            "label": "Physical Damage",
            "meta": "Visible vehicle, trailer, cargo, or property damage.",
            "url": url_for("driver.new_damage_report"),
        },
        {
            "label": "Crash / Safety Incident",
            "meta": "Crash, hit, dock or yard safety event, injury, tow-away, police, or claim details.",
            "url": url_for("driver.new_accident_incident"),
        },
        {
            "label": "Truck Issue / Maintenance",
            "meta": "Opens the route stop form because truck issues are recorded on the stop.",
            "url": url_for("driver.new_driving_log", report_type="truck_issue"),
        },
        {
            "label": "Route Note / Other",
            "meta": "Opens the route stop form because route notes are recorded with the stop record.",
            "url": url_for("driver.new_driving_log", report_type="route_note"),
        },
    ]
    recent_reports = []
    for report in (
        DamageReport.query.filter_by(reported_by_id=current_user.id)
        .order_by(DamageReport.created_at.desc())
        .limit(5)
    ):
        recent_reports.append(
            {
                "type": "Physical Damage",
                "title": report.description or "Damage report",
                "status": report.status or "open",
                "created_at": report.created_at,
                "url": url_for("driver.view_damage_report", report_id=report.id),
            }
        )
    for report in (
        AccidentIncidentReport.query.filter(
            or_(
                AccidentIncidentReport.driver_id == current_user.id,
                AccidentIncidentReport.created_by_id == current_user.id,
            )
        )
        .order_by(AccidentIncidentReport.created_at.desc())
        .limit(5)
    ):
        recent_reports.append(
            {
                "type": "Crash or Safety Incident",
                "title": report.plant_or_location or "Incident report",
                "status": report.manager_review_status or "open",
                "created_at": report.created_at,
                "url": url_for("driver.view_accident_incident", report_id=report.id),
            }
        )
    for worksheet in (
        IftaWorksheet.query.filter(
            or_(
                IftaWorksheet.driver_id == current_user.id,
                IftaWorksheet.created_by_id == current_user.id,
            )
        )
        .order_by(IftaWorksheet.created_at.desc())
        .limit(5)
    ):
        recent_reports.append(
            {
                "type": "Fuel Record",
                "title": worksheet.truck or "Fuel or odometer record",
                "status": worksheet.review_status or "Draft",
                "created_at": worksheet.created_at,
                "url": url_for("driver.view_ifta_worksheet", worksheet_id=worksheet.id),
            }
        )
    recent_reports = sorted(
        recent_reports,
        key=lambda item: item["created_at"] or datetime.min,
        reverse=True,
    )[:8]
    return render_template(
        "driver_reports.html",
        report_choices=report_choices,
        report_context=report_context,
        report_count=len(recent_reports),
        recent_reports=recent_reports,
    )


@bp.route("/driver_logs/<int:log_id>/request_review", methods=["POST"], strict_slashes=False)
@login_required
def request_manager_review(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role != "driver" or log.driver_id != current_user.id:
        flash("Only the assigned driver can send this stop to manager review.", "warning")
        return redirect(url_for("driver.mobile_dashboard"))
    guard = _guard_driver_log_mutation(
        log,
        "request manager review for",
        next_url=url_for("driver.mobile_dashboard"),
    )
    if guard:
        return guard
    db.session.add(ExceptionEvent(
        event_type="manager_review_requested", severity="medium",
        stop_id=log.id, driver_log_id=log.id,
        driver_id=getattr(current_user, "id", None),
        plant_name=getattr(log, "plant_name", None),
        event_date=getattr(log, "date", None),
        summary="Driver requested manager review",
        details=(request.form.get("reason") or "").strip() or None,
    ))
    db.session.commit()
    flash("Sent to manager review.", "info")
    return redirect(url_for("driver.mobile_dashboard"))


@bp.route("/driver_logs/<int:log_id>/close_issue", methods=["POST"], strict_slashes=False)
@login_required
def close_driver_log_issue(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role != "driver" or log.driver_id != current_user.id:
        flash("Only the assigned driver can close this issue to continue.", "warning")
        return redirect(url_for("driver.view_driver_log", log_id=log.id))
    guard = _guard_driver_log_mutation(
        log,
        "close an issue on",
        next_url=request.form.get("next") or url_for("driver.view_driver_log", log_id=log.id),
    )
    if guard:
        return guard

    issue_type = (request.form.get("issue_type") or "route_issue").strip()
    resolution_action = (request.form.get("resolution_action") or "Close issue to continue").strip()
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Add a closeout reason so the manager can review why the route continued.", "warning")
        return redirect(request.form.get("next") or url_for("driver.view_driver_log", log_id=log.id))

    details = f"Issue: {issue_type.replace('_', ' ').title()}. Action: {resolution_action}. Reason: {reason}"
    db.session.add(ExceptionEvent(
        event_type="manager_review_resolved",
        severity="medium",
        stop_id=log.id,
        driver_log_id=log.id,
        driver_id=current_user.id,
        plant_name=getattr(log, "plant_name", None),
        event_date=getattr(log, "date", None),
        summary="Driver closed issue to continue",
        details=details,
    ))
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="exception",
        action="driver_closed",
        title="Driver issue closed to continue",
        details=f"{_plant_label(log.plant_name)} stop #{log.id}; {details}",
        target_type="driver_log",
        target_id=log.id,
    )
    _emit_driver_log_updated(log, "issue_closed")
    flash("Issue closed with driver reason. Manager can still review the closeout.", "success")
    return redirect(request.form.get("next") or url_for("driver.mobile_dashboard"))


@bp.route("/damage_reports/new", methods=["GET", "POST"])
@login_required
def new_damage_report():
    form = DamageReportForm()
    guard = _guard_route_record_mutation(
        current_user.id,
        _today_local_date(),
        "damage report",
        "create",
        next_url=url_for("driver.damage_reports"),
    )
    if guard:
        return guard
    if form.validate_on_submit():
        classification = classify_packet_text(
            form.description.data,
            form.move_reference.data,
            form.plant_name.data,
            form.truck_number.data,
            form.trailer_number.data,
        )
        if classification.packet_type == PacketClassification.FUEL_ODO_IFTA.value:
            worksheet = create_ifta_worksheet_from_form(
                _fuel_form_from_damage_form(form),
                {"receipt_photo": request.files.get(form.photo.name)},
                user=current_user,
                report_context=build_report_context(
                    user=current_user,
                    selected_report_type="fuel_odo_ifta",
                ),
            )
            record_activity(
                user_id=current_user.id,
                category="ifta",
                action="created",
                title="Fuel Record created",
                details="Fuel/odometer issue was routed to Fuel Records instead of Physical Damage.",
                target_type="ifta_worksheet",
                target_id=worksheet.id,
                commit=False,
            )
            db.session.commit()
            flash("Fuel / odometer record saved with receipt photo.", "success")
            return redirect(url_for("driver.view_ifta_worksheet", worksheet_id=worksheet.id))

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
        flash("Damage report saved. You can edit or archive it until the route is finalized or you submit it.", "success")
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
    classification = classify_damage_report(report)
    pretrip_evidence_target = _pretrip_from_damage_report(report)
    return render_template(
        "view_damage_report.html",
        report=report,
        can_modify=_can_modify_damage_report(report),
        route_finalized=_is_damage_report_route_finalized(report),
        accident_form_available=classification.packet_type == PacketClassification.ACCIDENT_INCIDENT.value,
        ifta_form_available=classification.packet_type == PacketClassification.FUEL_ODO_IFTA.value,
        pretrip_evidence_target=pretrip_evidence_target,
    )


@bp.route("/damage_reports/<int:report_id>/evidence_packet")
@login_required
def damage_evidence_packet(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    classification = classify_damage_report(report)
    if classification.packet_type == PacketClassification.FUEL_ODO_IFTA.value:
        flash("Use the IFTA Support Worksheet for fuel and odometer records.", "info")
        return redirect(url_for("driver.new_ifta_worksheet"))
    packet_label = packet_label_for_report(report)
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="evidence_packet_generated",
        title=f"{packet_label} generated",
        details=f"Generated {packet_label} #{report.id}.",
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


def _driver_can_view_accident(report):
    if current_user.role == "management":
        return True
    return report.driver_id == current_user.id or report.created_by_id == current_user.id


def _driver_can_view_ifta(worksheet):
    if current_user.role == "management":
        return True
    return worksheet.driver_id == current_user.id or worksheet.created_by_id == current_user.id


@bp.route("/packet-media/<int:media_id>")
@login_required
def packet_media(media_id):
    media = ProofMediaFile.query.get_or_404(media_id)
    if media.owner_type == "accident_incident_report":
        report = AccidentIncidentReport.query.get_or_404(media.owner_id)
        if not _driver_can_view_accident(report):
            abort(403)
    elif media.owner_type == "pretrip":
        pretrip = _active_pretrips_query().filter_by(id=media.owner_id).first_or_404()
        if current_user.role != "management" and pretrip.user_id != current_user.id:
            abort(403)
    path = accident_media_path(media)
    if not path:
        abort(404)
    return send_from_directory(os.path.dirname(path), os.path.basename(path))


@bp.route("/accident-incident/new", methods=["GET", "POST"])
@login_required
def new_accident_incident():
    damage_report = None
    driver_log = None
    damage_report_id = request.values.get("damage_report_id", type=int)
    driver_log_id = request.values.get("driver_log_id", type=int)
    if damage_report_id:
        damage_report = _damage_report_or_404(damage_report_id)
        if damage_report is None:
            return redirect(url_for("driver.damage_reports"))
    if driver_log_id:
        driver_log = _active_driver_logs_query().filter_by(id=driver_log_id).first_or_404()
        if current_user.role != "management" and driver_log.driver_id != current_user.id:
            abort(403)
    report_context = build_report_context(
        user=current_user,
        selected_report_type="accident_incident",
        driver_log_id=getattr(driver_log, "id", None) or driver_log_id,
        stop_id=request.values.get("stop_id", type=int),
    )
    if request.method == "POST":
        if not accident_form_required(
            packet_type=request.form.get("packet_type") or "accident_incident",
            answers=request.form,
        ):
            flash("Choose Crash or Safety Incident or answer yes to a crash trigger question before opening this form.", "warning")
            return redirect(url_for("driver.new_accident_incident"))
        report = create_accident_report_from_form(
            request.form,
            request.files,
            user=current_user,
            damage_report=damage_report,
            driver_log=driver_log,
            report_context=report_context,
        )
        record_activity(
            user_id=current_user.id,
            category="accident_incident",
            action="created",
            title="Crash or Safety Incident recorded",
            details=f"Crash or Safety Incident #{report.id} saved for manager review.",
            target_type="accident_incident_report",
            target_id=report.id,
            commit=False,
        )
        db.session.commit()
        flash("Crash or Safety Incident saved for Manager Review.", "success")
        return redirect(url_for("driver.view_accident_incident", report_id=report.id))
    return render_template(
        "accident_incident_form.html",
        report=None,
        damage_report=damage_report,
        driver_log=driver_log,
        report_context=report_context,
        manager_view=False,
    )


@bp.route("/damage_reports/<int:report_id>/accident-incident")
@login_required
def accident_incident_from_damage_report(report_id):
    return redirect(
        url_for(
            "driver.new_accident_incident",
            damage_report_id=report_id,
            packet_type="accident_incident",
        )
    )


@bp.route("/driver_logs/<int:log_id>/accident-incident")
@login_required
def accident_incident_from_driver_log(log_id):
    return redirect(
        url_for(
            "driver.new_accident_incident",
            driver_log_id=log_id,
            packet_type="accident_incident",
        )
    )


@bp.route("/accident-incident/<int:report_id>")
@login_required
def view_accident_incident(report_id):
    report = AccidentIncidentReport.query.get_or_404(report_id)
    if not _driver_can_view_accident(report):
        abort(403)
    return render_template("accident_incident_view.html", report=report, manager_view=False)


@bp.route("/accident-incident/<int:report_id>/packet")
@login_required
def accident_incident_packet(report_id):
    report = AccidentIncidentReport.query.get_or_404(report_id)
    if not _driver_can_view_accident(report):
        abort(403)
    packet = build_accident_packet(report, generated_by=current_user)
    return render_template(
        "accident_incident_packet.html",
        packet=packet,
        manager_view=False,
        back_url=url_for("driver.view_accident_incident", report_id=report.id),
    )


@bp.route("/ifta-worksheet/new", methods=["GET", "POST"])
@login_required
def new_ifta_worksheet():
    report_context = build_report_context(
        user=current_user,
        selected_report_type="fuel_odo_ifta",
        driver_log_id=request.values.get("driver_log_id", type=int),
        stop_id=request.values.get("stop_id", type=int),
    )
    recent_fuel_records = (
        IftaFuelRecord.query.join(IftaWorksheet, IftaFuelRecord.worksheet_id == IftaWorksheet.id)
        .filter(
            or_(
                IftaWorksheet.driver_id == current_user.id,
                IftaWorksheet.created_by_id == current_user.id,
            )
        )
        .order_by(IftaFuelRecord.purchase_date.desc(), IftaFuelRecord.id.desc())
        .limit(6)
        .all()
    )
    recent_fuel_rows = [
        {"record": record, "receipt_available": ifta_receipt_available(record)}
        for record in recent_fuel_records
    ]
    if request.method == "POST":
        worksheet = create_ifta_worksheet_from_form(
            request.form,
            request.files,
            user=current_user,
            report_context=report_context,
        )
        record_activity(
            user_id=current_user.id,
            category="ifta",
            action="created",
            title="Fuel Record created",
            details=f"IFTA Support Worksheet #{worksheet.id} saved.",
            target_type="ifta_worksheet",
            target_id=worksheet.id,
            commit=False,
        )
        db.session.commit()
        flash("Fuel Record saved.", "success")
        return redirect(url_for("driver.view_ifta_worksheet", worksheet_id=worksheet.id))
    return render_template(
        "ifta_worksheet_form.html",
        worksheet=None,
        manager_view=False,
        report_context=report_context,
        recent_fuel_rows=recent_fuel_rows,
    )


@bp.route("/ifta-worksheet/<int:worksheet_id>")
@login_required
def view_ifta_worksheet(worksheet_id):
    worksheet = IftaWorksheet.query.get_or_404(worksheet_id)
    if not _driver_can_view_ifta(worksheet):
        abort(403)
    packet = build_ifta_packet(worksheet, generated_by=current_user)
    return render_template("ifta_worksheet_view.html", worksheet=worksheet, packet=packet, manager_view=False)


@bp.route("/ifta-worksheet/<int:worksheet_id>/packet")
@login_required
def ifta_worksheet_packet(worksheet_id):
    worksheet = IftaWorksheet.query.get_or_404(worksheet_id)
    if not _driver_can_view_ifta(worksheet):
        abort(403)
    packet = build_ifta_packet(worksheet, generated_by=current_user)
    return render_template(
        "ifta_worksheet_packet.html",
        packet=packet,
        manager_view=False,
        receipt_endpoint="driver.ifta_receipt",
        back_url=url_for("driver.view_ifta_worksheet", worksheet_id=worksheet.id),
    )


@bp.route("/ifta-worksheet/receipt/<int:fuel_id>")
@login_required
def ifta_receipt(fuel_id):
    fuel = IftaFuelRecord.query.get_or_404(fuel_id)
    if not _driver_can_view_ifta(fuel.worksheet):
        abort(403)
    path = ifta_receipt_path(fuel.receipt_photo)
    if path:
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    if fuel.receipt_data:
        mimetype = (
            fuel.receipt_mimetype
            or mimetypes.guess_type(fuel.receipt_photo or "")[0]
            or "application/octet-stream"
        )
        return send_file(
            io.BytesIO(fuel.receipt_data),
            mimetype=mimetype,
            download_name=fuel.receipt_photo or f"fuel-receipt-{fuel.id}",
        )
    abort(404)


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


@bp.route("/damage_reports/<int:report_id>/move-to-pretrip-evidence", methods=["POST"])
@login_required
def move_damage_report_to_pretrip_evidence(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    if not _can_modify_damage_report(report):
        flash("This damage report is locked because it was submitted or the route was finalized.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    pretrip = _pretrip_from_damage_report(report)
    if not pretrip:
        flash("This damage report is not linked to a PreTrip inspection.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    before = model_snapshot(report, DAMAGE_REPORT_AUDIT_FIELDS)
    before["photos"] = [photo.filename for photo in report.photos]
    moved_media = _copy_damage_photos_to_pretrip_evidence(report, pretrip)
    if not moved_media:
        flash("No available photo file could be moved into the PreTrip evidence record.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    report.status = "closed"
    report.resolved_at = datetime.utcnow()
    after = model_snapshot(report, ["status", "resolved_at"])
    after["pretrip_id"] = pretrip.id
    after["pretrip_evidence_ids"] = [media.id for media in moved_media]
    record_audit_event(
        user_id=current_user.id,
        target_type="damage_report",
        target_id=report.id,
        action="reclassified_to_pretrip_evidence",
        reason=f"Driver moved mistaken PreTrip damage report into PreTrip #{pretrip.id} inspection evidence.",
        before_values=before,
        after_values=after,
        commit=False,
    )
    record_activity(
        user_id=current_user.id,
        category="pretrip",
        action="evidence_uploaded",
        title="PreTrip evidence moved from damage report",
        details=f"Moved {len(moved_media)} photo(s) from damage report #{report.id} to PreTrip #{pretrip.id}.",
        target_type="pretrip",
        target_id=pretrip.id,
        commit=False,
    )
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="archived",
        title="Damage report moved to PreTrip evidence",
        details=f"Damage report #{report.id} archived after its photo was moved to PreTrip #{pretrip.id}.",
        target_type="damage_report",
        target_id=report.id,
        commit=False,
    )
    db.session.commit()
    flash("Moved the photo to PreTrip inspection evidence and archived the mistaken damage report.", "success")
    return redirect(url_for("driver.view_pretrip", pretrip_id=pretrip.id))


@bp.route("/damage_reports/<int:report_id>/delete", methods=["POST"])
@login_required
def delete_damage_report(report_id):
    report = _damage_report_or_404(report_id)
    if report is None:
        return redirect(url_for("driver.damage_reports"))
    if not _can_modify_damage_report(report):
        flash("This damage report is locked because it was submitted or the route was finalized.", "warning")
        return redirect(url_for("driver.view_damage_report", report_id=report.id))

    before = model_snapshot(report, DAMAGE_REPORT_AUDIT_FIELDS)
    before["photos"] = [photo.filename for photo in report.photos]
    report.status = "closed"
    report.resolved_at = datetime.utcnow()
    after = model_snapshot(report, ["status", "resolved_at"])
    after["photos_preserved"] = [photo.filename for photo in report.photos]
    record_audit_event(
        user_id=current_user.id,
        target_type="damage_report",
        target_id=report.id,
        action="driver_archived",
        reason="Driver archived open damage report before route finalization.",
        before_values=before,
        after_values=after,
        commit=False,
    )
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="archived",
        title="Damage report archived",
        details=f"Damage report #{report.id} archived for {report.plant_name}; evidence remains attached.",
        target_type="damage_report",
        target_id=report.id,
        commit=False,
    )
    db.session.commit()
    flash("Damage report archived.", "success")
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

    selected_truck, inspection_trucks = _driver_selected_inspection_truck(
        current_user.id,
        request.args.get("truck_number"),
    )
    truck_number = selected_truck["truck_number"] if selected_truck else ""
    latest_pretrip = selected_truck["latest_pretrip"] if selected_truck else None
    current_pretrip_id = None
    if latest_pretrip and _same_truck_number(latest_pretrip.truck_number, truck_number) and not latest_pretrip.posttrip:
        current_pretrip_id = latest_pretrip.id

    return render_template(
        "truck_maintenance_history.html",
        truck_number=truck_number,
        inspection_trucks=inspection_trucks,
        history=_truck_maintenance_history(
            truck_number,
            current_pretrip_id=current_pretrip_id,
            limit=25,
        ),
        todays_pretrip=latest_pretrip if latest_pretrip and latest_pretrip.pretrip_date == _today_local_date() else None,
    )


@bp.route("/mobile/history/<report_date>")
@login_required
def mobile_day_report(report_date):
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    parsed_date = _parse_report_date(report_date)
    if parsed_date is None:
        return redirect(url_for("driver.mobile_history"))

    today_local_date = _today_local_date()
    if parsed_date == today_local_date:
        _repair_today_pretrip_dates(current_user.id, today_local_date)

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
    return render_template(
        "mobile_day_report.html",
        report_date=parsed_date,
        today_local_date=today_local_date,
        logs=logs,
        log_reports=log_reports,
        log_routes=log_routes,
        route_task_events=route_task_events,
        route_finalized=_driver_route_record_finalized(current_user.id, parsed_date),
        pretrips=pretrips,
        transfers=transfers,
        transfer_reports=transfer_reports,
    )


def _mobile_route_map_fragment_context(route_date=None):
    now_local, _ = _now_local_and_utc()
    today_local_date = now_local.date()
    _repair_today_pretrip_dates(current_user.id, today_local_date)
    open_shift = _open_shift_for_driver(current_user.id)
    route_date = route_date or _requested_mobile_route_date() or _dashboard_route_date_for_driver(
        current_user.id,
        today_local_date,
        open_shift=open_shift,
    )
    if route_date == today_local_date:
        _repair_today_driver_log_dates(current_user.id, today_local_date)
        _repair_today_pretrip_dates(current_user.id, today_local_date)

    tasks = _driver_task_queue(current_user.id)
    active_task = tasks[0] if tasks else None
    task_queue = [task for task in tasks if not active_task or task.id != active_task.id]
    latest_pretrip = (
        _active_pretrips_query().filter_by(user_id=current_user.id)
        .order_by(PreTrip.created_at.desc())
        .first()
    )
    today_pretrips = _route_pretrips_for_driver_date(current_user.id, today_local_date)
    route_pretrips = _route_pretrips_for_driver_date(current_user.id, route_date)
    open_shift_route_date = _shift_route_date(open_shift)
    route_context = build_route_context(driver_id=current_user.id, route_date=route_date, now=now_local)
    todays_pretrip = _select_route_pretrip(
        today_pretrips,
        route_context=route_context if route_date == today_local_date else None,
        open_shift=open_shift,
    )
    route_pretrip = _select_route_pretrip(
        route_pretrips,
        route_context=route_context,
        open_shift=open_shift,
    )
    route_is_active = bool(
        (open_shift and (not open_shift_route_date or open_shift_route_date == route_date))
        or route_context.route_status == "active"
    )
    active_pretrip = todays_pretrip or (route_pretrip if route_is_active else None)
    pending_posttrip = False
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
    current_stop = route_context.current_stop
    pending_posttrip = _posttrip_due_for_route(
        active_pretrip,
        route_context,
        route_is_active=route_is_active,
    )
    departed_today = any(getattr(log, "depart_time", None) for log in todays_logs)
    has_transfer_today = bool(
        _active_plant_transfers_query()
        .filter_by(user_id=current_user.id, transfer_date=route_date)
        .first()
    )
    proof_missing = bool(departed_today and not has_transfer_today)
    route_map = build_driver_route_map_context(
        driver=current_user,
        date=route_date,
        selected_stop_id=current_stop.id if current_stop else None,
        route_pretrip=route_pretrip,
        proof_missing=proof_missing,
        pending_posttrip=pending_posttrip,
    )
    route_cta = build_route_cta_context(
        route_context,
        proof_missing=proof_missing,
        has_active_shift=bool(open_shift),
        route_is_active=route_is_active,
        route_date=route_date,
        today_local_date=today_local_date,
        has_last_route=bool(todays_logs),
        selected_date_forced=bool(request.args.get("date")),
        pending_posttrip=pending_posttrip,
    )
    route_cta = _apply_route_end_cta(route_cta, route_context, active_pretrip, route_date, today_local_date)
    route_map_mode = build_driver_map_mode_context(
        route_context,
        route_map,
        route_date=route_date,
        today_local_date=today_local_date,
        route_is_active=route_is_active,
    )
    route_map.update(route_map_mode)
    route_cta_urls = _route_cta_urls(
        route_date,
        current_stop=current_stop,
        active_pretrip=active_pretrip,
        pending_posttrip=pending_posttrip,
        route_context=route_context,
    )

    truck_source_pretrip = active_pretrip or route_pretrip or latest_pretrip
    current_truck_number = _normalize_truck_number(
        truck_source_pretrip.truck_number if truck_source_pretrip else ""
    )
    if current_truck_number:
        recent_ryder_events = [
            event
            for event in recent_ryder_events
            if _same_truck_number(_detail_value(event.details, "Truck"), current_truck_number)
        ][:3]
    truck_maintenance_history = _truck_maintenance_history(
        current_truck_number,
        current_pretrip_id=active_pretrip.id if active_pretrip else None,
        limit=6,
    )
    ryder_context = _ryder_followup_context(current_user.id)

    return {
        "route_map": route_map,
        "route_map_mode": route_map_mode,
        "route_cta": route_cta,
        "route_cta_urls": route_cta_urls,
        "active_task": active_task,
        "task_queue": task_queue,
        "latest_pretrip": latest_pretrip,
        "todays_pretrip": todays_pretrip,
        "route_pretrip": route_pretrip,
        "active_pretrip": active_pretrip,
        "pending_posttrip": pending_posttrip,
        "latest_transfer": latest_transfer,
        "open_shift": open_shift,
        "today_local_date": today_local_date,
        "route_date": route_date,
        "route_is_active": route_is_active,
        "todays_logs": todays_logs,
        "current_stop": current_stop,
        "current_truck_number": current_truck_number,
        "truck_maintenance_history": truck_maintenance_history,
        "truck_issue_choices": TRUCK_ISSUE_CHOICES,
        "recent_ryder_events": recent_ryder_events,
        "depart_form": DepartForm(),
        "freight_memory": (
            _freight_stop_memory(current_user.id)
            if getattr(current_user, "is_day_driver", False)
            else None
        ),
        **ryder_context,
    }


@bp.route("/mobile")
@login_required
def mobile_dashboard():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))

    now_local, _ = _now_local_and_utc()
    today_local_date = now_local.date()
    _repair_today_pretrip_dates(current_user.id, today_local_date)
    open_shift = _open_shift_for_driver(current_user.id)
    requested_route_date = _requested_mobile_route_date()
    route_date = requested_route_date or _dashboard_route_date_for_driver(current_user.id, today_local_date, open_shift=open_shift)
    if route_date == today_local_date:
        _repair_today_driver_log_dates(current_user.id, today_local_date)
        _repair_today_pretrip_dates(current_user.id, today_local_date)
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
    today_pretrips = _route_pretrips_for_driver_date(current_user.id, today_local_date)
    route_pretrips = _route_pretrips_for_driver_date(current_user.id, route_date)
    open_shift_route_date = _shift_route_date(open_shift)
    route_context = build_route_context(driver_id=current_user.id, route_date=route_date, now=now_local)
    todays_pretrip = _select_route_pretrip(
        today_pretrips,
        route_context=route_context if route_date == today_local_date else None,
        open_shift=open_shift,
    )
    route_pretrip = _select_route_pretrip(
        route_pretrips,
        route_context=route_context,
        open_shift=open_shift,
    )
    route_is_active = bool(
        (open_shift and (not open_shift_route_date or open_shift_route_date == route_date))
        or route_context.route_status == "active"
    )
    active_pretrip = todays_pretrip or (route_pretrip if route_is_active else None)
    pending_posttrip = False
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
    route_transfers = (
        _active_plant_transfers_query().filter_by(user_id=current_user.id, transfer_date=route_date)
        .order_by(PlantTransfer.created_at.desc(), PlantTransfer.id.desc())
        .all()
    )
    route_damage_reports = _today_damage_reports(current_user.id, route_date)
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
    if route_is_active and route_date != today_local_date:
        route_panel_title = "Active Route"
    elif route_is_active:
        route_panel_title = "Today's Route"
    elif route_context.route_status == "completed" and route_date == today_local_date:
        route_panel_title = "Route Complete"
    elif route_context.route_status == "finalized" and route_date == today_local_date:
        route_panel_title = "Route Finalized"
    elif route_date == today_local_date:
        route_panel_title = "Today's Route"
    else:
        route_panel_title = "Last Route"
    truck_source_pretrip = active_pretrip or route_pretrip or latest_pretrip
    current_truck_number = _normalize_truck_number(
        truck_source_pretrip.truck_number if truck_source_pretrip else ""
    )
    if current_truck_number:
        recent_ryder_events = [
            event
            for event in recent_ryder_events
            if _same_truck_number(_detail_value(event.details, "Truck"), current_truck_number)
        ][:3]
    truck_maintenance_history = _truck_maintenance_history(
        current_truck_number,
        current_pretrip_id=active_pretrip.id if active_pretrip else None,
        limit=6,
    )
    ryder_context = _ryder_followup_context(current_user.id)

    open_damage_count = DamageReport.query.filter(
        DamageReport.status != "closed",
        DamageReport.reported_by_id == current_user.id,
        func.date(DamageReport.created_at) == today_local_date,
    ).count()
    departed_today = any(getattr(log, "depart_time", None) for log in todays_logs)
    has_transfer_today = bool(
        _active_plant_transfers_query()
        .filter_by(user_id=current_user.id, transfer_date=route_date)
        .first()
    )
    proof_missing = bool(departed_today and not has_transfer_today)
    pending_posttrip = _posttrip_due_for_route(
        active_pretrip,
        route_context,
        route_is_active=route_is_active,
    )
    route_map = build_driver_route_map_context(
        driver=current_user,
        date=route_date,
        selected_stop_id=current_stop.id if current_stop else None,
        route_pretrip=route_pretrip,
        proof_missing=proof_missing,
        pending_posttrip=pending_posttrip,
    )
    route_cta = build_route_cta_context(
        route_context,
        proof_missing=proof_missing,
        has_active_shift=bool(open_shift),
        route_is_active=route_is_active,
        route_date=route_date,
        today_local_date=today_local_date,
        has_last_route=bool(todays_logs),
        selected_date_forced=bool(requested_route_date),
        pending_posttrip=pending_posttrip,
    )
    route_cta = _apply_route_end_cta(route_cta, route_context, active_pretrip, route_date, today_local_date)
    driver_next_action = route_cta["next_action"]
    route_map_mode = build_driver_map_mode_context(
        route_context,
        route_map,
        route_date=route_date,
        today_local_date=today_local_date,
        route_is_active=route_is_active,
    )
    route_map.update(route_map_mode)
    route_date_options = _mobile_route_date_options(current_user.id, route_date, today_local_date)
    route_cta_urls = _route_cta_urls(
        route_date,
        current_stop=current_stop,
        active_pretrip=active_pretrip,
        pending_posttrip=pending_posttrip,
        route_context=route_context,
    )

    return render_template(
        "driver_mobile.html",
        route_map=route_map,
        route_map_mode=route_map_mode,
        route_cta=route_cta,
        route_cta_urls=route_cta_urls,
        route_date_options=route_date_options,
        driver_next_action=driver_next_action,
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
        route_transfers=route_transfers,
        route_damage_reports=route_damage_reports,
        current_truck_number=current_truck_number,
        truck_maintenance_history=truck_maintenance_history,
        truck_issue_choices=TRUCK_ISSUE_CHOICES,
        depart_form=DepartForm(),
        freight_memory=(
            _freight_stop_memory(current_user.id)
            if getattr(current_user, "is_day_driver", False)
            else None
        ),
        **ryder_context,
    )


@bp.route("/mobile/route-map-fragment")
@login_required
def mobile_route_map_fragment():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return render_template(
        "partials/_compact_route_map.html",
        **_mobile_route_map_fragment_context(),
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
        flash("Choose what is wrong with the truck and the service status.", "warning")
        return redirect(url_for("driver.new_driving_log" if next_target == "new_log" else "driver.mobile_dashboard"))

    details = f"Truck: {truck_number}; Issue: {issue}; Outcome: {RYDER_OUTCOME_LABELS[outcome]}"
    if pending_ryder_event and outcome in RYDER_CLOSING_ACTIONS:
        details = f"{details}; Service time: {_format_duration((datetime.utcnow() - pending_ryder_event.created_at).total_seconds())}"
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
    flash("Service note saved.", "success")
    return redirect(url_for("driver.new_driving_log" if next_target == "new_log" else "driver.mobile_dashboard"))


def _route_breaks_for_driver_date(driver_id, route_date):
    if not driver_id or not route_date:
        return []
    return (
        RouteBreak.query.filter_by(user_id=driver_id, break_date=route_date)
        .order_by(RouteBreak.start_time.asc(), RouteBreak.id.asc())
        .all()
    )


def _break_redirect_target():
    return url_for("driver.mobile_breaks") if request.form.get("next") == "breaks" else url_for("driver.mobile_dashboard")


def _break_elapsed_seconds(brk, *, now_utc=None):
    if not brk or not getattr(brk, "start_time", None):
        return 0
    now_utc = now_utc or datetime.utcnow()
    start_time = brk.start_time
    end_time = getattr(brk, "end_time", None) or now_utc
    if start_time.tzinfo is not None:
        start_time = start_time.astimezone(pytz.utc).replace(tzinfo=None)
    if end_time.tzinfo is not None:
        end_time = end_time.astimezone(pytz.utc).replace(tzinfo=None)
    return max(0, int((end_time - start_time).total_seconds()))


def _break_detail_rows(breaks, *, now_utc=None):
    now_utc = now_utc or datetime.utcnow()
    rows = []
    total_seconds = 0
    for brk in breaks or []:
        elapsed_seconds = _break_elapsed_seconds(brk, now_utc=now_utc)
        total_seconds += elapsed_seconds
        rows.append(
            {
                "break": brk,
                "kind": (getattr(brk, "break_type", None) or "Break").strip(),
                "elapsed_seconds": elapsed_seconds,
                "elapsed_label": _format_duration(elapsed_seconds),
                "duration_label": hos_service.format_minutes(elapsed_seconds // 60) or "Under 1 min",
                "is_open": not bool(getattr(brk, "end_time", None)),
            }
        )
    return rows, total_seconds


def _open_route_break(driver_id):
    if not driver_id:
        return None
    return (
        RouteBreak.query.filter_by(user_id=driver_id, end_time=None)
        .order_by(RouteBreak.start_time.desc(), RouteBreak.id.desc())
        .first()
    )


@bp.context_processor
def _inject_open_break():
    """Expose the driver's open break to every driver template so the bottom-nav
    Break action shows start/end state consistently across pages."""
    try:
        if current_user.is_authenticated and getattr(current_user, "role", None) != "management":
            open_break = _open_route_break(current_user.id)
            if open_break and not _open_shift_for_driver(current_user.id):
                # Self-heal stale data: a break can't outlive its shift. Stamp it
                # closed at shift end (zero-length if tapped after release).
                last_ended = (
                    ShiftRecord.query.filter(
                        ShiftRecord.user_id == current_user.id,
                        ShiftRecord.end_time.isnot(None),
                    )
                    .order_by(ShiftRecord.end_time.desc())
                    .first()
                )
                stamp = last_ended.end_time if last_ended else open_break.start_time
                open_break.end_time = max(open_break.start_time or stamp, stamp or datetime.utcnow())
                db.session.commit()
                open_break = None
            elapsed_seconds = 0
            if open_break and getattr(open_break, "start_time", None):
                start_time = open_break.start_time
                if start_time.tzinfo is not None:
                    start_time = start_time.astimezone(pytz.utc).replace(tzinfo=None)
                elapsed_seconds = max(0, int((datetime.utcnow() - start_time).total_seconds()))
            duty_card = None
            if getattr(current_user, "is_day_driver", False):
                duty_card = duty_log_service.current_status(current_user.id)
            return {
                "open_break": open_break,
                "open_break_elapsed_seconds": elapsed_seconds,
                "open_break_elapsed_label": _format_duration(elapsed_seconds),
                "duty_card": duty_card,
            }
    except Exception:  # pragma: no cover - never block a render on this
        pass
    return {"open_break": None, "open_break_elapsed_seconds": 0, "open_break_elapsed_label": "00:00", "duty_card": None}


@bp.route("/mobile/toggle-day-driver", methods=["POST"])
@login_required
def toggle_day_driver():
    """One-tap switch between the standard plant/part workspace and the
    day-driver freight workspace (commodity + weight) from the dashboard, so the
    mode is testable without digging into Profile."""
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    current_user.day_driver = not bool(current_user.day_driver)
    if current_user.day_driver and not (current_user.route_type or "").strip():
        current_user.route_type = "local_short_haul"
    db.session.commit()
    if current_user.day_driver:
        flash("Day-Driver freight workspace ON — logging by commodity & weight.", "success")
    else:
        flash("Day-Driver workspace OFF — standard plant/part logging.", "info")
    return redirect(url_for("driver.mobile_dashboard"))


@bp.route("/mobile/breaks")
@login_required
def mobile_breaks():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    now_local, _ = _now_local_and_utc()
    open_shift = _open_shift_for_driver(current_user.id)
    route_date = _active_route_date_for_driver(current_user.id, now_local.date(), open_shift=open_shift)
    breaks = _route_breaks_for_driver_date(current_user.id, route_date)
    open_break = _open_route_break(current_user.id)
    rows, total_seconds = _break_detail_rows(breaks)
    return render_template(
        "mobile_breaks.html",
        break_rows=rows,
        break_total_label=hos_service.format_minutes(total_seconds // 60) or "0 min",
        break_total_clock=_format_duration(total_seconds),
        break_types=hos_service.BREAK_TYPES,
        open_break=open_break,
        route_date=route_date,
    )


@bp.route("/mobile/break/start", methods=["POST"])
@login_required
def mobile_break_start():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    existing = _open_route_break(current_user.id)
    if existing:
        flash("A break is already in progress.", "info")
        return redirect(_break_redirect_target())
    if not _open_shift_for_driver(current_user.id):
        flash("You're off shift — breaks are tracked while a shift is open.", "info")
        return redirect(_break_redirect_target())
    break_type = (request.form.get("break_type") or "").strip() or "Break"
    if break_type not in {*hos_service.BREAK_TYPES, "Break"}:
        break_type = "Break"
    now_local, _ = _now_local_and_utc()
    db.session.add(RouteBreak(
        user_id=current_user.id,
        break_date=now_local.date(),
        break_type=break_type,
        start_time=datetime.utcnow(),
    ))
    db.session.commit()
    flash(f"{break_type} break started.", "success")
    return redirect(_break_redirect_target())


@bp.route("/mobile/break/end", methods=["POST"])
@login_required
def mobile_break_end():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    open_break = _open_route_break(current_user.id)
    if not open_break:
        flash("No break is in progress.", "info")
        return redirect(_break_redirect_target())
    open_break.end_time = datetime.utcnow()
    db.session.commit()
    flash("Break ended.", "success")
    return redirect(_break_redirect_target())


@bp.route("/mobile/hours-mode", methods=["POST"])
@login_required
def mobile_hours_mode():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    mode = hos_service.normalize_mode((request.form.get("hos_mode") or "").strip())
    shift = _open_shift_for_driver(current_user.id)
    if shift:
        shift.hos_mode = mode
        db.session.commit()
        flash("Hours Check mode updated.", "success")
    else:
        flash("Start a shift (pretrip) before changing the Hours Check mode.", "info")
    return redirect(url_for("driver.mobile_dashboard"))


@bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    return redirect(url_for("driver.mobile_dashboard"))


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
        current_user.day_driver = bool(form.day_driver.data)
        current_user.route_type = (form.route_type.data or "").strip() or None
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
        flash("Driver access required.", "warning")
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
    return redirect(url_for("driver.mobile_dashboard"))


# --- Driver's Daily Log (day-driver / solo freight workspace) ---------------
# The classic OFF/SB/D/ON record-of-duty-status grid, generated from captured
# events and exportable like the other branded print documents. Gated to
# day-driver mode so the fleet flow is untouched. Not a certified ELD.


def _daily_log_guard():
    if current_user.role == "management":
        flash("The Daily Log is a driver workspace.", "warning")
        return redirect(url_for("manager.manager_dashboard"))
    if not current_user.is_day_driver:
        flash("Turn on Day Driver mode to use the Daily Log.", "info")
        return redirect(url_for("driver.mobile_dashboard"))
    return None


def _daily_log_document_meta(day, driver, page="1 of 1"):
    return document_meta(
        "DRIVER'S DAILY LOG", f"DDL-{day.strftime('%Y%m%d')}-D{driver.id}", page=page
    )


def _daily_log_view_model(day, *, theme="paper"):
    now_local = datetime.now(pytz.timezone("America/Detroit"))
    segments, events = duty_log_service.day_segments(current_user.id, day, now_local=now_local)
    totals = duty_log_service.totals_minutes(segments)
    recap = duty_log_service.recap(current_user.id, day, now_local=now_local)
    pretrips = _active_pretrips_query().filter_by(user_id=current_user.id, pretrip_date=day).all()
    truck = _truck_from_pretrips(pretrips)
    odo_start = next((p.start_mileage for p in pretrips if p.start_mileage), None)
    odo_end = None
    miles = None
    for pretrip in pretrips:
        posttrip = PostTrip.query.filter_by(pretrip_id=pretrip.id).order_by(PostTrip.id.desc()).first()
        if posttrip:
            odo_end = posttrip.end_mileage or odo_end
            miles = posttrip.miles_driven or miles
    if miles is None and odo_start and odo_end and odo_end > odo_start:
        miles = odo_end - odo_start
    day_complete = duty_log_service.day_complete(current_user.id, day, now_local=now_local)
    hos_check = hos_service.hos_companion_check(
        shift_start=None,
        on_duty_minutes=totals.get("on", 0) + totals.get("d", 0),
        drive_minutes=totals.get("d", 0),
        now=now_local,
        prior_7day_minutes=max(0, recap["total_8day"] - recap["worked_today"]),
    )
    return {
        "day": day,
        "segments": segments,
        "events": events,
        "totals": totals,
        "totals_fmt": {k: duty_log_service.fmt_hm(v) for k, v in totals.items()},
        "recap": recap,
        "day_complete": day_complete,
        "hos_check": hos_check,
        "as_of_label": now_local.strftime("%I:%M %p").lstrip("0").lower(),
        "grid_svg": duty_log_service.grid_svg(segments, day=day, now_local=now_local, theme=theme),
        "truck": truck,
        "odo_start": odo_start,
        "odo_end": odo_end,
        "miles": miles,
        "manual_count": sum(1 for e in events if e["source"] == "manual"),
        "status_labels": duty_log_service.STATUS_LABELS,
        "status_short": duty_log_service.STATUS_SHORT,
        "not_an_eld": duty_log_service.NOT_AN_ELD,
        "fmt_hm": duty_log_service.fmt_hm,
        "is_today": day == _today_local_date(),
    }


@bp.route("/daily_log")
@login_required
def daily_log():
    guard = _daily_log_guard()
    if guard:
        return guard
    day = _selected_log_date_from_request()
    view = _daily_log_view_model(day, theme="dark")
    today = _today_local_date()
    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1) if day < today else None
    return render_template(
        "daily_log.html",
        view=view,
        the_date=day,
        prev_url=url_for("driver.daily_log", date=prev_day.isoformat()),
        next_url=url_for("driver.daily_log", date=next_day.isoformat()) if next_day else None,
        today_url=url_for("driver.daily_log"),
        duty_now=duty_log_service.current_status(current_user.id),
    )


@bp.route("/duty/status", methods=["GET", "POST"])
@login_required
def duty_status():
    guard = _daily_log_guard()
    if guard:
        return guard
    if request.method == "POST":
        status = (request.form.get("status") or "").strip().lower()
        if status not in DutyStatusEvent.STATUSES:
            flash("Pick a duty status.", "warning")
            return redirect(url_for("driver.duty_status"))
        location = (request.form.get("location") or "").strip()[:160] or None
        note = (request.form.get("note") or "").strip()[:200] or None
        db.session.add(
            DutyStatusEvent(
                user_id=current_user.id,
                status=status,
                at=datetime.utcnow(),
                location=location,
                note=note,
            )
        )
        db.session.commit()
        label = duty_log_service.STATUS_LABELS.get(status, status)
        record_activity(
            user_id=current_user.id,
            category="hos",
            action="duty_status_set",
            title=f"Duty status: {label}",
            details=location or "",
            target_type="duty_status_event",
        )
        flash(f"Duty status set to {label}.", "success")
        if request.form.get("next") == "mobile":
            return redirect(url_for("driver.mobile_dashboard"))
        return redirect(url_for("driver.daily_log"))
    last_located = (
        DutyStatusEvent.query.filter(
            DutyStatusEvent.user_id == current_user.id, DutyStatusEvent.location.isnot(None)
        )
        .order_by(DutyStatusEvent.at.desc())
        .first()
    )
    return render_template(
        "duty_status_form.html",
        duty_now=duty_log_service.current_status(current_user.id),
        status_labels=duty_log_service.STATUS_LABELS,
        status_short=duty_log_service.STATUS_SHORT,
        last_location=last_located.location if last_located else "",
        not_an_eld=duty_log_service.NOT_AN_ELD,
    )


@bp.route("/daily_log/print")
@login_required
def daily_log_print():
    guard = _daily_log_guard()
    if guard:
        return guard
    day = _selected_log_date_from_request()
    view = _daily_log_view_model(day)
    shift_record = _shift_record_for_driver_date(current_user.id, day, require_signature=True)
    record_activity(
        user_id=current_user.id,
        category="print",
        action="daily_log_printed",
        title="Daily log printed",
        details=f"Record of duty status for {day}.",
        target_type="duty_status_event",
    )
    return render_template(
        "daily_log_print.html",
        view=view,
        the_date=day,
        document_meta=_daily_log_document_meta(day, current_user),
        driver_signature=shift_record.driver_signature if shift_record else None,
        signature_timestamp=shift_record.signature_timestamp if shift_record else None,
        attachment_url=url_for("driver.daily_log_attachment", date=day.isoformat()),
    )


def _build_daily_log_pdf(day, driver, view, driver_signature=None):
    pdf = SimplePdf("Driver's Daily Log", LETTER)
    width, height = LETTER
    x = 36
    meta = _daily_log_document_meta(day, driver)

    def _page_footer():
        pdf.text(x, 30, duty_log_service.NOT_AN_ELD, size=6.6, color=(120, 128, 140))

    # Branded header — same layout family as the Driver Log Sheet.
    logo_path = os.path.join(current_app.static_folder or "", "brand", "movedefense_stripe_brand_icon_200x200.png")
    if os.path.exists(logo_path):
        pdf.fill_rect(36, 726, 26, 26, rgb=(13, 19, 32))
        pdf.image_file(logo_path, 37, 727, 24, 24)
    pdf.text(70, 742, "MoveDefense", size=12, bold=True, color=MD_PDF_INK)
    pdf.text(36, 714, "DRIVER", size=7, bold=True, color=MD_PDF_MUTED)
    pdf.text(36, 700, (driver.display_name or "").upper(), size=15, bold=True)
    pdf.text(36, 688, day.strftime("%A, %B %d, %Y"), size=8, bold=True, color=MD_PDF_MUTED)
    rx = 400
    pdf.text(rx, 742, f"Log No: {meta['document_no']}", size=8, bold=True)
    pdf.text(rx, 730, f"Generated: {meta.get('generated_at') or ''}", size=8)
    vehicle_facts = []
    if view["truck"]:
        vehicle_facts.append(f"Truck {view['truck']}")
    if view["odo_start"] and view["odo_end"]:
        vehicle_facts.append(f"Odometer {view['odo_start']:,} - {view['odo_end']:,}")
    elif view["odo_start"]:
        vehicle_facts.append(f"Odometer start {view['odo_start']:,}")
    if view["miles"]:
        vehicle_facts.append(f"{view['miles']:,} miles")
    if vehicle_facts:
        pdf.text(rx, 718, "  \xb7  ".join(vehicle_facts), size=8)
    pdf.text(rx, 706, "USA Property 70 hour / 8 day", size=8, color=MD_PDF_MUTED)
    pdf.fill_rect(36, 682, 540, 2, rgb=MD_PDF_BLUE)
    pdf.text(36, 666, "DRIVER'S DAILY LOG", size=15, bold=True, color=MD_PDF_INK)
    if not view.get("day_complete"):
        pdf.text(
            rx,
            668,
            f"LOG IN PROGRESS - through {view.get('as_of_label') or ''}",
            size=8,
            bold=True,
            color=(176, 124, 16),
        )
    y = 648

    pdf.text(x, y, "RECORD OF DUTY STATUS", size=9, bold=True, color=MD_PDF_BLUE)
    y -= 8
    y = duty_log_service.draw_grid_pdf(pdf, x, y, width - 2 * x, view["segments"], day=day)

    events = view["events"]
    if events:
        pdf.text(x, y, "DUTY EVENTS", size=9, bold=True, color=MD_PDF_BLUE)
        y -= 14
        rows = [
            [
                ev["at"].strftime("%I:%M %p").lstrip("0"),
                ev["status_short"],
                ev["label"],
                ev["location"] or "",
                ev["note"] or "",
            ]
            for ev in events
        ]
        # Every captured event prints; the table flows onto continuation pages.
        while rows:
            capacity = int((y - 70) // 18) - 1
            if capacity < 3:
                _page_footer()
                pdf.add_page()
                y = height - 50
                pdf.text(x, y, "DUTY EVENTS (CONTINUED)", size=9, bold=True, color=MD_PDF_BLUE)
                y -= 14
                capacity = int((y - 70) // 18) - 1
            chunk = rows[:capacity]
            rows = rows[capacity:]
            y = pdf.table(
                x,
                y,
                [56, 32, 110, 160, 182],
                18,
                ["Time", "Status", "Event", "Location / Stop", "Note"],
                chunk,
                font_size=7.5,
                header_rgb=MD_PDF_BLUE,
                header_color=(255, 255, 255),
            )
        y -= 16

    # Keep the recap + HOS check + certification together on one page.
    if y < 210:
        _page_footer()
        pdf.add_page()
        y = height - 50

    recap = view["recap"]
    if recap["has_data"]:
        fmt = duty_log_service.fmt_hm
        pdf.text(x, y, "RECAP - 70 HOUR / 8 DAY", size=9, bold=True, color=MD_PDF_BLUE)
        y -= 12
        recap_line = "   ".join(f"{row['date'].strftime('%m/%d')}: {row['label']}" for row in recap["rows"])
        pdf.text(x, y, recap_line, size=7.5)
        y -= 11
        pdf.text(
            x,
            y,
            f"Worked today {fmt(recap['worked_today'])}   -   8-day total {fmt(recap['total_8day'])}"
            f"   -   Hours available {fmt(recap['available'])}",
            size=8,
            bold=True,
        )
        y -= 18

    hos_items = view.get("hos_check") or []
    if hos_items:
        pdf.text(x, y, "HOS CHECK - HOURS REMAINING", size=9, bold=True, color=MD_PDF_BLUE)
        y -= 12
        pdf.text(x, y, "   -   ".join(f"{label}: {value}" for label, value in hos_items), size=8)
        y -= 18

    # Certification is only offered on a released day whose grid totals 24:00;
    # an in-progress log prints as a working copy instead.
    if view.get("day_complete") and view.get("totals", {}).get("total") == 24 * 60:
        pdf.text(
            x,
            y,
            "I hereby certify that my data entries and my record of duty status for this day are true and correct.",
            size=8,
        )
        y -= 30
        if driver_signature and not pdf.image_png_data_url(driver_signature, x, y - 4, 120, 28):
            pass
        pdf.line(x, y - 6, x + 220, y - 6, width=0.8)
        pdf.text(x, y - 16, "Driver Signature", size=7)
        pdf.text(x + 260, y - 16, "Date: ____________", size=7)
    else:
        pdf.text(
            x,
            y,
            "Log in progress - certification unlocks once the shift is released and the day totals 24:00.",
            size=8,
            color=MD_PDF_MUTED,
        )
    _page_footer()
    return pdf.build()


@bp.route("/daily_log/attachment")
@login_required
def daily_log_attachment():
    guard = _daily_log_guard()
    if guard:
        return guard
    day = _selected_log_date_from_request()
    view = _daily_log_view_model(day)
    shift_record = _shift_record_for_driver_date(current_user.id, day, require_signature=True)
    return _document_attachment_response(
        pdf_bytes=_build_daily_log_pdf(
            day,
            current_user,
            view,
            driver_signature=shift_record.driver_signature if shift_record else None,
        ),
        filename=f"daily-log-{day}.pdf",
        target_type="duty_status_event",
        title="Daily Log PDF downloaded",
    )
