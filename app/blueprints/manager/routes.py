"""Manager-facing routes.

All routes are gated by a before_request that requires the user to have the
`management` role; non-managers get redirected to the driver dashboard with a
flash message. This replaces the manager_bp.py / manager_routes.py /
db_setup.py sub-system that was unreachable at runtime (it imported from a
separate unbound SQLAlchemy instance, so any DB query inside it would have
raised "RuntimeError: working outside of application context").

Now wired against app.models.Task / app.extensions.db like everything else.
"""
from datetime import date, datetime
import csv
import io
import os
import re

from flask import current_app, flash, jsonify, make_response, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
import pytz
from sqlalchemy import or_

from app.blueprints.manager import bp
from app.services.database_status import database_status
from app.services.evidence_packet import build_damage_evidence_packet
from app.services.document_numbers import (
    document_meta,
    evidence_document_number,
    generated_at_label,
    manager_review_document_number,
    pretrip_document_number,
    transfer_document_number,
)
from app.extensions import db, socketio
from app.forms.followup import OperationalFollowUpForm
from app.forms.task import TaskForm
from app.models import ActivityEvent, AuditEvent, DamagePhoto, DamageReport, DispatchCapture, DriverLog, DriverLogPhoto, ExceptionEvent, HotPartPhoto, OperationalFollowUp, PartScanEvent, PlantTransfer, PreTrip, ShiftRecord, Task, User
from app.services.activity import record_activity
from app.services.audit import model_snapshot, record_audit_event
from app.services.dispatch_capture import create_dispatch_capture, convert_dispatch_capture, dismiss_dispatch_capture, open_dispatch_captures
from app.services.operations import build_exception_items
from app.services.floor_operations import build_floor_operations_snapshot
from app.services.production_flow import build_production_flow_context
from app.services.load_state import build_driver_log_route_context, route_problem_reason, secondary_not_dropped_reason, truck_issue_reason
from app.services.cargo_reconciliation_service import reconcile_cargo
from app.services.media_attachment_service import upload_file_path
from app.services.mileage_service import calculate_mileage_record
from app.services.next_load_prediction import build_next_load_prediction
from app.services.route_context import build_route_context
from app.services.route_state_service import build_route_state
from app.services.scan_scope_service import route_scope_id, route_stop_ids
from app.services.case_grouping import build_followup_cases, same_plant_intelligence, same_vehicle_intelligence
from app.services.hot_parts import build_route_hot_part_proof, ensure_hot_move_for_task
from app.services.management_readout import build_management_narrative
from app.services.plant_addresses import PLANT_LABELS, plant_label as _plant_label
from app.services.plant_time import forecast_for_stop, plant_forecast_rows, route_stop_forecasts
from app.services.report_summary import damage_report_count_label, damage_report_detail_label, damage_report_kind
from app.services.role_session import restore_role_user
from app.services.search_corpus import suggest_terms
from app.services.simple_pdf import LETTER, SimplePdf
from app.blueprints.driver.routes import (
    _build_plant_transfer_pdf,
    _build_pretrip_pdf,
    _pretrip_damage_reports,
    _plant_transfer_copy_sets,
    _shift_record_for_driver_date,
    _task_route_events_for_logs,
    _stop_photo_review_summary,
)


TRIM_PLANTS = ("Trim DC", "PPL", "DC")


def _first_record_id(records):
    return records[0].id if records else None


def _manager_review_document_meta(review, page="1 of 1"):
    return document_meta(
        "MANAGER ROUTE REVIEW",
        manager_review_document_number(
            review["the_date"],
            driver=review.get("driver"),
            truck=review.get("truck_label"),
            route_id=_first_record_id(review.get("logs") or []),
        ),
        page=page,
    )


def _pretrip_document_meta(pretrip, page="1 of 1"):
    return document_meta("DAILY VEHICLE INSPECTION REPORT", pretrip_document_number(pretrip), page=page)


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

PART_TOKEN_RE = re.compile(r"\b[A-Z]*\d[A-Z0-9-]{3,}\b", re.IGNORECASE)


@bp.after_request
def _no_store_manager_pages(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _populate_task_driver_choices(form):
    drivers = User.query.filter_by(role="driver").order_by(User.last_name, User.first_name, User.username).all()
    form.assigned_to.choices = [(0, "Open for any driver")] + [(driver.id, driver.manager_label) for driver in drivers]
    return drivers


def _part_suggestions():
    values = set()
    for value, in Task.query.with_entities(Task.part_number).filter(Task.part_number.isnot(None)).all():
        cleaned = (value or "").strip()
        if cleaned:
            values.add(cleaned)
    for value, in DriverLog.query.with_entities(DriverLog.part_number).filter(DriverLog.part_number.isnot(None)).all():
        cleaned = (value or "").strip()
        if cleaned:
            values.add(cleaned)
    return sorted(values)[:200]


def _active_driver_logs_query():
    return DriverLog.query.filter(DriverLog.deleted_at.is_(None))


def _active_pretrips_query():
    return PreTrip.query.filter(PreTrip.deleted_at.is_(None))


def _active_plant_transfers_query():
    return PlantTransfer.query.filter(PlantTransfer.deleted_at.is_(None))


def _latest_pretrip_for_driver(driver_id, target_date=None):
    if not driver_id:
        return None
    query = PreTrip.query.filter(
        PreTrip.user_id == driver_id,
        PreTrip.deleted_at.is_(None),
    )
    if target_date:
        query = query.filter(PreTrip.pretrip_date <= target_date)
    return query.order_by(PreTrip.pretrip_date.desc(), PreTrip.created_at.desc()).first()


def _truck_context_for_driver(driver_id, target_date=None):
    pretrip = _latest_pretrip_for_driver(driver_id, target_date)
    if not pretrip:
        return {
            "truck_id": "Truck not set",
            "truck_meta": "No same-day DVIR found",
            "pretrip_id": None,
        }
    meta = []
    if pretrip.trailer_number:
        meta.append(f"Trailer {pretrip.trailer_number}")
    if pretrip.truck_type:
        meta.append(pretrip.truck_type)
    odometer_warning = None
    if pretrip.start_mileage is not None:
        meta.append(f"Start {pretrip.start_mileage} mi")
        if pretrip.start_mileage >= 1_000_000:
            odometer_warning = (
                f"Verify odometer entry: {pretrip.start_mileage:,} mi is unusually high."
            )
    return {
        "truck_id": pretrip.truck_number or "Truck not set",
        "truck_meta": " • ".join(meta) if meta else f"DVIR #{pretrip.id}",
        "pretrip_id": pretrip.id,
        "odometer_warning": odometer_warning,
    }


def _related_task_for_log(log):
    query = Task.query.filter(Task.assigned_to == log.driver_id)
    if log.part_number:
        match = query.filter(Task.part_number == log.part_number).order_by(Task.created_at.desc()).first()
        if match:
            return match
    return query.filter(Task.status.in_(["pending", "in-progress"])).order_by(Task.created_at.desc()).first()


def _document_attachment_response(*, pdf_bytes, filename, target_type, target_id=None, title="PDF attachment downloaded"):
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    record_activity(
        user_id=current_user.id,
        category="download",
        action="manager_pdf_attachment",
        title=title,
        details=f"Prepared {filename} as a PDF attachment.",
        target_type=target_type,
        target_id=target_id,
    )
    return response


def _route_export_response(ctx, *, filename, delimiter, content_type, title):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow([
        "Stop",
        "Date",
        "Driver",
        "Plant",
        "Route Action",
        "Arrive",
        "Depart",
        "Inbound Cargo",
        "Outbound Cargo",
        "Part Number",
        "Hot",
        "No Pickup",
        "Delay Minutes",
        "Issue",
        "Fuel",
        "Fuel Mileage",
    ])
    for index, log in enumerate(ctx["logs"], 1):
        route = ctx["log_routes"].get(log.id, {})
        writer.writerow([
            index,
            log.date,
            ctx["driver"].display_name,
            route.get("plant") or _plant_label(log.plant_name),
            route.get("action") or "Logged stop",
            log.arrive_time or "",
            log.depart_time or "",
            route.get("arrive_cargo_desc") or log.load_size or "",
            route.get("depart_cargo_desc") or log.depart_load_size or "",
            log.part_number or "",
            "yes" if log.hot_parts else "",
            "yes" if log.no_pickup else "",
            log.dock_wait_minutes or "",
            log.downtime_reason or "",
            log.fuel or "",
            log.fuel_mileage or "",
        ])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = content_type
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    record_activity(
        user_id=current_user.id,
        category="download",
        action="manager_route_export",
        title=title,
        details=f"Prepared {filename} route export.",
        target_type="driver_log",
    )
    return response


def _transfer_line_summary(transfer, limit=3):
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
    return {
        "route": f"{transfer.ship_from} to {transfer.ship_to}",
        "trailer": transfer.trailer_number or "not set",
        "parts": _transfer_line_summary(transfer) or ["No parts/skids recorded"],
        "transfer_number": transfer.transfer_number or transfer.id,
    }


def _log_freight_summary(log, transfers):
    matches = [
        transfer
        for transfer in transfers
        if log.plant_name in {transfer.ship_from, transfer.ship_to}
    ]
    return [_transfer_summary(transfer) for transfer in matches]


def _division_for_text(*values):
    haystack = " ".join(value or "" for value in values).lower()
    if "trim" in haystack:
        return "Trim"
    return "Plastics"


def _division_for_user(user):
    if not user:
        return "Unassigned"
    return _division_for_text(user.department)


def _division_for_transfer(transfer):
    if transfer.ship_to in TRIM_PLANTS or transfer.ship_from in TRIM_PLANTS:
        return "Trim"
    return "Plastics"


def _status_label(task):
    if task.is_hot and task.status == "pending":
        return "Hot Move"
    if task.status == "in-progress":
        return "In Transit"
    return task.status.replace("-", " ").title()


def _parse_route(value):
    value = (value or "").strip()
    if not value:
        return "", ""
    pieces = re.split(r"\s+to\s+", value, maxsplit=1, flags=re.IGNORECASE)
    if len(pieces) != 2:
        return value, ""
    origin = pieces[0].strip()
    destination = pieces[1].strip()
    destination_token = destination.split()[0] if destination else ""
    if destination_token in PLANT_LABELS:
        destination = destination_token
    return _plant_label(origin), _plant_label(destination)


def _task_part_display(task):
    details = (task.details or "").strip()
    if task.part_number:
        return task.part_number.upper(), details
    source = details or (task.title or "").strip()
    match = PART_TOKEN_RE.search(source)
    if match:
        primary = match.group(0).upper()
        meta = source
    else:
        primary = source or "No part/skid recorded"
        meta = ""
    return primary, meta


def _transfer_part_display(transfer):
    first_line = None
    filled_lines = []
    for line in transfer.lines:
        if any([line.part_number, line.skids, line.quantity]):
            filled_lines.append(line)
            if first_line is None:
                first_line = line
    if first_line is None:
        primary = "No part/skid recorded"
        meta_parts = []
    else:
        primary = first_line.part_number or "No part number"
        meta_parts = []
        if first_line.skids:
            meta_parts.append(f"{first_line.skids} skid(s)")
        if first_line.quantity:
            meta_parts.append(f"qty {first_line.quantity}")
        if len(filled_lines) > 1:
            meta_parts.append(f"+{len(filled_lines) - 1} more line(s)")
    if transfer.trailer_number:
        meta_parts.append(f"Trailer {transfer.trailer_number}")
    return primary, " • ".join(meta_parts)


def _task_dispatch_row(task):
    assigned = task.assigned_user
    division = _division_for_user(assigned)
    if division == "Unassigned":
        division = _division_for_text(task.title, task.details)
    part_primary, part_meta = _task_part_display(task)
    route_from, route_to = _parse_route(task.title)
    truck = _truck_context_for_driver(task.assigned_to, date.today()) if task.assigned_to else {
        "truck_id": "Truck pending",
        "truck_meta": "Assign or accept first",
        "pretrip_id": None,
    }
    if task.completed_by:
        audit = f"Completed by {task.completed_by.manager_label}"
    elif task.accepted_by:
        audit = f"Accepted by {task.accepted_by.manager_label}"
    elif task.assigned_user:
        audit = f"Assigned to {task.assigned_user.manager_label}"
    else:
        audit = "Posted open for any driver"
    return {
        "id": f"T-{task.id}",
        "sort_time": task.created_at,
        "time": task.created_at,
        "division": division,
        "part": " ".join(value for value in [part_primary, part_meta] if value),
        "part_primary": part_primary,
        "part_meta": part_meta,
        "route": task.title,
        "route_from": route_from,
        "route_to": route_to,
        "driver": assigned.manager_label if assigned else "Open for any driver",
        "driver_meta": audit,
        "truck_id": truck["truck_id"],
        "truck_meta": truck["truck_meta"],
        "pretrip_id": truck["pretrip_id"],
        "status": _status_label(task),
        "status_key": "hot" if task.is_hot else task.status,
        "notes": task.details or "",
        "action_url": url_for("manager.manage_task", task_id=task.id),
    }


def _transfer_dispatch_row(transfer):
    summary = _transfer_summary(transfer)
    part_primary, part_meta = _transfer_part_display(transfer)
    truck = _truck_context_for_driver(transfer.user_id, transfer.transfer_date)
    return {
        "id": f"M-{summary['transfer_number']}",
        "sort_time": transfer.created_at,
        "time": transfer.created_at,
        "division": _division_for_transfer(transfer),
        "part": " ".join(value for value in [part_primary, part_meta] if value),
        "part_primary": part_primary,
        "part_meta": part_meta,
        "route": summary["route"],
        "route_from": _plant_label(transfer.ship_from),
        "route_to": _plant_label(transfer.ship_to),
        "trailer": summary["trailer"],
        "driver": transfer.driver_name or transfer.driver.manager_label,
        "driver_meta": f"Logged by {transfer.driver.manager_label}",
        "truck_id": truck["truck_id"],
        "truck_meta": truck["truck_meta"],
        "pretrip_id": truck["pretrip_id"],
        "status": "Logged",
        "status_key": "logged",
        "notes": "; ".join(summary["parts"]),
        "action_url": url_for("manager.view_plant_transfer", transfer_id=transfer.id),
    }


def _build_dispatch_rows(tasks, transfers):
    rows = [_task_dispatch_row(task) for task in tasks]
    rows.extend(_transfer_dispatch_row(transfer) for transfer in transfers)
    return sorted(rows, key=lambda row: row["sort_time"] or datetime.min, reverse=True)


def _driver_log_sort_key(log):
    return (log.date or date.min, log.arrive_time or "", log.created_at or datetime.min, log.id or 0)


def _driver_log_route_context(logs):
    return build_driver_log_route_context(logs)


def _damage_matches_log(report, log, route):
    if report.driver_log_id == log.id:
        return True
    if report.driver_log_id is not None:
        return False
    report_plant = (report.plant_name or "").strip().lower()
    if not report_plant or report_plant == "other":
        return False
    route_plant = (route or {}).get("plant") or ""
    candidates = {
        (log.plant_name or "").strip().lower(),
        route_plant.strip().lower(),
        _plant_label(log.plant_name).strip().lower(),
    }
    return report_plant in candidates


def _damage_photo_url(photo):
    if not photo:
        return None
    upload_root = current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, photo.filename))
    if not os.path.exists(upload_path):
        return None
    return url_for("manager.damage_photo", photo_id=photo.id)


