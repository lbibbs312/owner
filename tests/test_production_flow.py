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
    assert ctx["empty_states"]["no_flow_signals"] is True
    assert ctx["empty_states"]["flow_empty_message"] == "No production-flow signals for this date."
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


def test_flow_map_uses_large_objects_and_compact_stop_chips(client, app):
    with app.app_context():
        driver = _user("flow-stop-driver", "driver")
        _driver_log(driver, plant_name="RW", depart_time="08:30", load_size="Empty", depart_load_size="Trim DC Load")
        _driver_log(driver, plant_name="Trim DC", depart_time=None, load_size="Trim DC Load")

    _login(client, "flow-stop-driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "flow-object-card" in body
    assert "Load Build / Trailer" in body
    assert "Route-only data. Attach manifest or enter paper data to build expected flow." in body
    assert "Production Digital Twin" in body
    assert "Operational Alerts" in body
    assert "Plant Computer Console" in body
    assert "projected from events and current records" not in body
    assert "Receiving, unload, and reconcile events project here." not in body
    assert "route-step-chip" in body
    assert "Stop Details" in body
    assert "Actual Scans" in body
    assert "Event Timeline" in body
    assert "Shadow Ledger" in body
    assert "Movie Speed" not in body
    assert "Timeline Script" not in body
    assert "data-flow-mode-button" not in body
    assert "data-flow-replay-slider" not in body


def test_flow_map_edges_are_ledger_backed_and_animated(client, app):
    with app.app_context():
        driver = _user("flow-edge-driver", "driver")
        _driver_log(driver, plant_name="RW", depart_time="08:30", load_size="Empty", depart_load_size="Trim DC Load")
        _driver_log(driver, plant_name="Trim DC", depart_time=None, load_size="Trim DC Load")

        from app.services.flow_events import FlowEventService
        from app.services.production_flow import build_production_flow_context

        first = FlowEventService.append_event(
            event_type="DEPARTED_ORIGIN",
            entity_type="route_stop",
            entity_id=1,
            route_id="driver-route-edge",
            origin_node_id="RW",
            destination_node_id="Trim DC",
            occurred_at=datetime.utcnow() - timedelta(minutes=6),
            source="mobile",
            commit=True,
        )
        second = FlowEventService.append_event(
            event_type="ARRIVED_DESTINATION",
            entity_type="route_stop",
            entity_id=2,
            route_id="driver-route-edge",
            origin_node_id="RW",
            destination_node_id="Trim DC",
            occurred_at=datetime.utcnow() - timedelta(minutes=1),
            source="mobile",
            commit=True,
        )

        ctx = build_production_flow_context(date=date.today(), driver_id=driver.id)
        edges = ctx["flow_edges"]
        assert edges[0]["event_id"] == first.id
        assert edges[0]["source_key"] == "object:manifested"
        assert edges[0]["target_key"] == "object:in_transit"
        assert edges[0]["source"] == "mobile"
        assert edges[0]["proof_label"] == "none"
        assert edges[1]["event_id"] == second.id
        assert edges[1]["previous_event_id"] == first.id
        assert edges[1]["source_key"] == "object:in_transit"
        assert edges[1]["target_key"] == "object:receiving"
        assert edges[1]["is_live"] is True

    _login(client, "flow-edge-driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "FlowMapAnimator" in body
    assert "data-flow-edge-data" in body
    assert "flow-edge--new" in body
    assert "livePulse" in body
    assert "stroke-width: 4.25" in body
    assert "flow-edge--live" in body
    assert "flow-event-pulse" in body
    assert "data-flow-card-mask" in body
    assert "data-flow-edge-group" in body
    assert "livePulseRing" in body
    assert "ops-arrow-live-" in body
    assert "Shadow Ledger" in body
    assert "data-shadow-ledger-row" in body
    assert "filterShadowLedger" in body
    assert "data-flow-console-title" in body
    assert ".production-flow--mobile .ops-board-spatial .ops-spatial-body" in body
    assert 'data-flow-node-key="object:in_transit"' in body
    assert 'data-flow-event-id="' in body
    assert "System Summary" not in body


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


def test_board_uses_production_flow_wording_not_audit_defense(client, app):
    with app.app_context():
        manager = _user("boss-wording", "management")
        _move_request(manager.id, request_number="MR-WORD-1")

    _login(client, "boss-wording")
    resp = client.get("/manager/dashboard")

    body = resp.get_data(as_text=True)
    assert "Production Flow Board" in body
    assert "Operations &amp; Audit Defense Board" not in body
    assert "Operations & Audit Defense Board" not in body
    assert "Spatial Network Flow" not in body
    assert "Exception Management" not in body


def test_no_action_needed_no_exceptions_contradiction(client, app):
    # No move requests, no logs -> needs_attention section must not say "ACTION NEEDED: No active exceptions"
    with app.app_context():
        manager = _user("empty-mgr", "management")
        _move_request(manager.id, request_number="MR-EMPTY-1", status="completed")

    _login(client, "empty-mgr")
    resp = client.get("/manager/dashboard")
    body = resp.get_data(as_text=True)
    assert "ACTION NEEDED: No active exceptions" not in body
    assert "No active exceptions" not in body
    assert "Top Active Exceptions" not in body
    assert "Top Needs Attention" not in body
    assert "Shadow Ledger" in body


def test_route_stops_display_as_sequence_not_database_id(app):
    from app.services.production_flow import build_production_flow_context

    with app.app_context():
        driver = _user("seq-driver", "driver")
        today = date.today()
        _driver_log(driver, plant_name="RE", arrive_time="08:00", depart_time=None, load_size="Empty")
        _driver_log(driver, plant_name="DC", arrive_time="09:00", depart_time=None, load_size="Empty")
        _driver_log(driver, plant_name="AWE", arrive_time="10:00", depart_time=None, load_size="Empty")

        ctx = build_production_flow_context(date=today, driver_id=driver.id)
        stop_labels = [item["display_label"] for item in ctx["flow_items"] if item["item_type"] == "route_stop"]
        assert sorted(stop_labels) == ["Stop 1", "Stop 2", "Stop 3"]
        for item in ctx["flow_items"]:
            if item["item_type"] == "route_stop":
                assert item["source_label"] == "Driver route log"


def test_route_overlay_is_present_when_single_driver(app):
    from app.services.production_flow import build_production_flow_context

    with app.app_context():
        driver = _user("overlay-driver", "driver")
        today = date.today()
        _driver_log(driver, plant_name="RE", arrive_time="08:00", depart_time="08:30", load_size="Empty")
        _driver_log(driver, plant_name="DC", arrive_time="09:00", depart_time=None, load_size="Empty")

        ctx = build_production_flow_context(date=today, driver_id=driver.id)
        overlay = ctx["route_overlay"]
        assert overlay is not None
        assert overlay["path_node_keys"]
        assert len(overlay["stop_markers"]) == 2
        assert overlay["stop_markers"][0]["display_label"] == "Stop 1"
        assert overlay["stop_markers"][1]["display_label"] == "Stop 2"
        assert overlay["status"] == "in_progress"


def test_drawer_uses_friendly_source_label_not_raw_class_name(app):
    from app.services.production_flow import build_production_flow_context

    with app.app_context():
        mgr = _user("src-mgr", "management")
        _move_request(mgr.id, request_number="MR-SRC-1")
        ctx = build_production_flow_context(date=date.today())
        node_sources = []
        for node in ctx["flow_nodes"]:
            node_sources.extend(node.get("source_labels") or [])
        assert "Move request" in node_sources
