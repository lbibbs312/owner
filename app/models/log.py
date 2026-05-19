from datetime import datetime

from app.extensions import db


class DriverLog(db.Model):
    __tablename__ = "driver_log"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    arrive_time = db.Column(db.String(20))
    depart_time = db.Column(db.String(20))
    downtime_reason = db.Column(db.String(200), nullable=True)
    dock_wait_minutes = db.Column(db.Integer, nullable=True)
    part_number = db.Column(db.String(80), nullable=True)
    hot_parts = db.Column(db.Boolean, default=False)
    no_pickup = db.Column(db.Boolean, default=False)
    load_size = db.Column(db.String(80), nullable=False)
    depart_load_size = db.Column(db.String(80), nullable=True)
    secondary_load = db.Column(db.String(80), nullable=True)
    plant_name = db.Column(db.String(20), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    fuel_mileage = db.Column(db.Integer, nullable=True)
    meeting = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id])

    @property
    def action_label(self):
        return "Depart" if not self.depart_time else "Edit"

class DriverLogPhoto(db.Model):
    __tablename__ = "driver_log_photo"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(40), nullable=False, default="gallery")
    note = db.Column(db.Text, nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    log = db.relationship(
        "DriverLog",
        backref=db.backref(
            "photos",
            cascade="all, delete-orphan",
            order_by="DriverLogPhoto.uploaded_at.asc()",
        ),
    )
    uploaded_by = db.relationship("User", backref="driver_log_photos")

