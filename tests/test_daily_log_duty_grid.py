"""Driver's Daily Log duty grid: finalized days close at 24:00, totals stay in
sync with the route sheet's minute math, and same-minute events keep their
physical order. Seeds the Jun 11 2026 reference route (11 stops, a forgotten
mid-drive break, midnight switcher test-taps) and checks the invariants the
printed documents rely on."""
from datetime import date, datetime

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


DAY = date(2026, 6, 11)
# Local EDT = UTC-4 in June. Shift 1:34 PM, posttrip/release 9:15:30 PM.
SHIFT_START_UTC = datetime(2026, 6, 11, 17, 34, 10)
RELEASE_UTC = datetime(2026, 6, 12, 1, 15, 30)
# The printed sheet's 11 stops; legs sum to 151 driving minutes. Two arrivals
# carry UTC seconds on purpose - departures are HH:MM, so raw-timestamp sorts
# used to flip Arrived/Departed inside a minute.
STOPS = [
    ("Raleigh east", "13:35", "13:39"),
    ("Hellos dock 13", "2026-06-11 17:51:42", "14:24"),
    ("Raleigh east", "14:38", "14:42"),
    ("Ppl", "14:51", "14:57"),
    ("Paint central", "15:33", "15:34"),
    ("Raleigh east", "2026-06-11 19:52:33", "18:32"),
    ("Paint central", "18:59", "18:59"),
    ("Classic Transportation", "19:10", "19:11"),
    ("Paint central", "19:18", "20:48"),
    ("Ppl", "20:55", "21:04"),
    ("Raleigh east", "21:14", "21:14"),
]


def _seed_day(*, release=True, tag="a"):
    from app.extensions import db
    from app.models.duty import DutyStatusEvent
    from app.models.log import DriverLog
    from app.models.trip import RouteBreak, ShiftRecord
    from app.models.user import User

    user = User(username=f"grid driver {tag}", email=f"grid-{tag}@test.test", role="driver")
    for attr, value in (("password_hash", "x"), ("day_driver", True)):
        if hasattr(user, attr):
            setattr(user, attr, value)
    db.session.add(user)
    db.session.flush()

    # Midnight button-testing: four conflicting taps in one minute, then two.
    for hh, mm, ss, status in (
        (4, 9, 5, "sb"), (4, 9, 12, "d"), (4, 9, 30, "on"), (4, 9, 48, "off"),
        (4, 17, 10, "sb"), (4, 17, 25, "off"),
    ):
        db.session.add(DutyStatusEvent(user_id=user.id, status=status,
                                       at=datetime(2026, 6, 11, hh, mm, ss)))

    db.session.add(ShiftRecord(user_id=user.id, start_time=SHIFT_START_UTC))
    for plant, arrive, depart in STOPS:
        db.session.add(DriverLog(driver_id=user.id, date=DAY, plant_name=plant,
                                 arrive_time=arrive, depart_time=depart,
                                 load_size="Empty"))
    # The forgotten break: tapped 3:40 PM EDT mid-drive, never ended by hand.
    db.session.add(RouteBreak(user_id=user.id, break_date=DAY,
                              break_type="On-duty not driving",
                              start_time=datetime(2026, 6, 11, 19, 40, 1)))
    db.session.commit()

    if release:
        from app.blueprints.driver.routes import _end_open_shifts_for_driver

        _end_open_shifts_for_driver(user.id, ended_at=RELEASE_UTC)
        db.session.commit()
    return user


def _local(hh, mm):
    from app.services import duty_log as dl

    return dl.DETROIT_TZ.localize(datetime(2026, 6, 11, hh, mm))


