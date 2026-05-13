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
    part_number = db.Column(db.String(80), nullable=True)
    hot_parts = db.Column(db.Boolean, default=False)
    no_pickup = db.Column(db.Boolean, default=False)
    load_size = db.Column(db.String(10), nullable=False)
    plant_name = db.Column(db.String(20), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    meeting = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id])

    @property
    def action_label(self):
        return "Depart" if not self.depart_time else "Edit"
