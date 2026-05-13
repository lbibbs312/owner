"""Driver-facing routes.

Holds the routes a driver hits during a shift: dashboard, pre-trip / post-trip
inspections, driver logs, shift start/end, end-of-day. Currently only the
pre-trip / post-trip family lives here; the rest will move in subsequent sub-
PRs of PR-5c.
"""
from datetime import datetime, date

import pytz
from flask import flash, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.blueprints.driver import bp
from app.extensions import db
from app.extensions import socketio
from app.forms.log import DriverLogForm
from app.forms.plant_transfer import PlantTransferForm
from app.forms.messaging import DirectMessageForm
from app.forms.shift import EndOfDayForm
from app.forms.trip import PostTripForm, PreTripForm
from app.forms.user import ProfileForm
from app.services.activity import record_activity
from app.services.simple_pdf import LANDSCAPE_LETTER, LETTER, SimplePdf
from app.services.role_session import restore_role_user
from app.models import (
    ActivityEvent,
    DirectMessage,
    DriverLog,
    PlantTransfer,
    PlantTransferLine,
    PostTrip,
    PreTrip,
    ShiftRecord,
    Task,
    User,
)


PLANT_TRANSFER_LINE_COUNT = 20

DRIVER_ONLY_ENDPOINTS = {
    "dashboard",
    "mobile_dashboard",
    "mobile_history",
    "mobile_day_report",
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
    "edit_driver_log",
    "delete_driver_log",
    "depart_driver_log",
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


def _active_driver_logs_query():
    return DriverLog.query.filter(DriverLog.deleted_at.is_(None))


def _active_pretrips_query():
    return PreTrip.query.filter(PreTrip.deleted_at.is_(None))


def _active_plant_transfers_query():
    return PlantTransfer.query.filter(PlantTransfer.deleted_at.is_(None))


def _soft_delete_record(record):
    record.deleted_at = datetime.utcnow()
    record.deleted_by_id = current_user.id



def _active_driver_tasks_query():
    return Task.query.filter(
        Task.status.in_(["pending", "in-progress"]),
        (Task.assigned_to == current_user.id) | ((Task.assigned_to.is_(None)) & (Task.status == "pending")),
    )


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


def _apply_log_part_fields(log, form):
    log.part_number = (form.part_number.data or "").strip() or None
    log.hot_parts = bool(form.hot_parts.data)

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


def _yes_no(value):
    return "Yes" if value else "No"


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


def _shift_redirect():
    if request.args.get("next") == "mobile":
        return redirect(url_for("driver.mobile_dashboard"))
    return redirect(url_for("driver.dashboard"))


def _task_redirect():
    if request.args.get("next") == "mobile":
        return redirect(url_for("driver.mobile_dashboard"))
    return redirect(url_for("driver.list_tasks"))


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
    pdf = SimplePdf("PreTrip DVIR", LETTER)
    y = 748
    pdf.text(205, y, "DAILY VEHICLE INSPECTION REPORT", size=14, bold=True)
    y -= 28
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
    left = rows[:13]
    right = rows[13:]
    pdf.table(36, y, [150, 80, 150, 80], 18, ["Item", "Status", "Item", "Status"], [l + r for l, r in zip(left, right)], font_size=8)
    y = 210
    pdf.text(36, y, "Damage / Remarks", size=10, bold=True)
    pdf.rect(36, y - 70, 540, 60)
    pdf.multiline_text(42, y - 20, pretrip.damage_report or "", width_chars=95, size=9, max_lines=5)
    pdf.text(36, 92, "Driver Signature: ____________________________", size=10)
    pdf.text(335, 92, "Date: __________________", size=10)
    return pdf.build()


def _build_driver_logs_pdf(logs, the_date):
    pdf = SimplePdf("Driver Logs", LETTER)
    pdf.text(36, 748, f"Driver Logs - {the_date}", size=15, bold=True)
    rows = []
    for log in logs:
        rows.append([
            log.plant_name,
            _arrival_utc_to_local_hhmm(log.arrive_time) or "--",
            _format_hhmm_12h(log.depart_time) or "--",
            ("No Pickup " if log.no_pickup else "") + (("HOT " if log.hot_parts else "") + (log.part_number or "")).strip(),
            "X" if log.load_size == "Empty" else "",
            "X" if log.load_size == "Quarter" else "",
            "X" if log.load_size == "Half" else "",
            "X" if log.load_size == "Partial" else "",
            "X" if log.load_size == "Full" else "",
        ])
    pdf.table(36, 710, [72, 92, 70, 145, 24, 24, 24, 28, 24], 22, ["Plant", "Arrive", "Depart", "Parts", "Z", "Q", "H", "TQ", "F"], rows or [["No logs", "", "", "", "", "", "", "", ""]], font_size=7)
    return pdf.build()


def _build_eod_pdf(the_date, logs, plant_transfers):
    pdf = SimplePdf("End of Day", LETTER)
    pdf.text(36, 748, f"End of Day - {the_date}", size=15, bold=True)
    log_rows = []
    for log in logs:
        log_rows.append([
            log.plant_name,
            _arrival_utc_to_local_hhmm(log.arrive_time) or "--",
            _format_hhmm_12h(log.depart_time) or "--",
            ("No Pickup " if log.no_pickup else "") + (("HOT " if log.hot_parts else "") + (log.part_number or "")).strip(),
            log.load_size,
        ])
    y = pdf.table(36, 710, [80, 105, 75, 210, 60], 22, ["Plant", "Arrive", "Depart", "Parts", "Load"], log_rows or [["No logs", "", "", "", ""]], font_size=8)
    y -= 34
    pdf.text(36, y, "Plant Transfers", size=12, bold=True)
    y -= 14
    transfer_rows = []
    for transfer in plant_transfers:
        transfer_rows.append([
            transfer.transfer_number or transfer.id,
            transfer.ship_from,
            transfer.ship_to,
            transfer.trailer_number or "",
            transfer.driver_name or transfer.driver.display_name,
            len(transfer.lines),
        ])
    pdf.table(36, y, [60, 80, 80, 80, 150, 50], 22, ["No.", "From", "To", "Trailer", "Driver", "Lines"], transfer_rows or [["No transfers", "", "", "", "", ""]], font_size=8)
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
        pdf.text(340, 566, "LACKS INDUSTRIES INC.", size=8, bold=True)
        pdf.text(310, 548, "PLANT TRANSFER", size=18, bold=True)
        pdf.text(650, 552, f"No. {transfer.transfer_number or transfer.id}", size=10, bold=True)
        pdf.text(36, 530, f"SHIP TO: {transfer.ship_to}", size=9, bold=True)
        pdf.text(300, 530, f"SHIP FROM: {transfer.ship_from}", size=9, bold=True)
        pdf.text(610, 530, f"DATE: {transfer.transfer_date}", size=9, bold=True)
        pdf.text(620, 588, copy_set["label"], size=9, bold=True)
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
        pdf.text(430, 118, f"TIME: {_format_display_time(transfer.transfer_time)}", size=9, bold=True)
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

    form = PostTripForm()
    if form.validate_on_submit():
        end_mileage_val = form.end_mileage.data
        if pt.start_mileage is not None and end_mileage_val < pt.start_mileage:
            flash("End mileage cannot be lower than start mileage.", "danger")
            return render_template("posttrip.html", form=form, pretrip=pt)
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
    return render_template("posttrip.html", form=form, pretrip=pt)


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
        transfer.transfer_number = form.transfer_number.data
        transfer.transfer_date = form.transfer_date.data
        transfer.ship_to = form.ship_to.data
        transfer.ship_from = form.ship_from.data
        transfer.trailer_number = form.trailer_number.data
        transfer.driver_name = form.driver_name.data
        transfer.transfer_time = _normalize_hhmm_time(form.transfer_time.data) or form.transfer_time.data
        transfer.loaded_by = form.loaded_by.data
        _replace_plant_transfer_lines(transfer)
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
    date_str = request.args.get("date")
    try:
        search_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str
            else _today_local_date()
        )
    except ValueError:
        search_date = _today_local_date()

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
            search_date=search_date,
            today_local_date=_today_local_date(),
        )


