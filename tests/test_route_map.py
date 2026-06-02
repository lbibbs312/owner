"""Tests for route-map view models and reusable drawer partials."""
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


def _user(username="driver1", role="driver"):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=f"{username}@example.com", role=role)
    user.set_password("password1")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post(
        "/login",
        data={"login_name": username, "password": "password1"},
        follow_redirects=False,
    )


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


def _move_request(creator_id, **kw):
    from app.extensions import db
    from app.models import MoveRequest

    base = dict(
        raw_text="Move HDPE from Raleigh East to Paint West",
        created_by_id=creator_id,
        status="open",
        priority="normal",
        origin_location_text="Raleigh East",
        destination_location_text="Paint West",
        cargo_text="HDPE",
    )
    base.update(kw)
    req = MoveRequest(**base)
    db.session.add(req)
    db.session.commit()
    return req


def test_driver_route_map_no_data_returns_safe_empty_state(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    ctx = build_driver_route_map_context(driver=driver, date=date.today())

    assert ctx["empty_states"]["no_route"] is True
    assert ctx["empty_states"]["no_stops"] is True
    assert ctx["empty_states"]["no_move_requests"] is True
    assert ctx["route"]["current_location"] == "No current data"
    assert ctx["stops"] == []
    assert ctx["delivery_narratives"] == []
    assert ctx["moves"] == []


def test_driver_route_map_with_driver_log_returns_stop_nodes(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    completed = _driver_log(driver, plant_name="RE", depart_time="08:30")
    active = _driver_log(driver, plant_name="PW", arrive_time="2026-05-28 13:00:00")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())

    assert [stop["stop_id"] for stop in ctx["stops"]] == [completed.id, active.id]
    assert ctx["stops"][0]["status"] == "completed"
    assert ctx["stops"][1]["status"] == "active"
    assert ctx["stops"][0]["board_code"] == "STP-1"
    assert ctx["stops"][1]["board_detail"].startswith("Paint West · Empty → --")
    assert ctx["route"]["current_stop_id"] == active.id
    assert ctx["route"]["current_location"] == "Paint West"


def test_fuel_stop_uses_neutral_mileage_when_pretrip_delta_is_impossible(app):
    from app.extensions import db
    from app.models import PreTrip
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    pretrip = PreTrip(user_id=driver.id, pretrip_date=date.today(), start_mileage=150000)
    db.session.add(pretrip)
    db.session.commit()

    _driver_log(
        driver,
        plant_name="FUEL",
        fuel=True,
        fuel_mileage=1572,
        depart_time="12:20",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today(), route_pretrip=pretrip)

    assert ctx["stops"][0]["board_code"] == "FUEL"
    assert ctx["stops"][0]["board_detail"] == "1,572 mi recorded"
    assert "+-" not in ctx["stops"][0]["board_detail"]


def test_driver_route_map_flags_real_exception_states_for_warning_rows(app):
    from app.extensions import db
    from app.models import DamageReport
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    risky = _driver_log(
        driver,
        plant_name="RE",
        downtime_reason="Missing proof, transfer mismatch, rack shortage, delayed audit risk hold",
    )
    db.session.add(
        DamageReport(
            reported_by_id=driver.id,
            driver_log_id=risky.id,
            plant_name="RE",
            description="Damage found on rack",
            status="open",
        )
    )
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["status"] == "needs_review"
    assert stop["has_damage"] is True
    assert stop["has_issue"] is True
    assert {"Missing proof", "Mismatch", "Shortage", "Delay", "Audit risk", "Hold"}.issubset(set(stop["flags"]))


def test_driver_route_map_aggregates_delivery_and_empty_load_narratives(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    for hour in (8, 10):
        _driver_log(
            driver,
            plant_name="PC",
            arrive_time=f"2026-05-28 {hour:02d}:00:00",
            depart_time=f"{hour:02d}:15",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            part_number=f"P-RE-{hour}",
            hot_parts=(hour == 10),
        )
        _driver_log(
            driver,
            plant_name="RE",
            arrive_time=f"2026-05-28 {hour + 1:02d}:00:00",
            depart_time=f"{hour + 1:02d}:20",
            load_size="Raleigh East Load",
            depart_load_size="Empty",
            no_pickup=True,
        )
    _driver_log(
        driver,
        plant_name="PC",
        arrive_time="2026-05-28 12:00:00",
        depart_time="12:10",
        load_size="Empty",
        depart_load_size="Empty",
        no_pickup=True,
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    narratives = ctx["delivery_narratives"]

    delivery = next(item for item in narratives if item["kind"] == "delivery")
    empty = next(item for item in narratives if item["kind"] == "empty")
    assert delivery["title"] == "Raleigh East delivery from Paint Central"
    assert delivery["count"] == 2
    assert delivery["load_count_label"] == "2 loads"
    assert "P-RE-8" in delivery["parts"]
    assert "HOT P-RE-10" in delivery["parts"]
    assert "Hot" in delivery["flags"]
    assert delivery["details"][0]["pickup_label"].startswith("Picked up at Paint Central")
    assert empty["title"] == "Paint Central empty load"
    assert empty["board_detail"] == "Paint Central · empty return"
    assert empty["details"][0]["board_code"] == "STP-5"
    assert empty["count"] == 1
    assert "No pickup" in empty["flags"]


def test_route_map_with_move_requests_returns_plants_and_lanes(app):
    from app.services.route_map import build_manager_route_map_context

    manager = _user("mgr", "management")
    req = _move_request(manager.id)

    ctx = build_manager_route_map_context(date=date.today())
    labels = {plant["label"] for plant in ctx["plants"]}

    assert "Raleigh East" in labels
    assert "Paint West" in labels
    assert ctx["moves"][0]["move_request_id"] == req.id
    assert ctx["lanes"][0]["origin_label"] == "Raleigh East"
    assert ctx["lanes"][0]["destination_label"] == "Paint West"
    assert ctx["empty_states"]["no_lane_data"] is False


def test_completed_request_and_linked_stop_statuses(app):
    from app.services.route_map import build_driver_route_map_context

    manager = _user("mgr", "management")
    driver = _user("driver2", "driver")
    stop = _driver_log(driver, plant_name="RE", depart_time="09:00")
    _move_request(
        manager.id,
        status="completed",
        assigned_driver_id=driver.id,
        linked_driver_log_id=stop.id,
        updated_at=datetime.utcnow() - timedelta(minutes=5),
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())

    assert ctx["stops"][0]["status"] == "completed"
    assert ctx["moves"][0]["status"] == "completed"
    assert ctx["moves"][0]["linked_stop_id"] == stop.id


def test_route_map_drawer_partials_render(app):
    from flask import render_template
    from app.services.route_map import build_manager_route_map_context

    manager = _user("mgr", "management")
    driver = _user("driver3", "driver")
    _driver_log(driver, plant_name="RE")
    _move_request(manager.id, assigned_driver_id=driver.id)

    with app.test_request_context("/manager/dashboard"):
        ctx = build_manager_route_map_context(date=date.today())
        stop_html = render_template("partials/_stop_detail_drawer.html", route_map=ctx)
        plant_html = render_template("partials/_plant_detail_drawer.html", route_map=ctx)
        move_html = render_template("partials/_move_detail_drawer.html", route_map=ctx)

    assert "Next action" in stop_html
    assert "today route stops" in plant_html.lower()
    assert "Original request" in move_html


def test_add_stop_action_copy_stays_route_specific(app):
    from flask import render_template

    with app.test_request_context("/mobile"):
        html = render_template(
            "partials/_compact_route_map.html",
            route_map={"map_mode": "live_current_work", "stops": [], "route": {"next_action": "Attach document"}},
            route_cta={"next_action": "Attach document"},
            route_cta_urls={"add_stop": "/new_driving_log", "attach_document": "/driver/transfers/new"},
        )

    assert "<strong>Add Stop</strong>" in html
    assert "<span>Continue route</span>" in html
    assert "<strong>Add Stop</strong>\n      <span>Attach document</span>" not in html


def test_driver_dashboard_keeps_assigned_queue_off_main_route_display(client, app):
    driver = None
    with app.app_context():
        manager = _user("mgr", "management")
        driver = _user("driver4", "driver")
        _move_request(
            manager.id,
            status="assigned",
            assigned_driver_id=driver.id,
            request_number="MR-REAL-1",
        )

    _login(client, "driver4")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LIVE FLOW BOARD" in body
    assert "No route stops logged for this date." in body
    assert "Assigned Move Queue" not in body
    assert "MR-REAL-1" not in body
    assert "Production Flow" not in body


def test_driver_dashboard_renders_route_narrative_cards(client, app):
    with app.app_context():
        driver = _user("driver_route_narrative", "driver")
        for hour in (8, 10):
            _driver_log(
                driver,
                plant_name="PC",
                arrive_time=f"2026-05-28 {hour:02d}:00:00",
                depart_time=f"{hour:02d}:15",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                part_number=f"P-RE-{hour}",
                hot_parts=(hour == 10),
            )
            _driver_log(
                driver,
                plant_name="RE",
                arrive_time=f"2026-05-28 {hour + 1:02d}:00:00",
                depart_time=f"{hour + 1:02d}:20",
                load_size="Raleigh East Load",
                depart_load_size="Empty",
                no_pickup=True,
            )
        _driver_log(
            driver,
            plant_name="PC",
            arrive_time="2026-05-28 12:00:00",
            depart_time="12:10",
            load_size="Empty",
            depart_load_size="Empty",
            no_pickup=True,
        )

    _login(client, "driver_route_narrative")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Raleigh East delivery from Paint Central" in body
    assert "Raleigh East Load delivered from Paint Central to Raleigh East" in body
    assert "Dropped <strong>2 loads</strong> of <strong>Parts</strong>" in body
    assert "flow-route-pair" in body
    assert '<span class="flow-arrow flow-route-arrow" aria-hidden="true">→</span>' in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert "<em>Deliver</em><strong>Raleigh East</strong>" in body
    assert "2 loads" in body
    assert "2 stops" in body
    assert "P-RE-8" in body
    assert "HOT P-RE-10" in body
    assert "Paint Central empty load" in body
    assert "Arrived empty and departed empty at Paint Central" in body
    assert "LIVE FLOW BOARD" in body
    assert 'data-flow-row' in body
    assert 'data-flow-open-url' in body
    assert 'data-md-flow-work-panel' in body
    assert body.count('class="route-focus-card') == 0
    assert '<div class="compact-flow-canvas"' not in body
    assert 'class="route-narrative-count"' not in body


def test_driver_dashboard_renders_with_no_assigned_requests(client, app):
    with app.app_context():
        _user("driver5", "driver")

    _login(client, "driver5")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LIVE FLOW BOARD" in body
    assert "No route stops logged for this date." in body
    assert "Assigned Move Queue" not in body
    assert "Live Flow Map" not in body
    assert "Production Flow" not in body


def test_mobile_production_flow_view_is_not_driver_scoped(client, app):
    with app.app_context():
        manager = _user("flow_mgr", "management")
        _user("flow_driver", "driver")
        _move_request(manager.id, request_number="MR-BROAD-1")

    _login(client, "flow_driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-production-flow-mode="mobile"' not in body
    assert "Production Flow" not in body
    assert "MR-BROAD-1" not in body
    assert "LIVE FLOW BOARD" in body


def test_manager_dashboard_uses_issue_terminology(client, app):
    with app.app_context():
        _user("boss", "management")

    _login(client, "boss")
    resp = client.get("/manager/dashboard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Needs Attention" in body
    assert "Live Flow Map" in body
    assert "Critical Exceptions" not in body


def test_board_issue_drawer_explains_reason_and_offers_actions(client, app):
    with app.app_context():
        driver = _user("driver_issue_drawer", "driver")
        _driver_log(
            driver,
            plant_name="RE",
            arrive_time="2026-05-28 09:00:00",
            depart_time="09:20",
            load_size="Raleigh East Load",
            depart_load_size="Empty",
            downtime_reason="missing proof on this drop",
        )
    _login(client, "driver_issue_drawer")
    resp = client.get("/mobile")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "MISSING PROOF" in body              # explicit reason, never generic RISK
    assert "no photo, scan, or driver confirmation" in body   # drawer "why"
    assert "Add proof / photo" in body          # action
    assert "Send to manager" in body            # action
    assert "/request_review" in body            # manager-review endpoint wired


def test_manager_review_request_shows_in_review_state(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models.case import ExceptionEvent
        driver = _user("driver_review_state", "driver")
        log = _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 10:00:00",
                          depart_time="10:15", load_size="Raleigh East Load", depart_load_size="Empty")
        db.session.add(ExceptionEvent(event_type="manager_review_requested", severity="medium",
                                      stop_id=log.id, summary="review"))
        db.session.commit()
    _login(client, "driver_review_state")
    body = client.get("/mobile").get_data(as_text=True)
    assert ">REVIEW<" in body
    assert "IN REVIEW" in body


def test_completed_stop_states_reflect_cargo_action(client, app):
    with app.app_context():
        driver = _user("driver_states", "driver")
        _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 08:00:00",
                    depart_time="08:15", load_size="Empty", depart_load_size="Raleigh East Load")
        _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 09:00:00",
                    depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    _login(client, "driver_states")
    body = client.get("/mobile").get_data(as_text=True)
    assert "LOADED" in body          # Empty -> Load = picked up
    assert "DROPPED" in body         # Load -> Empty = dropped at destination
    assert "Picked up <strong>Parts</strong>" in body
    assert "Dropped <strong>Parts</strong>" in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert "<em>Deliver</em><strong>Raleigh East</strong>" in body
    assert '<span class="flow-arrow flow-route-arrow" aria-hidden="true">→</span>' in body
    assert "Raleigh East Load &rarr; Empty" not in body
    assert ">DELIVERED<" not in body  # no generic catch-all label
    assert 'class="flow-code"' not in body  # STP- code column removed


def test_partial_drop_is_recorded_not_route_review(client, app):
    with app.app_context():
        driver = _user("driver_partial_drop", "driver")
        _driver_log(
            driver,
            plant_name="PC",
            arrive_time="2026-05-28 08:00:00",
            depart_time="08:15",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            secondary_load="PPL Load",
            created_at=datetime(2026, 5, 28, 8, 0),
        )
        _driver_log(
            driver,
            plant_name="PPL",
            arrive_time="2026-05-28 09:00:00",
            depart_time="09:20",
            load_size="Raleigh East Load",
            depart_load_size="Raleigh East Load",
            created_at=datetime(2026, 5, 28, 9, 0),
        )

    _login(client, "driver_partial_drop")
    body = client.get("/mobile").get_data(as_text=True)

    assert "PPL &middot; Dropped <strong>1 load</strong> of <strong>Parts</strong>" in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert "<em>Deliver</em><strong>PPL</strong>" in body
    assert "ROUTE?" not in body
    assert "Verify route" not in body