def _damage_report_summary(report):
    photo = report.photos[0] if report.photos else None
    plant = report.plant_name or "Other"
    return {
        "type": "Damage Open" if (report.status or "").lower() != "closed" else "Damage Submitted",
        "label": "Damage Open" if (report.status or "").lower() != "closed" else "Damage Submitted",
        "detail": f"{plant} - {report.stage or 'move'} move - {report.description or 'Damage report'}",
        "photo_url": _damage_photo_url(photo),
        "url": url_for("manager.view_damage_report", report_id=report.id),
    }


def _live_exceptions_for_log(log, route=None, *, is_current_active=False, route_finalized=False):
    route = route or {}
    exceptions = []
    damage_reports = (
        DamageReport.query
        .filter(
            DamageReport.status != "closed",
            db.or_(
                DamageReport.driver_log_id == log.id,
                db.and_(
                    DamageReport.reported_by_id == log.driver_id,
                    DamageReport.driver_log_id.is_(None),
                    db.func.date(DamageReport.created_at) == log.date,
                ),
            ),
        )
        .order_by(DamageReport.created_at.desc())
        .all()
    )
    for report in damage_reports:
        if _damage_matches_log(report, log, route):
            exceptions.append(_damage_report_summary(report))

    plant_name = route.get("plant") or _plant_label(log.plant_name)
    photo_review = _stop_photo_review_summary(log, plant_name)
    if photo_review:
        thumbnail = photo_review.get("thumbnail")
        exceptions.append({
            "type": photo_review["label"],
            "label": photo_review["label"],
            "detail": photo_review["detail"],
            "photo_url": url_for("manager.driver_log_photo", photo_id=thumbnail.id) if thumbnail else None,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })

    truck_issue = truck_issue_reason(log)
    if log.maintenance or truck_issue:
        exceptions.append({
            "type": "Truck Issue",
            "label": "Truck Issue",
            "detail": truck_issue or "Maintenance issue checked by driver",
            "photo_url": None,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })

    cargo_issue = secondary_not_dropped_reason(log) or route_problem_reason(log)
    if cargo_issue:
        exceptions.append({
            "type": "Cargo Mismatch",
            "label": "Cargo Mismatch",
            "detail": cargo_issue,
            "photo_url": None,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })

    if not log.depart_time and (route_finalized or not is_current_active):
        exceptions.append({
            "type": "Missing Departure",
            "label": "Missing Departure",
            "detail": f"Stop #{route.get('stop_number') or ''} {route.get('plant') or _plant_label(log.plant_name)} needs departure/load-out.",
            "photo_url": None,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })

    return exceptions


def _critical_exception_rows(live_stop_rows, todays_logs):
    rows = []
    seen = set()
    for row in live_stop_rows:
        for item in row["exceptions"]:
            key = (row["log"].id, item["label"], item["detail"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "type": item["label"],
                "route_stop": f"Stop #{row['stop_number']} {row['route'].get('plant') or _plant_label(row['log'].plant_name)}",
                "driver": row["driver"].display_name,
                "issue": item["detail"],
                "url": item["url"],
                "photo_url": item.get("photo_url"),
            })

    route_level_reports = (
        DamageReport.query
        .filter(
            DamageReport.status != "closed",
            DamageReport.driver_log_id.is_(None),
            db.func.date(DamageReport.created_at) == date.today(),
        )
        .order_by(DamageReport.created_at.desc())
        .all()
    )
    log_driver_ids = {log.driver_id for log in todays_logs}
    for report in route_level_reports:
        if report.reported_by_id not in log_driver_ids:
            continue
        report_plant = (report.plant_name or "").strip().lower()
        if report_plant and report_plant != "other":
            continue
        key = ("damage", report.id)
        if key in seen:
            continue
        seen.add(key)
        summary = _damage_report_summary(report)
        rows.append({
            "type": summary["label"],
            "route_stop": report.plant_name or "Route-level",
            "driver": report.reported_by.display_name if report.reported_by else "Driver",
            "issue": summary["detail"],
            "url": summary["url"],
            "photo_url": summary.get("photo_url"),
        })
    return rows[:8]

def _exception_key(item):
    return ":".join(
        str(item.get(part) or "")
        for part in ("target_type", "target_id", "category")
    )


def _reviewed_exception_keys():
    events = ActivityEvent.query.filter(
        ActivityEvent.category == "exception",
        ActivityEvent.action.in_(["reviewed", "deleted"]),
    ).all()
    keys = set()
    for event in events:
        for part in (event.details or "").split(";"):
            part = part.strip()
            if part.startswith("key:"):
                keys.add(part[4:].strip())
    return keys


def _active_exception_items():
    reviewed = _reviewed_exception_keys()
    return [
        item for item in build_exception_items(dock_delay_minutes=_dock_delay_minutes())
        if _exception_key(item) not in reviewed
    ]


def _live_stop_rows(logs):
    sorted_logs = sorted(logs, key=_driver_log_sort_key)
    counts = {}
    rows = []
    contexts = {}
    for log in sorted_logs:
        key = (log.driver_id, log.date)
        if key not in contexts:
            contexts[key] = build_route_context(driver_id=log.driver_id, route_date=log.date)
        counts[key] = counts.get(key, 0) + 1
        route_context = contexts[key]
        snapshot_row = next((item for item in route_context.rows if item.get("log_id") == log.id), {})
        route = snapshot_row.get("route") or {}
        route["stop_number"] = counts[key]
        is_current_active = snapshot_row.get("status") == "Current"
        exceptions = _live_exceptions_for_log(log, route, is_current_active=is_current_active)
        timing = snapshot_row.get("timing") or (forecast_for_stop(log) if not log.depart_time else None)
        if timing and timing.get("severity") in {"warning", "high"} and not is_current_active:
            exceptions.append({
                "type": "Timing Status",
                "label": "Timing Status",
                "detail": f"{timing['status']}: elapsed {timing['elapsed_label']} vs estimate {timing['estimate_label']}.",
                "photo_url": None,
                "url": url_for("manager.view_driver_log", log_id=log.id),
            })
        status = "1. Current Active Stop" if is_current_active else snapshot_row.get("status", "Completed")
        status_key = snapshot_row.get("status_key") or ("open" if not log.depart_time else "complete")
        rows.append({
            "log": log,
            "route": route,
            "stop_number": counts[key],
            "driver": log.driver,
            "status": status,
            "status_key": status_key,
            "cargo": snapshot_row.get("cargo_out") or snapshot_row.get("cargo_in") or log.depart_load_size or log.load_size or "--",
            "dock_wait": f"{log.dock_wait_minutes} min" if (log.dock_wait_minutes or 0) > 0 else "--",
            "forecast": timing,
            "exceptions": exceptions,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })
    return list(reversed(rows))


def _route_print_context(driver_id, route_date):
    driver = User.query.get_or_404(driver_id)
    logs = sorted(
        _active_driver_logs_query().filter_by(driver_id=driver.id, date=route_date).all(),
        key=_driver_log_sort_key,
    )
    pretrips = _active_pretrips_query().filter_by(user_id=driver.id, pretrip_date=route_date).all()
    log_routes = _driver_log_route_context(logs)
    damage_reports = (
        DamageReport.query
        .filter(
            DamageReport.reported_by_id == driver.id,
            db.func.date(DamageReport.created_at) == route_date,
        )
        .order_by(DamageReport.created_at.desc())
        .all()
    )
    parts_carried = sorted({log.part_number for log in logs if log.part_number})
    exception_notes = []
    log_issue_details = {}
    for log in logs:
        route = log_routes.get(log.id, {})
        plant_name = route.get("plant") or _plant_label(log.plant_name)
        if log.maintenance or log.downtime_reason:
            exception_notes.append(f"Issue at {plant_name}: {log.downtime_reason or 'Maintenance marked'}")
            log_issue_details[log.id] = {"truck": log.downtime_reason or "Maintenance marked", "route": ""}
        photo_review = _stop_photo_review_summary(log, plant_name)
        if photo_review:
            exception_notes.append(f"{photo_review['label']}: {photo_review['detail']}")
    signature_shift = _shift_record_for_driver_date(driver.id, route_date, require_signature=True)
    route_truck_context = _manager_route_truck_context(driver.id, route_date, pretrips)
    mileage_review = _manager_mileage_review(pretrips, logs, route_truck_context)
    current_stop = next((log for log in reversed(logs) if not log.depart_time), None) or (logs[-1] if logs else None)
    stop_forecasts = route_stop_forecasts(logs)
    current_stop_forecast = stop_forecasts.get(current_stop.id) if current_stop else None
    route_context = build_route_context(
        driver_id=driver.id,
        route_date=route_date,
        truck_id=route_truck_context.get("label"),
        now=None,
    )
    next_load_prediction = route_context.next_load_prediction or (build_next_load_prediction(
        current_stop=current_stop,
        driver_id=driver.id,
        truck_id=route_truck_context.get("label"),
        current_cargo_state=None,
        route_date=route_date,
        timing_forecast=current_stop_forecast,
    ).to_dict() if current_stop else None)
    return {
        "driver": driver,
        "logs": logs,
        "log_routes": log_routes,
        "the_date": route_date,
        "pretrips": pretrips,
        "damage_reports": damage_reports,
        "damage_report_summary": damage_report_count_label(damage_reports),
        "damage_report_details": [damage_report_detail_label(report) for report in damage_reports],
        "total_miles": mileage_review["total_miles"],
        "mileage_review": mileage_review,
        "route_truck_context": route_truck_context,
        "parts_carried": parts_carried,
        "exception_notes": exception_notes,
        "log_issue_details": log_issue_details,
        "route_task_events": _task_route_events_for_logs(logs),
        "stop_forecasts": stop_forecasts,
        "next_load_prediction": next_load_prediction,
        "route_context": route_context,
        "driver_signature": signature_shift.driver_signature if signature_shift else None,
        "signature_timestamp": signature_shift.signature_timestamp if signature_shift else None,
        "route_finalized": _route_finalized_for_driver_date(driver.id, route_date),
        "part_scan_events": _part_scan_events_for_logs(logs),
    }


def _route_finalized_for_driver_date(driver_id, route_date):
    return ActivityEvent.query.filter_by(
        user_id=driver_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(route_date))).first() is not None


def _part_scan_events_for_logs(logs):
    log_ids = route_stop_ids(logs)
    scope_id = route_scope_id(logs)
    if not log_ids and not scope_id:
        return []
    filters = []
    if scope_id:
        filters.append(PartScanEvent.route_id == scope_id)
    if log_ids:
        filters.extend([
            PartScanEvent.stop_id.in_(log_ids),
            PartScanEvent.driver_log_id.in_(log_ids),
        ])
    return (
        PartScanEvent.query
        .filter(or_(*filters))
        .order_by(PartScanEvent.timestamp.asc(), PartScanEvent.id.asc())
        .all()
    )


