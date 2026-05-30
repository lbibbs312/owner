from datetime import datetime

from app.extensions import db


class DispatchCapture(db.Model):
    __tablename__ = "dispatch_capture"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    raw_text = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(40), nullable=False, default="manager_dashboard", index=True)
    captured_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    guessed_type = db.Column(db.String(40), nullable=True, index=True)
    priority = db.Column(db.String(20), nullable=False, default="normal", index=True)
    confidence = db.Column(db.String(20), nullable=True)
    extracted_from_node = db.Column(db.String(160), nullable=True)
    extracted_to_node = db.Column(db.String(160), nullable=True)
    extracted_part_numbers = db.Column(db.Text, nullable=True)
    extracted_trailer_ids = db.Column(db.Text, nullable=True)
    extracted_quantities = db.Column(db.Text, nullable=True)
    extracted_people = db.Column(db.Text, nullable=True)
    missing_fields_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="captured", index=True)
    converted_entity_type = db.Column(db.String(50), nullable=True)
    converted_entity_id = db.Column(db.Integer, nullable=True, index=True)

    captured_by_user = db.relationship("User", foreign_keys=[captured_by], backref="dispatch_captures")

    @property
    def display_number(self):
        return f"CAP-{self.id:03d}"
