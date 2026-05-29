"""Tests for the Operations & Audit Defense Board view model + page.

The board is a presentation layer over ``build_production_flow_context`` and
must stay faithful to real records: real geometry derived from real nodes, real
per-node stat tiles, and an honest proof checklist with no fabricated telemetry.
"""
from datetime import date, datetime, timedelta

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


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(username="mgr", role="management"):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=f"{username}@example.com", role=role)
    user.set_password("password1")
    db.session.add(user)
    db.session.commit()
    return user


def _move_request(creator_id, **kw):
    from app.extensions import db
    from app.models import MoveRequest

    base = dict(
        raw_text="Move racks from Raleigh East to Plastic West",
        created_by_id=creator_id,
        status="open",
        priority="normal",
        origin_location_text="Raleigh East",
        destination_location_text="Plastic West",
        cargo_text="Rack load",
        requested_at=datetime.utcnow() - timedelta(minutes=20),
    )
    base.update(kw)
    req = MoveRequest(**base)
    db.session.add(req)
    db.session.commit()
    return req


def _driver_log(driver, **kw):
    from app.extensions import db
    from app.models import DriverLog

    base = dict(
        driver_id=driver.id,
        date=date.today(),
        arrive_time="2026-05-28 12:00:00",
        depart_time=None,
        load_size="Empty",
        plant_name="PW",
    )
    base.update(kw)
    log = DriverLog(**base)
    db.session.add(log)
    db.session.commit()
    return log


def _damage(reporter_id, **kw):
    from app.extensions import db
    from app.models import DamageReport

    base = dict(
        reported_by_id=reporter_id,
        plant_name="PW",
        description="Cracked tote",
        status="open",
        created_at=datetime.utcnow(),
    )
    base.update(kw)
    report = DamageReport(**base)
    db.session.add(report)
    db.session.commit()
    return report


def _login(client, username):
    return client.post(
        "/login",
        data={"login_name": username, "password": "password1"},
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# view model
# --------------------------------------------------------------------------- #
def test_empty_board_has_safe_empty_state(app):
    from app.services.operations_board import build_operations_board_context

    board = build_operations_board_context(date=date.today())

    assert board["empty"] is True
    assert board["nodes"] == []
    assert board["lanes"] == []
    assert board["tokens"] == []
    assert board["header"]["active"] == 0
    assert board["header"]["exceptions"] == 0


def test_move_request_yields_positioned_nodes_lane_and_token(app):
    from app.services.operations_board import build_operations_board_context

    manager = _user()
    _move_request(manager.id, request_number="MR-OB-1", status="assigned", assigned_driver_text="S. Jenkins")

    board = build_operations_board_context(date=date.today())

    labels = {node["label"]: node for node in board["nodes"]}
    assert {"Raleigh East", "Plastic West"} <= set(labels)

    # every node gets real numeric geometry
    for node in board["nodes"]:
        for key in ("cx", "cy", "left", "top"):
            assert isinstance(node["pos"][key], (int, float))

    # the lane between the two plants is positioned with endpoints
    assert len(board["lanes"]) == 1
    lane = board["lanes"][0]
    for key in ("x1", "y1", "x2", "y2", "mid_x", "mid_y"):
        assert isinstance(lane[key], (int, float))

    # exactly one move token, placed on the canvas with a badge
    assert len(board["tokens"]) == 1
    token = board["tokens"][0]
    assert token["label"] == "MR-OB-1"
    assert isinstance(token["left"], (int, float))
    assert isinstance(token["top"], (int, float))
    assert token["badge"]["label"] == "ACTIVE"

    # in/out tiles reflect the lane direction
    assert labels["Plastic West"]["stats"]["in"] == 1
    assert labels["Raleigh East"]["stats"]["out"] == 1


def test_proof_checklist_reflects_real_records(app):
    from app.services.operations_board import build_operations_board_context

    manager = _user()
    _move_request(
        manager.id,
        request_number="MR-PROOF",
        status="assigned",
        assigned_driver_text="S. Jenkins",
        linked_document_id=999,
    )

    board = build_operations_board_context(date=date.today())
    move = next(m for m in board["moves"] if m["label"] == "MR-PROOF")
    states = {step["label"]: step["state"] for step in move["checklist"]}

    assert states["Request logged"] == "complete"
    assert states["Driver assigned"] == "complete"
    assert states["Proof document attached"] == "complete"
    # not tracked / not done yet -> honest pending, never faked complete
    assert states["Arrival recorded"] == "pending"
    assert states["Departure recorded"] == "pending"


def test_no_pickup_and_delay_surface_in_stats_and_ticker(app):
    from app.services.operations_board import build_operations_board_context

    driver = _user("drv", "driver")
    _driver_log(driver, plant_name="PW", no_pickup=True, dock_wait_minutes=75)

    board = build_operations_board_context(date=date.today())
    pw = next(node for node in board["nodes"] if node["label"] == "Plastic West")

    assert pw["stats"]["nop"] == 1
    assert pw["stats"]["dly"] == 1

    reasons = {entry["reason"] for entry in board["ticker"]}
    assert "Failed pickup" in reasons


def test_damage_increments_node_damage_and_exceptions(app):
    from app.services.operations_board import build_operations_board_context

    driver = _user("drv2", "driver")
    _damage(driver.id, plant_name="PW")

    board = build_operations_board_context(date=date.today())
    pw = next(node for node in board["nodes"] if node["label"] == "Plastic West")

    assert pw["stats"]["dmg"] == 1
    assert board["header"]["exceptions"] >= 1


# --------------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------------- #
def test_board_page_renders_for_manager_and_driver(client, app):
    with app.app_context():
        manager = _user("boss", "management")
        _user("rider", "driver")
        _move_request(manager.id, request_number="MR-PAGE-1", status="assigned", assigned_driver_text="L. Bibbs")

    for username in ("boss", "rider"):
        _login(client, username)
        resp = client.get("/operations-board")
        assert resp.status_code == 200, username
        body = resp.get_data(as_text=True)
        assert "Operations &amp; Audit Defense Board" in body
        assert "Plastic West" in body
        assert "MR-PAGE-1" in body
        client.get("/logout")


def test_board_page_does_not_fabricate_telemetry_or_savings(client, app):
    with app.app_context():
        manager = _user("boss2", "management")
        _move_request(manager.id, request_number="MR-CLEAN", status="assigned")

    _login(client, "boss2")
    body = client.get("/operations-board").get_data(as_text=True).lower()

    for banned in ("gps", "telemetry", "camera", "prevention savings", "dvir"):
        assert banned not in body
