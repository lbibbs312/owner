from datetime import date, datetime

from app.extensions import db


class FlowEvent(db.Model):
    __tablename__ = "flow_event"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.String(80), nullable=False, index=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    manifest_id = db.Column(db.Integer, db.ForeignKey("flow_manifest.id"), nullable=True, index=True)
    vehicle_id = db.Column(db.String(80), nullable=True, index=True)
    trailer_id = db.Column(db.String(80), nullable=True, index=True)
    container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=True, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("container_item.id"), nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    actor_role = db.Column(db.String(40), nullable=True)
    origin_node_id = db.Column(db.String(80), nullable=True, index=True)
    destination_node_id = db.Column(db.String(80), nullable=True, index=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    device_id = db.Column(db.String(120), nullable=True, index=True)
    offline_event_id = db.Column(db.String(120), nullable=True, index=True)
    correlation_id = db.Column(db.String(120), nullable=True, index=True)
    source = db.Column(db.String(30), nullable=False, default="system", index=True)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    notes = db.Column(db.Text, nullable=True)
    photo_id = db.Column(db.Integer, nullable=True)
    document_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("User", backref="flow_events")
    stop = db.relationship("DriverLog", backref="flow_events")
    manifest = db.relationship("FlowManifest", backref="events", foreign_keys=[manifest_id])
    container = db.relationship("FlowContainer", backref="events", foreign_keys=[container_id])
    item = db.relationship("ContainerItem", backref="events", foreign_keys=[item_id])

    __table_args__ = (
        db.Index(
            "ix_flow_event_offline_idempotency",
            "tenant_id",
            "device_id",
            "offline_event_id",
        ),
        db.Index(
            "uq_flow_event_offline_idempotency_present",
            "tenant_id",
            "device_id",
            "offline_event_id",
            unique=True,
            sqlite_where=db.text("device_id IS NOT NULL AND offline_event_id IS NOT NULL"),
            postgresql_where=db.text("device_id IS NOT NULL AND offline_event_id IS NOT NULL"),
        ),
    )


class EntityCurrentState(db.Model):
    __tablename__ = "entity_current_state"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.String(80), nullable=False, index=True)
    current_status = db.Column(db.String(60), nullable=False, default="unknown", index=True)
    current_node_id = db.Column(db.String(80), nullable=True, index=True)
    parent_container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=True, index=True)
    active_manifest_id = db.Column(db.Integer, db.ForeignKey("flow_manifest.id"), nullable=True, index=True)
    active_route_id = db.Column(db.String(80), nullable=True, index=True)
    last_event_id = db.Column(db.Integer, db.ForeignKey("flow_event.id"), nullable=True)
    last_event_at = db.Column(db.DateTime, nullable=True, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    parent_container = db.relationship("FlowContainer", foreign_keys=[parent_container_id])
    active_manifest = db.relationship("FlowManifest", foreign_keys=[active_manifest_id])
    last_event = db.relationship("FlowEvent", foreign_keys=[last_event_id])

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_entity_current_state_entity"),
    )


class FlowNodeSnapshot(db.Model):
    __tablename__ = "flow_node_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    node_id = db.Column(db.String(80), nullable=False, index=True)
    snapshot_date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    wip_count = db.Column(db.Integer, nullable=False, default=0)
    staged_count = db.Column(db.Integer, nullable=False, default=0)
    loaded_count = db.Column(db.Integer, nullable=False, default=0)
    in_transit_count = db.Column(db.Integer, nullable=False, default=0)
    received_count = db.Column(db.Integer, nullable=False, default=0)
    blocked_count = db.Column(db.Integer, nullable=False, default=0)
    proof_needed_count = db.Column(db.Integer, nullable=False, default=0)
    exception_count = db.Column(db.Integer, nullable=False, default=0)
    last_event_id = db.Column(db.Integer, db.ForeignKey("flow_event.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "node_id", "snapshot_date", name="uq_flow_node_snapshot_day"),
    )


class ContainerType(db.Model):
    __tablename__ = "container_type"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    name = db.Column(db.String(80), nullable=False)
    code = db.Column(db.String(40), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "code", name="uq_container_type_tenant_code"),
    )