@bp.route("/new_driving_log", methods=["GET", "POST"])
@login_required
def new_driving_log():
    form = DriverLogForm()
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("driver.new_driving_log"))

        local_tz = pytz.timezone("America/Detroit")
        now_local = datetime.now(local_tz)
        local_date = now_local.date()

        now_utc = datetime.utcnow()
        arrive_time_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=form.load_size.data,
            part_number=(form.part_number.data or "").strip() or None,
            hot_parts=form.hot_parts.data,
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
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
            details=f"{newlog.plant_name} / {newlog.load_size} load for {newlog.date}.",
            target_type="driver_log",
            target_id=newlog.id,
        )
        flash("New driving log added (local date, UTC arrival time)!", "success")
        return redirect(url_for("driver.driver_logs"))

    _prefill_log_form_from_task(form)
    return render_template("new_driving_log.html", form=form)


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

        log.plant_name = form.plant_name.data
        log.load_size = form.load_size.data
        _apply_log_part_fields(log, form)
        log.maintenance = form.maintenance.data
        log.fuel = form.fuel.data
        log.meeting = form.meeting.data

        if arrive_time:
            log.arrive_time = _local_hhmm_to_arrival_utc(arrive_time, log.date)
        if depart_time:
            log.depart_time = depart_time

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
        flash(f"Driving log updated (ID: {log.id}).", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_template("edit_driver_log.html", form=form, log=log)


@bp.route("/driver_logs/<int:log_id>/delete", methods=["POST"])
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
    flash("Driver log deleted.", "success")
    return redirect(url_for("driver.driver_logs"))


@bp.route("/driver_logs/<int:log_id>/depart", methods=["POST"])
@login_required
def depart_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to depart someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    log.depart_time = now_local.strftime("%H:%M")
    db.session.commit()
    record_activity(
        user_id=current_user.id,
        category="log",
        action="departed",
        title="Driver log departed",
        details=f"{log.plant_name} departed at {_format_display_time(log.depart_time)}.",
        target_type="driver_log",
        target_id=log.id,
    )
    flash(f"Departed log #{log.id}.", "success")
    return redirect(url_for("driver.driver_logs"))



@bp.route("/driver_logs/<int:log_id>/no_pickup", methods=["POST"])
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
    log.no_pickup = True
    log.load_size = "Empty"
    log.depart_time = now_local.strftime("%H:%M")
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
    flash(f"No pickup recorded for log #{log.id}.", "success")
    return redirect(url_for("driver.driver_logs"))


@bp.route("/driver_logs/<int:log_id>/pickup", methods=["GET", "POST"])
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
    form.plant_name.data = log.plant_name
    _prefill_log_form_from_task(form)
    if form.validate_on_submit():
        if not form.load_size.data:
            flash("Please select the pickup load size.", "danger")
            return render_template("pickup_driver_log.html", form=form, log=log)

        now_local, arrive_time_str = _now_local_and_utc()
        log.depart_time = now_local.strftime("%H:%M")
        pickup_log = DriverLog(
            driver_id=log.driver_id,
            plant_name=log.plant_name,
            load_size=form.load_size.data,
            part_number=(form.part_number.data or "").strip() or None,
            hot_parts=form.hot_parts.data,
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            meeting=form.meeting.data,
            date=now_local.date(),
        )
        db.session.add(pickup_log)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="log",
            action="pickup",
            title="Same-plant pickup recorded",
            details=(
                f"{log.plant_name} dropoff log #{log.id} departed and "
                f"pickup log #{pickup_log.id} started with {pickup_log.load_size} load."
            ),
            target_type="driver_log",
            target_id=pickup_log.id,
        )
        flash(f"Pickup recorded at {log.plant_name}; new log #{pickup_log.id} started.", "success")
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
    )


