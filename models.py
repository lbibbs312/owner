import datetime
from datetime import date, datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

#
# 1) USER MODEL
#
class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default="driver")  # "driver" or "management"

    def set_password(self, pwd):
        # You can use Werkzeug or other hashing
        pass

    def check_password(self, pwd):
        # Compare hashed password
        return False


#
# 2) PRETRIP & POSTTRIP
#
class PreTrip(db.Model):
    __tablename__ = "pretrip"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Basic info
    truck_number = db.Column(db.String(50))
    trailer_number = db.Column(db.String(50))
    pretrip_date = db.Column(db.Date, default=date.today)
    shift = db.Column(db.String(10))
    start_mileage = db.Column(db.Integer)

    # General Condition
    cab_doors_windows = db.Column(db.Boolean, default=False)
    body_doors = db.Column(db.Boolean, default=False)
    oil_leak = db.Column(db.Boolean, default=False)
    grease_leak = db.Column(db.Boolean, default=False)
    coolant_leak = db.Column(db.Boolean, default=False)
    fuel_leak = db.Column(db.Boolean, default=False)
    gc_no_defects = db.Column(db.Boolean, default=False)

    # In-Cab
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

    # Engine Compartment
    oil_level = db.Column(db.Boolean, default=False)
    coolant_level = db.Column(db.Boolean, default=False)
    belts = db.Column(db.Boolean, default=False)
    hoses = db.Column(db.Boolean, default=False)
    ec_no_defects = db.Column(db.Boolean, default=False)

    # Exterior
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

    # Towed Unit
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

    # Additional fields
    truck_type = db.Column(db.String(20))
    oil_system_status = db.Column(db.String(20), default="operational")
    tires_status = db.Column(db.String(20), default="operational")
    damage_report = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # One-to-one relationship to PostTrip
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


#
# 3) DRIVER LOG
#
class DriverLog(db.Model):
    __tablename__ = "driver_log"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    driver = db.relationship("User", backref="driver_logs", lazy="joined")

    date = db.Column(db.Date, nullable=False)
    arrive_time = db.Column(db.String(20))
    depart_time = db.Column(db.String(20))
    downtime_reason = db.Column(db.String(200), nullable=True)
    load_size = db.Column(db.String(10), nullable=False)
    plant_name = db.Column(db.String(20), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    meeting = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


#
# 4) MISC MODELS
#
class ChatMessage(db.Model):
    __tablename__ = "chat_message"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    room = db.Column(db.String(100), default="global")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="chat_messages")


class Announcement(db.Model):
    __tablename__ = "announcement"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DirectMessage(db.Model):
    __tablename__ = "direct_message"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="received_messages")


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


class KnowledgeBaseEntry(db.Model):
    __tablename__ = "knowledge_base"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    title = db.Column(db.String(100))
    body = db.Column(db.Text)