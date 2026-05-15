from datetime import datetime

from app.extensions import db


class OperationalFollowUp(db.Model):
    __tablename__ = "operational_follow_up"

    id = db.Column(db.Integer, primary_key=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    plant_name = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship("User", backref="operational_followups")
