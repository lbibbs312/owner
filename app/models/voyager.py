from datetime import datetime

from app.extensions import db


EQUIPMENT_TRAILER = "TRAILER"
EQUIPMENT_STRAIGHT_TRUCK = "STRAIGHT_TRUCK"
EQUIPMENT_FORKLIFT = "FORKLIFT"
EQUIPMENT_SHUTTLE = "SHUTTLE"
EQUIPMENT_TYPES = (EQUIPMENT_TRAILER, EQUIPMENT_STRAIGHT_TRUCK, EQUIPMENT_FORKLIFT, EQUIPMENT_SHUTTLE)

UTILIZATION_EMPTY = "EMPTY"
UTILIZATION_QUARTER = "QUARTER"
UTILIZATION_HALF = "HALF"
UTILIZATION_THREE_QUARTER = "THREE_QUARTER"
UTILIZATION_FULL = "FULL"
UTILIZATION_STEPS = (
    UTILIZATION_EMPTY,
    UTILIZATION_QUARTER,
    UTILIZATION_HALF,
    UTILIZATION_THREE_QUARTER,
    UTILIZATION_FULL,
)

VOYAGER_AVAILABLE = "AVAILABLE"
VOYAGER_EN_ROUTE = "EN_ROUTE"
VOYAGER_LOADING = "LOADING"
VOYAGER_UNLOADING = "UNLOADING"
VOYAGER_OUT_OF_SERVICE = "OUT_OF_SERVICE"


class Voyager(db.Model):
    __tablename__ = "voyager"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    equipment_id = db.Column(db.String(80), nullable=False, index=True)
    equipment_type = db.Column(db.String(40), nullable=False, default=EQUIPMENT_TRAILER, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    current_node_key = db.Column(db.String(120), nullable=True, index=True)
    current_status = db.Column(db.String(40), nullable=False, default=VOYAGER_AVAILABLE, index=True)
    current_load_utilization = db.Column(db.String(20), nullable=False, default=UTILIZATION_EMPTY)
    current_manifest_id = db.Column(db.Integer, db.ForeignKey("flow_manifest.id"), nullable=True, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    driver = db.relationship("User", backref="voyagers")
    current_manifest = db.relationship("FlowManifest", foreign_keys=[current_manifest_id])

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "equipment_id", name="uq_voyager_tenant_equipment"),
    )
