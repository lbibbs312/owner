from datetime import datetime

from app.extensions import db


class ExceptionEvent(db.Model):
    __tablename__ = "exception_events"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="medium")
    route_id = db.Column(db.String(80), nullable=True, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    truck_id = db.Column(db.String(50), nullable=True, index=True)
    plant_name = db.Column(db.String(50), nullable=True, index=True)
    event_date = db.Column(db.Date, nullable=True, index=True)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stop = db.relationship("DriverLog", foreign_keys=[stop_id])
    driver_log = db.relationship("DriverLog", foreign_keys=[driver_log_id])
    driver = db.relationship("User", backref="exception_events")


class FollowupCase(db.Model):
    __tablename__ = "followup_cases"

    id = db.Column(db.Integer, primary_key=True)
    case_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    scope_key = db.Column(db.String(160), nullable=False, index=True)
    plant_name = db.Column(db.String(50), nullable=True, index=True)
    truck_id = db.Column(db.String(50), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="open")
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", backref="owned_followup_cases")
    events = db.relationship("CaseEvent", backref="case", cascade="all, delete-orphan")


class CaseEvent(db.Model):
    __tablename__ = "case_events"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("followup_cases.id"), nullable=False, index=True)
    exception_event_id = db.Column(db.Integer, db.ForeignKey("exception_events.id"), nullable=True)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    exception_event = db.relationship("ExceptionEvent", backref="case_events")