def _driver_short_name(driver):
    raw_name = (driver.first_name or driver.display_name or driver.username or "Driver").split()[0]
    return raw_name[:1].upper() + raw_name[1:] if raw_name else "Driver"


def _pretrip_sort_key(pretrip):
    return (
        pretrip.pretrip_date or date.min,
        pretrip.created_at or datetime.min,
        pretrip.id or 0,
    )


def _manager_pretrip_truck_label(pretrip):
    if not pretrip:
        return "Not recorded"
    return pretrip.truck_number or f"PreTrip #{pretrip.id}"


def _manager_route_truck_context(driver_id, route_date, pretrips):
    sorted_pretrips = sorted(pretrips, key=_pretrip_sort_key)
    by_id = {pretrip.id: pretrip for pretrip in sorted_pretrips}
    route_shifts = (
        ShiftRecord.query.join(PreTrip, ShiftRecord.pretrip_id == PreTrip.id)
        .filter(ShiftRecord.user_id == driver_id, PreTrip.pretrip_date == route_date)
        .order_by(ShiftRecord.start_time.asc(), ShiftRecord.id.asc())
        .all()
    )
    route_ids = []
    source = "none"

    for shift in route_shifts:
        if shift.pretrip_id in by_id and shift.pretrip_id not in route_ids:
            route_ids.append(shift.pretrip_id)

    if route_ids:
        source = "shift-linked"
    elif len(sorted_pretrips) == 1:
        route_ids = [sorted_pretrips[0].id]
        source = "single-dvir"
    elif sorted_pretrips:
        latest = sorted_pretrips[-1]
        route_ids = [latest.id]
        source = "selected-same-day-dvir"

    route_pretrips = [by_id[pretrip_id] for pretrip_id in route_ids if pretrip_id in by_id]
    route_trucks = []
    for pretrip in route_pretrips:
        label = _manager_pretrip_truck_label(pretrip)
        if label and label not in route_trucks:
            route_trucks.append(label)
    separate_pretrips = [pretrip for pretrip in sorted_pretrips if pretrip.id not in set(route_ids)]

    if len(route_trucks) > 1:
        label = "Multiple trucks: " + ", ".join(route_trucks)
    else:
        label = route_trucks[0] if route_trucks else "Not recorded"
    return {
        "label": label,
        "route_pretrip_ids": set(route_ids),
        "route_trucks": route_trucks,
        "multiple_trucks": len(route_trucks) > 1,
        "separate_pretrips": separate_pretrips,
        "source": source,
        "route_shift_ids": [shift.id for shift in route_shifts],
    }


def _manager_truck_label(pretrips):
    latest = sorted(pretrips, key=_pretrip_sort_key)[-1] if pretrips else None
    return _manager_pretrip_truck_label(latest)


def _manager_mileage_label(value, suffix="mi"):
    if value is None:
        return "--"
    try:
        formatted = f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)
    return f"{formatted} {suffix}" if suffix else formatted


def _manager_normal_route_miles_max():
    try:
        return int(current_app.config.get("MANAGER_ROUTE_NORMAL_MILES_MAX", 1000))
    except (TypeError, ValueError):
        return 1000


def _manager_calculate_mileage_record(pretrip, normal_max=None):
    normal_max = _manager_normal_route_miles_max() if normal_max is None else normal_max
    mileage = calculate_mileage_record(pretrip, normal_max=normal_max)
    if mileage["status"] == "Needs correction" and mileage.get("start") in {None, 0}:
        if mileage.get("end") is not None:
            mileage["detail"] = f"Beginning odometer is missing or zero; ending odometer {_manager_mileage_label(mileage['end'])} cannot be used as route miles."
    elif mileage["status"] == "Needs correction" and mileage.get("calculated_miles") is not None and mileage["calculated_miles"] < 0:
        mileage["detail"] = f"Ending odometer {_manager_mileage_label(mileage['end'])} is lower than beginning odometer {_manager_mileage_label(mileage['start'])}."
    return mileage


def _manager_mileage_review(pretrips, logs, route_truck_context=None):
    rows = []
    route_issue_details = []
    route_pending_details = []
    route_pending = False
    route_completed = False
    route_total_miles = 0
    sorted_pretrips = sorted(pretrips, key=_pretrip_sort_key)
    route_ids = set((route_truck_context or {}).get("route_pretrip_ids") or [])
    if not route_ids and sorted_pretrips:
        route_ids = {sorted_pretrips[-1].id}
    route_label = (route_truck_context or {}).get("label") or _manager_truck_label(sorted_pretrips)
    route_pretrips = [pretrip for pretrip in sorted_pretrips if pretrip.id in route_ids]

    for index, pretrip in enumerate(route_pretrips, start=1):
        truck_label = _manager_pretrip_truck_label(pretrip)
        mileage = _manager_calculate_mileage_record(pretrip)
        calculated_miles = mileage["calculated_miles"]
        if mileage["status"] == "Pending":
            route_pending = True
            route_pending_details.append(f"{truck_label}: {mileage['detail']}")
        elif mileage["status"] == "Needs correction":
            route_issue_details.append(f"{truck_label}: {mileage['detail']}")
        else:
            route_total_miles += calculated_miles or 0
            route_completed = True

        rows.append({
            "checkpoint": f"PreTrip {index}",
            "scope": "Route truck",
            "truck": truck_label,
            "start": _manager_mileage_label(mileage["start"]),
            "end": _manager_mileage_label(mileage["end"]),
            "miles": _manager_mileage_label(calculated_miles, "miles") if calculated_miles is not None else mileage["status"],
            "status": mileage["status"],
            "detail": mileage["detail"],
            "blocks_approval": mileage["blocks_approval"],
        })

    route_mileage_label = _manager_mileage_label(route_total_miles, "miles") if route_completed else "Pending posttrip mileage"
    if route_issue_details:
        detail = route_issue_details[0]
        quality_item = {"label": "Mileage", "status": "Needs correction", "detail": detail, "blocks_approval": True, "blocker_label": "Mileage conflict / correction required", "action": "Correct route mileage before approving route."}
        label = "Needs correction"
        total_value = route_total_miles if route_completed else None
    elif route_pending or not route_completed:
        detail = route_pending_details[0] if route_pending_details else ("Mileage pending PostTrip: PostTrip end mileage has not been recorded." if logs or route_pretrips else "No route mileage records were found.")
        quality_item = {"label": "Mileage", "status": "Pending", "detail": detail, "blocks_approval": True, "blocker_label": "Mileage pending PostTrip", "action": "Complete PostTrip mileage before approving route."}
        label = "Pending posttrip mileage" if logs or route_pretrips else "Not recorded"
        total_value = None
    else:
        quality_item = {"label": "Mileage", "status": "Normal", "detail": f"Route truck {route_label} shows {route_mileage_label}.", "blocks_approval": False, "blocker_label": "", "action": ""}
        label = route_mileage_label
        total_value = route_total_miles

    return {
        "label": label,
        "status": quality_item["status"],
        "detail": quality_item["detail"],
        "rows": rows,
        "total_miles": total_value,
        "route_miles_label": route_mileage_label,
        "route_truck_label": route_label,
        "route_issue_details": route_issue_details,
        "separate_issue_details": [],
        "excluded_pretrip_count": len([pretrip for pretrip in sorted_pretrips if pretrip.id not in route_ids]),
        "quality_item": quality_item,
        "blocks_approval": bool(quality_item.get("blocks_approval")),
    }


def _manager_uploaded_label(stamp):
    if not stamp:
        return "--"
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    utc_stamp = stamp.astimezone(pytz.utc)
    local_stamp = utc_stamp.astimezone(pytz.timezone("America/Detroit"))
    time_part = local_stamp.strftime("%I:%M%p").lstrip("0").lower()
    return f"{time_part} {local_stamp.tzname()}"


