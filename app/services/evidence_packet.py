import hashlib
from datetime import datetime
from pathlib import Path

import pytz
from flask import current_app, url_for

from app.extensions import db
from app.models import ActivityEvent, AuditEvent, DriverLog, PlantTransfer, PreTrip, ShiftRecord, Task
from app.services.load_state import (
    build_driver_log_route_context,
    route_problem_reason,
    secondary_not_dropped_reason,
    truck_issue_reason,
)
from app.services.packet_classification import classify_damage_report
from app.services.plant_addresses import plant_label


DETROIT_TZ = pytz.timezone("America/Detroit")
UTC_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def _coerce_utc(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return pytz.utc.localize(value) if value.tzinfo is None else value.astimezone(pytz.utc)
    if isinstance(value, str):
        for fmt in UTC_FORMATS:
            try:
                return pytz.utc.localize(datetime.strptime(value, fmt))
            except ValueError:
                continue
    return None


def _local_dt(value):
    dt_utc = _coerce_utc(value)
    return dt_utc.astimezone(DETROIT_TZ) if dt_utc else None


def _label_dt(value):
    dt = value if isinstance(value, datetime) and value.tzinfo else _local_dt(value)
    if not dt:
        return "Time not recorded"
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt).astimezone(DETROIT_TZ)
    return dt.strftime("%Y-%m-%d %I:%M%p %Z").replace(" 0", " ").lower()


def _label_time(value):
    dt = _local_dt(value)
    if dt:
        return dt.strftime("%I:%M%p").lower().lstrip("0")
    value = (value or "").strip()
    if not value:
        return "--"
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            return datetime.strptime(value, fmt).strftime("%I:%M%p").lower().lstrip("0")
        except ValueError:
            continue
    return value


def _report_date(report):
    stamp = report.damage_time or report.created_at or datetime.utcnow()
    dt = _local_dt(stamp)
    return dt.date() if dt else stamp.date()


def route_finalized_for_report(report):
    report_date = _report_date(report)
    return ActivityEvent.query.filter_by(
        user_id=report.reported_by_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(report_date))).first() is not None


def _driver_can_edit(report):
    return report.status == "open" and not route_finalized_for_report(report)


def _upload_path(filename):
    upload_root = Path(current_app.config.get("DAMAGE_UPLOAD_FOLDER", "uploads/damage_photos"))
    if not upload_root.is_absolute():
        upload_root = Path(current_app.root_path).parent / upload_root
    return upload_root / filename


def _file_hash(path):
    if not path.exists():
        return "Missing file"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _activity_conditions(target_pairs):
    conditions = []
    for target_type, target_id in target_pairs:
        if target_id is not None:
            conditions.append(db.and_(ActivityEvent.target_type == target_type, ActivityEvent.target_id == target_id))
    return conditions


def _audit_conditions(target_pairs):
    conditions = []
    for target_type, target_id in target_pairs:
        if target_id is not None:
            conditions.append(db.and_(AuditEvent.target_type == target_type, AuditEvent.target_id == target_id))
    return conditions


def _event(stamp, event, user, source, detail=""):
    local = _local_dt(stamp) if not (isinstance(stamp, datetime) and stamp.tzinfo) else stamp.astimezone(DETROIT_TZ)
    return {
        "sort_time": local or DETROIT_TZ.localize(datetime.max.replace(year=2999)),
        "time": _label_dt(local) if local else "Time not recorded",
        "event": event,
        "user": user or "System",
        "source": source,
        "detail": detail,
    }


def _related_records(report):
    report_date = _report_date(report)
    logs = (
        DriverLog.query.filter(
            DriverLog.deleted_at.is_(None),
            DriverLog.driver_id == report.reported_by_id,
            DriverLog.date == report_date,
        )
        .order_by(DriverLog.created_at.asc(), DriverLog.id.asc())
        .all()
    )
    if report.driver_log and report.driver_log not in logs:
        logs.append(report.driver_log)
    pretrips = (
        PreTrip.query.filter(
            PreTrip.deleted_at.is_(None),
            PreTrip.user_id == report.reported_by_id,
            PreTrip.pretrip_date == report_date,
        )
        .order_by(PreTrip.created_at.asc(), PreTrip.id.asc())
        .all()
    )
    transfers = (
        PlantTransfer.query.filter(
            PlantTransfer.deleted_at.is_(None),
            PlantTransfer.user_id == report.reported_by_id,
            PlantTransfer.transfer_date == report_date,
        )
        .order_by(PlantTransfer.created_at.asc(), PlantTransfer.id.asc())
        .all()
    )
    tasks = []
    if report.task_id:
        task = Task.query.get(report.task_id)
        if task:
            tasks.append(task)
    return report_date, logs, pretrips, transfers, tasks


