"""Driver-facing routes.

Holds the routes a driver hits during a shift: dashboard, pre-trip / post-trip
inspections, driver logs, shift start/end, end-of-day. Currently only the
pre-trip / post-trip family lives here; the rest will move in subsequent sub-
PRs of PR-5c.
"""
from datetime import datetime, date

import pytz
from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.blueprints.driver import bp
from app.extensions import db
from app.extensions import socketio
from app.forms.log import DriverLogForm
from app.forms.messaging import DirectMessageForm
from app.forms.shift import EndOfDayForm
from app.forms.trip import PostTripForm, PreTripForm
from app.forms.user import ProfileForm
from app.models import (
    DirectMessage,
    DriverLog,
    PostTrip,
    PreTrip,
    ShiftRecord,
    Task,
    User,
)


@bp.route("/list_pretrips")
@login_required
def list_pretrips():
    if current_user.role == "management":
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
    else:
        pretrips = (
            PreTrip.query.filter_by(user_id=current_user.id)
            .order_by(PreTrip.created_at.desc())
            .all()
        )
    return render_template("list_pretrips.html", pretrips=pretrips)


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
        db.session.commit()

        flash("PreTrip saved successfully!", "success")
        return redirect(url_for("driver.list_pretrips"))

    return render_template("new_pretrip.html", form=form)


@bp.route("/do_posttrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def do_posttrip(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to complete a PostTrip for someone else's PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))

    form = PostTripForm()
    if form.validate_on_submit():
        end_mileage_val = form.end_mileage.data
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

        flash("PostTrip completed successfully and shift clock ended!", "success")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pretrip_id))
    return render_template("posttrip.html", form=form, pretrip=pt)


@bp.route("/view_pretrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def view_pretrip(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to view that PreTrip.", "danger")
        return redirect(url_for("driver.list_pretrips"))
    return render_template(
        "view_pretrip.html",
        pretrip=pt,
        readonly=(current_user.role == "management"),
    )


@bp.route("/edit_pretrip_entry/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def edit_pretrip_entry(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
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

        session["reviewing_driver"] = request.form.get("reviewing_driver")
        session["reviewing_date"] = request.form.get("reviewing_date")

        flash("PreTrip updated!", "success")
        return redirect(url_for("driver.view_pretrip", pretrip_id=pt.id))

    return render_template("edit_pretrip_entry.html", form=form, pretrip=pt)


@bp.route("/pretrip_printable/<int:pretrip_id>")
@login_required
def pretrip_printable(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
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
    )


@bp.route("/driver_logs", methods=["GET"])
@login_required
def driver_logs():
    date_str = request.args.get("date")
    try:
        search_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str
            else datetime.now().date()
        )
    except ValueError:
        search_date = datetime.now().date()

    if current_user.role == "management":
        all_drivers = User.query.filter_by(role="driver").all()
        selected_driver_id = request.args.get("driver_id", type=int)
        query = DriverLog.query.filter(DriverLog.date == search_date).order_by(
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
        )
    else:
        logs = (
            DriverLog.query.filter_by(driver_id=current_user.id, date=search_date)
            .order_by(DriverLog.created_at.desc())
            .all()
        )
        return render_template("driver_logs.html", logs=logs, search_date=search_date)


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
            downtime_reason=form.downtime_reason.data,
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            meeting=form.meeting.data,
            date=local_date,
        )
        db.session.add(newlog)
        db.session.commit()
        flash("New driving log added (local date, UTC arrival time)!", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_template("new_driving_log.html", form=form)


@bp.route("/edit_driver_log/<int:log_id>", methods=["GET", "POST"])
@login_required
def edit_driver_log(log_id):
    log = DriverLog.query.get_or_404(log_id)
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to edit someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))

    form = DriverLogForm(obj=log)
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("driver.edit_driver_log", log_id=log.id))

        log.plant_name = form.plant_name.data
        log.load_size = form.load_size.data
        log.downtime_reason = form.downtime_reason.data
        log.maintenance = form.maintenance.data
        log.fuel = form.fuel.data
        log.meeting = form.meeting.data

        if form.depart_time.data.strip():
            log.depart_time = form.depart_time.data.strip()
        else:
            local_tz = pytz.timezone("America/Detroit")
            now_local = datetime.now(local_tz)
            log.depart_time = now_local.strftime("%H:%M")

        db.session.commit()
        flash(f"Driving log updated (ID: {log.id}).", "success")
        return redirect(url_for("driver.driver_logs"))

    return render_template("edit_driver_log.html", form=form, log=log)


