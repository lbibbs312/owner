"""Tests for the production-flow view model."""
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
        plant_name="RE",
    )
    base.update(kw)
    log = DriverLog(**base)
    db.session.add(log)
    db.session.commit()
    return log


def _login(client, username):
    return client.post(
        "/login",
        data={"login_name": username, "password": "password1"},
        follow_redirects=False,
    )


def _flatten_strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _flatten_strings(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _flatten_strings(child)
    elif isinstance(value, str):
        yield value


def test_production_flow_no_data_returns_safe_empty_states(app):
    from app.services.production_flow import build_production_flow_context

    ctx = build_production_flow_context(date=date.today())

    assert ctx["mode"] == "widescreen"
    assert ctx["permissions"]["can_view"] is True
    assert ctx["permissions"]["can_edit"] is False
    assert ctx["flow_nodes"] == []
    assert ctx["flow_lanes"] == []
    assert ctx["flow_items"] == []
    assert ctx["empty_states"]["no_flow_nodes"] is True
    assert ctx["empty_states"]["carrier_unit_snapshot"] == "Carrier unit snapshot not connected yet"
    assert ctx["empty_states"]["rack_capacity"] == "Rack/capacity data not connected yet"
    assert ctx["empty_states"]["data_scope"] == "Using route and move request data only"


def test_move_requests_create_location_nodes_and_lanes(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    req = _move_request(manager.id, request_number="MR-PF-1")

    ctx = build_production_flow_context(date=date.today())
    labels = {node["label"] for node in ctx["flow_nodes"]}
    lane = ctx["flow_lanes"][0]

    assert {"Raleigh East", "Plastic West"} <= labels
    assert lane["origin_label"] == "Raleigh East"
    assert lane["destination_label"] == "Plastic West"
    assert lane["linked_request_ids"] == [req.id]
    assert ctx["flow_items"][0]["item_type"] == "move_request"
    assert ctx["flow_items"][0]["label"] == "MR-PF-1"


def test_production_flow_map_uses_spatial_graph_layout(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id, request_number="MR-PF-1", origin_location_text="Raleigh East", destination_location_text="Plastic West")
    _move_request(manager.id, request_number="MR-PF-2", origin_location_text="Raleigh East", destination_location_text="Paint Central")
    _move_request(manager.id, request_number="MR-PF-3", origin_location_text="Kraft Plant", destination_location_text="Plastic West")
    _move_request(manager.id, request_number="MR-PF-4", origin_location_text="PPL", destination_location_text="52nd Street")

    ctx = build_production_flow_context(date=date.today())
    node_points = [(node["layout"]["x"], node["layout"]["y"]) for node in ctx["flow_nodes"]]
    y_positions = {round(y) for _, y in node_points}

    assert len(ctx["flow_nodes"]) >= 5
    assert len(y_positions) >= 3
    assert all(6 <= x <= 94 and 6 <= y <= 94 for x, y in node_points)
    assert all("path_d" in lane["layout"] for lane in ctx["flow_lanes"])
    assert all((" Q " in lane["layout"]["path_d"] or " C " in lane["layout"]["path_d"]) for lane in ctx["flow_lanes"])


def test_selected_plant_is_centered_as_graph_hub(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id, origin_location_text="Raleigh East", destination_location_text="Plastic West")
    _move_request(manager.id, origin_location_text="Paint Central", destination_location_text="Plastic West")

    ctx = build_production_flow_context(date=date.today(), selected_plant="Plastic West")
    selected = next(node for node in ctx["flow_nodes"] if node["label"] == "Plastic West")

    assert ctx["selected_context"]["selected_node_key"] == selected["key"]
    assert selected["layout"]["is_hub"] is True
    assert selected["layout"]["x"] == 50.0
    assert selected["layout"]["y"] == 50.0


def test_production_flow_context_supports_mode_and_action_permissions(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id)

    ctx = build_production_flow_context(
        date=date.today(),
        mode="admin",
        can_edit=True,
        can_assign=True,
        can_review=True,
        can_export=True,
    )

    assert ctx["mode"] == "admin"
    assert ctx["permissions"] == {
        "can_view": True,
        "can_edit": True,
        "can_assign": True,
        "can_review": True,
        "can_export": True,
    }


def test_driver_logs_contribute_route_flow_items(app):
    from app.services.production_flow import build_production_flow_context

    driver = _user("driver1", "driver")
    log = _driver_log(driver, plant_name="PW")

    ctx = build_production_flow_context(date=date.today())

    route_items = [item for item in ctx["flow_items"] if item["item_type"] == "route_stop"]
    assert len(route_items) == 1
    assert route_items[0]["linked_route_stop_id"] == log.id
    assert route_items[0]["plant_location"] == "Plastic West"
    assert ctx["floor_summary"]["active_stop_count"] == 1


def test_driver_logs_create_real_lanes_between_stops(app):
    from app.services.production_flow import build_production_flow_context

    driver = _user("driver2", "driver")
    first = _driver_log(
        driver,
        plant_name="RE",
        depart_time="2026-05-28 12:20:00",
        created_at=datetime.utcnow() - timedelta(minutes=40),
    )
    second = _driver_log(
        driver,
        plant_name="PW",
        depart_time=None,
        created_at=datetime.utcnow() - timedelta(minutes=10),
    )

    ctx = build_production_flow_context(date=date.today())
    lane = next(lane for lane in ctx["flow_lanes"] if lane["origin_label"] == "Raleigh East" and lane["destination_label"] == "Plastic West")

    assert lane["waiting_count"] == 1
    assert lane["linked_driver_log_ids"] == [first.id, second.id]


def test_production_flow_does_not_invent_carrier_or_rack_snapshot_data(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id)

    ctx = build_production_flow_context(date=date.today())

    assert ctx["floor_summary"]["production_snapshot_available"] is False
    assert ctx["floor_summary"]["carrier_unit_snapshot"] is None
    assert ctx["floor_summary"]["rack_capacity_snapshot"] is None
    assert all(item["carrier_unit_count"] is None for item in ctx["flow_items"])
    assert all(item["rack_count"] is None for item in ctx["flow_items"])
    assert all(node["meta"]["carrier_unit_snapshot"] is None for node in ctx["flow_nodes"])
    assert all(node["meta"]["rack_capacity_snapshot"] is None for node in ctx["flow_nodes"])


def test_status_counts_are_correct(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id, status="open")
    _move_request(manager.id, status="assigned")
    _move_request(manager.id, status="waiting")
    _move_request(manager.id, status="blocked", blocked_reason="No parts")
    _move_request(manager.id, status="completed", updated_at=datetime.utcnow())

    ctx = build_production_flow_context(date=date.today())
    summary = ctx["queue_summary"]
    lane = ctx["flow_lanes"][0]

    assert summary["open_count"] == 1
    assert summary["active_count"] == 1
    assert summary["waiting_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["completed_count"] == 1
    assert summary["needs_attention_count"] == 1
    assert lane["open_count"] == 1
    assert lane["active_count"] == 1
    assert lane["waiting_count"] == 1
    assert lane["blocked_count"] == 1
    assert lane["completed_count"] == 1
    assert lane["worst_status"] == "blocked"


def test_no_fake_telemetry_fields_appear(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id)

    ctx = build_production_flow_context(date=date.today())
    rendered_contract = " ".join(_flatten_strings(ctx)).lower()

    banned = ["gps", "telemetry", "rpm", "fuel economy", "biometric", "camera", "elog"]
    for term in banned:
        assert term not in rendered_contract


def test_manager_dashboard_uses_production_flow_mode(client, app):
    with app.app_context():
        manager = _user("boss", "management")
        _move_request(manager.id, request_number="MR-PROD-1")

    _login(client, "boss")
    resp = client.get("/manager/dashboard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-route-map-mode="production"' in body
    assert 'data-production-flow-mode="admin"' in body
    assert "Production Flow Map" in body
    assert "MR-PROD-1" in body
    assert 'class="route-stop-rail"' not in body


def test_mobile_dashboard_uses_compact_shared_production_flow(client, app):
    with app.app_context():
        driver = _user("mobile-pf-driver", "driver")
        _driver_log(driver, plant_name="RE")

    _login(client, "mobile-pf-driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-production-flow-mode="mobile"' in body
    assert "Compact Production Flow" in body
    assert "View Production Flow" in body
    assert "full 2D" not in body


def test_operations_board_is_shared_read_only_plant_floor_board(client, app):
    with app.app_context():
        manager = _user()
        _move_request(manager.id, request_number="MR-FLOOR-1")

    resp = client.get("/operations-board")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Plant Floor Board" in body
    assert 'data-production-flow-mode="plant_floor"' in body
    assert "MR-FLOOR-1" in body
    assert "Requires authorized identity." in body
