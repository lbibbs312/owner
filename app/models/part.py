from datetime import datetime

from app.extensions import db


class PartMaster(db.Model):
    __tablename__ = "part_master"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    canonical_part_number = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    customer = db.Column(db.String(120), nullable=True)
    program = db.Column(db.String(120), nullable=True)
    default_origin_plant_id = db.Column(db.String(50), nullable=True)
    default_destination_plant_id = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    active = db.Column(db.Boolean, nullable=False, default=True)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    seen_count = db.Column(db.Integer, nullable=False, default=0)

    aliases = db.relationship(
        "PartAlias",
        backref="part",
        cascade="all, delete-orphan",
        order_by="PartAlias.last_seen_at.desc()",
    )


class PartAlias(db.Model):
    __tablename__ = "part_alias"

    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=False)
    raw_barcode_value = db.Column(db.String(255), nullable=False)
    normalized_value = db.Column(db.String(120), nullable=False, index=True)
    symbology = db.Column(db.String(80), nullable=True)
    label_source = db.Column(db.String(80), nullable=True)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class PartScanEvent(db.Model):
    __tablename__ = "part_scan_event"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    raw_value = db.Column(db.String(255), nullable=False)
    normalized_value = db.Column(db.String(120), nullable=False, index=True)
    barcode_format = db.Column(db.String(80), nullable=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=True)
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    truck_id = db.Column(db.String(50), nullable=True)
    trailer_id = db.Column(db.String(50), nullable=True)
    plant_id = db.Column(db.String(50), nullable=True)
    scan_context = db.Column(db.String(40), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    device_id = db.Column(db.String(120), nullable=True)
    gps_lat = db.Column(db.Float, nullable=True)
    gps_lng = db.Column(db.Float, nullable=True)
    validation_status = db.Column(db.String(40), nullable=False, default="recorded")
    validation_message = db.Column(db.String(255), nullable=True)
    created_offline = db.Column(db.Boolean, nullable=False, default=False)
    synced_at = db.Column(db.DateTime, nullable=True)
    damage_report_id = db.Column(db.Integer, db.ForeignKey("damage_report.id"), nullable=True)
    delay_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)

    part = db.relationship("PartMaster", backref="scan_events")
    move = db.relationship("Task", backref="part_scan_events")
    stop = db.relationship("DriverLog", foreign_keys=[stop_id], backref="part_scan_events")
    driver = db.relationship("User", backref="part_scan_events")
    damage_report = db.relationship("DamageReport", backref="part_scan_events")
    delay_log = db.relationship("DriverLog", foreign_keys=[delay_log_id], backref="delay_part_scan_events")


class MovePart(db.Model):
    __tablename__ = "move_part"

    id = db.Column(db.Integer, primary_key=True)
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=False)
    expected_quantity = db.Column(db.Integer, nullable=False, default=1)
    picked_quantity = db.Column(db.Integer, nullable=False, default=0)
    dropped_quantity = db.Column(db.Integer, nullable=False, default=0)
    current_status = db.Column(db.String(40), nullable=False, default="expected")
    expected_drop_stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    actual_drop_stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)

    move = db.relationship("Task", backref="move_parts")
    part = db.relationship("PartMaster", backref="move_parts")
    expected_drop_stop = db.relationship("DriverLog", foreign_keys=[expected_drop_stop_id])
    actual_drop_stop = db.relationship("DriverLog", foreign_keys=[actual_drop_stop_id])


class PartLocationHistory(db.Model):
    __tablename__ = "part_location_history"

    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=False)
    plant_id = db.Column(db.String(50), nullable=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    status = db.Column(db.String(40), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    source_scan_event_id = db.Column(db.Integer, db.ForeignKey("part_scan_event.id"), nullable=True)

    part = db.relationship("PartMaster", backref="location_history")
    stop = db.relationship("DriverLog", backref="part_location_history")
    move = db.relationship("Task", backref="part_location_history")
    source_scan_event = db.relationship("PartScanEvent", backref="location_history")
