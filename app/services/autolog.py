"""AutoLog engine: turn a stream of GPS/motion points into detected stops,
candidate actions, a minimal live-screen state, and learned memory.

Design rules baked in here:
- The driver taps BEGIN and drives; everything else is inferred.
- Detection is a guess (CandidateStop/CandidateAction). Nothing is final until
  the driver confirms (ConfirmedStop), which is also what TRAINS memory.
- Recompute is idempotent: re-processing the same points yields the same stops,
  so offline replay / out-of-order sync is safe.
- The live view shows only what's needed right now (status, timer, one line,
  at most one action) — never a board, feed, map, or checklist.
"""
import math
import re
from datetime import datetime

from app.extensions import db
from app.models import (
    AutoLogSession,
    CandidateAction,
    CandidateStop,
    ConfirmedStop,
    DriverMemory,
    MotionSegment,
    PlaceMemory,
    RawLocationPoint,
    RouteReviewQueue,
)

# --- tuning constants (meters / seconds / m·s⁻¹) --------------------------------
STOP_SPEED_MPS = 2.2          # ~5 mph: below this the truck is parked
STOP_RADIUS_M = 60.0         # points within this of an anchor cluster together
DEPART_RADIUS_M = 90.0       # moved past this from the cluster center => left
DWELL_THRESHOLD_S = 180      # a cluster must last this long to be a real stop
FUEL_DWELL_MAX_S = 1200      # a short stop at a fuel place looks like fueling
BREAK_DWELL_MIN_S = 1500     # a long dwell off a known place looks like a break
DEFAULT_PLACE_RADIUS_M = 150.0


def haversine_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in meters."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _normalize(value):
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


# --- pure detection -------------------------------------------------------------

def detect_clusters(points):
    """Pure: given time-ordered point dicts, return (stops, driving_spans).

    Each point dict: {latitude, longitude, speed_mps (optional), recorded_at}.
    A stop is a run of points that stays within STOP_RADIUS_M long enough to pass
    DWELL_THRESHOLD_S. Driving spans are the gaps between stops.
    """
    pts = [p for p in points if p.get("latitude") is not None and p.get("longitude") is not None]
    pts = sorted(pts, key=lambda p: p["recorded_at"])
    clusters = []
    current = None

    def _close(cluster):
        if cluster:
            clusters.append(cluster)

    for p in pts:
        moving = p.get("speed_mps") is not None and p["speed_mps"] > STOP_SPEED_MPS
        if current is not None:
            d = haversine_m(current["center"][0], current["center"][1], p["latitude"], p["longitude"])
            if not moving and d <= STOP_RADIUS_M:
                current["points"].append(p)
                current["end"] = p["recorded_at"]
                # drift the center toward the running centroid
                n = len(current["points"])
                current["center"] = (
                    sum(q["latitude"] for q in current["points"]) / n,
                    sum(q["longitude"] for q in current["points"]) / n,
                )
                continue
            _close(current)
            current = None
        if not moving:
            current = {"points": [p], "start": p["recorded_at"], "end": p["recorded_at"],
                       "center": (p["latitude"], p["longitude"])}
    _close(current)

    stops = []
    for c in clusters:
        dwell = int((c["end"] - c["start"]).total_seconds())
        if dwell >= DWELL_THRESHOLD_S:
            stops.append({
                "center_latitude": c["center"][0],
                "center_longitude": c["center"][1],
                "arrived_at": c["start"],
                "departed_at": c["end"],
                "dwell_seconds": dwell,
            })
    return stops, _driving_spans(pts, stops)


def _driving_spans(pts, stops):
    if not pts:
        return []
    spans = []
    cursor = pts[0]["recorded_at"]
    for s in stops:
        if s["arrived_at"] > cursor:
            spans.append({"started_at": cursor, "ended_at": s["arrived_at"]})
        cursor = s["departed_at"]
    if pts[-1]["recorded_at"] > cursor:
        spans.append({"started_at": cursor, "ended_at": pts[-1]["recorded_at"]})
    return spans


def _is_open_stop(stop, now):
    """A detected stop whose last point is recent enough that the driver is
    probably still parked there (no clearly-later driving point closed it)."""
    return stop.departed_at is None


# --- place / memory matching ----------------------------------------------------

def match_place(user_id, lat, lng):
    """Closest PlaceMemory whose geofence contains the point, else None."""
    best, best_d = None, None
    for place in PlaceMemory.query.filter_by(user_id=user_id).all():
        d = haversine_m(lat, lng, place.center_latitude, place.center_longitude)
        if d <= (place.radius_m or DEFAULT_PLACE_RADIUS_M) and (best_d is None or d < best_d):
            best, best_d = place, d
    return best


