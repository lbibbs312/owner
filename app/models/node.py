from datetime import datetime

from app.extensions import db


NODE_TYPE_PRODUCTION_LINE = "PRODUCTION_LINE"
NODE_TYPE_STAGING_BAY = "STAGING_BAY"
NODE_TYPE_YARD_SLOT = "YARD_SLOT"
NODE_TYPE_RECEIVING_DOCK = "RECEIVING_DOCK"
NODE_TYPE_PLANT = "PLANT"

NODE_TYPES = (
    NODE_TYPE_PRODUCTION_LINE,
    NODE_TYPE_STAGING_BAY,
    NODE_TYPE_YARD_SLOT,
    NODE_TYPE_RECEIVING_DOCK,
    NODE_TYPE_PLANT,
)


class Node(db.Model):
    __tablename__ = "node"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    key = db.Column(db.String(120), nullable=False, index=True)
    short_code = db.Column(db.String(40), nullable=True, index=True)
    label = db.Column(db.String(160), nullable=False)
    node_type = db.Column(db.String(40), nullable=False, default=NODE_TYPE_PLANT, index=True)
    allowed_equipment_types = db.Column(db.JSON, nullable=False, default=list)
    section = db.Column(db.String(80), nullable=True)
    row = db.Column(db.String(80), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "key", name="uq_node_tenant_key"),
    )

    def allows(self, equipment_type):
        if not self.allowed_equipment_types:
            return True
        return equipment_type in self.allowed_equipment_types
