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
import re

from flask import current_app, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app.blueprints.manager import bp
from app.extensions import db, socketio
from app.forms.followup import OperationalFollowUpForm
from app.forms.task import TaskForm
from app.models import ActivityEvent, AuditEvent, DamageReport, DriverLog, OperationalFollowUp, PlantTransfer, PreTrip, Task, User
from app.services.activity import record_activity
from app.services.operations import build_delay_report, build_exception_items, build_weekly_savings
from app.services.load_state import build_driver_log_route_context
from app.services.plant_addresses import PLANT_LABELS, plant_label as _plant_label
from app.services.role_session import restore_role_user
from app.services.search_corpus import suggest_terms
from app.blueprints.driver.routes import (
    _build_driver_logs_pdf,
    _build_plant_transfer_pdf,
    _build_pretrip_pdf,
    _plant_transfer_copy_sets,
    _total_miles_for_pretrips,
    _task_route_events_for_logs,
)


TRIM_PLANTS = ("Trim DC", "PPL", "DC")
PART_TOKEN_RE = re.compile(r"\b[A-Z]*\d[A-Z0-9-]{3,}\b", re.IGNORECASE)


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
    if pretrip.start_mileage is not None:
        meta.append(f"Start {pretrip.start_mileage} mi")
    return {
        "truck_id": pretrip.truck_number or "Truck not set",
        "truck_meta": " • ".join(meta) if meta else f"DVIR #{pretrip.id}",
        "pretrip_id": pretrip.id,
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
    routes = _driver_log_route_context(sorted_logs)
    counts = {}
    rows = []
    for log in sorted_logs:
        key = (log.driver_id, log.date)
        counts[key] = counts.get(key, 0) + 1
        route = routes.get(log.id, {})
        rows.append({
            "log": log,
            "route": route,
            "stop_number": counts[key],
            "driver": log.driver,
            "status": "Open stop - needs departure" if not log.depart_time else "Completed stop",
            "status_key": "open" if not log.depart_time else "complete",
            "cargo": route.get("depart_cargo_desc") or route.get("arrive_cargo_desc") or log.depart_load_size or log.load_size or "--",
            "dock_wait": f"{log.dock_wait_minutes} min" if log.dock_wait_minutes is not None else "--",
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
    return {
        "driver": driver,
        "logs": logs,
        "log_routes": log_routes,
        "the_date": route_date,
        "pretrips": pretrips,
        "damage_reports": damage_reports,
        "total_miles": _total_miles_for_pretrips(pretrips),
        "parts_carried": parts_carried,
        "exception_notes": exception_notes,
        "log_issue_details": log_issue_details,
        "route_task_events": _task_route_events_for_logs(logs),
    }

def _requested_url():
    return request.full_path if request.query_string else request.path


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
    metrics = build_weekly_savings(dock_delay_minutes=_dock_delay_minutes())
    followups = OperationalFollowUp.query.order_by(OperationalFollowUp.created_at.desc()).limit(20).all()
    damage_reports = DamageReport.query.order_by(DamageReport.created_at.desc()).limit(10).all()
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


@bp.route("/damage-reports/<int:report_id>")
def view_damage_report(report_id):
    report = DamageReport.query.get_or_404(report_id)
    return render_template("view_damage_report.html", report=report, manager_view=True)


@bp.route("/delays")
def delay_finder():
    delay_report = build_delay_report(dock_delay_minutes=_dock_delay_minutes())
    return render_template("delay_finder.html", delay_report=delay_report)


@bp.route("/weekly-savings")
def weekly_savings():
    metrics = build_weekly_savings(dock_delay_minutes=_dock_delay_minutes())
    return render_template("weekly_savings.html", metrics=metrics)


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


@bp.route("/dashboard", methods=["GET", "POST"])
def manager_dashboard():
    create_task_form = TaskForm()
    drivers = _populate_task_driver_choices(create_task_form)
    today = date.today()
    division_filter = request.args.get("division", "All")
    if division_filter not in {"All", "Plastics", "Trim"}:
        division_filter = "All"
    selected_driver_id = request.args.get("driver_id", type=int)
    focus_panel = request.args.get("focus", "jobs")
    if focus_panel not in {"jobs", "routes", "delays"}:
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

    dock_wait_values = [log.dock_wait_minutes for log in todays_logs if log.dock_wait_minutes is not None]
    avg_dock_wait_today = round(sum(dock_wait_values) / len(dock_wait_values), 1) if dock_wait_values else None

    active_driver_ids = {log.driver_id for log in todays_logs}
    active_drivers = [driver for driver in drivers if driver.id in active_driver_ids]
    plastics_drivers = [driver for driver in drivers if _division_for_user(driver) == "Plastics"]
    trim_drivers = [driver for driver in drivers if _division_for_user(driver) == "Trim"]
    plastics_moves = [row for row in _build_dispatch_rows(uncompleted_tasks, todays_transfers) if row["division"] == "Plastics"]
    trim_moves = [row for row in _build_dispatch_rows(uncompleted_tasks, todays_transfers) if row["division"] == "Trim"]

    return render_template(
        "manager_dashboard.html",
        create_task_form=create_task_form,
        uncompleted_tasks=uncompleted_tasks,
        dispatch_rows=dispatch_rows,
        live_stop_rows=live_stop_rows,
        selected_driver_id=selected_driver_id,
        focus_panel=focus_panel,
        drivers=drivers,
        division_filter=division_filter,
        total_active_moves=len(uncompleted_tasks) + len(todays_transfers),
        plastics_move_count=len(plastics_moves),
        trim_move_count=len(trim_moves),
        active_driver_count=len(active_drivers),
        avg_dock_wait_today=avg_dock_wait_today,
        dock_wait_record_count=len(dock_wait_values),
        plastics_driver_count=len(plastics_drivers),
        trim_driver_count=len(trim_drivers),
        has_drivers=bool(drivers),
        today=today,
        manager_division=_division_for_user(current_user),
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
    ctx = _route_print_context(driver_id, route_date)
    return render_template(
        "driver_logs_print.html",
        **ctx,
        print_driver=ctx["driver"],
        route_finalized=False,
        driver_signature=None,
        signature_timestamp=None,
        attachment_url=url_for("manager.driver_route_attachment", driver_id=driver_id, date=route_date.isoformat()),
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
    ctx = _route_print_context(driver_id, route_date)
    return _document_attachment_response(
        pdf_bytes=_build_driver_logs_pdf(ctx["logs"], route_date, driver=ctx["driver"]),
        filename=f"driver-route-{driver_id}-{route_date}.pdf",
        target_type="driver_log",
        title="Manager Driver Route PDF downloaded",
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
    stop_position = next((index + 1 for index, day_log in enumerate(day_logs) if day_log.id == log.id), None)

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

    # Delay detail: any stop on this driver/date with dock wait or downtime reason
    delay_logs = [dl for dl in day_logs if (dl.dock_wait_minutes or 0) > 0 or dl.downtime_reason]

    # Average dock wait across the day (stops that recorded a value)
    wait_values = [dl.dock_wait_minutes for dl in day_logs if dl.dock_wait_minutes is not None]
    avg_dock_wait = round(sum(wait_values) / len(wait_values), 1) if wait_values else None

    all_routes = _driver_log_route_context(day_logs)
    return render_template(
        "view_driver_log.html",
        log=log,
        log_route=all_routes.get(log.id),
        log_routes=all_routes,
        truck_context=_truck_context_for_driver(log.driver_id, log.date),
        related_task=related_task,
        stop_position=stop_position,
        stop_count=len(day_logs),
        today_local_date=date.today(),
        damage_reports=damage_reports,
        delay_logs=delay_logs,
        avg_dock_wait=avg_dock_wait,
        day_logs=day_logs,
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