def suggest_loads(user_id, limit=6):
    """Driver's loads/commodities as one-tap chips, most-used first."""
    rows = (
        DriverMemory.query.filter_by(user_id=user_id, memory_type="load")
        .order_by(DriverMemory.use_count.desc(), DriverMemory.last_used_at.desc())
        .limit(limit)
        .all()
    )
    return [r.value for r in rows]


def remember_load(user_id, value, *, now=None):
    value = (value or "").strip()
    if not value:
        return None
    now = now or datetime.utcnow()
    norm = _normalize(value)
    row = DriverMemory.query.filter_by(user_id=user_id, memory_type="load", normalized_value=norm).first()
    if row:
        row.use_count += 1
        row.last_used_at = now
        row.value = value
    else:
        row = DriverMemory(user_id=user_id, memory_type="load", value=value,
                           normalized_value=norm, use_count=1, last_used_at=now)
        db.session.add(row)
    return row


def remember_place(user_id, label, lat, lng, *, place_type="unknown", usual_load=None, now=None):
    now = now or datetime.utcnow()
    place = match_place(user_id, lat, lng)
    if place:
        place.visit_count += 1
        place.last_visited_at = now
        if label:
            place.label = label
        if place_type and place_type != "unknown":
            place.place_type = place_type
        if usual_load:
            place.usual_load = usual_load
        return place
    place = PlaceMemory(user_id=user_id, label=label or "Saved place", center_latitude=lat,
                        center_longitude=lng, radius_m=DEFAULT_PLACE_RADIUS_M, place_type=place_type or "unknown",
                        usual_load=usual_load, visit_count=1, last_visited_at=now)
    db.session.add(place)
    return place


# --- action inference -----------------------------------------------------------

def infer_action(stop, sequence, place):
    """Return (action_type, confidence, suggested_label) for a detected stop.

    Place type wins when known; otherwise fall back to position in the route
    (first meaningful stop = pickup, next = delivery). Long dwell off a known
    place looks like a break. Everything stays low-confidence until confirmed.
    """
    if place and place.place_type == "fuel":
        return "fuel", "high", place.label
    if place and place.place_type == "service":
        return "service", "high", place.label
    if place and place.place_type in ("pickup", "delivery"):
        return place.place_type, "medium", place.usual_load or place.label
    if not place and stop.get("dwell_seconds", 0) >= BREAK_DWELL_MIN_S and sequence > 1:
        return "break", "low", None
    if sequence <= 1:
        return "pickup", "low" if not place else "medium", (place.usual_load if place else None)
    return "delivery", "low" if not place else "medium", (place.usual_load if place else None)


# --- session processing (DB) ----------------------------------------------------

def begin_session(user_id, *, now=None):
    """Driver tapped BEGIN. No setup required."""
    now = now or datetime.utcnow()
    session = AutoLogSession(user_id=user_id, started_at=now, status="active",
                             live_state="READY", last_point_at=None)
    db.session.add(session)
    db.session.flush()
    return session


def record_points(session, raw_points, *, now=None):
    """Idempotently ingest a batch of client points (offline replay safe) and
    re-derive the session. raw_points: list of dicts with client_id, latitude,
    longitude, speed_mps, accuracy_m, heading, recorded_at (ISO or datetime)."""
    now = now or datetime.utcnow()
    existing = {p.client_id for p in session.points if p.client_id}
    added = 0
    for rp in raw_points or []:
        cid = rp.get("client_id")
        if cid and cid in existing:
            continue
        recorded = rp.get("recorded_at")
        if isinstance(recorded, str):
            recorded = datetime.fromisoformat(recorded.replace("Z", "+00:00")).replace(tzinfo=None)
        if recorded is None:
            recorded = now
        db.session.add(RawLocationPoint(
            session_id=session.id, user_id=session.user_id, client_id=cid,
            latitude=rp["latitude"], longitude=rp["longitude"],
            accuracy_m=rp.get("accuracy_m"), speed_mps=rp.get("speed_mps"),
            heading=rp.get("heading"), recorded_at=recorded,
        ))
        if cid:
            existing.add(cid)
        added += 1
    db.session.flush()
    process_session(session, now=now)
    return added