def _shift_signature(driver_id, report_date):
    by_pretrip = (
        ShiftRecord.query.join(PreTrip, ShiftRecord.pretrip_id == PreTrip.id)
        .filter(
            ShiftRecord.user_id == driver_id,
            ShiftRecord.driver_signature.isnot(None),
            PreTrip.pretrip_date == report_date,
        )
        .order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc())
        .first()
    )
    if by_pretrip:
        return by_pretrip
    shifts = (
        ShiftRecord.query.filter(ShiftRecord.user_id == driver_id, ShiftRecord.driver_signature.isnot(None))
        .order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc())
        .limit(50)
        .all()
    )
    for shift in shifts:
        local_start = _local_dt(shift.start_time)
        if local_start and local_start.date() == report_date:
            return shift
    return None


def _photo_rows(report):
    rows = []
    for index, photo in enumerate(report.photos, 1):
        path = _upload_path(photo.filename)
        rows.append(
            {
                "number": index,
                "photo": photo,
                "url": url_for("manager.damage_photo", photo_id=photo.id),
                "stage": photo.stage or report.stage,
                "uploaded_by": report.reported_by.display_name if report.reported_by else "Driver",
                "uploaded_at": _label_dt(photo.uploaded_at),
                "related_truck": report.truck_number or "Not set",
                "related_trailer": report.trailer_number or "Not set",
                "related_move": report.move_reference or "Not linked",
                "filename": photo.original_filename or photo.filename,
                "stored_filename": photo.filename,
                "content_type": photo.content_type or "Not recorded",
                "hash": photo.sha256_hash or _file_hash(path),
                "file_exists": path.exists(),
                "file_status": "Available" if path.exists() else "Photo not available in upload storage",
                "driver_note": report.description,
                "manager_note": "No manager photo note recorded",
            }
        )
    return rows


def _timeline(report, logs, pretrips, transfers, tasks, signature_shift):
    events = [
        _event(
            report.created_at,
            "Report created",
            report.reported_by.display_name if report.reported_by else "Driver",
            "Driver report",
            report.description,
        )
    ]
    if report.damage_time and report.damage_time != report.created_at:
        events.append(_event(report.damage_time, "Report time", report.reported_by.display_name if report.reported_by else "Driver", "Driver entry"))
    for photo in report.photos:
        events.append(_event(photo.uploaded_at, "Photo uploaded", report.reported_by.display_name if report.reported_by else "Driver", "Mobile report photo", photo.original_filename or photo.filename))
    for pretrip in pretrips:
        events.append(_event(pretrip.created_at, "PreTrip DVIR created", report.reported_by.display_name if report.reported_by else "Driver", "DVIR", f"Truck {pretrip.truck_number or 'not set'} / trailer {pretrip.trailer_number or 'not set'}"))
    routes = build_driver_log_route_context(logs)
    for index, log in enumerate(logs, 1):
        route = routes.get(log.id, {})
        plant = route.get("plant") or plant_label(log.plant_name)
        events.append(_event(log.arrive_time, f"Stop #{index} arrival", log.driver.display_name if log.driver else "Driver", "Route workflow", plant))
        if log.depart_time:
            try:
                depart_stamp = DETROIT_TZ.localize(datetime.combine(log.date, datetime.strptime(log.depart_time, "%H:%M").time()))
            except ValueError:
                depart_stamp = log.created_at
            events.append(_event(depart_stamp, f"Stop #{index} departure", log.driver.display_name if log.driver else "Driver", "Route workflow", route.get("depart_cargo_desc") or log.depart_load_size or "Cargo not recorded"))
    for transfer in transfers:
        events.append(_event(transfer.created_at, "Plant transfer paperwork created", transfer.driver.display_name if transfer.driver else "Driver", "Plant transfer", f"{transfer.ship_from} to {transfer.ship_to}; trailer {transfer.trailer_number or 'not set'}"))
    for task in tasks:
        events.append(_event(task.created_at, "Related task created", "Dispatch", "Task", task.title))
        if task.accepted_at:
            events.append(_event(task.accepted_at, "Task accepted", task.accepted_by.display_name if task.accepted_by else "Driver", "Task", task.title))
        if task.completed_at:
            events.append(_event(task.completed_at, "Task completed", task.completed_by.display_name if task.completed_by else "Driver", "Task", task.title))
    if signature_shift and signature_shift.signature_timestamp:
        events.append(_event(signature_shift.signature_timestamp, "Driver signature captured", signature_shift.user.display_name if signature_shift.user else "Driver", "End-of-day route signature"))

    target_pairs = [("damage_report", report.id)]
    target_pairs.extend(("driver_log", log.id) for log in logs)
    target_pairs.extend(("plant_transfer", transfer.id) for transfer in transfers)
    activity_conditions = _activity_conditions(target_pairs)
    if activity_conditions:
        activities = ActivityEvent.query.filter(db.or_(*activity_conditions)).order_by(ActivityEvent.created_at.asc()).all()
        for activity in activities:
            events.append(_event(activity.created_at, activity.title, activity.user.display_name if activity.user else "System", activity.category.replace("_", " ").title(), activity.details or activity.action))
    eod_events = ActivityEvent.query.filter_by(user_id=report.reported_by_id, category="eod", action="finalized", target_type="end_of_day").all()
    report_date = _report_date(report)
    for activity in eod_events:
        if str(report_date) in (activity.details or ""):
            events.append(_event(activity.created_at, "Route finalized", activity.user.display_name if activity.user else "Driver", "End-of-day", activity.details))

    audit_conditions = _audit_conditions(target_pairs)
    if audit_conditions:
        audits = AuditEvent.query.filter(db.or_(*audit_conditions)).order_by(AuditEvent.created_at.asc()).all()
        for audit in audits:
            events.append(_event(audit.created_at, f"Audit: {audit.action}", audit.user.display_name if audit.user else "System", "Immutable audit", audit.reason))
    return sorted(events, key=lambda row: row["sort_time"])