@bp.route("/view_driver_log/<int:log_id>")
@login_required
def view_driver_log(log_id):
    log = DriverLog.query.get_or_404(log_id)
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to view someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    return render_template("view_driver_log.html", log=log)


@bp.route("/driver_logs_print")
@login_required
def driver_logs_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = DriverLog.query.filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    return render_template(
        "driver_logs_print.html", logs=logs, the_date=today_local_date
    )


@bp.route("/start_shift", methods=["GET", "POST"])
@login_required
def start_shift():
    existing_open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if existing_open_shift:
        flash("You already have a shift in progress!", "warning")
        return redirect(url_for("driver.dashboard"))

    new_shift = ShiftRecord(
        user_id=current_user.id,
        pretrip_id=None,
        start_time=datetime.utcnow(),
        week_ending=None,
    )
    db.session.add(new_shift)
    db.session.commit()

    flash("Shift started!", "success")
    return redirect(url_for("driver.dashboard"))


@bp.route("/end_shift", methods=["GET", "POST"])
@login_required
def end_shift():
    open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if not open_shift:
        flash("No open shift found!", "warning")
        return redirect(url_for("driver.dashboard"))

    open_shift.end_time = datetime.utcnow()
    open_shift.total_hours = (
        open_shift.end_time - open_shift.start_time
    ).total_seconds() / 3600
    db.session.commit()

    flash("Shift ended!", "success")
    return redirect(url_for("driver.dashboard"))


@bp.route("/end_of_day_summary", methods=["GET", "POST"])
@login_required
def end_of_day_summary():
    form = EndOfDayForm()
    if form.validate_on_submit():
        flash("Submitted End of Day Summary (interactive)!", "success")
        return redirect(url_for("driver.dashboard"))

    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()

    logs = DriverLog.query.filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    drivers_logs = {current_user.username: logs}

    pretrips_today = PreTrip.query.filter_by(
        user_id=current_user.id, pretrip_date=today_local_date
    ).all()
    drivers_pretrips = {current_user.username: pretrips_today}

    return render_template(
        "end_of_day_summary.html",
        form=form,
        the_date=today_local_date,
        drivers_logs=drivers_logs,
        drivers_pretrips=drivers_pretrips,
    )


@bp.route("/end_of_day_print")
@login_required
def end_of_day_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = DriverLog.query.filter_by(
        driver_id=current_user.id, date=today_local_date
    ).all()
    drivers_logs = {current_user.username: logs}

    return render_template(
        "end_of_day_print.html", the_date=today_local_date, drivers_logs=drivers_logs
    )


@bp.route("/submit_end_of_day", methods=["POST"])
@login_required
def submit_end_of_day():
    flash("Submitted End of Day Summary via separate route!", "success")
    return redirect(url_for("driver.dashboard"))


@bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    logs = (
        DriverLog.query.filter_by(driver_id=current_user.id)
        .order_by(DriverLog.created_at.desc())
        .limit(5)
        .all()
    )
    pretrips = (
        PreTrip.query.filter_by(user_id=current_user.id)
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
        current_user.email = form.email.data
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Profile updated!", "success")
        return redirect(url_for("driver.profile"))
    return render_template("profile.html", profile_form=form)


@bp.route("/list_tasks")
@login_required
def list_tasks():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
    else:
        tasks = (
            Task.query.filter_by(assigned_to=current_user.id)
            .order_by(Task.created_at.desc())
            .all()
        )
    return render_template("list_tasks.html", tasks=tasks)
