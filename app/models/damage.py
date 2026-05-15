from datetime import datetime

from app.extensions import db


class DamageReport(db.Model):
    __tablename__ = "damage_report"

    id = db.Column(db.Integer, primary_key=True)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    plant_transfer_id = db.Column(db.Integer, db.ForeignKey("plant_transfer.id"), nullable=True)
    truck_number = db.Column(db.String(50), nullable=True)
    trailer_number = db.Column(db.String(50), nullable=True)
    plant_name = db.Column(db.String(50), nullable=False)
    damage_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    stage = db.Column(db.String(20), nullable=False, default="before")
    move_reference = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    reported_by = db.relationship("User", backref="damage_reports")
    task = db.relationship("Task", backref="damage_reports")
    driver_log = db.relationship("DriverLog", backref="damage_reports")
    plant_transfer = db.relationship("PlantTransfer", backref="damage_reports")
    photos = db.relationship(
        "DamagePhoto",
        backref="damage_report",
        cascade="all, delete-orphan",
        order_by="DamagePhoto.uploaded_at",
    )


class DamagePhoto(db.Model):
    __tablename__ = "damage_photo"

    id = db.Column(db.Integer, primary_key=True)
    damage_report_id = db.Column(db.Integer, db.ForeignKey("damage_report.id"), nullable=False)
    stage = db.Column(db.String(20), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
