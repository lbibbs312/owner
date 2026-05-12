"""Driver-facing routes.

Holds the routes a driver hits during a shift: dashboard, pre-trip / post-trip
inspections, driver logs, shift start/end, end-of-day. Currently only the
pre-trip / post-trip family lives here; the rest will move in subsequent sub-
PRs of PR-5c.
"""
from datetime import datetime, date

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.blueprints.driver import bp
from app.extensions import db
from app.forms.trip import PostTripForm, PreTripForm
from app.models import PostTrip, PreTrip, ShiftRecord


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
