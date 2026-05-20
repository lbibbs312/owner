from datetime import datetime

from app.extensions import db


class LoadIntent(db.Model):
    __tablename__ = "load_intent"

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    truck_id = db.Column(db.String(50), nullable=True, index=True)
    pickup_plant_id = db.Column(db.String(50), nullable=True, index=True)
    destination_plant_id = db.Column(db.String(50), nullable=True, index=True)
    load_label = db.Column(db.String(160), nullable=True)
    source = db.Column(db.String(40), nullable=False, default="unknown")
    confidence = db.Column(db.String(30), nullable=False, default="unknown")
    predicted_ready_at = db.Column(db.DateTime, nullable=True)
    estimated_remaining_minutes = db.Column(db.Integer, nullable=True)
    reason_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="predicted")
    confirmed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    promoted_driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    stop = db.relationship("DriverLog", foreign_keys=[stop_id], backref="load_intents")
    promoted_driver_log = db.relationship("DriverLog", foreign_keys=[promoted_driver_log_id])
    driver = db.relationship("User", foreign_keys=[driver_id], backref="load_intents")
    confirmed_by_user = db.relationship("User", foreign_keys=[confirmed_by])


class PlantPredictionRule(db.Model):
    __tablename__ = "plant_prediction_rule"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.String(50), nullable=False, index=True)
    condition_json = db.Column(db.Text, nullable=True)
    predicted_destination_plant_id = db.Column(db.String(50), nullable=False, index=True)
    confidence = db.Column(db.String(30), nullable=False, default="medium")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PlantTimeSample(db.Model):
    __tablename__ = "plant_time_sample"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.String(50), nullable=False, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    load_type = db.Column(db.String(40), nullable=True)
    manifest_line_count = db.Column(db.Integer, nullable=True)
    container_count = db.Column(db.Integer, nullable=True)
    gross_weight = db.Column(db.Float, nullable=True)
    hot_flag = db.Column(db.Boolean, nullable=False, default=False)
    arrived_at = db.Column(db.DateTime, nullable=True)
    departed_at = db.Column(db.DateTime, nullable=True)
    elapsed_minutes = db.Column(db.Integer, nullable=True)
    included_in_average = db.Column(db.Boolean, nullable=False, default=True)
    excluded_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stop = db.relationship("DriverLog", backref="plant_time_samples")
