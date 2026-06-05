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

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "canonical_part_number", name="uq_part_master_tenant_canonical"),
    )


class PartAlias(db.Model):
    __tablename__ = "part_alias"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=False)
    raw_scan_value = db.Column(db.String(255), nullable=False, default="")
    raw_barcode_value = db.Column(db.String(255), nullable=False)
    normalized_value = db.Column(db.String(120), nullable=False, index=True)
    label_format = db.Column(db.String(80), nullable=True)
    symbology = db.Column(db.String(80), nullable=True)
    label_source = db.Column(db.String(80), nullable=True)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "normalized_value", name="uq_part_alias_tenant_normalized"),
    )


class PartScanEvent(db.Model):
    __tablename__ = "part_scan_event"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    raw_value = db.Column(db.String(255), nullable=False)
    normalized_value = db.Column(db.String(120), nullable=False, index=True)
    barcode_format = db.Column(db.String(80), nullable=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=True)
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
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
    driver_log = db.relationship("DriverLog", foreign_keys=[driver_log_id], backref="driver_log_part_scan_events")
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

    __table_args__ = (
        db.CheckConstraint("expected_quantity >= 0", name="ck_move_part_expected_quantity_nonnegative"),
        db.CheckConstraint("picked_quantity >= 0", name="ck_move_part_picked_quantity_nonnegative"),
        db.CheckConstraint("dropped_quantity >= 0", name="ck_move_part_dropped_quantity_nonnegative"),
        db.CheckConstraint(
            "picked_quantity <= expected_quantity",
            name="ck_move_part_picked_not_over_expected",
        ),
        db.CheckConstraint(
            "dropped_quantity <= expected_quantity",
            name="ck_move_part_dropped_not_over_expected",
        ),
    )


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


class HotPartAlert(db.Model):
    __tablename__ = "hot_part_alert"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=True)
    raw_part_number = db.Column(db.String(120), nullable=True)
    priority = db.Column(db.String(30), nullable=False, default="hot")
    source = db.Column(db.String(30), nullable=False, default="dispatch")
    status = db.Column(db.String(30), nullable=False, default="active")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    cleared_at = db.Column(db.DateTime, nullable=True)

    part = db.relationship("PartMaster", backref="hot_part_alerts")
    created_by_user = db.relationship("User", backref="created_hot_part_alerts")


class HotMove(db.Model):
    __tablename__ = "hot_move"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    hot_part_alert_id = db.Column(db.Integer, db.ForeignKey("hot_part_alert.id"), nullable=True)
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    truck_id = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="assigned")
    accepted_at = db.Column(db.DateTime, nullable=True)
    picked_up_at = db.Column(db.DateTime, nullable=True)
    dropped_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    alert = db.relationship("HotPartAlert", backref="hot_moves")
    move = db.relationship("Task", backref="hot_moves")
    driver = db.relationship("User", backref="hot_moves")


class HotPartPhoto(db.Model):
    __tablename__ = "hot_part_photo"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by = db.relationship("User", backref="hot_part_photos")


class HotPartEvent(db.Model):
    __tablename__ = "hot_part_event"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    hot_move_id = db.Column(db.Integer, db.ForeignKey("hot_move.id"), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=True)
    event_type = db.Column(db.String(40), nullable=False)
    raw_scan_value = db.Column(db.String(255), nullable=True)
    normalized_scan_value = db.Column(db.String(120), nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey("hot_part_photo.id"), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    truck_id = db.Column(db.String(50), nullable=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    plant_id = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_offline = db.Column(db.Boolean, nullable=False, default=False)
    synced_at = db.Column(db.DateTime, nullable=True)

    hot_move = db.relationship("HotMove", backref=db.backref("events", order_by="HotPartEvent.timestamp"))
    part = db.relationship("PartMaster", backref="hot_part_events")
    photo = db.relationship("HotPartPhoto", backref="hot_part_events")
    driver = db.relationship("User", backref="hot_part_events")
    stop = db.relationship("DriverLog", backref="hot_part_events")


class PartRouteProfile(db.Model):
    __tablename__ = "part_route_profile"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    part_id = db.Column(db.Integer, db.ForeignKey("part_master.id"), nullable=False)
    origin_plant_id = db.Column(db.String(50), nullable=True)
    destination_plant_id = db.Column(db.String(50), nullable=True)
    route_label = db.Column(db.String(120), nullable=True)
    times_completed = db.Column(db.Integer, nullable=False, default=0)
    times_exception = db.Column(db.Integer, nullable=False, default=0)
    confidence_score = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(30), nullable=False, default="pending")
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    part = db.relationship("PartMaster", backref="route_profiles")


class ExternalDocument(db.Model):
    __tablename__ = "external_document"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    move_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    document_type = db.Column(db.String(30), nullable=False, default="other")
    file_id = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    move = db.relationship("Task", backref="external_documents")
    uploaded_by_user = db.relationship("User", backref="external_documents")
