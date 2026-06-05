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


def _plant_transfer(driver, **kw):
    from app.extensions import db
    from app.models import PlantTransfer

    base = dict(
        user_id=driver.id,
        transfer_date=date.today(),
        ship_from="RE",
        ship_to="PW",
        transfer_number="PT-PF-1",
    )
    base.update(kw)
    transfer = PlantTransfer(**base)
    db.session.add(transfer)
    db.session.commit()
    return transfer


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
    labels = {node["label"] for node in ctx["flow_nodes"]}
    assert {"Raleigh West", "Kraft Plater", "Paint West", "52nd Street DC", "Raleigh East", "Trim DC"} <= labels
    plant_flow_lanes = [lane for lane in ctx["flow_lanes"] if lane["lane_type"] == "plant_flow"]
    assert plant_flow_lanes
    assert all(lane["default_visible"] is True for lane in plant_flow_lanes)
    assert ctx["flow_items"] == []
    assert ctx["empty_states"]["no_flow_signals"] is False
    assert ctx["empty_states"]["no_flow_nodes"] is False
    assert ctx["empty_states"]["no_flow_lanes"] is False
    assert ctx["empty_states"]["no_flow_items"] is True
    assert ctx["empty_states"]["carrier_unit_snapshot"] == "Carrier unit snapshot not connected yet"
    assert ctx["empty_states"]["rack_capacity"] == "Rack/capacity data not connected yet"
    assert ctx["empty_states"]["data_scope"] == "Using route and move request data only"


