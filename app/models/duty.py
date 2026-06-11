from datetime import datetime

from app.extensions import db


class DutyStatusEvent(db.Model):
    """A driver-entered duty status change (OFF / SB / D / ON) for the Daily Log.

    Same philosophy as RouteBreak: stores only what the driver actually tapped,
    with an optional location/note like the paper logbook's remarks line. The
    Daily Log grid merges these with events derived from captures the app
    already records (shift start/end, breaks, stop arrive/depart). Driver-entered
    record of duty status - not a certified ELD.
    """

    __tablename__ = "duty_status_event"

    STATUSES = ("off", "sb", "d", "on")

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(4), nullable=False)
    at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    location = db.Column(db.String(160), nullable=True)
    note = db.Column(db.String(200), nullable=True)
    source = db.Column(db.String(20), nullable=False, default="manual")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="duty_status_events")