def _clean_manager_driver_note(note):
    text = re.sub(r"\s+", " ", (note or "").strip())
    if not text:
        return ""
    text = re.sub(r"\bun[\s-]?balanced\b", "unbalanced", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    normalized = text.lower()
    if "load is unbalanced" in normalized and "causes skid" in normalized and "tip over" in normalized:
        return "The load is unbalanced. This is what causes skids to tip over."
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def _driver_log_photo_file_path(photo):
    if not photo:
        return None
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    return upload_file_path(upload_root, photo.filename)


def _manager_photo_reviews(logs, log_routes):
    rows = []
    for log in logs:
        plant = (log_routes.get(log.id) or {}).get("plant") or _plant_label(log.plant_name)
        summary = _stop_photo_review_summary(log, plant)
        if not summary:
            continue
        latest = summary.get("latest")
        note = (getattr(latest, "note", "") or "").strip()
        lower_note = note.lower()
        safety_terms = ("unbalanced", "un-balanced", "skid", "tip", "tipped", "safety", "unsafe")
        review_type = "Cargo safety review" if any(term in lower_note for term in safety_terms) else summary["label"]
        photo_for_url = latest or summary.get("thumbnail")
        rows.append({
            "log": log,
            "plant": plant,
            "summary": summary,
            "photo": latest,
            "thumbnail": summary.get("thumbnail"),
            "photo_id": getattr(photo_for_url, "id", None),
            "photo_path": _driver_log_photo_file_path(photo_for_url),
            "note": note,
            "display_note": _clean_manager_driver_note(note),
            "review_type": review_type,
            "uploaded_at": getattr(latest, "uploaded_at", None),
            "uploaded_label": _manager_uploaded_label(getattr(latest, "uploaded_at", None)),
            "photo_url": url_for("manager.driver_log_photo", photo_id=photo_for_url.id) if photo_for_url else None,
            "photo_load_warning": not bool(getattr(photo_for_url, "file_available", False)) if photo_for_url else True,
        })
    return rows


def _manager_cargo_timing_rows(logs, log_routes, stop_forecasts):
    rows = []
    for log in logs:
        forecast = (stop_forecasts or {}).get(log.id)
        if not forecast or forecast.get("estimate_minutes") is None or forecast.get("elapsed_minutes") is None:
            continue
        route = log_routes.get(log.id, {})
        plant = route.get("plant") or _plant_label(log.plant_name)
        today_average = forecast.get("today_average_label") if forecast.get("today_average") is not None else None
        rows.append({
            "plant": plant,
            "actual": forecast.get("elapsed_label") or "--",
            "average": today_average or forecast.get("estimate_label") or "--",
            "status": forecast.get("status") or "On pace",
            "class": forecast.get("severity") or "muted",
        })
    return rows


def _manager_cargo_review(logs, log_routes, part_scan_events, stop_forecasts=None):
    cargo_state = reconcile_cargo(logs, log_routes)
    issues = list(cargo_state.get("issues") or [])
    still_onboard = bool(issues)

    pending_statuses = {"unknown", "pending", "needs_review", "needs review", "pending_part"}
    failed_statuses = {"failed", "unexpected", "mismatch"}
    pending_scans = []
    failed_scans = []
    unexpected_scans = []
    for event in part_scan_events:
        status = (event.validation_status or "").lower().strip()
        if status in failed_statuses:
            failed_scans.append(event)
        if status == "unexpected":
            unexpected_scans.append(event)
        if status in pending_statuses or status.startswith("pending"):
            pending_scans.append(event)

    pending_scan_events = []
    seen_scan_ids = set()
    for event in pending_scans + failed_scans:
        event_key = event.id or id(event)
        if event_key not in seen_scan_ids:
            pending_scan_events.append(event)
            seen_scan_ids.add(event_key)

    stop_lookup = {log.id: log for log in logs}
    pending_scan_rows = []
    for event in pending_scan_events:
        log = stop_lookup.get(event.stop_id)
        route = log_routes.get(log.id, {}) if log else {}
        plant = route.get("plant") or (_plant_label(log.plant_name) if log else None) or event.plant_id or "Route scan"
        pending_scan_rows.append({
            "id": event.id,
            "stop": plant,
            "context": (event.scan_context or "scan").replace("_", " ").title(),
            "status": (event.validation_status or "needs review").replace("_", " "),
            "value": event.normalized_value or event.raw_value or "",
            "time": _manager_uploaded_label(event.timestamp),
        })

    pending_count = len(pending_scan_events)
    needs_review = bool(issues or pending_count or still_onboard or unexpected_scans)
    cargo_status = "Needs Review" if needs_review else "Clean"
    scan_records_attached = bool(part_scan_events)
    manifest_linked = False
    pending_scan_label = f"{pending_count} pending cargo scan{'s' if pending_count != 1 else ''}" if pending_count else "No pending cargo scans"
    if pending_count == 1:
        pending_scan_reason = "1 scan needs manager confirmation."
        pending_scan_value = "1 scan"
    elif pending_count:
        pending_scan_reason = f"{pending_count} scans need manager confirmation."
        pending_scan_value = f"{pending_count} scans"
    else:
        pending_scan_reason = "No pending scan confirmations."
        pending_scan_value = "No pending scans"

    if issues:
        mismatch_summary = "; ".join(issues[:2])
    else:
        mismatch_summary = "No cargo mismatch was detected from driver-entered route data."
    if pending_count:
        summary_detail = f"{mismatch_summary} {pending_scan_reason} No shipper/manifest record is linked, so cargo is not fully manifest-verified."
    elif issues:
        summary_detail = f"{mismatch_summary} No shipper/manifest record is linked, so cargo is not fully manifest-verified."
    else:
        summary_detail = f"{mismatch_summary} No shipper/manifest record is linked, so cargo is not manifest-verified."

    unresolved = []
    if pending_count:
        unresolved.append(pending_scan_reason)
    if issues:
        unresolved.extend(issues[:2])
    if unexpected_scans:
        unresolved.append(f"{len(unexpected_scans)} unexpected scan{'s' if len(unexpected_scans) != 1 else ''} require review.")

    summary_rows = [
        {"label": "Cargo status", "value": cargo_status, "detail": summary_detail, "class": "needs-review" if needs_review else "clean"},
        {"label": "Verification level", "value": "Route-entered + scans only", "detail": "Cargo verification source: driver route entries + scan records only.", "class": "warning"},
        {"label": "Manifest linked", "value": "No", "detail": "No shipper/manifest record is linked.", "class": "warning"},
    ]
    if pending_count:
        summary_rows.append({"label": "Pending", "value": pending_scan_value, "detail": pending_scan_reason, "class": "needs-review"})
    if unresolved:
        summary_rows.append({"label": "Unresolved cargo questions", "value": str(len(unresolved)), "detail": " ".join(unresolved[:3]), "class": "needs-review"})
    summary_rows.append({
        "label": "Final cargo approval",
        "value": "Blocked" if needs_review else "Ready for manager decision",
        "detail": "Blocked until scans are confirmed." if pending_count else ("Blocked until cargo issues are resolved." if needs_review else "No cargo approval blocker detected from route entries."),
        "class": "needs-review" if needs_review else "clean",
    })

    return {
        "movement_rows": [],
        "issues": issues,
        "cargo_state": cargo_state,
        "scan_records_attached": scan_records_attached,
        "manifest_linked": manifest_linked,
        "manifest_label": "No",
        "scan_review_status": "Needs manager confirmation" if pending_count else ("Recorded" if part_scan_events else "No scan records linked"),
        "pending_scan_count": pending_count,
        "pending_scan_label": pending_scan_label,
        "pending_scan_reason": pending_scan_reason,
        "pending_scan_rows": pending_scan_rows,
        "status": cargo_status,
        "status_class": "needs-review" if needs_review else "clean",
        "summary_rows": summary_rows,
        "timing_rows": _manager_cargo_timing_rows(logs, log_routes, stop_forecasts or {}),
        "detail_needed": False,
        "approval_detail": pending_scan_reason if pending_count else ("; ".join(issues[:2]) if issues else ""),
    }

def _manager_delay_forecast_label(forecast):
    if not forecast:
        return "No plant average available", "muted"
    severity = forecast.get("severity") or "muted"
    if forecast.get("estimate_minutes") is None:
        return "First-time stop - no historical baseline for dock time", "muted"
    status = forecast.get("status") or "On pace"
    elapsed = forecast.get("elapsed_label") or "--"
    estimate = forecast.get("estimate_label") or "--"
    if severity in {"warning", "high"}:
        return f"{status}; elapsed {elapsed} vs expected {estimate}", severity
    return f"On pace; expected around {estimate}", "ok"


def _manager_delay_review(logs, log_routes, stop_forecasts):
    rows = []
    for log in logs:
        route = log_routes.get(log.id, {})
        forecast = (stop_forecasts or {}).get(log.id)
        if (log.dock_wait_minutes or 0) > 0 or log.downtime_reason or (forecast and forecast.get("severity") in {"warning", "high"}):
            plant = route.get("plant") or _plant_label(log.plant_name)
            forecast_label, forecast_class = _manager_delay_forecast_label(forecast)
            requires_reason = bool(forecast and forecast.get("severity") in {"warning", "high"} and not log.depart_time and not log.downtime_reason)
            rows.append({
                "plant": plant,
                "dock_wait": f"{log.dock_wait_minutes} min" if (log.dock_wait_minutes or 0) > 0 else (forecast.get("elapsed_label") if forecast else "--"),
                "reason": "Driver delay reason missing." if requires_reason else (log.downtime_reason or "No driver delay reason recorded."),
                "forecast": forecast_label,
                "forecast_class": forecast_class,
                "requires_reason": requires_reason,
                "action": f"Add delay reason for {plant} before final approval." if requires_reason else "",
            })
    return rows


def _manager_data_quality(logs, log_routes, mileage_quality_item, driver_signature, route_finalized):
    items = [mileage_quality_item]
    all_departed = bool(logs) and all(log.depart_time for log in logs)
    if all_departed and not route_finalized:
        items.append({"label": "Route status", "status": "Ready for final review", "detail": "All recorded stops are closed. Route is awaiting final review."})
    for index, log in enumerate(logs):
        route = log_routes.get(log.id, {})
        plant = route.get("plant") or _plant_label(log.plant_name)
        if not log.depart_time and (route_finalized or index < len(logs) - 1):
            reason = "the route is being finalized" if route_finalized else "a later stop exists"
            items.append({"label": "Missing Departure", "status": "Correction required", "detail": f"{plant} is missing departure because {reason}."})
        if log.arrive_time and log.depart_time:
            # Keep detailed time math out of this lightweight report until arrival/departure formats are normalized.
            pass
    if not driver_signature:
        items.append({"label": "Driver signature", "status": "Missing", "detail": "Driver route signature has not been captured."})
    items.append({"label": "Manager signature", "status": "Pending", "detail": "Manager review signature is required before approval."})
    return items


def _manager_damage_report_rows(damage_reports):
    rows = []
    for report in damage_reports or []:
        stop = report.driver_log
        photo_count = len(report.photos or [])
        rows.append({
            "id": report.id,
            "type": damage_report_kind(report).title(),
            "stop": _plant_label(stop.plant_name) if stop else _plant_label(report.plant_name),
            "status": (report.status or "open").replace("_", " ").title(),
            "note": report.description or "No driver note recorded.",
            "photo_attached": "Yes" if photo_count else "No",
            "photo_count": photo_count,
        })
    return rows


def _manager_required_actions(data_quality_items, photo_reviews, cargo_review, route_finalized, logs, driver_signature, delay_review_rows=None, next_load_prediction=None):
    actions = []
    mileage_item = next((item for item in data_quality_items if item["label"] == "Mileage"), None)
    if mileage_item and mileage_item.get("blocks_approval"):
        active_open_stop = bool(logs) and any(not log.depart_time for log in logs)
        if active_open_stop and mileage_item.get("status") == "Pending":
            actions.append("Record PostTrip mileage after route close before final approval.")
        else:
            actions.append(mileage_item.get("action") or "Correct route mileage before approving route.")
    for review in photo_reviews:
        if "safety" in review["review_type"].lower() or review["summary"]["label"] == "Cargo Photo Proof":
            actions.append(f"Review/classify {review['plant']} cargo photo.")
            break
    if cargo_review["issues"] or cargo_review["pending_scan_count"]:
        actions.append("Confirm cargo movement and pending scan review.")
    for row in delay_review_rows or []:
        if row.get("requires_reason"):
            actions.append(row.get("action") or f"Add delay reason for {row['plant']} before final approval.")
            break
    if next_load_prediction and next_load_prediction.get("required_driver_action") and not all(log.depart_time for log in logs):
        actions.append(next_load_prediction["required_driver_action"])
    all_departed = bool(logs) and all(log.depart_time for log in logs)
    if all_departed and not route_finalized:
        actions.append("Finalize route after confirming final unload.")
    if not driver_signature:
        actions.append("Collect missing signatures.")
    if not actions:
        actions.append("Sign manager review or approve route.")
    return actions


def _manager_approval_blockers(data_quality_items, photo_reviews, cargo_review, route_finalized, logs, driver_signature):
    blockers = []
    mileage_item = next((item for item in data_quality_items if item["label"] == "Mileage"), None)
    all_departed = bool(logs) and all(log.depart_time for log in logs)
    active_open_stop = bool(logs) and not all_departed

    if active_open_stop:
        open_stop = next((log for log in reversed(logs) if not log.depart_time), logs[-1])
        blockers.append({"label": "Active stop still open", "detail": f"{_plant_label(open_stop.plant_name)} is awaiting departure/load-out."})
        if mileage_item and mileage_item.get("blocks_approval"):
            blockers.append({"label": "PostTrip mileage not yet due", "detail": "PostTrip mileage is pending until the route is closed."})
    elif mileage_item and mileage_item.get("blocks_approval"):
        blockers.append({"label": mileage_item.get("blocker_label") or "Mileage conflict / correction required", "detail": mileage_item["detail"]})

    if cargo_review.get("pending_scan_count"):
        blockers.append({"label": cargo_review["pending_scan_label"], "detail": "Final cargo approval is blocked until scans are confirmed."})
    if cargo_review.get("issues"):
        blockers.append({"label": "Cargo route issue", "detail": "; ".join(cargo_review["issues"][:2])})
    for review in photo_reviews:
        if "safety" in review["review_type"].lower() or review["summary"]["label"] == "Cargo Photo Proof":
            blockers.append({"label": "Cargo safety photo needs classification", "detail": f"{review['plant']} photo proof requires manager classification."})
            break
    if all_departed and not route_finalized:
        blockers.append({"label": "Route awaiting final review", "detail": "All recorded stops are closed. Manager review/signature is still pending."})
    if not driver_signature:
        label = "Driver signature pending route close" if active_open_stop else "Driver signature missing"
        detail = "Driver signature is pending until route close." if active_open_stop else "Driver route signature has not been captured."
        blockers.append({"label": label, "detail": detail})
    blockers.append({"label": "Manager signature pending", "detail": "Manager review signature is required before final approval."})
    return blockers


def _manager_review_status(required_actions, data_quality_items, photo_reviews, cargo_review, route_finalized, logs):
    correction_labels = {"Missing departure", "Missing Departure", "Mileage"}
    if any(item["label"] in correction_labels and item["status"] in {"Needs correction", "Correction required"} for item in data_quality_items):
        return "Correction Required"
    if photo_reviews or cargo_review["issues"] or cargo_review["pending_scan_count"] or any(item["status"] in {"Missing", "Finalization required", "Ready for final review", "Pending", "Separate issue"} for item in data_quality_items):
        return "Needs Review"
    if route_finalized:
        return "Clean"
    if logs:
        return "Needs Review"
    return "Needs Review"


def _manager_time_label(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        stamp = pytz.utc.localize(value) if value.tzinfo is None else value.astimezone(pytz.utc)
        return stamp.astimezone(pytz.timezone("America/Detroit")).strftime("%I:%M%p").lower().lstrip("0")
    raw = str(value).strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            stamp = pytz.utc.localize(datetime.strptime(raw, fmt))
            return stamp.astimezone(pytz.timezone("America/Detroit")).strftime("%I:%M%p").lower().lstrip("0")
        except ValueError:
            pass
    normalized = raw.lower().replace(" ", "")
    for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%I:%M%p").lower().lstrip("0")
        except ValueError:
            pass
    return raw


def _manager_stop_complete_time(log):
    return _manager_time_label(getattr(log, "depart_time", None)) or _manager_time_label(getattr(log, "arrive_time", None))



def _manager_post_unload_stop_label(log, route):
    plant = route.get("plant") or _plant_label(getattr(log, "plant_name", ""))
    if getattr(log, "maintenance", False) or truck_issue_reason(log):
        return f"{plant} maintenance"
    if getattr(log, "fuel", False):
        return f"{plant} fuel"
    if getattr(log, "meeting", False):
        return f"{plant} meeting"
    if getattr(log, "no_pickup", False):
        return f"{plant} drop/no pickup"
    return f"{plant} non-cargo stop"


def _manager_blocker_phrase(blockers):
    labels = []
    signature_blocked = False
    for blocker in blockers:
        label = blocker["label"]
        if "pending cargo scan" in label:
            labels.append(label)
        elif label == "Cargo safety photo needs classification":
            detail = blocker.get("detail") or ""
            plant = detail.split(" photo", 1)[0] if " photo" in detail else "Cargo safety"
            labels.append(f"one {plant} cargo-safety photo requiring classification")
        elif label == "Active stop still open":
            labels.append("active stop still open")
        elif label == "PostTrip mileage not yet due":
            labels.append("PostTrip mileage pending route close")
        elif label == "Route not finalized":
            labels.append("route finalization")
        elif label in {"Driver signature missing", "Driver signature pending route close", "Manager signature pending"}:
            signature_blocked = True
        elif label == "Mileage pending PostTrip":
            labels.append("pending posttrip mileage")
        elif label == "Mileage conflict / correction required":
            labels.append("mileage correction")
        else:
            labels.append(label[:1].lower() + label[1:])
    if signature_blocked:
        labels.append("missing signatures")
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _manager_summary_sentence(driver, logs, log_routes, route_status, damage_reports, photo_reviews, total_miles, data_quality_items, approval_blockers=None, mileage_review=None, cargo_review=None, route_state=None, next_load_prediction=None):
    name = _driver_short_name(driver)
    approval_blockers = approval_blockers or []
    route_truck = (mileage_review or {}).get("route_truck_label") or ""
    truck_part = f" for truck {route_truck}" if route_truck and route_truck != "Not recorded" else ""
    parts = [f"{name} has {len(logs)} recorded stop event{'s' if len(logs) != 1 else ''}{truck_part}."]
    final_route = log_routes.get(logs[-1].id, {}) if logs else {}
    last_stop_plant = final_route.get("plant") or (_plant_label(logs[-1].plant_name) if logs else None)
    cargo_state = (cargo_review or {}).get("cargo_state") or {}
    final_cargo = cargo_state.get("final_cargo") or {}
    final_unload_log = final_cargo.get("log")
    final_unload_plant = final_cargo.get("plant")
    current_activity = (route_state or {}).get("current_activity")
    active_summary_covers_approval = False
    if current_activity and final_unload_plant and last_stop_plant and final_unload_plant != last_stop_plant:
        active_summary_covers_approval = True
        prediction = next_load_prediction or {}
        prediction_sentence = ""
        if prediction.get("is_known"):
            prediction_sentence = f" Next load estimate: {prediction.get('predicted_load_label')} to {prediction.get('display_destination')} ({prediction.get('confidence_label')} via {prediction.get('source_label')})."
        else:
            prediction_sentence = " Next load is unknown until a shipper scan, dispatch task, plant rule, or driver confirmation is recorded."
        parts.append(f"The previous cargo cycle appears complete. {name} is currently at {current_activity['plant']} awaiting departure/load-out.{prediction_sentence} Final route approval is unavailable until the active stop is closed, PostTrip mileage is recorded, and signatures are captured.")
    elif final_unload_plant and last_stop_plant and final_unload_plant != last_stop_plant:
        final_unload_index = logs.index(final_unload_log) if final_unload_log in logs else -1
        post_unload_logs = logs[final_unload_index + 1:] if final_unload_index >= 0 else []
        later_cargo_issues = cargo_state.get("later_cargo_issues") or []
        unload_time = _manager_stop_complete_time(final_unload_log)
        unload_stamp = f" {unload_time}" if unload_time else ""
        if post_unload_logs and not later_cargo_issues:
            post_labels = "; ".join(_manager_post_unload_stop_label(log, log_routes.get(log.id, {})) for log in post_unload_logs)
            parts.append(f"The route is complete and awaiting final review. Final cargo unload was at {final_unload_plant}{unload_stamp}; subsequent stops were non-cargo ({post_labels}).")
        elif later_cargo_issues:
            cargo_plants = ", ".join(later_cargo_issues)
            parts.append(f"Route needs review: final cargo unload at {final_unload_plant}{unload_stamp}, but later cargo activity was recorded at {cargo_plants}.")
        else:
            parts.append(f"The route is complete and awaiting final review. Final cargo unload was at {final_unload_plant}{unload_stamp}.")
    elif route_status in {"Completed", "Finalization Required"}:
        parts.append("The route is complete and awaiting final review.")
    elif route_status == "Active":
        parts.append("The route is active and still in progress.")
    elif route_status == "Finalized":
        parts.append("The route has been finalized.")

    active_open_stop = route_status == "Active" and any(blocker["label"] == "Active stop still open" for blocker in approval_blockers)
    mileage_issue = next((item for item in data_quality_items if item["label"] == "Mileage"), None)
    if mileage_issue and mileage_issue["status"] == "Needs correction":
        parts.append(f"Mileage needs correction before approval: {mileage_issue['detail']}")
    elif mileage_issue and mileage_issue["status"] == "Pending" and not active_summary_covers_approval:
        parts.append("PostTrip mileage is pending route close." if active_open_stop else "Mileage pending PostTrip review.")
    if approval_blockers and not active_summary_covers_approval:
        blocker_phrase = _manager_blocker_phrase(approval_blockers)
        if active_open_stop:
            parts.append(f"Final approval is not yet available because {blocker_phrase}.")
        else:
            parts.append(f"Approval is blocked by {blocker_phrase}.")
    elif damage_reports:
        parts.append(damage_report_count_label(damage_reports) + ".")
    elif photo_reviews:
        first = photo_reviews[0]
        photo_type = "cargo-safety photo" if "safety" in first["review_type"].lower() else "cargo photo"
        parts.append(f"One {first['plant']} {photo_type} requires manager classification.")
    else:
        parts.append("No formal damage report was filed.")
    return " ".join(parts)

def _manager_route_review_context(ctx):
    logs = ctx.get("logs") or []
    log_routes = ctx.get("log_routes") or {}
    route_finalized = bool(ctx.get("route_finalized"))
    stop_forecasts = ctx.get("stop_forecasts") or {}
    route_context = ctx.get("route_context")
    route_state = route_context.route_state if route_context else build_route_state(logs, log_routes, stop_forecasts, route_finalized)
    route_status = route_state["route_status"]
    all_departed = route_state["all_departed"]
    photo_reviews = _manager_photo_reviews(logs, log_routes)
    cargo_review = _manager_cargo_review(logs, log_routes, ctx.get("part_scan_events") or [], stop_forecasts)
    delay_review_rows = _manager_delay_review(logs, log_routes, stop_forecasts)
    next_load_prediction = ctx.get("next_load_prediction")
    damage_report_rows = _manager_damage_report_rows(ctx.get("damage_reports") or [])
    route_truck_context = ctx.get("route_truck_context") or _manager_route_truck_context(ctx["driver"].id, ctx["the_date"], ctx.get("pretrips") or [])
    mileage_review = ctx.get("mileage_review") or _manager_mileage_review(ctx.get("pretrips") or [], logs, route_truck_context)
    data_quality_items = _manager_data_quality(logs, log_routes, mileage_review["quality_item"], ctx.get("driver_signature"), route_finalized)
    approval_blockers = _manager_approval_blockers(data_quality_items, photo_reviews, cargo_review, route_finalized, logs, ctx.get("driver_signature"))
    required_actions = _manager_required_actions(data_quality_items, photo_reviews, cargo_review, route_finalized, logs, ctx.get("driver_signature"), delay_review_rows, next_load_prediction)
    review_status = _manager_review_status(required_actions, data_quality_items, photo_reviews, cargo_review, route_finalized, logs)
    manager_summary = _manager_summary_sentence(ctx["driver"], logs, log_routes, route_status, ctx.get("damage_reports") or [], photo_reviews, mileage_review.get("total_miles"), data_quality_items, approval_blockers, mileage_review, cargo_review, route_state, next_load_prediction)
    followup_cases = build_followup_cases(anchor=ctx["the_date"])
    current_log = route_state.get("current_activity", {}).get("log") if route_state.get("current_activity") else None
    route_truck = route_truck_context.get("label") if route_truck_context else ""
    manager_intelligence = []
    if current_log:
        manager_intelligence.extend(same_plant_intelligence(current_log, stop_forecasts.get(current_log.id), logs))
    manager_intelligence.extend(same_vehicle_intelligence(route_truck, followup_cases))
    return {
        **ctx,
        "review_status": review_status,
        "route_status": route_status,
        "route_state": route_state,
        "route_context": route_context,
        "manager_summary": (route_context.report_summary_sentence if route_context and route_context.current_stop else manager_summary),
        "required_actions": required_actions,
        "approval_blockers": approval_blockers,
        "approval_blocked": bool(approval_blockers),
        "approval_blocker_title": "Final Approval Not Yet Available" if route_status == "Active" else "Approval Blocked By",
        "data_quality_items": data_quality_items,
        "photo_reviews": photo_reviews,
        "damage_report_rows": damage_report_rows,
        "cargo_review": cargo_review,
        "next_load_prediction": next_load_prediction,
        "delay_review_rows": delay_review_rows,
        "truck_label": route_truck_context["label"],
        "route_truck_context": route_truck_context,
        "mileage_review": mileage_review,
        "followup_cases": followup_cases,
        "manager_intelligence": manager_intelligence,
    }


def _pdf_new_page_if_needed(pdf, y, min_y=90):
    if y < min_y:
        pdf.add_page()
        return 748
    return y


def _build_manager_route_review_pdf(review):
    meta = _manager_review_document_meta(review, page="1 of 2")
    pdf = SimplePdf("Manager Route Review", LETTER)
    _draw_pdf_header(
        pdf,
        "Manager Route Review",
        meta["document_no"],
        meta["generated_at"],
        meta["page"],
        driver=review["driver"].display_name,
        truck=review["truck_label"],
        date_value=review["the_date"],
    )
    y = 704
    pdf.text(36, y, f"Review Status: {review['review_status']}", size=11, bold=True)
    pdf.text(330, y, f"Mileage: {review['mileage_review']['label']}", size=9)
    y -= 22
    y = pdf.multiline_text(36, y, review["manager_summary"], width_chars=96, size=9, leading=11, max_lines=5)
    y -= 12

    current_activity = (review.get("route_state") or {}).get("current_activity")
    if current_activity:
        pdf.text(36, y, "Current Active Stop", size=11, bold=True)
        y -= 14
        y = pdf.multiline_text(44, y, f"Current Active Stop: {current_activity['plant']}. {current_activity['detail']} {current_activity['forecast_status']}", width_chars=92, size=8, leading=10, max_lines=2)
        prediction = review.get("next_load_prediction") or {}
        if prediction:
            y = pdf.multiline_text(44, y, f"{prediction.get('title')}: {prediction.get('predicted_load_label')}. Confidence: {prediction.get('confidence_label')}. Basis: {prediction.get('reason_text')}", width_chars=92, size=8, leading=10, max_lines=3)
            if prediction.get("delay_reason_required"):
                y = pdf.multiline_text(44, y, prediction.get("delay_reason_text"), width_chars=92, size=8, leading=10, max_lines=2, bold=True)
        y -= 12

    if review.get("approval_blockers"):
        pdf.text(36, y, review.get("approval_blocker_title") or "Approval Blocked By", size=11, bold=True, color=(176, 0, 32))
        y -= 14
        blocker_rows = [[item["label"], item["detail"]] for item in review["approval_blockers"]]
        y = pdf.table(36, y, [180, 360], 22, ["Blocker", "Detail"], blocker_rows[:6], font_size=7, header_gray=0.86)
        y -= 16

    y = _pdf_new_page_if_needed(pdf, y, 180)
    pdf.text(36, y, "3. Mileage Review", size=11, bold=True)
    y -= 14
    mileage_rows = [[review["mileage_review"]["status"], review["mileage_review"]["label"], review["mileage_review"]["detail"]]]
    y = pdf.table(36, y, [110, 130, 300], 22, ["Status", "Route Miles", "Detail"], mileage_rows, font_size=7)
    if review["mileage_review"].get("rows"):
        y -= 8
        odometer_rows = [[row["scope"], row["truck"], row["start"], row["end"], row["miles"], row["detail"]] for row in review["mileage_review"]["rows"][:6]]
        y = pdf.table(36, y, [80, 90, 80, 80, 80, 130], 22, ["Scope", "Truck", "Start", "End", "Miles", "Status"], odometer_rows, font_size=7)
    y -= 16

    y = _pdf_new_page_if_needed(pdf, y, 170)
    pdf.text(36, y, "4. Required Actions", size=11, bold=True)
    y -= 14
    for idx, action in enumerate(review["required_actions"], start=1):
        y = pdf.multiline_text(44, y, f"{idx}. {action}", width_chars=88, size=8, leading=10, max_lines=2)
    y -= 12

    y = _pdf_new_page_if_needed(pdf, y, 170)
    pdf.text(36, y, "5. Data Quality Review", size=11, bold=True)
    y -= 14
    quality_rows = [[item["label"], item["status"], item["detail"]] for item in review["data_quality_items"]] or [["Route", "Clean", "No data quality issues flagged."]]
    y = pdf.table(36, y, [110, 110, 320], 22, ["Check", "Status", "Detail"], quality_rows[:6], font_size=7)
    y -= 18

    y = _pdf_new_page_if_needed(pdf, y, 190)
    pdf.text(36, y, "6. Cargo / Manifest Review", size=11, bold=True)
    y -= 14
    cargo_rows = [[row["label"], row["value"], row["detail"]] for row in review["cargo_review"]["summary_rows"]]
    y = pdf.table(36, y, [125, 125, 290], 22, ["Audit", "Status", "Detail"], cargo_rows[:8], font_size=7)
    y -= 14
    if review["cargo_review"].get("pending_scan_rows"):
        y = _pdf_new_page_if_needed(pdf, y, 145)
        pdf.text(36, y, "Pending Scan Evidence", size=9, bold=True)
        y -= 12
        scan_rows = [[f"#{row['id']}", row["stop"], row["context"], row["status"], row["value"]] for row in review["cargo_review"]["pending_scan_rows"][:8]]
        y = pdf.table(36, y, [55, 135, 115, 115, 120], 20, ["Scan", "Stop", "Context", "Status", "Value"], scan_rows, font_size=7)
        y -= 14
    if review["cargo_review"].get("timing_rows"):
        y = _pdf_new_page_if_needed(pdf, y, 145)
        pdf.text(36, y, "Timing Intelligence", size=9, bold=True)
        y -= 12
        timing_rows = [[row["plant"], row["actual"], row["average"], row["status"]] for row in review["cargo_review"]["timing_rows"][:6]]
        y = pdf.table(36, y, [140, 120, 130, 150], 20, ["Stop", "Load / Dock", "Plant Avg", "Status"], timing_rows, font_size=7)
    y -= 18

    if review.get("photo_reviews") or review.get("damage_report_rows"):
        y = _pdf_new_page_if_needed(pdf, y, 260)
        pdf.text(36, y, "7. Photo Proof / Damage Review", size=11, bold=True)
        y -= 16
        if review.get("damage_report_rows"):
            damage_rows = [[f"#{row['id']}", row["type"], row["stop"], row["status"], row["photo_attached"], row["note"]] for row in review["damage_report_rows"][:5]]
            y = pdf.table(36, y, [45, 70, 105, 75, 55, 190], 22, ["Incident", "Type", "Stop", "Status", "Photo", "Driver note"], damage_rows, font_size=6)
            y -= 12
        for row in review["photo_reviews"][:3]:
            y = _pdf_new_page_if_needed(pdf, y, 230)
            photo_id = f"Photo ID #{row['photo_id']}" if row.get("photo_id") else "Photo ID unavailable"
            pdf.text(36, y, f"{row['plant']} - {row['review_type']} ({photo_id})", size=9, bold=True)
            y -= 12
            image_y = y - 78
            image_drawn = bool(row.get("photo_path")) and pdf.image_file(row["photo_path"], 36, image_y, 96, 72)
            if not image_drawn:
                pdf.rect(36, image_y, 96, 72)
                pdf.multiline_text(42, image_y + 46, "Photo record exists but file failed to render. Review in system before approval.", width_chars=22, size=6, leading=8, max_lines=4, bold=True)
            pdf.text(146, y, f"Uploaded: {row['uploaded_label']}", size=8, bold=True)
            pdf.multiline_text(146, y - 12, f"Driver note: {row['display_note'] or 'No driver note recorded.'}", width_chars=68, size=7, leading=9, max_lines=3)
            checks = "[ ] No issue   [ ] Cargo loading issue   [ ] Damage event   [ ] Safety concern"
            pdf.multiline_text(146, y - 44, checks, width_chars=78, size=7, leading=9, max_lines=2)
            pdf.text(146, y - 68, "[ ] Plant follow-up required   [ ] Driver coaching required", size=7)
            pdf.text(146, y - 86, "Manager notes:", size=7, bold=True)
            pdf.rect(146, y - 126, 390, 34)
            y -= 146
        y -= 4

    pdf.add_page()
    meta = _manager_review_document_meta(review, page="2 of 2")
    _draw_pdf_header(pdf, "Manager Route Review", meta["document_no"], meta["generated_at"], meta["page"], driver=review["driver"].display_name, truck=review["truck_label"], date_value=review["the_date"])
    y = 704
    pdf.text(36, y, "8. Route Detail Table", size=12, bold=True)
    y -= 14
    pdf.text(36, y, f"{len(review.get('logs') or [])} recorded stop event(s). Route records are listed below.", size=8)
    y -= 12
    route_rows = []
    for row in (review.get("route_state") or {}).get("rows", []):
        log = row["log"]
        route_rows.append([
            str(row["index"]),
            row["status"],
            row["plant"],
            _manager_time_label(log.arrive_time) or "--",
            _manager_time_label(log.depart_time) or "--",
            row["cargo_out"],
            row["note"],
        ])
    y = pdf.table(36, y, [30, 55, 95, 55, 55, 120, 130], 22, ["Stop #", "Status", "Plant", "Arrive", "Depart", "Cargo Out", "Notes"], route_rows[:18], font_size=6)
    y -= 18

    y = _pdf_new_page_if_needed(pdf, y, 185)
    pdf.text(36, y, "9. Signatures / Manager Decision", size=11, bold=True)
    y -= 14
    if review.get("approval_blocked"):
        pdf.text(44, y, "Approval unavailable until blocked items are resolved.", size=8, bold=True, color=(176, 0, 32))
        y -= 14
        decisions = [
            "[ ] Approve route - unavailable",
            "[ ] Return to driver for correction",
            "[ ] Manager review required",
            "[ ] Escalate to safety",
            "[ ] Escalate to maintenance",
            "[ ] Escalate to plant manager",
            "[ ] Mark as data-entry correction only",
        ]
    else:
        decisions = ["[ ] Approve route", "[ ] Return to driver for correction", "[ ] Escalate to safety", "[ ] Escalate to maintenance", "[ ] Escalate to plant manager", "[ ] Data-entry correction only"]
    for decision in decisions:
        color = (110, 110, 110) if "Approve route - unavailable" in decision else None
        pdf.text(44, y, decision, size=8, color=color)
        y -= 12
    y -= 6
    pdf.text(36, y, "Manager notes:", size=8, bold=True)
    pdf.rect(36, y - 48, 540, 42)
    y -= 70
    pdf.text(36, y, "Manager Signature", size=9, bold=True)
    pdf.line(36, y - 18, 270, y - 18)
    pdf.text(330, y, "Reviewed date/time", size=9, bold=True)
    pdf.line(330, y - 18, 576, y - 18)
    if review.get("driver_signature"):
        pdf.text(36, 42, "Driver e-signature captured", size=8)
    return pdf.build()

def _requested_url():
    return request.full_path if request.query_string else request.path


def _safe_manager_next(default_endpoint="manager.review_dashboard"):
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return url_for(default_endpoint)


@bp.before_request
def require_management_role():
    if restore_role_user("management"):
        return None
    flash("Manager credentials required.", "warning")
    return redirect(
        url_for(
            "auth.login",
            next=_requested_url(),
            required_role="management",
        )
    )


@bp.route("/")
def manager_root():
    return redirect(url_for("manager.manager_dashboard"))


def _dock_delay_minutes():
    return int(current_app.config.get("DOCK_DELAY_MINUTES", 30))


def _exception_url(item):
    target_type = item.get("target_type")
    target_id = item.get("target_id")
    if target_type == "plant_transfer":
        return url_for("manager.view_plant_transfer", transfer_id=target_id)
    if target_type == "driver_log":
        return url_for("manager.view_driver_log", log_id=target_id)
    if target_type == "task":
        return url_for("manager.manage_task", task_id=target_id)
    if target_type == "damage_report":
        return url_for("manager.view_damage_report", report_id=target_id)
    if target_type == "followup":
        return url_for("manager.review_dashboard")
    return None


def _with_exception_urls(items):
    rows = []
    for item in items:
        row = dict(item)
        row["url"] = _exception_url(item)
        row["review_key"] = _exception_key(item)
        rows.append(row)
    return rows


@bp.route("/review", methods=["GET", "POST"])
def review_dashboard():
    form = OperationalFollowUpForm()
    if form.validate_on_submit():
        followup = OperationalFollowUp(
            created_by_id=current_user.id,
            kind=form.kind.data,
            plant_name=form.plant_name.data or None,
            details=form.details.data,
        )
        db.session.add(followup)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="followup",
            action="created",
            title="Operational follow-up added",
            details=f"{followup.kind.replace('_', ' ').title()}: {followup.details}",
            target_type="followup",
            target_id=followup.id,
        )
        flash("Follow-up added.", "success")
        return redirect(url_for("manager.review_dashboard"))

    exceptions = _with_exception_urls(_active_exception_items())
    metrics = {
        "active_count": len(exceptions),
        "high_count": len([item for item in exceptions if item["severity"] == "high"]),
        "truck_damage_count": len([item for item in exceptions if item["category"] in {"Truck issue", "Damage flag"}]),
        "followup_count": len([item for item in exceptions if item["severity"] == "followup"]),
        "unassigned_issue_count": len([item for item in exceptions if item["severity"] != "followup" and item.get("category") in {"Truck issue", "Damage flag"}]),
    }
    followups = OperationalFollowUp.query.order_by(OperationalFollowUp.created_at.desc()).limit(20).all()
    damage_reports = DamageReport.query.order_by(DamageReport.created_at.desc()).limit(10).all()
    plant_forecasts = plant_forecast_rows(date.today())[:8]
    followup_cases = build_followup_cases(anchor=date.today())
    exception_history = (
        ActivityEvent.query.filter_by(category="exception")
        .order_by(ActivityEvent.created_at.desc())
        .limit(25)
        .all()
    )
    return render_template(
        "manager_review.html",
        form=form,
        exceptions=exceptions,
        metrics=metrics,
        followups=followups,
        damage_reports=damage_reports,
        plant_forecasts=plant_forecasts,
        followup_cases=followup_cases,
        exception_history=exception_history,
    )


@bp.route("/exceptions")
def exceptions_dashboard():
    return redirect(url_for("manager.review_dashboard"))


@bp.route("/exceptions/reviewed", methods=["POST"])
def mark_exception_reviewed():
    review_key = (request.form.get("review_key") or "").strip()
    target_type = (request.form.get("target_type") or "exception").strip()
    target_id = request.form.get("target_id", type=int)
    category = (request.form.get("category") or "Exception").strip()
    label = (request.form.get("label") or "Exception").strip()
    review_action = (request.form.get("review_action") or "reviewed").strip()
    if review_action not in {"reviewed", "deleted"}:
        review_action = "reviewed"
    if not review_key:
        flash("Exception review key missing.", "warning")
        return redirect(url_for("manager.review_dashboard"))

    if target_type == "followup" and target_id:
        followup = OperationalFollowUp.query.get(target_id)
        if followup:
            followup.status = "closed"
            followup.resolved_at = datetime.utcnow()

    record_activity(
        user_id=current_user.id,
        category="exception",
        action=review_action,
        title="Exception deleted" if review_action == "deleted" else "Exception reviewed",
        details=f"key:{review_key}; {category}: {label}",
        target_type=target_type,
        target_id=target_id,
    )
    db.session.commit()
    flash("Exception deleted from active review." if review_action == "deleted" else "Exception marked completed.", "success")
    return redirect(url_for("manager.review_dashboard"))


@bp.route("/followups/<int:followup_id>/close", methods=["POST"])
def close_followup(followup_id):
    followup = OperationalFollowUp.query.get_or_404(followup_id)
    followup.status = "closed"
    followup.resolved_at = datetime.utcnow()
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="followup",
        action="closed",
        title="Operational follow-up closed",
        details=followup.details,
        target_type="followup",
        target_id=followup.id,
    )
    flash("Follow-up closed.", "success")
    return redirect(url_for("manager.review_dashboard"))


