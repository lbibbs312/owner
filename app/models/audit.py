from datetime import datetime

from app.extensions import db


class AuditEvent(db.Model):
    __tablename__ = "audit_event"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers", index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(50), nullable=False)
    correlation_id = db.Column(db.String(120), nullable=True, index=True)
    reason = db.Column(db.Text, nullable=False)
    before_values = db.Column(db.Text, nullable=True)
    after_values = db.Column(db.Text, nullable=True)
    before_json = db.Column(db.JSON, nullable=True)
    after_json = db.Column(db.JSON, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="audit_events")
