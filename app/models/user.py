from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default="driver")  # "driver" or "management"
    # Day-driver workspace mode: swaps the Lacks plant/part questions for the
    # generic commodity + weight DVIR flow. Off by default so existing drivers
    # keep the plant-transfer flow unchanged.
    day_driver = db.Column(db.Boolean, default=False)
    # Day-driver route classification (drives the Hours Check display, not an ELD):
    # "local_short_haul" (default), "general_freight" (owner-operator), "company_shuttle".
    route_type = db.Column(db.String(30), nullable=True)
    first_name = db.Column(db.String(64), nullable=True)
    last_name = db.Column(db.String(64), nullable=True)
    employee_id = db.Column(db.String(32), nullable=True)
    shift = db.Column(db.String(16), nullable=True)
    department = db.Column(db.String(32), nullable=True)

    tasks = db.relationship(
        "Task",
        backref="assigned_user",
        lazy="dynamic",
        foreign_keys="Task.assigned_to",
    )
    driver_logs = db.relationship(
        "DriverLog",
        backref="driver",
        lazy="dynamic",
        foreign_keys="DriverLog.driver_id",
    )
    pretrips = db.relationship(
        "PreTrip",
        backref="driver",
        lazy="dynamic",
        foreign_keys="PreTrip.user_id",
    )
    chat_messages = db.relationship("ChatMessage", backref="user", lazy="dynamic")

    @property
    def display_name(self):
        name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return name or self.username

    @property
    def is_day_driver(self):
        return bool(self.day_driver)

    @property
    def day_driver_route_type(self):
        return self.route_type or "local_short_haul"

    @property
    def division_label(self):
        return self.department or "No division"

    @property
    def badge_label(self):
        return self.employee_id or "No badge"

    @property
    def manager_label(self):
        meta = []
        if self.department:
            meta.append(self.department)
        if self.employee_id:
            meta.append(f"Badge {self.employee_id}")
        return " | ".join([self.display_name] + meta)

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)
