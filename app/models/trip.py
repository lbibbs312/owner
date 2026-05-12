"""PreTrip, PostTrip, and ShiftRecord.

PreTrip captures the DOT-required pre-shift vehicle inspection. The 50+ Boolean
fields each correspond to a checkbox on the inspection form; do not drop or
rename any without a corresponding Alembic migration and a paper-trail change
review — these columns are part of the audit record.
"""
from datetime import date, datetime

from app.extensions import db


class PreTrip(db.Model):
    __tablename__ = "pretrip"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    truck_number = db.Column(db.String(50))
    trailer_number = db.Column(db.String(50))
    pretrip_date = db.Column(db.Date, default=date.today)
    shift = db.Column(db.String(10))
    start_mileage = db.Column(db.Integer)
    # Additional fields for the PreTrip inspection
    truck_type = db.Column(db.String(20))
    oil_system_status = db.Column(db.String(20))
    tires_ok = db.Column(db.Boolean, default=False)
    tires_status = db.Column(db.String(50))
    # GENERAL CONDITION
    cab_doors_windows = db.Column(db.Boolean, default=False)
    body_doors = db.Column(db.Boolean, default=False)
    oil_leak = db.Column(db.Boolean, default=False)
    grease_leak = db.Column(db.Boolean, default=False)
    coolant_leak = db.Column(db.Boolean, default=False)
    fuel_leak = db.Column(db.Boolean, default=False)
    gc_no_defects = db.Column(db.Boolean, default=False)
    # IN-CAB
    gauges_warning = db.Column(db.Boolean, default=False)
    wipers = db.Column(db.Boolean, default=False)
    horn = db.Column(db.Boolean, default=False)
    heater_defroster = db.Column(db.Boolean, default=False)
    mirrors = db.Column(db.Boolean, default=False)
    seat_belts_steering = db.Column(db.Boolean, default=False)
    clutch = db.Column(db.Boolean, default=False)
    service_brakes = db.Column(db.Boolean, default=False)
    parking_brake = db.Column(db.Boolean, default=False)
    emergency_brakes = db.Column(db.Boolean, default=False)
    triangles = db.Column(db.Boolean, default=False)
    fire_extinguisher = db.Column(db.Boolean, default=False)
    safety_equipment = db.Column(db.Boolean, default=False)
    incab_no_defects = db.Column(db.Boolean, default=False)
    # ENGINE COMPARTMENT
    oil_level = db.Column(db.Boolean, default=False)
    coolant_level = db.Column(db.Boolean, default=False)
    belts = db.Column(db.Boolean, default=False)
    hoses = db.Column(db.Boolean, default=False)
    ec_no_defects = db.Column(db.Boolean, default=False)
    # EXTERIOR
    lights_working = db.Column(db.Boolean, default=False)
    reflectors = db.Column(db.Boolean, default=False)
    suspension = db.Column(db.Boolean, default=False)
    tires = db.Column(db.Boolean, default=False)
    wheels_rims = db.Column(db.Boolean, default=False)
    battery = db.Column(db.Boolean, default=False)
    exhaust = db.Column(db.Boolean, default=False)
    brakes = db.Column(db.Boolean, default=False)
    air_lines = db.Column(db.Boolean, default=False)
    light_line = db.Column(db.Boolean, default=False)
    fifth_wheel = db.Column(db.Boolean, default=False)
    coupling = db.Column(db.Boolean, default=False)
    tie_downs = db.Column(db.Boolean, default=False)
    rear_end_protection = db.Column(db.Boolean, default=False)
    exterior_no_defects = db.Column(db.Boolean, default=False)
    # TOWED UNIT
    towed_bodydoors = db.Column(db.Boolean, default=False)
    towed_tiedowns = db.Column(db.Boolean, default=False)
    towed_lights = db.Column(db.Boolean, default=False)
    towed_reflectors = db.Column(db.Boolean, default=False)
    towed_suspension = db.Column(db.Boolean, default=False)
    towed_tires = db.Column(db.Boolean, default=False)
    towed_wheels = db.Column(db.Boolean, default=False)
    towed_brakes = db.Column(db.Boolean, default=False)
    towed_landing_gear = db.Column(db.Boolean, default=False)
    towed_kingpin = db.Column(db.Boolean, default=False)
    towed_fifthwheel = db.Column(db.Boolean, default=False)
    towed_othercoupling = db.Column(db.Boolean, default=False)
    towed_rearend = db.Column(db.Boolean, default=False)
    towed_no_defects = db.Column(db.Boolean, default=False)
    # REMARKS / DAMAGE
    damage_report = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    posttrip = db.relationship("PostTrip", uselist=False, backref="pretrip")


class PostTrip(db.Model):
    __tablename__ = "posttrip"
    id = db.Column(db.Integer, primary_key=True)
    pretrip_id = db.Column(db.Integer, db.ForeignKey("pretrip.id"), nullable=False)
    end_mileage = db.Column(db.Integer, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    miles_driven = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


class ShiftRecord(db.Model):
    __tablename__ = "shift_record"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pretrip_id = db.Column(db.Integer, db.ForeignKey("pretrip.id"), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Float, nullable=True)
    week_ending = db.Column(db.Date, nullable=True)

    user = db.relationship("User", backref="shift_records")
    pretrip = db.relationship("PreTrip", backref="shift_record")