def _open_item_rows(report, logs, pretrips, photos, signature_shift, route_finalized):
    open_items = []
    if not photos:
        open_items.append("Photo not attached to this report.")
    for photo in photos:
        if not photo["file_exists"]:
            open_items.append(f"Photo #{photo['number']} not available in upload storage.")
    if not pretrips:
        open_items.append("No same-day PreTrip DVIR is linked to this driver/date.")
    if not signature_shift or not signature_shift.driver_signature:
        open_items.append("No driver route signature is captured for this date.")
    open_items.append("Manager signature not captured for this packet.")
    if _driver_can_edit(report):
        open_items.append("Report is still editable by the driver; submit or finalize to lock it.")
    if report.status != "closed":
        open_items.append("Manager review is not closed.")
    for log in logs:
        plant = plant_label(log.plant_name)
        if not log.depart_time:
            open_items.append(f"No departure recorded for {plant}.")
        route_issue = route_problem_reason(log) or secondary_not_dropped_reason(log)
        if route_issue:
            open_items.append(f"Route issue at {plant}: {route_issue}")
        truck_issue = truck_issue_reason(log)
        if truck_issue:
            open_items.append(f"Truck issue at {plant}: {truck_issue}")
    for pretrip in pretrips:
        if pretrip.start_mileage is not None and pretrip.start_mileage >= 1_000_000:
            open_items.append(f"Verify odometer entry on PreTrip #{pretrip.id}: {pretrip.start_mileage:,} mi.")
    if route_finalized and report.status == "open":
        open_items.append("Route is finalized, but this report is still open.")
    return open_items


def build_damage_evidence_packet(report, *, generated_by):
    report_date, logs, pretrips, transfers, tasks = _related_records(report)
    route_finalized = route_finalized_for_report(report)
    signature_shift = _shift_signature(report.reported_by_id, report_date)
    photo_rows = _photo_rows(report)
    routes = build_driver_log_route_context(logs)
    audit_count = AuditEvent.query.filter_by(target_type="damage_report", target_id=report.id).count()
    generated_at = datetime.utcnow()
    classification = classify_damage_report(report)
    open_items = _open_item_rows(report, logs, pretrips, photo_rows, signature_shift, route_finalized)
    return {
        "report": report,
        "report_date": report_date,
        "packet_type": classification.packet_type,
        "packet_label": classification.label,
        "packet_title": f"{classification.label} #{report.id}",
        "needs_clarification": classification.needs_clarification,
        "classification_question": classification.question,
        "packet_version": f"1.{audit_count}",
        "generated_by": generated_by.display_name,
        "generated_at": _label_dt(generated_at),
        "route_finalized": route_finalized,
        "driver_can_edit": _driver_can_edit(report),
        "current_status": "Locked" if route_finalized or report.status != "open" else "Editable by driver",
        "photos": photo_rows,
        "timeline": _timeline(report, logs, pretrips, transfers, tasks, signature_shift),
        "open_items": open_items,
        "logs": logs,
        "log_routes": routes,
        "pretrips": pretrips,
        "transfers": transfers,
        "tasks": tasks,
        "signature_shift": signature_shift,
        "driver_signature_complete": bool(signature_shift and signature_shift.driver_signature),
        "manager_signature_complete": False,
        "related_move_label": report.move_reference or (f"Driver log #{report.driver_log_id}" if report.driver_log_id else "Not linked"),
        "truck_label": report.truck_number or "Not set",
        "trailer_label": report.trailer_number or "Not set",
        "plant_label": plant_label(report.plant_name),
        "damage_time_label": _label_dt(report.damage_time or report.created_at),
        "created_time_label": _label_dt(report.created_at),
        "reviewed_time_label": _label_dt(report.resolved_at) if report.resolved_at else "Not reviewed/closed",
        "submitted_time_label": "Submitted" if report.status != "open" else "Not submitted",
    }
