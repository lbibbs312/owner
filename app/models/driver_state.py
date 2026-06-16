from datetime import datetime

from app.extensions import db


class DriverState(db.Model):
    """Server-side copy of a one-driver app's full client state (the `S` blob).

    One row per user. Lets the welcome.html logger sync and survive across
    browsers, the installed Android app, and devices, instead of living only in
    each browser's localStorage.
    """

    __tablename__ = "driver_state"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False, index=True
    )
    data = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