def test_move_requests_create_location_nodes_and_lanes(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    req = _move_request(manager.id, request_number="MR-PF-1")

    ctx = build_production_flow_context(date=date.today())
    labels = {node["label"] for node in ctx["flow_nodes"]}
    lane = next(lane for lane in ctx["flow_lanes"] if lane["linked_request_ids"] == [req.id])

    assert {"Raleigh East", "Paint West"} <= labels
    assert lane["origin_label"] == "Raleigh East"
    assert lane["destination_label"] == "Paint West"
    assert lane["linked_request_ids"] == [req.id]
    assert lane["default_visible"] is False
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


def test_selected_plant_uses_fixed_production_position_not_graph_recentering(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(manager.id, origin_location_text="Raleigh East", destination_location_text="Plastic West")
    _move_request(manager.id, origin_location_text="Paint Central", destination_location_text="Plastic West")

    ctx = build_production_flow_context(date=date.today(), selected_plant="Plastic West")
    selected = next(node for node in ctx["flow_nodes"] if node["label"] == "Paint West")

    assert ctx["selected_context"]["selected_node_key"] == selected["key"]
    assert selected["layout"]["is_hub"] is True
    assert selected["production_profile"]["role_label"] == "COATING / PAINT"
    assert selected["layout"]["ring"] == "production"
    assert selected["layout"]["x"] == 64
    assert selected["layout"]["y"] == 24


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
    assert route_items[0]["plant_location"] == "Paint West"
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
    lane = next(lane for lane in ctx["flow_lanes"] if lane["origin_label"] == "Raleigh East" and lane["destination_label"] == "Paint West")

    assert lane["waiting_count"] == 1
    assert lane["linked_driver_log_ids"] == [first.id, second.id]
    assert lane["default_visible"] is False
    assert ctx["route_overlay"]["path_segments"]


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


def test_known_plants_render_as_production_positions(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user()
    _move_request(
        manager.id,
        request_number="MR-PPL-KP",
        origin_location_text="PPL",
        destination_location_text="KP",
        cargo_text="Raw grille substrates",
        part_number="GRILLE-BASE-N1511",
    )
    _move_request(
        manager.id,
        request_number="MR-KP-52L",
        origin_location_text="KP",
        destination_location_text="52L",
        cargo_text="Chrome grille assemblies",
    )

    ctx = build_production_flow_context(date=date.today())
    by_label = {node["label"]: node for node in ctx["flow_nodes"]}

    assert "PPL" not in by_label
    assert by_label["Raleigh West"]["production_profile"]["role_label"] == "FRONT END / INTAKE / EMPTY PACK RETURN"
    assert by_label["Kraft Plater"]["production_profile"]["role_label"] == "PLATING"
    assert by_label["52nd Street DC"]["production_profile"]["role_label"] == "ASSEMBLY / CARRIER ALLOCATION"
    assert by_label["Raleigh West"]["production_profile"]["primary_value"] == "1 flow signal"
    assert "GRILLE-BASE-N1511" in by_label["Raleigh West"]["production_profile"]["material_lines"][0]
    assert by_label["Raleigh West"]["layout"]["ring"] == "production"
    assert by_label["Kraft Plater"]["layout"]["ring"] == "production"


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
    lane = next(lane for lane in ctx["flow_lanes"] if len(lane["linked_request_ids"]) == 5)

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
    assert lane["replay_status"] == "held-up"


def test_hot_part_focuses_destination_plant_card(client, app):
    from app.services.production_flow import build_production_flow_context

    with app.app_context():
        manager = _user("hot-map-manager", "management")
        _move_request(
            manager.id,
            priority="hot",
            origin_location_text="Kraft Plater",
            destination_location_text="Raleigh East",
            cargo_text="Hot grille part",
        )

        ctx = build_production_flow_context(date=date.today())
        by_label = {node["label"]: node for node in ctx["flow_nodes"]}
        assert by_label["Raleigh East"]["hot_count"] == 1
        assert by_label["Kraft Plater"]["hot_count"] == 0

    _login(client, "hot-map-manager")
    resp = client.get("/manager/dashboard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "flow-node--hot-focus" in body
    assert 'data-hot-count="1"' in body
    assert "Hot part" in body
    assert "centerHotNode" in body


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
    assert "Live Flow Map" in body
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
    assert "LIVE FLOW BOARD" in body
    assert "Today&#39;s Route" not in body
    assert "Today's Route" not in body
    assert "Raleigh West" in body
    assert "Trim DC" in body
    assert "flow-object-card" not in body
    assert "Load Build / Trailer" not in body
    assert "Live Flow Map" not in body
    assert "Operational Alerts" not in body
    assert "Plant Computer Console" not in body
    assert "production-node-card" not in body
    assert "production-material-list" not in body
    assert "driver-shuttle-token" not in body
    assert "facility-grid" not in body
    assert "projected from events and current records" not in body
    assert "Receiving, unload, and reconcile events project here." not in body
    assert "flow-lane--route-proof" not in body
    assert "Actual Scans" not in body
    assert "Event Timeline" not in body
    assert "Replay Lines" not in body
    assert "flow-lane--plant-flow" not in body
    assert "flow-lane--flow-replay" not in body
    assert "data-flow-sequence-token" not in body
    assert "production-flow-node-positions" not in body
    assert "bindNodeDragging" not in body
    assert 'data-flow-draggable="node"' not in body
    assert "flow-replay--held-up" not in body
    assert "Shadow Ledger" not in body
    assert "Production Digital Twin" not in body
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
    assert "LIVE FLOW BOARD" in body
    assert "Today&#39;s Route" not in body
    assert "Today's Route" not in body
    assert "Trim DC" in body
    assert "FlowMapAnimator" not in body
    assert "data-flow-edge-data" not in body
    assert "flow-edge--new" not in body
    assert "data-flow-live-board" not in body
    assert "flow-edge--live" not in body
    assert "renderFilteredEdges" not in body
    assert "flow-lane--route-proof" not in body
    assert "Replay Lines" not in body
    assert "data-shadow-ledger-row" not in body
    assert "System Summary" not in body

    fragment = client.get("/mobile/production-flow-fragment")
    assert fragment.status_code == 200
    body = fragment.get_data(as_text=True)
    assert "FlowMapAnimator" in body
    assert "data-flow-edge-data" in body
    assert "flow-edge--new" in body
    assert "livePulse" in body
    assert "stroke-width: 3.7" in body
    assert "flow-edge--live" in body
    assert "renderFilteredEdges" in body
    assert "edgeMatchesTrigger" in body
    assert "flow-lane--route-proof" in body
    assert "flow-live-pulse" in body
    assert "flow-event-pulse" in body
    assert "data-flow-card-mask" in body
    assert "data-flow-edge-group" in body
    assert "livePulseRing" in body
    assert "ops-arrow-live-" in body
    assert "Replay Lines" in body
    assert "Dashed replay uses green completed, yellow held up, red hot part, and blue held flow." in body
    assert "flow-lane--flow-replay" in body
    assert "data-flow-sequence-token" in body
    assert "data-shadow-ledger-row" in body
    assert "filterShadowLedger" in body
    assert "data-flow-console-title" in body
    assert "origin_node_key" in body
    assert "destination_node_key" in body
    assert ".production-flow--mobile .ops-board-spatial .ops-spatial-body" in body
    assert 'data-flow-node-key="object:in_transit"' in body
    assert 'data-flow-event-id="' in body
    assert "System Summary" not in body


def test_driver_scoped_production_flow_filters_edges_and_ledger_counts(app):
    from app.extensions import db
    from app.models import FlowEvent
    from app.services.production_flow import build_production_flow_context

    driver = _user("scoped-flow-driver", "driver")
    other_driver = _user("other-flow-driver", "driver")
    log = _driver_log(driver, plant_name="RE")
    other_log = _driver_log(other_driver, plant_name="PW")
    db.session.add_all([
        FlowEvent(
            event_type="DEPARTED_ORIGIN",
            entity_type="route_stop",
            entity_id=str(log.id),
            stop_id=log.id,
            occurred_at=datetime.utcnow() - timedelta(minutes=3),
            source="mobile",
        ),
        FlowEvent(
            event_type="MISMATCH_DETECTED",
            entity_type="route_stop",
            entity_id=str(other_log.id),
            stop_id=other_log.id,
            occurred_at=datetime.utcnow() - timedelta(minutes=2),
            source="mobile",
        ),
    ])
    db.session.commit()

    ctx = build_production_flow_context(date=date.today(), driver_id=driver.id)

    assert [edge["stop_id"] for edge in ctx["flow_edges"]] == [log.id]
    assert ctx["ledger_summary"]["event_count"] == 1
    assert ctx["queue_summary"]["ledger_exception_count"] == 0


def test_resolved_exception_events_do_not_keep_production_nodes_blocked(app):
    from app.extensions import db
    from app.models.case import ExceptionEvent
    from app.services.production_flow import build_production_flow_context

    driver = _user("resolved-node-driver", "driver")
    log = _driver_log(driver, plant_name="RE")
    opened_at = datetime.utcnow() - timedelta(minutes=10)
    resolved_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.add_all([
        ExceptionEvent(
            event_type="damage_reported",
            severity="critical",
            stop_id=log.id,
            driver_log_id=log.id,
            driver_id=driver.id,
            plant_name="RE",
            event_date=date.today(),
            summary="Damage reported",
            created_at=opened_at,
        ),
        ExceptionEvent(
            event_type="manager_review_resolved",
            severity="medium",
            stop_id=log.id,
            driver_log_id=log.id,
            driver_id=driver.id,
            plant_name="RE",
            event_date=date.today(),
            summary="Resolved",
            created_at=resolved_at,
        ),
    ])
    db.session.commit()

    ctx = build_production_flow_context(date=date.today(), driver_id=driver.id)
    node = next(node for node in ctx["flow_nodes"] if node["label"] == "Raleigh East")

    assert [item for item in ctx["flow_items"] if item["item_type"] == "issue"] == []
    assert node["blocked_count"] == 0
    assert ctx["floor_summary"]["issue_count"] == 0


def test_mobile_dashboard_uses_compact_shared_production_flow(client, app):
    with app.app_context():
        driver = _user("mobile-pf-driver", "driver")
        _driver_log(driver, plant_name="RE")

    _login(client, "mobile-pf-driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LIVE FLOW BOARD" in body
    assert "Production Flow" not in body
    assert 'data-production-flow-lazy' not in body
    assert "/mobile/production-flow-fragment" not in body
    assert '<section class="driver-next-card">' not in body
    assert '<div class="compact-flow-canvas"' not in body
    assert "full 2D" not in body

    fragment = client.get("/mobile/production-flow-fragment")
    assert fragment.status_code == 200
    fragment_body = fragment.get_data(as_text=True)
    assert 'data-production-flow-mode="mobile"' in fragment_body
    assert "Compact Production Flow" in fragment_body
    assert "min-height: 960px" in fragment_body


def test_operations_board_is_shared_read_only_plant_floor_board(client, app):
    with app.app_context():
        manager = _user()
        _move_request(
            manager.id,
            request_number="MR-FLOOR-1",
            raw_text="Secret dispatch detail for driver 12",
            cargo_text="Sensitive cargo",
            part_number="SECRET-PART",
            assigned_driver_text="Named Driver",
        )

    _login(client, "mgr")
    resp = client.get("/operations-board")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Plant Floor Board" in body
    assert 'data-production-flow-mode="plant_floor"' in body
    assert "mgr / management" in body
    assert "MR-FLOOR-1" not in body
    assert "Secret dispatch detail" not in body
    assert "Sensitive cargo" not in body
    assert "SECRET-PART" not in body
    assert "Named Driver" not in body
    assert "Requires authorized identity." in body


def test_active_move_requests_do_not_pollute_historical_production_flow_date(app):
    from app.services.production_flow import build_production_flow_context

    manager = _user("pf-historical-mgr", "management")
    driver = _user("pf-historical-driver", "driver")
    historical_date = date.today() - timedelta(days=4)
    _driver_log(driver, date=historical_date, plant_name="RE")
    _move_request(
        manager.id,
        status="assigned",
        assigned_driver_id=driver.id,
        request_number="MR-CURRENT-ONLY",
        requested_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    ctx = build_production_flow_context(date=historical_date, driver_id=driver.id)

    assert all(item.get("label") != "MR-CURRENT-ONLY" for item in ctx["flow_items"])
    assert ctx["queue_summary"]["active_count"] == 0


def test_production_flow_manager_items_have_record_urls(app):
    from app.extensions import db
    from app.models.case import ExceptionEvent
    from app.services.production_flow import build_production_flow_context

    driver = _user("url-driver", "driver")
    transfer = _plant_transfer(driver)
    log = _driver_log(driver, plant_name="RE")
    db.session.add(ExceptionEvent(
        event_type="manager_review_requested",
        severity="medium",
        stop_id=log.id,
        driver_log_id=log.id,
        driver_id=driver.id,
        plant_name="RE",
        event_date=date.today(),
        summary="Review stop",
    ))
    db.session.commit()

    with app.test_request_context("/manager/dashboard"):
        ctx = build_production_flow_context(date=date.today(), can_review=True)

    transfer_item = next(item for item in ctx["flow_items"] if item["item_type"] == "plant_transfer")
    issue_item = next(item for item in ctx["flow_items"] if item["item_type"] == "issue")

    assert transfer_item["view_url"] == f"/manager/plant-transfers/{transfer.id}"
    assert issue_item["view_url"] == f"/manager/driver-logs/{log.id}"


def test_operations_board_requires_authentication(client, app):
    resp = client.get("/operations-board", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_board_uses_production_flow_wording_not_audit_defense(client, app):
    with app.app_context():
        manager = _user("boss-wording", "management")
        _move_request(manager.id, request_number="MR-WORD-1")

    _login(client, "boss-wording")
    resp = client.get("/manager/dashboard")

    body = resp.get_data(as_text=True)
    assert "Live Flow Map" in body
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
    assert "Replay Lines" in body


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
