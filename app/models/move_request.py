from datetime import datetime

from app.extensions import db


class MoveRequest(db.Model):
    __tablename__ = "move_request"

    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(50), unique=True, nullable=True, index=True)
    source = db.Column(db.String(30), nullable=False, default="manual", index=True)
    raw_text = db.Column(db.Text, nullable=False)
    requested_by = db.Column(db.String(120), nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    request_type = db.Column(db.String(30), nullable=False, default="move", index=True)
    priority = db.Column(db.String(20), nullable=False, default="normal", index=True)
    origin_location_text = db.Column(db.String(160), nullable=True)
    destination_location_text = db.Column(db.String(160), nullable=True)
    cargo_text = db.Column(db.Text, nullable=True)
    part_number = db.Column(db.String(80), nullable=True, index=True)
    quantity_value = db.Column(db.Float, nullable=True)
    quantity_unit = db.Column(db.String(40), nullable=True)
    quantity_text = db.Column(db.String(120), nullable=True)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    due_time_text = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="open", index=True)
    blocked_reason = db.Column(db.Text, nullable=True)
    closed_reason = db.Column(db.Text, nullable=True)
    assigned_driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    assigned_driver_text = db.Column(db.String(120), nullable=True)
    equipment_id = db.Column(db.String(80), nullable=True)
    equipment_text = db.Column(db.String(120), nullable=True)
    linked_driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    linked_route_id = db.Column(db.String(80), nullable=True, index=True)
    linked_plant_transfer_id = db.Column(db.Integer, db.ForeignKey("plant_transfer.id"), nullable=True, index=True)
    linked_document_id = db.Column(db.Integer, db.ForeignKey("external_document.id"), nullable=True)
    parsed_confidence = db.Column(db.String(30), nullable=True)
    parse_warnings = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assigned_driver = db.relationship("User", foreign_keys=[assigned_driver_id], backref="assigned_move_requests")
    created_by = db.relationship("User", foreign_keys=[created_by_id], backref="created_move_requests")
    updated_by = db.relationship("User", foreign_keys=[updated_by_id], backref="updated_move_requests")
    linked_driver_log = db.relationship("DriverLog", foreign_keys=[linked_driver_log_id], backref="move_requests")
    linked_plant_transfer = db.relationship("PlantTransfer", foreign_keys=[linked_plant_transfer_id], backref="move_requests")
    linked_document = db.relationship("ExternalDocument", foreign_keys=[linked_document_id], backref="move_requests")

    @property
    def display_number(self):
        return self.request_number or f"MR-{self.id:03d}"

    @property
    def quantity_display(self):
        if self.quantity_text:
            return self.quantity_text
        if self.quantity_value is None:
            return ""
        value = int(self.quantity_value) if float(self.quantity_value).is_integer() else self.quantity_value
        return f"{value} {self.quantity_unit or ''}".strip()

    @property
    def cargo_part_display(self):
        parts = []
        if self.cargo_text:
            parts.append(self.cargo_text)
        if self.part_number and self.part_number not in parts:
            parts.append(self.part_number)
        return " / ".join(parts)

    @property
    def assigned_display(self):
        if self.assigned_driver:
            return self.assigned_driver.manager_label
        return self.assigned_driver_text or ""

    @property
    def equipment_display(self):
        return self.equipment_text or self.equipment_id or ""