def process_session(session, *, now=None):
    """Recompute segments, candidate stops, actions, review queue, and live
    state from all of the session's points. Idempotent."""
    now = now or datetime.utcnow()
    points = [
        {"latitude": p.latitude, "longitude": p.longitude, "speed_mps": p.speed_mps,
         "recorded_at": p.recorded_at}
        for p in sorted(session.points, key=lambda p: p.recorded_at)
    ]
    stops, spans = detect_clusters(points)

    # Rebuild motion segments from scratch (cheap, idempotent).
    MotionSegment.query.filter_by(session_id=session.id).delete()
    for sp in spans:
        db.session.add(MotionSegment(session_id=session.id, kind="driving",
                                     started_at=sp["started_at"], ended_at=sp["ended_at"]))
    for st in stops:
        db.session.add(MotionSegment(session_id=session.id, kind="stopped",
                                     started_at=st["arrived_at"], ended_at=st["departed_at"],
                                     start_latitude=st["center_latitude"],
                                     start_longitude=st["center_longitude"]))

    # The last detected stop is "open" if no driving span starts after it.
    last_driving_end = max((sp["ended_at"] for sp in spans), default=None)
    existing_stops = {(_round(s.center_latitude), _round(s.center_longitude)): s
                      for s in session.candidate_stops if s.status != "deleted"}
    sequence = 0
    for st in stops:
        sequence += 1
        key = (_round(st["center_latitude"]), _round(st["center_longitude"]))
        is_open = last_driving_end is None or st["departed_at"] >= last_driving_end
        cand = existing_stops.get(key)
        if cand is None:
            cand = CandidateStop(session_id=session.id, user_id=session.user_id,
                                 center_latitude=st["center_latitude"],
                                 center_longitude=st["center_longitude"],
                                 arrived_at=st["arrived_at"])
            db.session.add(cand)
            db.session.flush()
        if cand.status == "confirmed":
            continue  # never overwrite a driver-blessed stop
        cand.sequence = sequence
        cand.arrived_at = st["arrived_at"]
        cand.departed_at = None if is_open else st["departed_at"]
        cand.dwell_seconds = (int((now - st["arrived_at"]).total_seconds())
                              if is_open else st["dwell_seconds"])
        cand.status = "open" if is_open else "closed"
        place = match_place(session.user_id, st["center_latitude"], st["center_longitude"])
        cand.place_memory_id = place.id if place else None
        cand.likely_place_label = place.label if place else None
        cand.needs_review = True

        action_type, confidence, label = infer_action(st, sequence, place)
        existing_action = cand.actions[0] if cand.actions else None
        if existing_action and existing_action.status == "suggested":
            existing_action.action_type = action_type
            existing_action.confidence = confidence
            existing_action.suggested_label = label
        elif not existing_action:
            db.session.add(CandidateAction(candidate_stop_id=cand.id, session_id=session.id,
                                           action_type=action_type, confidence=confidence,
                                           suggested_label=label))
        _ensure_review_item(session, cand)

    session.last_point_at = points[-1]["recorded_at"] if points else None
    session.live_state = _derive_state(session, stops, spans, now=now)
    db.session.flush()
    return session


def _round(v):
    return round(v, 4)  # ~11m grid for matching a recomputed stop to its row


def _ensure_review_item(session, cand):
    if cand.status == "confirmed":
        return
    item = RouteReviewQueue.query.filter_by(candidate_stop_id=cand.id, status="pending").first()
    if not item:
        db.session.add(RouteReviewQueue(session_id=session.id, user_id=session.user_id,
                                        candidate_stop_id=cand.id, reason="stop detected"))


def _open_candidate(session):
    return next((s for s in session.candidate_stops if s.status == "open"), None)


def _derive_state(session, stops, spans, *, now=None):
    if session.status == "complete":
        return "ROUTE_COMPLETE"
    open_stop = _open_candidate(session)
    if open_stop:
        action = open_stop.actions[0] if open_stop.actions else None
        atype = action.action_type if action else "unknown"
        if atype == "fuel":
            return "FUEL_STOP"
        if atype == "service":
            return "SERVICE"
        if atype == "break":
            return "BREAK"
        if open_stop.place_memory_id is None:
            return "LEARNING_STOP"
        return "WAITING"
    if spans:
        return "DRIVING"
    return "READY"


# --- minimal live view ----------------------------------------------------------

def _pending_review_count(session):
    return RouteReviewQueue.query.filter_by(session_id=session.id, status="pending").count()


