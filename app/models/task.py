from datetime import datetime

from app.extensions import db


class Task(db.Model):
    __tablename__ = "task"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text)
    part_number = db.Column(db.String(80), nullable=True)
    is_hot = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="pending")
    shift = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    accepted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    accepted_by = db.relationship("User", foreign_keys=[accepted_by_id])
    completed_by = db.relationship("User", foreign_keys=[completed_by_id])
