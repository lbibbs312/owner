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


class DriverPresence(db.Model):
    """Live telemetry summary for the one-driver welcome app.

    One row per driver, updated by lightweight client heartbeats while the app
    is open. This is intentionally separate from DriverState so owner telemetry
    can update frequently without rewriting the full client state blob.
    """

    __tablename__ = "driver_presence"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False, index=True
    )
    session_id = db.Column(db.String(80), nullable=True)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True, index=True)
    last_heartbeat_at = db.Column(db.DateTime, nullable=True)
    active_day_key = db.Column(db.String(10), nullable=True, index=True)
    active_today_seconds = db.Column(db.Integer, nullable=False, default=0)
    total_active_seconds = db.Column(db.Integer, nullable=False, default=0)
    screen = db.Column(db.String(32), nullable=True)
    route_state = db.Column(db.String(32), nullable=True)
    location_label = db.Column(db.String(160), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    state = db.Column(db.String(40), nullable=True)
    current_target = db.Column(db.String(160), nullable=True)
    stop_count = db.Column(db.Integer, nullable=False, default=0)
    export_count = db.Column(db.Integer, nullable=False, default=0)
    last_export_at = db.Column(db.DateTime, nullable=True)
    last_export_type = db.Column(db.String(40), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DriverActivityEvent(db.Model):
    """Owner-visible activity events from the welcome app."""

    __tablename__ = "driver_activity_event"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    event_type = db.Column(db.String(32), nullable=False, index=True)
    event_label = db.Column(db.String(128), nullable=True)
    session_id = db.Column(db.String(80), nullable=True)
    screen = db.Column(db.String(32), nullable=True)
    location_label = db.Column(db.String(160), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    state = db.Column(db.String(40), nullable=True)
    metadata_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