def _pending_review_stop_ids():
    """Stop ids that a driver flagged for manager review and that have not yet
    been resolved.

    Mirrors the IN REVIEW contract in app/services/route_map.py: a stop is in
    review when it has a ``manager_review_requested`` ExceptionEvent and no
    matching ``manager_review_resolved`` ExceptionEvent for the same stop_id.
    """
    requested = {
        stop_id
        for (stop_id,) in ExceptionEvent.query.with_entities(ExceptionEvent.stop_id)
        .filter(
            ExceptionEvent.event_type == "manager_review_requested",
            ExceptionEvent.stop_id.isnot(None),
        )
        .all()
    }
    if not requested:
        return set()
    resolved = {
        stop_id
        for (stop_id,) in ExceptionEvent.query.with_entities(ExceptionEvent.stop_id)
        .filter(
            ExceptionEvent.event_type == "manager_review_resolved",
            ExceptionEvent.stop_id.in_(requested),
        )
        .all()
    }
    return requested - resolved


def _pending_review_rows():
    """Build display rows for every stop currently awaiting manager review.

    One row per pending stop, using the most recent ``manager_review_requested``
    event for that stop so the reason/requester reflect the latest flag.
    """
    pending_ids = _pending_review_stop_ids()
    if not pending_ids:
        return []
    requests = (
        ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_requested",
            ExceptionEvent.stop_id.in_(pending_ids),
        )
        .order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc())
        .all()
    )
    latest_by_stop = {}
    for event in requests:
        latest_by_stop.setdefault(event.stop_id, event)

    rows = []
    for stop_id, event in latest_by_stop.items():
        log = event.stop or DriverLog.query.get(stop_id)
        if log is None or log.deleted_at is not None:
            continue
        requester = event.driver or (log.driver if log else None)
        plant = _plant_label(log.plant_name)
        rows.append({
            "log": log,
            "log_id": log.id,
            "event": event,
            "plant": plant,
            "stop_label": f"{plant} - {log.date.isoformat() if log.date else 'no date'}",
            "reason": (event.details or "").strip() or event.summary or "Driver requested manager review",
            "requested_by": requester.display_name if requester else "Driver",
            "requested_at": event.created_at,
            "arrive_time": log.arrive_time or "--",
            "depart_time": log.depart_time or "--",
            "arrived_cargo": log.load_size or "--",
            "departed_cargo": log.depart_load_size or "--",
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })
    rows.sort(key=lambda row: row["requested_at"] or datetime.min, reverse=True)
    return rows