def test_finalized_day_totals_exactly_24h(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    segments, _ = dl.day_segments(user.id, DAY, now_local=_local(22, 49))
    totals = dl.totals_minutes(segments)
    assert totals["off"] + totals["sb"] + totals["d"] + totals["on"] == 24 * 60
    assert totals["total"] == 24 * 60
    # Drive matches the sheet's depart->arrive legs; worked = sheet on-duty.
    assert totals["d"] == 151
    assert totals["d"] + totals["on"] == 461
    assert dl.day_complete(user.id, DAY, now_local=_local(22, 49))


def test_generated_at_does_not_affect_finalized_totals(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    early, _ = dl.day_segments(user.id, DAY, now_local=_local(21, 16))
    late, _ = dl.day_segments(user.id, DAY, now_local=_local(23, 58))
    assert dl.totals_minutes(early) == dl.totals_minutes(late)


def test_d_plus_on_equals_worked_today(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    now_local = _local(22, 49)
    segments, _ = dl.day_segments(user.id, DAY, now_local=now_local)
    totals = dl.totals_minutes(segments)
    recap = dl.recap(user.id, DAY, now_local=now_local)
    assert recap["worked_today"] == totals["d"] + totals["on"]


def test_in_progress_day_is_not_certifiable(app):
    from app.services import duty_log as dl

    user = _seed_day(release=False)
    now_local = _local(21, 0)
    assert not dl.day_complete(user.id, DAY, now_local=now_local)
    segments, _ = dl.day_segments(user.id, DAY, now_local=now_local)
    totals = dl.totals_minutes(segments)
    assert totals["total"] == 21 * 60  # runs to "now", not midnight


def test_same_minute_events_keep_physical_order(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    _, events = dl.day_segments(user.id, DAY, now_local=_local(22, 49))

    def index_of(label, hh, mm, location):
        at = _local(hh, mm)
        for idx, ev in enumerate(events):
            if ev["label"] == label and ev["at"] == at and ev["location"] == location:
                return idx
        raise AssertionError(f"missing {label} {hh}:{mm} {location}")

    # Same stop, same minute: Arrived sorts before Departed (zero-min dock).
    assert index_of("Arrived", 18, 59, "Paint central") < index_of("Departed", 18, 59, "Paint central")
    assert index_of("Arrived", 21, 14, "Raleigh east") < index_of("Departed", 21, 14, "Raleigh east")
    # An arrival stored with seconds still sorts after the prior stop's depart
    # and before its own departure.
    assert index_of("Departed", 14, 42, "Raleigh east") < index_of("Arrived", 14, 51, "Ppl")
    assert index_of("Arrived", 13, 51, "Hellos dock 13") < index_of("Departed", 14, 24, "Hellos dock 13")
    # No event precedes the shift start; none follows the shift end.
    labels = [ev["label"] for ev in events]
    assert labels[0] == "Shift start"
    assert labels[-1] == "Shift end"


def test_break_open_at_release_is_auto_closed_and_grid_stays_correct(app):
    from app.models.trip import RouteBreak
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    brk = RouteBreak.query.filter_by(user_id=user.id).one()
    assert brk.end_time == RELEASE_UTC  # shift end stamps the forgotten break
    _, events = dl.day_segments(user.id, DAY, now_local=_local(22, 49))
    ended = [ev for ev in events if ev["label"] == "Break ended"]
    assert ended and ended[0]["status"] == "off"
    # Break ended never sorts after Shift end in its minute.
    labels = [ev["label"] for ev in events]
    assert labels.index("Break ended") < labels.index("Shift end")


def test_midnight_test_taps_stay_off_the_log(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    _, events = dl.day_segments(user.id, DAY, now_local=_local(22, 49))
    assert not [ev for ev in events if ev["source"] == "manual"]


def test_pdf_grid_totals_match_event_table(app):
    from app.services import duty_log as dl

    user = _seed_day(release=True)
    now_local = _local(22, 49)
    segments, events = dl.day_segments(user.id, DAY, now_local=now_local)
    totals = dl.totals_minutes(segments)

    # Recompute the grid independently by walking the event table.
    start_local, end_local = dl._day_bounds_local(DAY)
    walked = {"off": 0, "sb": 0, "d": 0, "on": 0}
    status = dl.carry_in_status(user.id, DAY)
    cursor = start_local
    for ev in events:
        walked[status] += int((ev["at"] - cursor).total_seconds() // 60)
        status = ev["status"]
        cursor = ev["at"]
    walked[status] += int((end_local - cursor).total_seconds() // 60)
    for key in walked:
        assert walked[key] == totals[key], key


def test_pdf_certification_gates_on_completion(app):
    from app.blueprints.driver.routes import _build_daily_log_pdf
    from app.services import duty_log as dl

    def build(user, now_local):
        segments, events = dl.day_segments(user.id, DAY, now_local=now_local)
        totals = dl.totals_minutes(segments)
        view = {
            "segments": segments,
            "events": events,
            "totals": totals,
            "recap": dl.recap(user.id, DAY, now_local=now_local),
            "truck": "st4",
            "odo_start": 246148,
            "odo_end": 246174,
            "miles": 26,
            "day_complete": dl.day_complete(user.id, DAY, now_local=now_local),
            "hos_check": [("11-hour driving", "8:29 left")],
            "as_of_label": now_local.strftime("%I:%M %p").lstrip("0").lower(),
        }
        return _build_daily_log_pdf(DAY, user, view)

    released = _seed_day(release=True)
    pdf = build(released, _local(22, 49))
    assert b"I hereby certify" in pdf
    assert b"LOG IN PROGRESS" not in pdf

    open_user = _seed_day(release=False, tag="b")
    pdf = build(open_user, _local(21, 0))
    assert b"I hereby certify" not in pdf
    assert b"LOG IN PROGRESS" in pdf
