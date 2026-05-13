from datetime import datetime

from app.extensions import db


class ActivityEvent(db.Model):
    __tablename__ = "activity_event"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text, nullable=True)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="activity_events")