def _recent_driver_closeout_rows(limit=20):
    events = (
        ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_resolved",
            ExceptionEvent.summary == "Driver closed issue to continue",
        )
        .order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc())
        .limit(limit)
        .all()
    )
    rows = []
    for event in events:
        log = event.stop or DriverLog.query.get(event.stop_id)
        if log is None or log.deleted_at is not None:
            continue
        closer = event.driver or log.driver
        rows.append({
            "log": log,
            "log_id": log.id,
            "plant": _plant_label(log.plant_name),
            "closed_by": closer.display_name if closer else "Driver",
            "closed_at": event.created_at,
            "reason": (event.details or "").strip() or event.summary,
            "url": url_for("manager.view_driver_log", log_id=log.id),
        })
    return rows


def _pending_review_count():
    return len(_pending_review_stop_ids())


@bp.route("/reviews")
def review_queue():
    rows = _pending_review_rows()
    driver_closeouts = _recent_driver_closeout_rows()
    return render_template(
        "manager_reviews.html",
        review_rows=rows,
        driver_closeout_rows=driver_closeouts,
        pending_review_count=len(rows),
        today=date.today(),
    )


@bp.route("/reviews/<int:log_id>/resolve", methods=["POST"])
def resolve_review(log_id):
    if current_user.role != "management":
        flash("Manager credentials required.", "warning")
        return redirect(url_for("manager.review_queue"))
    log = DriverLog.query.get_or_404(log_id)
    db.session.add(ExceptionEvent(
        event_type="manager_review_resolved",
        severity="medium",
        stop_id=log_id,
        driver_log_id=log_id,
        driver_id=current_user.id,
        plant_name=getattr(log, "plant_name", None),
        event_date=getattr(log, "date", None),
        summary="Manager resolved review",
        details=(request.form.get("note") or "").strip() or None,
    ))
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="exception",
        action="reviewed",
        title="Manager review resolved",
        details=f"Resolved manager review for stop #{log_id} ({_plant_label(log.plant_name)}).",
        target_type="driver_log",
        target_id=log_id,
    )
    flash("Stop review resolved.", "success")
    return redirect(url_for("manager.review_queue"))


