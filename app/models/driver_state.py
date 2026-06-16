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


class DriverDayState(db.Model):
    """Per-driver, per-calendar-day copy of one-driver app state.

    This lets the app fetch a single trip/fuel day without moving the driver's
    entire history over the wire. The full DriverState row stays as a backup
    while the client is migrated toward day-scoped reads and writes.
    """

    __tablename__ = "driver_day_state"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    day_key = db.Column(db.String(10), nullable=False, index=True)
    data = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "day_key", name="uq_driver_day_state_user_day"),
    )