class FlowContainer(db.Model):
    __tablename__ = "flow_container"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    container_type_id = db.Column(db.Integer, db.ForeignKey("container_type.id"), nullable=False, index=True)
    identifier = db.Column(db.String(120), nullable=False, index=True)
    parent_container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=True, index=True)
    current_node_id = db.Column(db.String(80), nullable=True, index=True)
    current_status = db.Column(db.String(60), nullable=False, default="unknown", index=True)
    capacity_units = db.Column(db.Float, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    container_type = db.relationship("ContainerType", backref="containers")
    parent_container = db.relationship("FlowContainer", remote_side=[id], backref="child_containers")
    items = db.relationship("ContainerItem", backref="container", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "identifier", name="uq_flow_container_identifier"),
    )


class ContainerItem(db.Model):
    __tablename__ = "container_item"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=False, index=True)
    part_sku = db.Column(db.String(120), nullable=True, index=True)
    serial_number = db.Column(db.String(120), nullable=True, index=True)
    lot_id = db.Column(db.String(120), nullable=True, index=True)
    delivery_order_number = db.Column(db.String(120), nullable=True, index=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    disposition = db.Column(db.String(60), nullable=True, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.CheckConstraint("quantity >= 0", name="ck_container_item_quantity_nonnegative"),
    )


class ContainerTreeSnapshot(db.Model):
    __tablename__ = "container_tree_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=False, index=True)
    parent_container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=True, index=True)
    root_container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=False, index=True)
    current_node_id = db.Column(db.String(80), nullable=True, index=True)
    current_status = db.Column(db.String(60), nullable=False, default="unknown", index=True)
    current_quantity = db.Column(db.Float, nullable=False, default=0)
    active_manifest_id = db.Column(db.Integer, db.ForeignKey("flow_manifest.id"), nullable=True, index=True)
    last_event_id = db.Column(db.Integer, db.ForeignKey("flow_event.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    container = db.relationship("FlowContainer", foreign_keys=[container_id])

    __table_args__ = (
        db.CheckConstraint("current_quantity >= 0", name="ck_container_tree_snapshot_quantity_nonnegative"),
        db.UniqueConstraint("tenant_id", "container_id", name="uq_container_tree_snapshot_container"),
    )


class FlowManifest(db.Model):
    __tablename__ = "flow_manifest"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    manifest_number = db.Column(db.String(120), nullable=False, index=True)
    shipper_id = db.Column(db.String(120), nullable=True, index=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    vehicle_id = db.Column(db.String(80), nullable=True, index=True)
    trailer_id = db.Column(db.String(80), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    origin_node_id = db.Column(db.String(80), nullable=True, index=True)
    destination_node_id = db.Column(db.String(80), nullable=True, index=True)
    current_status = db.Column(db.String(60), nullable=False, default="draft", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    driver = db.relationship("User", backref="flow_manifests")
    lines = db.relationship("ManifestLine", backref="manifest", cascade="all, delete-orphan", order_by="ManifestLine.id")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "manifest_number", name="uq_flow_manifest_number"),
    )


class ManifestLine(db.Model):
    __tablename__ = "manifest_line"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    manifest_id = db.Column(db.Integer, db.ForeignKey("flow_manifest.id"), nullable=False, index=True)
    delivery_order_number = db.Column(db.String(120), nullable=True, index=True)
    part_sku = db.Column(db.String(120), nullable=True, index=True)
    serial_number = db.Column(db.String(120), nullable=True, index=True)
    lot_id = db.Column(db.String(120), nullable=True, index=True)
    container_id = db.Column(db.Integer, db.ForeignKey("flow_container.id"), nullable=True, index=True)
    quantity_expected = db.Column(db.Float, nullable=False, default=0)
    quantity_scanned = db.Column(db.Float, nullable=False, default=0)
    scan_status = db.Column(db.String(60), nullable=False, default="pending", index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)

    container = db.relationship("FlowContainer", backref="manifest_lines")

    __table_args__ = (
        db.CheckConstraint("quantity_expected >= 0", name="ck_manifest_line_expected_nonnegative"),
        db.CheckConstraint("quantity_scanned >= 0", name="ck_manifest_line_scanned_nonnegative"),
        db.CheckConstraint(
            "quantity_scanned <= quantity_expected",
            name="ck_manifest_line_scanned_not_over_expected",
        ),
    )