@bp.route("/damage-photos/<int:photo_id>")
def damage_photo(photo_id):
    photo = DamagePhoto.query.get_or_404(photo_id)
    upload_root = current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    return send_from_directory(upload_path, photo.filename)


@bp.route("/hot-part-photos/<int:photo_id>")
def hot_part_photo(photo_id):
    photo = HotPartPhoto.query.get_or_404(photo_id)
    upload_root = current_app.config.get("HOT_PART_UPLOAD_FOLDER", "uploads/hot_part_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    return send_from_directory(upload_path, photo.filename)


@bp.route("/driver-log-photos/<int:photo_id>")
def driver_log_photo(photo_id):
    photo = DriverLogPhoto.query.get_or_404(photo_id)
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    return send_from_directory(upload_path, photo.filename)


def _delete_driver_log_photo_file(photo):
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, photo.filename))
    try:
        if os.path.exists(upload_path):
            os.remove(upload_path)
    except OSError:
        current_app.logger.warning("Unable to remove driver log photo %s", upload_path, exc_info=True)


@bp.route("/driver-log-photos/<int:photo_id>/delete", methods=["POST"], strict_slashes=False)
def delete_driver_log_photo(photo_id):
    photo = DriverLogPhoto.query.get_or_404(photo_id)
    log = photo.log
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
        target_id=log.id if log else None,
        commit=False,
    )
    db.session.delete(photo)
    db.session.commit()
    flash("Stop photo proof deleted.", "success")
    return redirect(request.form.get("next") or (url_for("manager.view_driver_log", log_id=log.id) if log else url_for("manager.driver_logs")))


@bp.route("/damage-reports/<int:report_id>")
def view_damage_report(report_id):
    report = DamageReport.query.get_or_404(report_id)
    return render_template("view_damage_report.html", report=report, manager_view=True)


@bp.route("/damage-reports/<int:report_id>/delete", methods=["POST"])
def delete_damage_report(report_id):
    report = DamageReport.query.get_or_404(report_id)
    before = model_snapshot(
        report,
        [
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
        ],
    )
    before["photos"] = [photo.filename for photo in report.photos]
    record_audit_event(
        user_id=current_user.id,
        target_type="damage_report",
        target_id=report.id,
        action="manager_deleted",
        reason="Manager deleted damage report from review cleanup.",
        before_values=before,
        after_values={"deleted": True},
        commit=False,
    )
    record_activity(
        user_id=current_user.id,
        category="damage",
        action="deleted",
        title="Damage report deleted by manager",
        details=f"Damage report #{report.id} deleted for {report.plant_name}.",
        target_type="damage_report",
        target_id=report.id,
        commit=False,
    )
    db.session.delete(report)
    db.session.commit()
    flash("Damage report deleted.", "success")
    return redirect(_safe_manager_next())


@bp.route("/damage-reports/<int:report_id>/evidence-packet")
def damage_evidence_packet(report_id):
    report = DamageReport.query.get_or_404(report_id)
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
        manager_view=True,
        document_meta=_evidence_document_meta(report, page="1 of 5"),
        back_url=url_for("manager.view_damage_report", report_id=report.id),
    )


@bp.route("/audit-history")
def audit_history():
    audit_events = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(100).all()
    return render_template("audit_history.html", audit_events=audit_events)


@bp.route("/search/suggest")
def search_suggest():
    query = (request.args.get("q") or "").strip()
    plant = (request.args.get("plant") or "").strip()
    context_key = f"plant:{plant}" if plant else None
    return jsonify({"results": suggest_terms(query, context_key=context_key, limit=10)})


@bp.route("/dispatch-captures", methods=["POST"])
def create_dispatch_capture_route():
    data = request.get_json(silent=True) if request.is_json else request.form
    raw_text = (data.get("raw_text") if data else "") or ""
    capture_type = (data.get("capture_type") if data else "") or ""
    source = (data.get("source") if data else "") or "manager_dashboard"
    if not raw_text.strip():
        if request.is_json:
            return jsonify({"ok": False, "error": "raw_text is required"}), 400
        flash("Paste or type the dispatch message first.", "warning")
        return redirect(url_for("manager.manager_dashboard"))

    capture = create_dispatch_capture(
        raw_text=raw_text,
        capture_type=capture_type,
        source=source,
        user=current_user,
    )
    if request.is_json:
        return jsonify({"ok": True, "capture_id": capture.id, "status": capture.status})
    flash("Dispatch capture saved.", "success")
    return redirect(url_for("manager.manager_dashboard", focus="jobs"))


@bp.route("/dispatch-captures/<int:capture_id>/convert", methods=["POST"])
def convert_dispatch_capture_route(capture_id):
    capture = DispatchCapture.query.get_or_404(capture_id)
    if capture.status not in {"captured", "needs_triage"}:
        flash("That dispatch capture is already closed.", "info")
        return redirect(url_for("manager.manager_dashboard", focus="jobs"))
    entity_type = request.form.get("entity_type") or "move_request"
    converted = convert_dispatch_capture(capture, entity_type=entity_type, user=current_user)
    flash(f"{capture.display_number} converted to {capture.converted_entity_type} #{converted.id}.", "success")
    return redirect(url_for("manager.manager_dashboard", focus="jobs"))


@bp.route("/dispatch-captures/<int:capture_id>/dismiss", methods=["POST"])
def dismiss_dispatch_capture_route(capture_id):
    capture = DispatchCapture.query.get_or_404(capture_id)
    if capture.status in {"captured", "needs_triage"}:
        dismiss_dispatch_capture(capture, user=current_user)
        flash(f"{capture.display_number} dismissed.", "info")
    return redirect(url_for("manager.manager_dashboard", focus="jobs"))


@bp.route("/dashboard", methods=["GET", "POST"])
def manager_dashboard():
    create_task_form = TaskForm()
    drivers = _populate_task_driver_choices(create_task_form)
    today = date.today()
    division_filter = request.args.get("division", "All")
    if division_filter not in {"All", "Plastics", "Trim"}:
        division_filter = "All"
    selected_driver_id = request.args.get("driver_id", type=int)
    selected_plant = (request.args.get("plant") or "").strip() or None
    focus_panel = request.args.get("focus", "jobs")
    if focus_panel not in {"jobs", "routes"}:
        focus_panel = "jobs"

    day_start = datetime.combine(today, datetime.min.time())
    uncompleted_tasks = (
        Task.query.filter(or_(Task.status != "completed", Task.completed_at >= day_start))
        .order_by(Task.created_at.desc())
        .all()
    )
    todays_transfers = (
        _active_plant_transfers_query().filter_by(transfer_date=today)
        .order_by(PlantTransfer.created_at.desc())
        .all()
    )
    todays_logs = _active_driver_logs_query().filter_by(date=today).all()
    live_logs = [log for log in todays_logs if not selected_driver_id or log.driver_id == selected_driver_id]
    live_stop_rows = _live_stop_rows(live_logs)

    dispatch_rows = _build_dispatch_rows(uncompleted_tasks, todays_transfers)
    if division_filter != "All":
        dispatch_rows = [row for row in dispatch_rows if row["division"] == division_filter]
    dispatch_capture_rows = open_dispatch_captures()
    dispatch_capture_count = len(dispatch_capture_rows)

    reported_delay_count = len([log for log in todays_logs if (log.dock_wait_minutes or 0) > 0])
    critical_exceptions = _critical_exception_rows(live_stop_rows, live_logs)
    followup_cases = build_followup_cases(anchor=today)
    live_problem_count = len(critical_exceptions)
    review_rows = _pending_review_rows()
    pending_review_count = len(review_rows)

    active_driver_ids = {log.driver_id for log in todays_logs}
    active_drivers = [driver for driver in drivers if driver.id in active_driver_ids]
    floor = build_floor_operations_snapshot(today)
    production_flow = build_production_flow_context(
        date=today,
        mode="admin",
        selected_plant=selected_plant,
        driver_id=selected_driver_id,
        can_edit=True,
        can_assign=True,
        can_review=True,
        can_export=True,
    )
    if floor and floor.get("queue_summary") is not None:
        floor["queue_summary"]["captured_requests"] = dispatch_capture_count
    if production_flow is not None:
        production_flow["dispatch_capture_count"] = dispatch_capture_count
    return render_template(
        "manager_dashboard.html",
        create_task_form=create_task_form,
        floor=floor,
        production_flow=production_flow,
        dispatch_capture_rows=dispatch_capture_rows,
        dispatch_capture_count=dispatch_capture_count,
        selected_plant=selected_plant,
        uncompleted_tasks=uncompleted_tasks,
        dispatch_rows=dispatch_rows,
        live_stop_rows=live_stop_rows,
        selected_driver_id=selected_driver_id,
        focus_panel=focus_panel,
        drivers=drivers,
        division_filter=division_filter,
        total_active_moves=len(uncompleted_tasks) + len(todays_transfers),
        active_driver_count=len(active_drivers),
        reported_delay_count=reported_delay_count,
        live_problem_count=live_problem_count,
        critical_exceptions=critical_exceptions,
        review_rows=review_rows,
        pending_review_count=pending_review_count,
        followup_cases=followup_cases,
        plant_forecasts=plant_forecast_rows(today)[:6],
        has_drivers=bool(drivers),
        today=today,
        database_status=database_status(current_app.config.get("SQLALCHEMY_DATABASE_URI", "")),
    )


@bp.route("/trim")
@bp.route("/trim-dashboard")
def trim_dashboard():
    flash("Trim dashboard was removed; use Live Dispatch filters instead.", "info")
    return redirect(url_for("manager.manager_dashboard"))


@bp.route("/driver-logs", methods=["GET"])
def driver_logs():
    date_str = request.args.get("date")
    try:
        search_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        )
    except ValueError:
        search_date = date.today()

    all_drivers = User.query.filter_by(role="driver").order_by(
        User.last_name, User.first_name, User.username
    ).all()
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
        today_local_date=date.today(),
    )