def live_view(session, *, now=None):
    """The ONLY thing the active screen renders: status, timer anchor, one line,
    and at most one action. No board, feed, map, or checklist."""
    now = now or datetime.utcnow()
    state = session.live_state
    pending = _pending_review_count(session)
    open_stop = _open_candidate(session)

    view = {"state": state, "timer_since": None, "line": "", "action": None,
            "urgent": None, "pending_review": pending}

    if state in ("WAITING", "LEARNING_STOP", "FUEL_STOP", "BREAK", "SERVICE") and open_stop:
        view["timer_since"] = open_stop.arrived_at.isoformat()
        if open_stop.likely_place_label:
            view["line"] = f"Likely stop: {open_stop.likely_place_label}"
            view["action"] = {"label": "Confirm stop", "kind": "confirm_stop", "stop_id": open_stop.id}
        else:
            view["line"] = "New stop detected"
            view["action"] = {"label": "Confirm now", "kind": "confirm_stop", "stop_id": open_stop.id}
    elif state == "DRIVING":
        view["timer_since"] = _current_driving_since(session)
        next_place = _likely_next_place(session)
        view["line"] = f"Heading to {next_place}" if next_place else "Learning route"
        view["action"] = {"label": "Break", "kind": "break"}
    elif state == "READY":
        view["line"] = "Tap Begin and drive"
        view["action"] = {"label": "Begin", "kind": "begin"}
    elif state == "ROUTE_COMPLETE":
        view["line"] = (f"{pending} stop{'s' if pending != 1 else ''} need confirmation"
                        if pending else "Route logged")
        view["action"] = ({"label": "Review route", "kind": "review"} if pending
                          else {"label": "Done", "kind": "done"})

    # While driving, surface review only as a quiet urgent hint, never a board.
    if state == "DRIVING" and pending:
        view["urgent"] = {"label": f"{pending} to review", "kind": "review"}
    return view


def _current_driving_since(session):
    seg = (MotionSegment.query.filter_by(session_id=session.id, kind="driving")
           .order_by(MotionSegment.started_at.desc()).first())
    return seg.started_at.isoformat() if seg else None


def _likely_next_place(session):
    """If the driver usually goes somewhere next from here, name it. Kept simple
    for the first build: the place they most recently confirmed as a delivery."""
    return None


# --- confirmation (trains memory) ----------------------------------------------

def confirm_stop(candidate_stop, *, label=None, action_type=None, cargo_label=None,
                 weight=None, place_type=None, now=None):
    """Driver confirmed/edited a detected stop. Promote it to a ConfirmedStop and
    LEARN: update DriverMemory (load) and PlaceMemory (this geofence + usual load
    + type), so the next route guesses better."""
    now = now or datetime.utcnow()
    session = candidate_stop.session
    action = candidate_stop.actions[0] if candidate_stop.actions else None
    action_type = action_type or (action.action_type if action else "unknown")

    place = remember_place(
        session.user_id, label or candidate_stop.likely_place_label,
        candidate_stop.center_latitude, candidate_stop.center_longitude,
        place_type=place_type or action_type, usual_load=cargo_label, now=now,
    )
    if cargo_label:
        remember_load(session.user_id, cargo_label, now=now)

    confirmed = ConfirmedStop(
        session_id=session.id, user_id=session.user_id, candidate_stop_id=candidate_stop.id,
        place_memory_id=place.id if place else None, sequence=candidate_stop.sequence,
        label=label or candidate_stop.likely_place_label, action_type=action_type,
        cargo_label=cargo_label, weight=weight, arrived_at=candidate_stop.arrived_at,
        departed_at=candidate_stop.departed_at, confirmed_at=now,
    )
    db.session.add(confirmed)
    candidate_stop.status = "confirmed"
    candidate_stop.needs_review = False
    if action:
        action.status = "confirmed"
        action.action_type = action_type
    for item in RouteReviewQueue.query.filter_by(candidate_stop_id=candidate_stop.id, status="pending").all():
        item.status = "resolved"
    db.session.flush()
    return confirmed


def delete_candidate_stop(candidate_stop):
    """Driver said this isn't a real stop. Drop it from the record + review."""
    candidate_stop.status = "deleted"
    candidate_stop.needs_review = False
    for item in RouteReviewQueue.query.filter_by(candidate_stop_id=candidate_stop.id, status="pending").all():
        item.status = "resolved"
    db.session.flush()


def complete_session(session, *, now=None):
    now = now or datetime.utcnow()
    session.ended_at = now
    session.status = "complete"
    process_session(session, now=now)
    session.live_state = "ROUTE_COMPLETE"
    db.session.flush()
    return session
