"""AutoLog engine tests: feed synthetic GPS tracks and assert the engine detects
stops, derives the minimal live state, learns from confirmations, and replays
offline batches idempotently — i.e. the acceptance criteria, without hardware."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("MANAGER_REGISTRATION_PIN", "0000")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


BASE = datetime(2026, 6, 10, 8, 0, 0)


def _at(sec):
    return BASE + timedelta(seconds=sec)


def _pt(cid, lat, lng, speed, sec):
    return {"client_id": cid, "latitude": lat, "longitude": lng, "speed_mps": speed,
            "recorded_at": _at(sec)}


def _driver(username="autolog_driver"):
    from app.extensions import db
    from app.models import User
    u = User(username=username, email=f"{username}@example.com", role="driver")
    u.set_password("p")
    db.session.add(u)
    db.session.commit()
    return u


def _track_drive_stop_drive_stop():
    """origin -> drive -> STOP P1 (5 min) -> drive -> STOP P2 (still there)."""
    pts, cid = [], 0
    for i in range(6):  # driving, 0..150s
        pts.append(_pt(f"c{cid}", 35.0, -78.0 - i * 0.002, 20.0, i * 30)); cid += 1
    for i in range(6):  # P1 parked 180..480s
        pts.append(_pt(f"c{cid}", 35.0, -78.010, 0.0, 180 + i * 60)); cid += 1
    for i in range(6):  # driving away 540..690s
        pts.append(_pt(f"c{cid}", 35.0, -78.010 - i * 0.002, 20.0, 540 + i * 30)); cid += 1
    for i in range(6):  # P2 parked 720..1020s (current/open stop)
        pts.append(_pt(f"c{cid}", 35.0, -78.022, 0.0, 720 + i * 60)); cid += 1
    return pts


def test_begin_requires_no_setup_and_starts_ready(app):
    from app.services.autolog import begin_session, live_view
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    assert session.status == "active"
    assert session.live_state == "READY"
    assert live_view(session, now=BASE)["state"] == "READY"


def test_driving_then_stop_detected_without_driver_input(app):
    from app.services.autolog import begin_session, record_points, live_view
    from app.models import CandidateStop
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))

    # Two stops detected purely from GPS, no driver input.
    stops = CandidateStop.query.filter_by(session_id=session.id).filter(CandidateStop.status != "deleted").all()
    assert len(stops) == 2
    # The most recent stop is open (driver still parked) -> WAITING-family state.
    view = live_view(session, now=_at(1020))
    assert session.live_state in ("WAITING", "LEARNING_STOP")
    assert view["timer_since"] is not None
    assert view["action"]["kind"] == "confirm_stop"


def test_unknown_stop_says_new_stop_detected(app):
    from app.services.autolog import begin_session, record_points, live_view
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))
    view = live_view(session, now=_at(1020))
    assert view["line"] == "New stop detected"          # no place memory yet
    assert session.live_state == "LEARNING_STOP"


def test_leaving_closes_stop_and_resumes_driving(app):
    from app.services.autolog import begin_session, record_points
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    pts = _track_drive_stop_drive_stop()
    # drive away from P2
    for i in range(1, 6):
        pts.append(_pt(f"d{i}", 35.0, -78.022 - i * 0.002, 20.0, 1020 + i * 30))
    record_points(session, pts, now=_at(1200))
    assert session.live_state == "DRIVING"
    from app.models import CandidateStop
    open_stops = CandidateStop.query.filter_by(session_id=session.id, status="open").all()
    assert open_stops == []


def test_first_stop_is_pickup_second_is_delivery(app):
    from app.services.autolog import begin_session, record_points
    from app.models import CandidateStop
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))
    stops = (CandidateStop.query.filter_by(session_id=session.id)
             .filter(CandidateStop.status != "deleted").order_by(CandidateStop.sequence).all())
    assert stops[0].actions[0].action_type == "pickup"
    assert stops[1].actions[0].action_type == "delivery"


def test_confirm_trains_driver_and_place_memory(app):
    from app.services.autolog import begin_session, record_points, confirm_stop, suggest_loads, match_place
    from app.models import CandidateStop, ConfirmedStop, RouteReviewQueue
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))
    first = (CandidateStop.query.filter_by(session_id=session.id)
             .order_by(CandidateStop.sequence).first())

    confirm_stop(first, label="PPL", action_type="pickup", cargo_label="Water", now=_at(1100))

    # Promoted + learned.
    assert ConfirmedStop.query.filter_by(session_id=session.id).count() == 1
    assert "Water" in suggest_loads(driver.id)
    place = match_place(driver.id, first.center_latitude, first.center_longitude)
    assert place is not None and place.label == "PPL"
    # Review item resolved.
    assert RouteReviewQueue.query.filter_by(candidate_stop_id=first.id, status="pending").count() == 0


def test_memory_makes_next_visit_a_known_stop(app):
    from app.services.autolog import begin_session, record_points, confirm_stop, live_view
    from app.models import CandidateStop
    driver = _driver()
    # Session 1: learn P1 as "PPL".
    s1 = begin_session(driver.id, now=BASE)
    record_points(s1, _track_drive_stop_drive_stop(), now=_at(1020))
    first = CandidateStop.query.filter_by(session_id=s1.id).order_by(CandidateStop.sequence).first()
    confirm_stop(first, label="PPL", action_type="pickup", cargo_label="Water", now=_at(1100))

    # Session 2: stop at the same spot -> recognized as a known place.
    s2 = begin_session(driver.id, now=_at(2000))
    pts, cid = [], 0
    for i in range(4):
        pts.append(_pt(f"x{cid}", 35.0, -78.0 - i * 0.002, 20.0, 2000 + i * 30)); cid += 1
    for i in range(6):  # park at P1's coords
        pts.append(_pt(f"x{cid}", 35.0, -78.010, 0.0, 2160 + i * 60)); cid += 1
    record_points(s2, pts, now=_at(2520))
    view = live_view(s2, now=_at(2520))
    assert s2.live_state == "WAITING"
    assert view["line"] == "Likely stop: PPL"
    assert view["action"]["label"] == "Confirm stop"


def test_offline_replay_is_idempotent(app):
    from app.services.autolog import begin_session, record_points
    from app.models import RawLocationPoint, CandidateStop
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    track = _track_drive_stop_drive_stop()
    record_points(session, track, now=_at(1020))
    n_points = RawLocationPoint.query.filter_by(session_id=session.id).count()
    n_stops = CandidateStop.query.filter_by(session_id=session.id).count()
    # Replay the exact same batch (offline resend) -> no duplicates.
    added = record_points(session, track, now=_at(1020))
    assert added == 0
    assert RawLocationPoint.query.filter_by(session_id=session.id).count() == n_points
    assert CandidateStop.query.filter_by(session_id=session.id).count() == n_stops


def test_complete_session_sets_route_complete_and_review_count(app):
    from app.services.autolog import begin_session, record_points, complete_session, live_view
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))
    complete_session(session, now=_at(1100))
    view = live_view(session, now=_at(1100))
    assert session.live_state == "ROUTE_COMPLETE"
    assert "need confirmation" in view["line"]
    assert view["action"]["kind"] == "review"


def test_delete_candidate_drops_it_from_review(app):
    from app.services.autolog import begin_session, record_points, delete_candidate_stop
    from app.models import CandidateStop, RouteReviewQueue
    driver = _driver()
    session = begin_session(driver.id, now=BASE)
    record_points(session, _track_drive_stop_drive_stop(), now=_at(1020))
    stop = CandidateStop.query.filter_by(session_id=session.id).order_by(CandidateStop.sequence).first()
    delete_candidate_stop(stop)
    assert stop.status == "deleted"
    assert RouteReviewQueue.query.filter_by(candidate_stop_id=stop.id, status="pending").count() == 0
