"""AutoLog: automatic GPS/motion-driven driver logging.

The driver taps BEGIN and drives. The app records movement locally, detects
stops and wait time, guesses likely places and candidate actions, and lets the
driver review/confirm/edit/delete later. Confirmed corrections train memory so
future suggestions improve.

Nothing here is the source of truth for the driver's official record until the
driver CONFIRMS it — CandidateStop / CandidateAction are guesses; ConfirmedStop
is the driver-blessed result. Everything is captured offline-first (the client
writes locally and replays through SyncOutbox), so logging never blocks on the
network.
"""
from datetime import datetime

from app.extensions import db


# Live states the active screen can be in (kept minimal on purpose).
LIVE_STATES = (
    "READY",
    "DRIVING",
    "WAITING",
    "STOPPED",
    "FUEL_STOP",
    "BREAK",
    "SERVICE",
    "LEARNING_STOP",
    "NEEDS_REVIEW",
    "ROUTE_COMPLETE",
)

ACTION_TYPES = ("pickup", "delivery", "fuel", "break", "service", "unknown")


class AutoLogSession(db.Model):
    """One BEGIN→complete route. Holds the current live state for the screen."""

    __tablename__ = "autolog_session"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")  # active | complete
    live_state = db.Column(db.String(20), nullable=False, default="READY")
    # The candidate stop currently open (driver is parked there), if any.
    current_candidate_stop_id = db.Column(db.Integer, nullable=True)
    last_point_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")
    points = db.relationship("RawLocationPoint", backref="session", cascade="all, delete-orphan")
    segments = db.relationship("MotionSegment", backref="session", cascade="all, delete-orphan")
    candidate_stops = db.relationship(
        "CandidateStop", backref="session", cascade="all, delete-orphan",
        order_by="CandidateStop.sequence.asc()",
    )


class RawLocationPoint(db.Model):
    """A single GPS/motion sample. client_id makes offline replay idempotent."""

    __tablename__ = "autolog_location_point"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    client_id = db.Column(db.String(80), nullable=True, index=True)  # de-dupe on resync
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy_m = db.Column(db.Float, nullable=True)
    speed_mps = db.Column(db.Float, nullable=True)
    heading = db.Column(db.Float, nullable=True)
    moving = db.Column(db.Boolean, nullable=True)  # engine-derived
    recorded_at = db.Column(db.DateTime, nullable=False)  # client clock
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # server receipt

    __table_args__ = (
        db.UniqueConstraint("session_id", "client_id", name="uq_autolog_point_session_client"),
    )


class MotionSegment(db.Model):
    """A continuous stretch of DRIVING or STOPPED inferred from the points."""

    __tablename__ = "autolog_motion_segment"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)  # driving | stopped
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    start_latitude = db.Column(db.Float, nullable=True)
    start_longitude = db.Column(db.Float, nullable=True)
    end_latitude = db.Column(db.Float, nullable=True)
    end_longitude = db.Column(db.Float, nullable=True)
    distance_m = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CandidateStop(db.Model):
    """A stop the engine detected from a GPS cluster + dwell. A GUESS until the
    driver confirms it. While open the live screen shows WAITING with a timer."""

    __tablename__ = "autolog_candidate_stop"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    sequence = db.Column(db.Integer, nullable=False, default=1)
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    arrived_at = db.Column(db.DateTime, nullable=False)
    departed_at = db.Column(db.DateTime, nullable=True)
    dwell_seconds = db.Column(db.Integer, nullable=False, default=0)
    place_memory_id = db.Column(db.Integer, db.ForeignKey("autolog_place_memory.id"), nullable=True)
    likely_place_label = db.Column(db.String(120), nullable=True)  # None => Learning stop
    # open (driver still parked) | closed (left) | confirmed | deleted
    status = db.Column(db.String(20), nullable=False, default="open")
    needs_review = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    place_memory = db.relationship("PlaceMemory")
    actions = db.relationship(
        "CandidateAction", backref="candidate_stop", cascade="all, delete-orphan",
        order_by="CandidateAction.id.asc()",
    )


class CandidateAction(db.Model):
    """An inferred pickup/delivery/fuel/break/service at a candidate stop. Not
    final until the driver confirms it."""

    __tablename__ = "autolog_candidate_action"

    id = db.Column(db.Integer, primary_key=True)
    candidate_stop_id = db.Column(db.Integer, db.ForeignKey("autolog_candidate_stop.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    action_type = db.Column(db.String(20), nullable=False, default="unknown")
    confidence = db.Column(db.String(10), nullable=False, default="low")  # low | medium | high
    suggested_label = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(12), nullable=False, default="suggested")  # suggested | confirmed | rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ConfirmedStop(db.Model):
    """A stop the driver confirmed/edited from the review screen. This is the
    blessed record AutoLog promotes into the official log."""

    __tablename__ = "autolog_confirmed_stop"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    candidate_stop_id = db.Column(db.Integer, db.ForeignKey("autolog_candidate_stop.id"), nullable=True)
    place_memory_id = db.Column(db.Integer, db.ForeignKey("autolog_place_memory.id"), nullable=True)
    sequence = db.Column(db.Integer, nullable=False, default=1)
    label = db.Column(db.String(120), nullable=True)
    action_type = db.Column(db.String(20), nullable=False, default="unknown")
    cargo_label = db.Column(db.String(120), nullable=True)
    weight = db.Column(db.String(40), nullable=True)
    arrived_at = db.Column(db.DateTime, nullable=True)
    departed_at = db.Column(db.DateTime, nullable=True)
    confirmed_at = db.Column(db.DateTime, default=datetime.utcnow)


class DriverMemory(db.Model):
    """Per-driver learned values (loads/commodities/actions) surfaced as one-tap
    chips, ranked by use. The 'remember loads/cargo' requirement for drivers
    with no GPS-place history."""

    __tablename__ = "autolog_driver_memory"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    memory_type = db.Column(db.String(20), nullable=False, default="load")  # load | action
    value = db.Column(db.String(120), nullable=False)
    normalized_value = db.Column(db.String(120), nullable=False)
    use_count = db.Column(db.Integer, nullable=False, default=1)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "memory_type", "normalized_value", name="uq_autolog_driver_memory"),
    )


class PlaceMemory(db.Model):
    """A learned place (geofence) for a driver. Matching a candidate stop to one
    of these is what lets the app prefill a likely stop and the usual load."""

    __tablename__ = "autolog_place_memory"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    radius_m = db.Column(db.Float, nullable=False, default=90.0)
    place_type = db.Column(db.String(20), nullable=False, default="unknown")  # pickup|delivery|fuel|service|yard|unknown
    usual_load = db.Column(db.String(120), nullable=True)
    visit_count = db.Column(db.Integer, nullable=False, default=1)
    last_visited_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RouteReviewQueue(db.Model):
    """One pending review item per candidate stop that needs the driver's
    confirmation. Drives the 'N stops need confirmation' line."""

    __tablename__ = "autolog_review_queue"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    candidate_stop_id = db.Column(db.Integer, db.ForeignKey("autolog_candidate_stop.id"), nullable=False)
    reason = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(12), nullable=False, default="pending")  # pending | resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SyncOutbox(db.Model):
    """Server-side ledger of client events received offline-first. The client
    keeps its own outbox and replays; client_event_id de-dupes so a replay never
    double-applies."""

    __tablename__ = "autolog_sync_outbox"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("autolog_session.id"), nullable=True)
    client_event_id = db.Column(db.String(80), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.JSON, nullable=True)
    applied = db.Column(db.Boolean, nullable=False, default=False)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "client_event_id", name="uq_autolog_sync_client_event"),
    )
