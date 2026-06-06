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
        requested_at=datetime.combine(date.today(), datetime.min.time()),
    )
    base.update(kw)
    req = MoveRequest(**base)
    db.session.add(req)
    db.session.commit()
    return req


def _plant_transfer(driver, **kw):
    from app.extensions import db
    from app.models import PlantTransfer, PlantTransferLine

    base = dict(
        user_id=driver.id,
        transfer_date=date.today(),
        ship_from="PC",
        ship_to="RE",
        transfer_number="PT-001",
    )
    base.update(kw)
    transfer = PlantTransfer(**base)
    db.session.add(transfer)
    db.session.flush()
    db.session.add(
        PlantTransferLine(
            plant_transfer_id=transfer.id,
            line_number=1,
            side="left",
            part_number="3034",
            quantity="1600",
            skids="10",
        )
    )
    db.session.commit()
    return transfer


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
    assert ctx["dispatch_ticker_text"] == "NO ALERTS FROM DISPATCH"
    assert ctx["cta_pulse"]["key"] == "none"


def test_driver_route_map_with_driver_log_returns_stop_nodes(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    completed = _driver_log(driver, plant_name="RE", depart_time="08:30")
    active = _driver_log(driver, plant_name="PW", arrive_time="2026-05-28 13:00:00")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())

    assert [stop["stop_id"] for stop in ctx["stops"]] == [completed.id, active.id]
    assert ctx["stops"][0]["status"] == "completed"
    assert ctx["stops"][1]["status"] == "active"
    assert ctx["stops"][0]["board_code"] == "Stop 1"
    assert ctx["stops"][1]["board_detail"].startswith("Paint West · Empty → --")
    assert ctx["route"]["current_stop_id"] == active.id
    assert ctx["route"]["current_location"] == "Paint West"


