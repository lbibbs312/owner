from datetime import datetime

from app.extensions import db


class DraftEntry(db.Model):
    __tablename__ = "draft_entry"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    draft_key = db.Column(db.String(255), nullable=False)
    form_id = db.Column(db.String(120), nullable=True)
    path = db.Column(db.String(500), nullable=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="draft_entries")

    __table_args__ = (
        db.UniqueConstraint("user_id", "draft_key", name="uq_draft_entry_user_key"),
        db.Index("ix_draft_entry_user_updated", "user_id", "updated_at"),
    )