@bp.route("/driver-logs/route-print")
def driver_route_print():
    driver_id = request.args.get("driver_id", type=int)
    if not driver_id:
        flash("Choose a driver before printing the full route.", "warning")
        return redirect(url_for("manager.driver_logs", date=request.args.get("date") or date.today().isoformat()))
    try:
        route_date = datetime.strptime(request.args.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        route_date = date.today()
    ctx = _manager_route_review_context(_route_print_context(driver_id, route_date))
    return render_template(
        "manager_route_review.html",
        **ctx,
        document_meta=_manager_review_document_meta(ctx),
        attachment_url=url_for("manager.driver_route_attachment", driver_id=driver_id, date=route_date.isoformat()),
        csv_url=url_for("manager.driver_route_export", driver_id=driver_id, date=route_date.isoformat(), type="csv"),
        sheets_url=url_for("manager.driver_route_export", driver_id=driver_id, date=route_date.isoformat(), type="sheets"),
        email_mode=False,
    )


@bp.route("/driver-logs/route-attachment")
def driver_route_attachment():
    driver_id = request.args.get("driver_id", type=int)
    if not driver_id:
        flash("Choose a driver before downloading the route PDF.", "warning")
        return redirect(url_for("manager.driver_logs"))
    try:
        route_date = datetime.strptime(request.args.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        route_date = date.today()
    ctx = _manager_route_review_context(_route_print_context(driver_id, route_date))
    return _document_attachment_response(
        pdf_bytes=_build_manager_route_review_pdf(ctx),
        filename=f"manager-route-review-{driver_id}-{route_date}.pdf",
        target_type="driver_log",
        title="Manager Route Review PDF downloaded",
    )


@bp.route("/driver-logs/route-export")
def driver_route_export():
    driver_id = request.args.get("driver_id", type=int)
    if not driver_id:
        flash("Choose a driver before exporting the route.", "warning")
        return redirect(url_for("manager.driver_logs"))
    try:
        route_date = datetime.strptime(request.args.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        route_date = date.today()
    export_type = request.args.get("type", "csv")
    ctx = _route_print_context(driver_id, route_date)
    if export_type == "sheets":
        return _route_export_response(
            ctx,
            filename=f"driver-route-{driver_id}-{route_date}-sheets.tsv",
            delimiter="\t",
            content_type="text/tab-separated-values; charset=utf-8",
            title="Manager Driver Route Sheets export downloaded",
        )
    return _route_export_response(
        ctx,
        filename=f"driver-route-{driver_id}-{route_date}.csv",
        delimiter=",",
        content_type="text/csv; charset=utf-8",
        title="Manager Driver Route CSV downloaded",
    )


@bp.route("/driver-logs/<int:log_id>")
def view_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    day_logs = (
        _active_driver_logs_query()
        .filter_by(driver_id=log.driver_id, date=log.date)
        .order_by(DriverLog.created_at.asc())
        .all()
    )
    related_task = _related_task_for_log(log)
    day_log_positions = {day_log.id: index + 1 for index, day_log in enumerate(day_logs)}
    stop_position = day_log_positions.get(log.id)

    # Damage reports linked to this log or reported by this driver on this date
    damage_reports = (
        DamageReport.query
        .filter(
            db.or_(
                DamageReport.driver_log_id == log.id,
                db.and_(
                    DamageReport.reported_by_id == log.driver_id,
                    DamageReport.driver_log_id.is_(None),
                    db.func.date(DamageReport.created_at) == log.date,
                )
            )
        )
        .order_by(DamageReport.created_at.desc())
        .all()
    )

    # Delay detail: only stops where the driver recorded a wait or downtime reason.
    delay_logs = [dl for dl in day_logs if (dl.dock_wait_minutes or 0) > 0 or dl.downtime_reason]
    has_reported_delay = bool(delay_logs)
    route_finalized = ActivityEvent.query.filter_by(
        user_id=log.driver_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(log.date))).first() is not None

    all_routes = _driver_log_route_context(day_logs)
    truck_context = _truck_context_for_driver(log.driver_id, log.date)
    part_scan_events = _part_scan_events_for_logs(day_logs)
    driver_log_photos = []
    if day_logs:
        driver_log_photos = (
            DriverLogPhoto.query
            .filter(DriverLogPhoto.driver_log_id.in_([day_log.id for day_log in day_logs]))
            .order_by(DriverLogPhoto.uploaded_at.asc(), DriverLogPhoto.id.asc())
            .all()
        )
    hot_part_proof = build_route_hot_part_proof(day_logs, related_task)
    issue_closeout = (
        ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_resolved",
            ExceptionEvent.stop_id == log.id,
        )
        .order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc())
        .first()
    )
    management_narrative = build_management_narrative(
        {
            "log": log,
            "day_logs": day_logs,
            "log_routes": all_routes,
            "delay_logs": delay_logs,
            "damage_reports": damage_reports,
            "truck_context": truck_context,
            "related_task": related_task,
            "part_scan_events": part_scan_events,
            "driver_log_photos": driver_log_photos,
            "hot_part_proof": hot_part_proof,
            "route_finalized": route_finalized,
        }
    )
    return render_template(
        "view_driver_log.html",
        log=log,
        log_route=all_routes.get(log.id),
        log_routes=all_routes,
        truck_context=truck_context,
        related_task=related_task,
        stop_position=stop_position,
        stop_count=len(day_logs),
        today_local_date=date.today(),
        damage_reports=damage_reports,
        delay_logs=delay_logs,
        has_reported_delay=has_reported_delay,
        day_logs=day_logs,
        day_log_positions=day_log_positions,
        management_narrative=management_narrative,
        part_scan_events=part_scan_events,
        hot_part_proof=hot_part_proof,
        driver_log_photos=driver_log_photos,
        issue_closeout=issue_closeout,
    )


@bp.route("/pretrips")
def list_pretrips():
    pretrips = _active_pretrips_query().order_by(PreTrip.created_at.desc()).all()
    return render_template(
        "list_pretrips.html", pretrips=pretrips, today_local_date=date.today()
    )


@bp.route("/pretrips/<int:pretrip_id>")
def view_pretrip(pretrip_id):
    pretrip = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    return render_template(
        "view_pretrip.html",
        pretrip=pretrip,
        readonly=True,
        today_local_date=date.today(),
        pretrip_damage_reports=_pretrip_damage_reports(pretrip),
        document_meta=_pretrip_document_meta(pretrip),
    )


@bp.route("/pretrips/<int:pretrip_id>/print")
def pretrip_printable(pretrip_id):
    pretrip = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    return render_template(
        "pretrip_printable.html",
        pretrip=pretrip,
        ephemeral_driver=None,
        ephemeral_date=None,
        email_mode=False,
        pretrip_damage_reports=_pretrip_damage_reports(pretrip),
        document_meta=_pretrip_document_meta(pretrip),
    )


@bp.route("/pretrips/<int:pretrip_id>/attachment")
def pretrip_attachment(pretrip_id):
    pretrip = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    return _document_attachment_response(
        pdf_bytes=_build_pretrip_pdf(pretrip),
        filename=f"pretrip-{pretrip.id}.pdf",
        target_type="pretrip",
        target_id=pretrip.id,
        title="Manager PreTrip PDF downloaded",
    )


@bp.route("/pretrips/<int:pretrip_id>/mark_printed", methods=["POST"])
def mark_pretrip_printed(pretrip_id):
    pretrip = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    record_activity(
        user_id=current_user.id,
        category="print",
        action="manager_pretrip_printed",
        title="Manager PreTrip printed",
        details=f"Printed DVIR for truck {pretrip.truck_number or 'unlisted'}.",
        target_type="pretrip",
        target_id=pretrip.id,
    )
    return jsonify({"ok": True})


@bp.route("/plant-transfers")
def plant_transfers():
    transfers = _active_plant_transfers_query().order_by(
        PlantTransfer.created_at.desc()
    ).all()
    return render_template(
        "plant_transfers.html", transfers=transfers, today_local_date=date.today()
    )


@bp.route("/plant-transfers/<int:transfer_id>")
def view_plant_transfer(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    return render_template(
        "view_plant_transfer.html", transfer=transfer, today_local_date=date.today()
    )


@bp.route("/plant-transfers/<int:transfer_id>/print")
def plant_transfer_printable(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    lines_by_number = {line.line_number: line for line in transfer.lines}
    print_rows = [
        (lines_by_number.get(i + 1), lines_by_number.get(i + 11)) for i in range(10)
    ]
    requested_copy = request.args.get("copy", "pink").lower()
    all_copy_sets, copy_sets, requested_copy = _plant_transfer_copy_sets(requested_copy)
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


@bp.route("/plant-transfers/<int:transfer_id>/attachment")
def plant_transfer_attachment(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    requested_copy = request.args.get("copy", "pink")
    pdf_bytes, requested_copy = _build_plant_transfer_pdf(transfer, requested_copy)
    return _document_attachment_response(
        pdf_bytes=pdf_bytes,
        filename=f"plant-transfer-{transfer.transfer_number or transfer.id}-{requested_copy}.pdf",
        target_type="plant_transfer",
        target_id=transfer.id,
        title="Manager Plant Transfer PDF downloaded",
    )


@bp.route("/plant-transfers/<int:transfer_id>/mark_printed", methods=["POST"])
def mark_plant_transfer_printed(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    record_activity(
        user_id=current_user.id,
        category="print",
        action="manager_plant_transfer_printed",
        title="Manager Plant Transfer printed",
        details=(
            f"{transfer.ship_from} to {transfer.ship_to}; "
            f"copy: {request.args.get('copy', 'selected')}."
        ),
        target_type="plant_transfer",
        target_id=transfer.id,
    )
    return jsonify({"ok": True})


@bp.route("/tasks/<int:task_id>", methods=["GET", "POST"])
def manage_task(task_id):
    task = Task.query.get_or_404(task_id)
    drivers = User.query.filter_by(role="driver").order_by(
        User.last_name, User.first_name, User.username
    ).all()
    statuses = ["pending", "in-progress", "completed", "declined"]
    shifts = ["1st", "2nd", "3rd"]

    if request.method == "POST":
        assigned_to = request.form.get("assigned_to", "0")
        try:
            assigned_id = int(assigned_to)
        except ValueError:
            assigned_id = 0
        task.assigned_to = assigned_id or None

        status = request.form.get("status", task.status)
        task_completed_now = False
        if status in statuses:
            previous_status = task.status
            task.status = status
            if status == "completed" and previous_status != "completed":
                task.completed_at = datetime.utcnow()
                task.completed_by_id = current_user.id
                task_completed_now = True
            elif status != "completed":
                task.completed_at = None
                task.completed_by_id = None

        shift = request.form.get("shift", task.shift)
        if shift in shifts:
            task.shift = shift

        task.details = request.form.get("details", "").strip()
        task.part_number = request.form.get("part_number", "").strip() or None
        task.is_hot = bool(request.form.get("is_hot"))
        if task.is_hot:
            ensure_hot_move_for_task(task, driver_id=task.assigned_to, created_by_id=current_user.id, source="dispatch")
        db.session.commit()

        assigned_driver = User.query.get(task.assigned_to) if task.assigned_to else None
        assigned_label = assigned_driver.manager_label if assigned_driver else "Unassigned"
        record_activity(
            user_id=current_user.id,
            category="task",
            action="completed" if task_completed_now else "managed",
            title="Assignment completed by manager" if task_completed_now else "Task updated by manager",
            details=f"{task.title}; status {task.status}; assigned to {assigned_label}.",
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
        flash("Move updated.", "success")
        return redirect(url_for("manager.manage_task", task_id=task.id))

    related_logs = []
    if task.assigned_to:
        related_logs = (
            _active_driver_logs_query().filter_by(driver_id=task.assigned_to)
            .order_by(DriverLog.created_at.desc())
            .limit(5)
            .all()
        )

    return render_template(
        "manager_task_detail.html",
        task=task,
        drivers=drivers,
        statuses=statuses,
        shifts=shifts,
        division=_division_for_user(task.assigned_user)
        if task.assigned_user
        else _division_for_text(task.title, task.details),
        related_logs=related_logs,
        truck_context=_truck_context_for_driver(task.assigned_to, date.today()) if task.assigned_to else None,
    )


@bp.route("/create_task_from_dashboard", methods=["POST"])
def create_task_from_dashboard():
    form = TaskForm()
    drivers = _populate_task_driver_choices(form)
    if form.validate_on_submit():
        assigned_driver = None
        if form.assigned_to.data:
            assigned_driver = User.query.filter_by(id=form.assigned_to.data, role="driver").first()
            if not assigned_driver:
                flash("Select a valid driver for this task or choose Open for any driver.", "danger")
                return redirect(url_for("manager.manager_dashboard"))

        route_from = (form.route_from.data or "").strip()
        route_to = (form.route_to.data or "").strip()
        summary = (form.title.data or "").strip()
        details = (form.details.data or "").strip()
        part_number = (form.part_number.data or "").strip()

        if bool(route_from) != bool(route_to):
            flash("Select both From Plant and To Plant, or leave both blank.", "danger")
            return redirect(url_for("manager.manager_dashboard"))
        if route_from and route_to:
            task_title = f"{route_from} to {route_to}"
        elif summary:
            task_title = summary
        elif part_number:
            task_title = f"Part {part_number}"
        else:
            flash("Add a route, part number, or move note before dispatching.", "danger")
            return redirect(url_for("manager.manager_dashboard"))

        if route_from and route_to and summary:
            details = f"{summary}\n{details}" if details else summary

        new_task = Task(
            title=task_title,
            details=details,
            part_number=part_number or None,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=assigned_driver.id if assigned_driver else None,
            status="pending",
        )
        db.session.add(new_task)
        db.session.flush()
        if new_task.is_hot:
            ensure_hot_move_for_task(new_task, created_by_id=current_user.id, source="dispatch")
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="task",
            action="assigned",
            title="Task assigned",
            details=f"{new_task.title} assigned to {assigned_driver.manager_label if assigned_driver else 'Open for any driver'}.",
            target_type="task",
            target_id=new_task.id,
        )
        socketio.emit(
            "task_assigned",
            {
                "task_id": new_task.id,
                "title": new_task.title,
                "assigned_driver_id": assigned_driver.id if assigned_driver else None,
            },
        )
        flash(f"Task posted to {assigned_driver.manager_label if assigned_driver else 'Open for any driver'}.", "success")
    else:
        flash("Failed to create task. Check form input.", "danger")

    return redirect(url_for("manager.manager_dashboard"))
