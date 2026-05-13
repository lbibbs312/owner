from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default="driver")  # "driver" or "management"
    first_name = db.Column(db.String(64), nullable=True)
    last_name = db.Column(db.String(64), nullable=True)
    employee_id = db.Column(db.String(32), nullable=True)
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
    def division_label(self):
        return self.department or "No division"

    @property
    def badge_label(self):
        return self.employee_id or "No badge"

    @property
    def manager_label(self):
        return f"{self.display_name} | {self.division_label} | Badge {self.badge_label}"

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)