def test_driver_route_map_stop_links_open_audit_ledger_anchor(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user()
    route_date = date(2026, 6, 2)
    log = _driver_log(driver, date=route_date, plant_name="RE", depart_time="08:30")

    with app.test_request_context("/mobile"):
        ctx = build_driver_route_map_context(driver=driver, date=route_date)

    expected_url = f"/driver_logs?date=2026-06-02#route-stop-{log.id}"
    assert ctx["stops"][0]["view_url"] == expected_url
    assert ctx["stops"][0]["actions"][0]["url"] == expected_url
    assert "/view_driver_log/" not in ctx["stops"][0]["view_url"]


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
    assert ctx["stops"][0]["badge"]["label"] == "FUELED"
    assert "+-" not in ctx["stops"][0]["board_detail"]


def test_first_empty_stop_is_route_start_without_issue(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("route_start_driver")
    _driver_log(driver, plant_name="PC", depart_time="08:20", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["movement_code"] == "route_start"
    assert stop["badge"]["label"] == "ROUTE START"
    assert stop["board_badge"]["label"] == "STARTED"
    assert stop["board_detail"] == "Paint Central · route start · arrived empty"
    assert "empty return" not in stop["board_detail"].lower()
    assert stop["issues"] == []
    assert ctx["dispatch_ticker_text"] == "NO ALERTS FROM DISPATCH"


def test_later_empty_movement_is_empty_return(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("empty_return_driver")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 08:00:00", depart_time="08:20", load_size="Empty", depart_load_size="Raleigh East Load")
    _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 09:00:00", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 10:00:00", depart_time="10:10", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][2]

    assert stop["movement_code"] == "empty_return"
    assert stop["badge"]["label"] == "EMPTY RETURN"
    assert stop["board_badge"]["label"] == "CLOSED"
    assert stop["board_detail"] == "Paint Central · empty return"
    assert stop["issues"] == []


def test_no_load_non_origin_stop_is_left_empty_not_empty_return(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("pc_no_load_driver")
    _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 08:00:00", depart_time="08:20", load_size="Empty", depart_load_size="PPL Load")
    _driver_log(driver, plant_name="PPL", arrive_time="2026-05-28 09:00:00", depart_time="09:20", load_size="PPL Load", depart_load_size="Empty")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 10:00:00", depart_time="10:10", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][2]

    assert stop["movement_code"] == "no_pickup"
    assert stop["movement_label"] == "LEFT EMPTY"
    assert stop["board_badge"]["label"] == "LEFT EMPTY"
    assert stop["board_detail"] == "Paint Central · left empty"
    assert stop["board_flow"]["text"] == "Paint Central · left empty"
    assert stop["ledger_title"] == "Paint Central · No load picked up"
    assert "empty return" not in f"{stop['board_detail']} {stop['movement_summary']} {stop['ledger_title']}".lower()
    assert [item for item in ctx["delivery_narratives"] if item["kind"] == "empty"] == []


def test_actual_return_to_origin_empty_leg_stays_empty_return(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("actual_empty_return_driver")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 08:00:00", depart_time="08:20", load_size="Empty", depart_load_size="Raleigh East Load")
    _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 09:00:00", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 10:00:00", depart_time="10:10", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][2]

    assert stop["movement_code"] == "empty_return"
    assert stop["board_detail"] == "Paint Central · empty return"
    assert stop["board_flow"]["text"] == "Paint Central · empty return"


def test_first_raleigh_east_empty_stop_is_route_start_not_empty_return(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("re_route_start_driver")
    _driver_log(driver, plant_name="RE", depart_time="08:20", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["movement_code"] == "route_start"
    assert stop["board_detail"] == "Raleigh East · route start · arrived empty"
    assert "empty return" not in stop["board_detail"].lower()


def test_picked_up_load_shows_loaded_info(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("loaded_driver")
    _driver_log(driver, plant_name="PC", depart_time="08:20", load_size="Empty", depart_load_size="Raleigh East Load")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "LOADED"
    assert stop["board_badge"]["label"] == "IN TRANSIT"
    assert stop["badge"]["severity"] == "info"
    assert stop["issues"] == []


def test_valid_drop_at_expected_destination_shows_dropped(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("valid_drop_driver")
    _driver_log(driver, plant_name="PPL", depart_time="09:20", load_size="PPL Load", depart_load_size="Empty")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "DROPPED"
    assert stop["badge"]["severity"] == "ok"
    assert stop["movement_code"] == "dropped"
    assert "dropped" in stop["movement_summary"].lower()
    assert "empty return" not in stop["board_detail"].lower()
    assert stop["issues"] == []


def test_valid_partial_drop_has_no_verify_or_risk_issue(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("valid_partial_drop_driver")
    _driver_log(
        driver,
        plant_name="PC",
        arrive_time="2026-05-28 08:00:00",
        depart_time="08:15",
        load_size="Empty",
        depart_load_size="Raleigh East Load",
        secondary_load="PPL Load",
    )
    _driver_log(
        driver,
        plant_name="PPL",
        arrive_time="2026-05-28 09:00:00",
        depart_time="09:20",
        load_size="Raleigh East Load",
        depart_load_size="Raleigh East Load",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][1]
    labels = [issue["label"] for issue in stop["issues"]]

    assert stop["badge"]["label"] == "DROPPED"
    assert stop["badge"]["severity"] == "ok"
    assert stop["issues"] == []
    assert "VERIFY" not in labels
    assert "RISK" not in labels


def test_missing_proof_is_specific_issue(app):
    from app.services.load_state import UNLOAD_NOT_COMPLETED_PREFIX
    from app.services.route_map import build_driver_route_map_context

    driver = _user("missing_proof_driver")
    _driver_log(
        driver,
        plant_name="PPL",
        depart_time="09:20",
        load_size="PPL Load",
        depart_load_size="Empty",
        downtime_reason=f"{UNLOAD_NOT_COMPLETED_PREFIX} delivery proof not attached",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "MISSING PROOF"
    assert stop["board_badge"]["label"] == "MISSING PROOF"
    assert stop["issues"][0]["code"] == "missing_proof"
    assert stop["evidence"]["proof"] == "None on file"
    assert ctx["dispatch_messages"][0]["text"].startswith("MISSING PROOF")
    assert ctx["cta_pulse"]["key"] == "camera"


def test_unrelated_same_plant_transfer_does_not_satisfy_drop_proof(app):
    from app.services.load_state import UNLOAD_NOT_COMPLETED_PREFIX
    from app.services.route_map import build_driver_route_map_context

    driver = _user("unrelated_transfer_driver")
    _driver_log(
        driver,
        plant_name="PPL",
        depart_time="09:20",
        load_size="PPL Load",
        depart_load_size="Empty",
        downtime_reason=f"{UNLOAD_NOT_COMPLETED_PREFIX} delivery proof not attached",
    )
    _plant_transfer(
        driver,
        ship_from="PC",
        ship_to="PPL",
        transfer_number="PT-UNRELATED",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "MISSING PROOF"
    assert stop["issues"][0]["code"] == "missing_proof"
    assert stop["evidence"]["transfer_count"] == 0
    assert stop["evidence"]["proof_count"] == 0


def test_destination_mismatch_is_specific_issue(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("dest_mismatch_driver")
    _driver_log(driver, plant_name="RE", depart_time="09:20", load_size="PPL Load", depart_load_size="Empty")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "DESTINATION MISMATCH"
    assert stop["issues"][0]["code"] == "destination_mismatch"
    assert stop["evidence"]["expected_destination"] == "PPL"
    assert stop["evidence"]["actual_stop"] == "Raleigh East"
    assert stop["evidence"]["action_needed"] == "Confirm destination or send to manager review"


def test_load_disappears_with_proof_but_without_confirmation_is_unconfirmed_drop(app):
    from app.extensions import db
    from app.models import DriverLogPhoto
    from app.services.load_state import UNLOAD_NOT_COMPLETED_PREFIX
    from app.services.route_map import build_driver_route_map_context

    driver = _user("unconfirmed_drop_driver")
    log = _driver_log(
        driver,
        plant_name="PPL",
        depart_time="09:20",
        load_size="PPL Load",
        depart_load_size="Empty",
        downtime_reason=f"{UNLOAD_NOT_COMPLETED_PREFIX} driver did not confirm delivery",
    )
    db.session.add(DriverLogPhoto(driver_log_id=log.id, filename="proof.jpg", original_filename="proof.jpg", source="proof"))
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "UNCONFIRMED DROP"
    assert stop["issues"][0]["code"] == "unconfirmed_drop"
    assert stop["evidence"]["proof_count"] == 1


def test_count_short_comes_from_scan_validation(app):
    from app.extensions import db
    from app.models import PartScanEvent
    from app.services.route_map import build_driver_route_map_context

    driver = _user("count_short_driver")
    log = _driver_log(driver, plant_name="RE", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    db.session.add(
        PartScanEvent(
            raw_value="RE-1",
            normalized_value="RE-1",
            stop_id=log.id,
            driver_log_id=log.id,
            driver_id=driver.id,
            scan_context="drop_scan",
            validation_status="missing",
            validation_message="Count short by 1 rack",
        )
    )
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "COUNT SHORT"
    assert stop["issues"][0]["code"] == "count_short"


def test_damage_report_shows_damage_issue(app):
    from app.extensions import db
    from app.models import DamageReport
    from app.services.route_map import build_driver_route_map_context

    driver = _user("damage_issue_driver")
    log = _driver_log(driver, plant_name="RE", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    db.session.add(DamageReport(reported_by_id=driver.id, driver_log_id=log.id, plant_name="RE", description="Rack damage", status="open"))
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "DAMAGE"
    assert stop["issues"][0]["code"] == "damage"


def test_driver_closeout_can_clear_damage_board_blocker(app):
    from app.extensions import db
    from app.models import DamageReport
    from app.models.case import ExceptionEvent
    from app.services.route_map import build_driver_route_map_context

    driver = _user("damage_closeout_driver")
    log = _driver_log(driver, plant_name="RE", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    db.session.add(DamageReport(reported_by_id=driver.id, driver_log_id=log.id, plant_name="RE", description="Rack damage", status="open"))
    db.session.add(ExceptionEvent(
        event_type="manager_review_resolved",
        severity="medium",
        stop_id=log.id,
        driver_log_id=log.id,
        driver_id=driver.id,
        summary="Driver closed issue to continue",
        details="Issue: Damage. Action: Close issue to continue. Reason: damage photo attached and route can continue.",
    ))
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["issues"] == []
    assert stop["badge"]["label"] == "DROPPED"


def test_open_stop_without_departure_is_actionable_needs_departure(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("needs_departure_driver")
    _driver_log(driver, plant_name="RE", load_size="Empty")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["badge"]["label"] == "NEEDS DEPARTURE"
    assert stop["board_badge"]["label"] == "OPEN"
    assert "needs departure" in stop["board_flow"]["text"]
    assert stop["badge"]["severity"] == "attention"
    assert stop["next_action"] == "Record departure"
    assert ctx["cta_pulse"]["key"] == "depart"


def test_earlier_open_stop_gets_actionable_missing_departure_issue(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("missing_departure_sequence_driver")
    first = _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 08:00:00")
    second = _driver_log(driver, plant_name="PW", arrive_time="2026-05-28 09:00:00")

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    first_stop, second_stop = ctx["stops"]

    assert first_stop["stop_id"] == first.id
    assert first_stop["badge"]["label"] == "MISSING DEPARTURE"
    assert first_stop["issues"][0]["code"] == "missing_departure_sequence"
    assert first_stop["issues"][0]["action"] == "Record departure or send to manager review"
    assert second_stop["stop_id"] == second.id
    assert second_stop["issues"][0]["code"] == "needs_departure"


def test_pending_posttrip_pulses_posttrip_after_clean_route(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("posttrip_cta_driver")
    _driver_log(driver, plant_name="RE", depart_time="08:20", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today(), pending_posttrip=True)

    assert ctx["stops"][0]["movement_code"] == "route_start"
    assert ctx["dispatch_ticker_text"] == "NO ALERTS FROM DISPATCH"
    assert ctx["cta_pulse"]["key"] == "posttrip"


def test_manager_resolved_review_clears_derived_issue(app):
    from app.extensions import db
    from app.models.case import ExceptionEvent
    from app.services.route_map import build_driver_route_map_context

    driver = _user("resolved_issue_driver")
    log = _driver_log(
        driver,
        plant_name="RE",
        depart_time="09:20",
        load_size="Raleigh East Load",
        depart_load_size="Empty",
        downtime_reason="missing proof on this drop",
    )
    db.session.add(ExceptionEvent(event_type="manager_review_resolved", severity="medium", stop_id=log.id, summary="Manager override"))
    db.session.commit()

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    assert stop["issues"] == []
    assert stop["badge"]["label"] == "DROPPED"


def test_driver_closeout_clears_issue_and_remains_manager_visible(client, app):
    from app.models.case import ExceptionEvent
    from app.services.route_map import build_driver_route_map_context

    driver = _user("closeout_driver", "driver")
    _user("closeout_manager", "management")
    log = _driver_log(
        driver,
        plant_name="RE",
        depart_time="09:20",
        load_size="Raleigh East Load",
        depart_load_size="Empty",
        downtime_reason="missing proof on this drop",
    )

    _login(client, "closeout_driver")
    response = client.post(
        f"/driver_logs/{log.id}/close_issue",
        data={
            "issue_type": "missing_proof",
            "resolution_action": "Close proof issue to continue",
            "reason": "Proof camera failed; load was dropped at assigned dock.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    event = ExceptionEvent.query.filter_by(
        event_type="manager_review_resolved",
        stop_id=log.id,
    ).one()
    assert event.driver_id == driver.id
    assert event.summary == "Driver closed issue to continue"
    assert "Proof camera failed" in event.details

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]
    assert stop["issues"] == []
    assert stop["badge"]["label"] == "DROPPED"

    client.get("/logout")
    _login(client, "closeout_manager")
    queue = client.get("/manager/reviews")
    assert queue.status_code == 200
    body = queue.get_data(as_text=True)
    assert "Driver-Closed Issue Closeouts" in body
    assert "Proof camera failed; load was dropped at assigned dock." in body
    assert "closeout_driver" in body


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
    assert {"Missing proof", "Mismatch", "Shortage", "Delay", "Hold"}.issubset(set(stop["flags"]))


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
    assert delivery["board_badge"]["label"] == "DELIVERED"
    assert "P-RE-8" in delivery["parts"]
    assert "HOT P-RE-10" in delivery["parts"]
    assert "Hot" in delivery["flags"]
    assert delivery["details"][0]["pickup_label"].startswith("Picked up at Paint Central")
    assert empty["title"] == "Paint Central empty load"
    assert empty["board_detail"] == "Paint Central · empty return"
    assert empty["details"][0]["board_code"] == "Stop 5"
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


def test_active_move_requests_do_not_pollute_historical_route_map_date(app):
    from app.services.route_map import build_driver_route_map_context

    manager = _user("historical_mgr", "management")
    driver = _user("historical_driver", "driver")
    historical_date = date.today() - timedelta(days=7)
    _driver_log(driver, date=historical_date, plant_name="RE", depart_time="09:00")
    _move_request(
        manager.id,
        status="assigned",
        assigned_driver_id=driver.id,
        requested_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    ctx = build_driver_route_map_context(driver=driver, date=historical_date)

    assert ctx["stops"]
    assert ctx["moves"] == []
    assert all(item["code"] != "LOAD" for item in ctx["ops_board_items"])


def test_assigned_move_request_adds_staged_ops_board_row(app):
    from app.services.route_map import build_driver_route_map_context

    manager = _user("ops_mgr", "management")
    driver = _user("staged_driver", "driver")
    _move_request(
        manager.id,
        status="assigned",
        assigned_driver_id=driver.id,
        origin_location_text="Paint Central",
        destination_location_text="Raleigh East",
        cargo_text="parts",
        quantity_text="1600 pcs",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    item = ctx["ops_board_items"][0]

    assert item["code"] == "LOAD"
    assert item["board_badge"]["label"] == "STAGED"
    assert item["board_badge"]["pill_tone"] == "open"
    assert "Paint Central → Raleigh East" in item["text"]
    assert "1600 pcs" in item["text"]


def test_transfer_sheet_and_pretrip_add_driver_board_statuses(app):
    from app.extensions import db
    from app.models import PreTrip
    from app.services.route_map import build_driver_route_map_context

    driver = _user("ops_status_driver", "driver")
    pretrip = PreTrip(user_id=driver.id, pretrip_date=date.today(), truck_number="T-12")
    db.session.add(pretrip)
    db.session.commit()
    _plant_transfer(driver)

    ctx = build_driver_route_map_context(
        driver=driver,
        date=date.today(),
        route_pretrip=pretrip,
    )
    by_code = {item["code"]: item for item in ctx["ops_board_items"]}

    assert by_code["XFER"]["board_badge"]["label"] == "SHEET ATTACHED"
    assert "10 LP" in by_code["XFER"]["text"]
    assert "TRUCK" not in by_code

    pretrip.damage_report = "CEL light"
    db.session.commit()

    ctx = build_driver_route_map_context(
        driver=driver,
        date=date.today(),
        route_pretrip=pretrip,
    )
    by_code = {item["code"]: item for item in ctx["ops_board_items"]}

    assert by_code["TRUCK"]["board_badge"]["label"] == "DEFECT"


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
    assert "<small>Continue route</small>" in html
    assert "<strong>Add Stop</strong>\n      <span>Attach document</span>" not in html


def test_mobile_between_loads_route_keeps_add_stop_cta(app):
    from flask import render_template

    today = date.today()
    with app.test_request_context("/mobile"):
        html = render_template(
            "partials/_compact_route_map.html",
            route_map={
                "map_mode": "live_current_work",
                "stops": [
                    {
                        "stop_id": 1,
                        "sequence": 1,
                        "status": "completed",
                        "plant_name": "Raleigh East",
                        "board_badge": {"row_tone": "delivery", "pill_tone": "delivery", "short": "DELIVERED"},
                        "badge": {"severity": "ok"},
                        "board_flow": {"mode": "plain", "text": "Raleigh East · dropped Parts"},
                        "board_detail": "Raleigh East · dropped Parts",
                        "arrived_with": "Paint Central Load",
                        "departed_with": "Empty",
                        "wait_minutes": 0,
                        "no_pickup": False,
                        "status_label": "Completed",
                        "next_action": "No action needed",
                    }
                ],
                "route": {"next_action": "Attach document"},
            },
            route_cta={
                "next_action": "Attach document",
                "primary_cta": {"label": "Attach Document", "action": "attach_document", "style": "primary"},
                "route_finalized": False,
            },
            route_cta_urls={"add_stop": "/new_driving_log", "attach_document": "/driver/transfers/new"},
            route_date=today,
            today_local_date=today,
        )

    assert '<a class="md-flow-primary-cta add-stop-action" href="/new_driving_log"' in html
    assert "<strong>Add Stop</strong>" in html
    assert "<small>Continue route</small>" in html


def test_mobile_live_flow_board_keeps_stop_sequence_and_active_glow(app):
    from flask import render_template
    from app.services.route_map import build_driver_route_map_context

    driver = _user("driver_active_sequence", "driver")
    completed = _driver_log(driver, plant_name="RE", depart_time="08:30")
    active = _driver_log(driver, plant_name="PW", arrive_time="2026-05-28 13:00:00")

    with app.test_request_context("/mobile"):
        ctx = build_driver_route_map_context(driver=driver, date=date.today())
        html = render_template(
            "partials/_compact_route_map.html",
            route_map=ctx,
            route_cta={"next_action": "Record departure"},
            route_cta_urls={"record_departure": "/driver_logs/2/depart"},
        )

    completed_row = html.index(f'data-title="Stop 1 - {ctx["stops"][0]["plant_name"]}"')
    active_row = html.index(f'data-title="Stop 2 - {ctx["stops"][1]["plant_name"]}"')
    assert completed.id == ctx["stops"][0]["stop_id"]
    assert active.id == ctx["stops"][1]["stop_id"]
    assert completed_row < active_row
    assert 'is-completed-stop' in html[completed_row - 240:completed_row]
    assert 'class="md-flow-row tone-active"' in html[active_row - 240:active_row]
    assert 'is-completed-stop' not in html[active_row - 240:active_row]
    assert f'{ctx["stops"][1]["plant_name"]} &middot; record departure' in html
    assert f'{ctx["stops"][1]["plant_name"]} &middot; {ctx["stops"][1]["wait_label"]} &middot; record departure' not in html
    assert "<span>Wait</span>" not in html


def test_driver_dashboard_shows_assigned_move_as_staged_board_row(client, app):
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
    assert "Assigned Move Queue" not in body
    assert "MR-REAL-1" in body
    assert ">STAGED<" in body


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
    assert body.count('data-title="Stop ') == 5
    assert 'data-detail-template="primary-event"' not in body
    assert 'data-detail-template="event-' not in body
    assert "Dropped <strong>2 loads</strong> of <strong>Parts</strong>" not in body
    first_pickup = body.index('data-title="Stop 1 - Paint Central"')
    first_drop = body.index('data-title="Stop 2 - Raleigh East"')
    second_pickup = body.index('data-title="Stop 3 - Paint Central"')
    second_drop = body.index('data-title="Stop 4 - Raleigh East"')
    empty_return = body.index('data-title="Stop 5 - Paint Central"')
    assert [first_pickup, first_drop, second_pickup, second_drop, empty_return] == sorted(
        [first_pickup, first_drop, second_pickup, second_drop, empty_return]
    )
    assert "flow-route-pair" in body
    assert '<span class="flow-arrow flow-route-arrow" aria-hidden="true">→</span>' in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert "<em>Delivered</em><strong>Raleigh East</strong>" in body
    assert "LIVE FLOW BOARD" in body
    assert 'data-detail-template="route-stop-' in body
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
    assert "START DAY" in body
    assert "No stops logged yet today. Start day by recording the first stop." in body
    assert "Assigned Move Queue" not in body
    assert "Live Flow Map" not in body


def test_mobile_route_board_does_not_show_manager_wide_requests(client, app):
    with app.app_context():
        manager = _user("flow_mgr", "management")
        _user("flow_driver", "driver")
        _move_request(manager.id, request_number="MR-BROAD-1")

    _login(client, "flow_driver")
    resp = client.get("/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
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
    assert "Live Flow Map" not in body
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
    assert "Add proof photo" in body            # action
    assert "Send to manager review" in body     # action
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
    assert ">IN REVIEW<" in body
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
    assert "IN TRANSIT" not in body  # Pickup load was later dropped, so it is no longer live in transit.
    assert ">DROPPED<" not in body   # Delivered work should not regress to a weaker board status.
    assert "Picked up <strong>Parts</strong>" in body
    assert "Dropped <strong>Parts</strong>" in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert '<span class="flow-route-end flow-route-end--deliver"><span class="flow-arrow flow-route-arrow" aria-hidden="true">→</span><em>Delivered</em><strong>Raleigh East</strong></span>' in body
    assert '<span class="flow-arrow flow-route-arrow" aria-hidden="true">→</span>' in body
    assert "grid-template-columns: auto auto;" in body
    assert "grid-template-columns: auto auto minmax(0, 1fr);" in body
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);" not in body
    assert "Raleigh East Load &rarr; Empty" not in body
    assert ">DELIVERED<" in body      # confirmed drop can graduate from DROPPED
    assert 'class="flow-code"' not in body


def test_unknown_route_pair_labels_are_explicit_not_fake(app):
    from app.services.route_map import build_driver_route_map_context

    driver = _user("driver_unknown_pair", "driver")
    _driver_log(
        driver,
        plant_name="PC",
        arrive_time="2026-05-28 08:00:00",
        depart_time="08:15",
        load_size="Empty",
        depart_load_size="Mystery Load",
    )
    _driver_log(
        driver,
        plant_name="RE",
        arrive_time="2026-05-28 09:00:00",
        depart_time="09:20",
        load_size="Mystery Load",
        depart_load_size="Empty",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    pickup_stop = ctx["stops"][0]
    drop_stop = ctx["stops"][1]

    assert pickup_stop["board_flow"]["deliver"] == "Destination needs confirmation"
    assert drop_stop["board_flow"]["pickup"] == "Pickup source unknown"
    combined = (
        f"{pickup_stop['board_detail']} {drop_stop['board_detail']} "
        f"{pickup_stop['board_flow']} {drop_stop['board_flow']}"
    )
    assert "Earlier stop" not in combined
    assert "Next stop" not in combined


def test_unknown_route_pair_renders_single_line_fact(client, app):
    with app.app_context():
        driver = _user("driver_unknown_pair_render", "driver")
        _driver_log(
            driver,
            plant_name="PC",
            arrive_time="2026-05-28 08:00:00",
            depart_time="08:15",
            load_size="Empty",
            depart_load_size="Mystery Load",
        )
        _driver_log(
            driver,
            plant_name="RE",
            arrive_time="2026-05-28 09:00:00",
            depart_time="09:20",
            load_size="Mystery Load",
            depart_load_size="Empty",
        )

    _login(client, "driver_unknown_pair_render")
    body = client.get("/mobile").get_data(as_text=True)

    assert "Paint Central &middot; Picked up <strong>Parts</strong>" in body
    assert "Raleigh East &middot;" in body
    assert '<span class="flow-route-pair">' not in body
    assert "<em>Pickup</em><strong>Pickup source unknown</strong>" not in body
    assert "<em>Delivered</em><strong>Destination needs confirmation</strong>" not in body
    assert "<em>Pickup</em><strong>--</strong>" not in body
    assert "<em>Delivered</em><strong>--</strong>" not in body


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

    assert "PPL &middot; Dropped <strong>1 load of Parts</strong>" in body
    assert "<em>Pickup</em><strong>Paint Central</strong>" in body
    assert "<em>Delivered</em><strong>PPL</strong>" in body
    assert "ROUTE?" not in body
    assert "Verify route" not in body


# --- Regression: in-transit cargo wording + next-action CTA (mobile flow board) ---


def test_in_transit_pickup_reads_destination_not_delivered(app):
    """Picked up at Paint Central, headed to Raleigh East, not yet dropped.

    The inline board label must NOT claim the load was delivered while the
    status pill still says IN TRANSIT. The destination still displays.
    """
    from flask import render_template
    from app.services.route_map import build_driver_route_map_context

    driver = _user("in_transit_pickup_driver")
    _driver_log(
        driver,
        plant_name="PC",
        depart_time="08:20",
        load_size="Empty",
        depart_load_size="Raleigh East Load",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][0]

    # Status pill stays IN TRANSIT while the load is moving.
    assert stop["board_badge"]["label"] == "IN TRANSIT"
    # Classification: destination is known, but the leg is not a delivery.
    assert stop["board_flow"]["deliver"] == "Raleigh East"
    assert stop["board_flow"]["deliver_state"] == "destination"

    with app.test_request_context("/mobile"):
        html = render_template(
            "partials/_compact_route_map.html",
            route_map=ctx,
            route_cta={"next_action": "Add Stop"},
            route_cta_urls={"add_stop": "/new_driving_log"},
        )

    # The exact contradiction the driver reported must be gone on mobile.
    assert "<em>Destination</em><strong>Raleigh East</strong>" in html
    assert "<em>Delivered</em><strong>Raleigh East</strong>" not in html


def test_pickup_label_graduates_to_delivered_after_drop_completes(app):
    """After the Raleigh East drop is recorded, the pickup leg may read Delivered.

    Pill and inline label agree (both DELIVERED) once the drop completes.
    """
    from app.services.route_map import build_driver_route_map_context

    driver = _user("pickup_graduates_driver")
    _driver_log(
        driver,
        plant_name="PC",
        arrive_time="2026-05-28 08:00:00",
        depart_time="08:15",
        load_size="Empty",
        depart_load_size="Raleigh East Load",
    )
    _driver_log(
        driver,
        plant_name="RE",
        arrive_time="2026-05-28 09:00:00",
        depart_time="09:20",
        load_size="Raleigh East Load",
        depart_load_size="Empty",
    )

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    pickup = ctx["stops"][0]

    assert pickup["board_badge"]["label"] == "DELIVERED"
    assert pickup["board_flow"]["deliver"] == "Raleigh East"
    assert pickup["board_flow"]["deliver_state"] == "delivered"


def test_in_transit_cta_names_destination_instead_of_generic_add_stop(app):
    """A known in-transit destination makes the CTA say 'Arrive at <plant>'."""
    from types import SimpleNamespace
    from app.services.route_context import build_route_cta_context

    departed_stop = SimpleNamespace(id=1, depart_time="08:20")
    route_context = SimpleNamespace(
        rows=[{"log_id": 1}],
        current_stop=departed_stop,
        route_status="active",
        route_finalized=False,
        all_departed=True,
        posttrip_status=None,
        current_cargo={"destination_label": "Raleigh East", "destination": "RE"},
    )

    cta = build_route_cta_context(
        route_context,
        route_is_active=True,
        has_active_shift=True,
        route_date=date.today(),
        today_local_date=date.today(),
    )

    assert cta["primary_cta"]["label"] == "Arrive at Raleigh East"
    # Action and its route guards are unchanged — only the label is specific.
    assert cta["primary_cta"]["action"] == "add_stop"


def test_idle_active_route_keeps_generic_add_stop_cta(app):
    """With no cargo in transit, the CTA stays the generic 'Add Stop'."""
    from types import SimpleNamespace
    from app.services.route_context import build_route_cta_context

    departed_stop = SimpleNamespace(id=1, depart_time="08:20")
    route_context = SimpleNamespace(
        rows=[{"log_id": 1}],
        current_stop=departed_stop,
        route_status="active",
        route_finalized=False,
        all_departed=True,
        posttrip_status=None,
        current_cargo={"destination_label": None, "destination": None},
    )

    cta = build_route_cta_context(
        route_context,
        route_is_active=True,
        has_active_shift=True,
        route_date=date.today(),
        today_local_date=date.today(),
    )

    assert cta["primary_cta"]["label"] == "Add Stop"
    assert cta["primary_cta"]["action"] == "add_stop"


def test_left_empty_stop_has_no_delivered_wording(app):
    """A no-load stop away from origin stays 'left empty' with no route pair."""
    from app.services.route_map import build_driver_route_map_context

    driver = _user("left_empty_label_driver")
    _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 08:00:00", depart_time="08:20", load_size="Empty", depart_load_size="PPL Load")
    _driver_log(driver, plant_name="PPL", arrive_time="2026-05-28 09:00:00", depart_time="09:20", load_size="PPL Load", depart_load_size="Empty")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 10:00:00", depart_time="10:10", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][2]

    assert stop["board_flow"]["text"] == "Paint Central · left empty"
    assert "deliver_state" not in stop["board_flow"]
    assert "empty return" not in stop["board_detail"].lower()


def test_actual_empty_return_stop_keeps_empty_return_wording(app):
    """A true empty return to origin stays 'empty return' with no route pair."""
    from app.services.route_map import build_driver_route_map_context

    driver = _user("empty_return_label_driver")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 08:00:00", depart_time="08:20", load_size="Empty", depart_load_size="Raleigh East Load")
    _driver_log(driver, plant_name="RE", arrive_time="2026-05-28 09:00:00", depart_time="09:20", load_size="Raleigh East Load", depart_load_size="Empty")
    _driver_log(driver, plant_name="PC", arrive_time="2026-05-28 10:00:00", depart_time="10:10", load_size="Empty", depart_load_size="Empty", no_pickup=True)

    ctx = build_driver_route_map_context(driver=driver, date=date.today())
    stop = ctx["stops"][2]

    assert stop["board_flow"]["text"] == "Paint Central · empty return"
    assert "deliver_state" not in stop["board_flow"]


def test_active_wait_banner_mutes_depart_button_when_board_cta_owns_it(app):
    """When the green board CTA carries Depart/Load, the banner is a timer chip.

    The duplicate "Depart / Load" button is dropped, but the wait timer and
    stop context stay so the driver still sees the live clock.
    """
    from flask import render_template

    wait = {"minutes": 2, "seconds": 134, "plant": "Raleigh East", "log_id": 1}

    with app.test_request_context("/mobile"):
        muted = render_template(
            "_driver_active_wait_banner.html",
            active_driver_wait=wait,
            active_wait_show_action=False,
        )
        shown = render_template(
            "_driver_active_wait_banner.html",
            active_driver_wait=wait,
            active_wait_show_action=True,
        )

    # Timer chip (label, plant, elapsed clock) stays in both states.
    for html in (muted, shown):
        assert "Active Stop Wait" in html
        assert "Raleigh East" in html
        assert "2:14" in html
        assert "elapsed" in html

    # The duplicate depart button is gone when muted, present otherwise.
    assert "driver-active-wait-action" not in muted
    assert ">Depart / Load<" not in muted
    assert "driver-active-wait-action" in shown
    assert ">Depart / Load<" in shown