@bp.route("/driver_logs_print")
@login_required
def driver_logs_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    record_activity(
        user_id=current_user.id,
        category="print",
        action="logs_printed",
        title="Driver logs printed",
        details=f"Printed {len(logs)} log(s) for {today_local_date}.",
        target_type="driver_log",
    )
    return render_template(
        "driver_logs_print.html",
        logs=logs,
        the_date=today_local_date,
        email_mode=False,
    )


@bp.route("/driver_logs_print/attachment")
@login_required
def driver_logs_attachment():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = _active_driver_logs_query().filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    return _document_attachment_response(
        pdf_bytes=_build_driver_logs_pdf(logs, today_local_date),
        filename=f"driver-logs-{today_local_date}.pdf",
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
        _record_eod_finalized(today_local_date, logs, pretrips_today, plant_transfers_today)
        flash("End of Day finalized and added to activity history.", "success")
        return redirect(url_for("driver.dashboard"))

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
    drivers_logs = {current_user.display_name: logs}
    drivers_plant_transfers = {current_user.display_name: plant_transfers}
    record_activity(
        user_id=current_user.id,
        category="print",
        action="eod_printed",
        title="End of day print generated",
        details=f"Printed EOD packet for {today_local_date}.",
        target_type="end_of_day",
    )

    return render_template(
        "end_of_day_print.html",
        the_date=today_local_date,
        drivers_logs=drivers_logs,
        drivers_plant_transfers=drivers_plant_transfers,
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
    return _document_attachment_response(
        pdf_bytes=_build_eod_pdf(today_local_date, logs, plant_transfers),
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


@bp.route("/mobile/history")
@login_required
def mobile_history():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return render_template("mobile_history.html", reports=_mobile_report_days(30))


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
    log_reports = [
        {"log": log, "freight": _log_freight_summary(log, transfers)}
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
    open_shift = (
        ShiftRecord.query.filter_by(user_id=current_user.id, end_time=None)
        .order_by(ShiftRecord.start_time.desc())
        .first()
    )
    shift_elapsed = None
    if open_shift:
        shift_elapsed = _format_duration((datetime.utcnow() - open_shift.start_time).total_seconds())

    tasks = (
        _active_driver_tasks_query()
        .order_by(Task.created_at.desc())
        .all()
    )
    tasks = sorted(
        tasks,
        key=lambda task: (
            task.status != "in-progress",
            not task.is_hot,
            task.created_at or datetime.min,
        ),
    )
    active_task = tasks[0] if tasks else None
    queued_tasks = tasks[1:4]
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
    pending_posttrip = bool(todays_pretrip and not todays_pretrip.posttrip)

    recent_transfers = (
        _active_plant_transfers_query().filter_by(user_id=current_user.id)
        .order_by(PlantTransfer.created_at.desc())
        .limit(3)
        .all()
    )
    latest_transfer = recent_transfers[0] if recent_transfers else None

    return render_template(
        "driver_mobile.html",
        active_task=active_task,
        queued_tasks=queued_tasks,
        hot_task_count=hot_task_count,
        latest_pretrip=latest_pretrip,
        todays_pretrip=todays_pretrip,
        pending_posttrip=pending_posttrip,
        recent_transfers=recent_transfers,
        latest_transfer=latest_transfer,
        open_shift=open_shift,
        shift_elapsed=shift_elapsed,
        today_local_date=today_local_date,
    )


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
    return render_template(
        "driver_task_detail.html",
        task=task,
        task_events=task_events,
        hot_part_logs=hot_part_logs,
    )


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
