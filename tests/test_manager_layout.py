"""Layout and route smoke tests for manager ops-board surfaces."""
from datetime import date, datetime, timedelta
import re

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


def _user(username="driver1", role="driver", **kwargs):
    from app.extensions import db
    from app.models import User

    user = User(
        username=username,
        email=f"{username}@example.com",
        role=role,
        first_name=kwargs.get("first_name"),
        last_name=kwargs.get("last_name"),
        department=kwargs.get("department"),
        employee_id=kwargs.get("employee_id"),
    )
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
        arrive_time="2026-06-05 08:00:00",
        depart_time="08:24",
        load_size="Empty",
        depart_load_size="Empty",
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
        raw_text="Move finished racks from a very long Raleigh East staging lane to an equally long Paint Central overflow dock",
        created_by_id=creator_id,
        status="open",
        priority="high",
        origin_location_text="Raleigh East North Overflow Staging Lane With Long Name",
        destination_location_text="Paint Central Secondary Review Dock With Long Name",
        cargo_text="Finished rack load with long cargo description",
        requested_at=datetime.utcnow() - timedelta(minutes=10),
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
        ship_from="RE",
        ship_to="PC",
        transfer_number="TRX-LAYOUT",
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
            part_number="LP-LAYOUT-001",
            quantity="1200",
            skids="8",
        )
    )
    db.session.commit()
    return transfer


def _seed_large_manager_dashboard(manager):
    from app.extensions import db
    from app.models import ExceptionEvent, Task

    logs = []
    for idx in range(20):
        driver = _user(
            f"layout_driver_{idx}",
            "driver",
            first_name="AlexandriaLongRouteName",
            last_name=f"OperationsDriverWithLongName{idx}",
            department="Trim" if idx % 2 else "Plastics",
            employee_id=f"LD{idx:02d}",
        )
        log = _driver_log(
            driver,
            plant_name="PC" if idx % 2 else "RE",
            arrive_time=f"2026-06-05 {8 + (idx % 8):02d}:00:00",
            depart_time=f"{8 + (idx % 8):02d}:24",
            maintenance=idx < 15,
            downtime_reason=(
                f"Long timing alert row {idx}: driver reported equipment delay "
                "and needs manager visibility without clipping the text."
            ) if idx < 15 else None,
            dock_wait_minutes=idx + 3,
        )
        logs.append(log)

    for log in logs[:4]:
        db.session.add(
            ExceptionEvent(
                event_type="manager_review_requested",
                severity="medium",
                stop_id=log.id,
                driver_log_id=log.id,
                driver_id=log.driver_id,
                plant_name=log.plant_name,
                event_date=log.date,
                summary="Manager review requested",
                details="Pending review row with enough text to exercise wrapping.",
            )
        )

    for idx in range(6):
        _move_request(
            manager.id,
            priority="hot" if idx % 2 else "high",
            status="assigned" if idx % 2 else "open",
            origin_location_text=f"Raleigh East Long Origin Lane {idx} With Extra Dispatch Detail",
            destination_location_text=f"Paint Central Long Destination Dock {idx} With Extra Dispatch Detail",
        )

    for idx in range(5):
        db.session.add(
            Task(
                title=f"Active dispatch job {idx}",
                details="Active job with long notes that should wrap in manager cards.",
                status="pending" if idx % 2 else "in-progress",
                assigned_to=logs[idx].driver_id,
            )
        )
    db.session.commit()
    return logs


def test_manager_dashboard_layout_handles_large_ops_board(client, app):
    with app.app_context():
        manager = _user("layout_boss", "management")
        _seed_large_manager_dashboard(manager)

    _login(client, "layout_boss")
    response = client.get("/manager/dashboard?focus=routes&target=attention")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Live Routes &amp; Stops" in body
    count_match = re.search(r"(\d+) issues visible; scroll this panel for the full list", body)
    assert count_match
    assert int(count_match.group(1)) >= 15
    assert "AlexandriaLongRouteName OperationsDriverWithLongName14" in body
    assert "Raleigh East Long Origin Lane 4 With Extra Dispatch Detail" in body
    assert ".mc-main { flex:1 1 auto; min-width:0; display:flex; flex-direction:column; min-height:100vh; overflow:visible; }" in body
    assert ".critical-list { display:grid; gap:8px; padding:12px 16px; max-height:min(72vh,720px); overflow-y:auto;" in body
    assert ".kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; }" in body
    assert "body.mgr-active .production-flow--admin" in body
    assert 'style="grid-template-columns:repeat(' not in body


def test_move_requests_uses_movedefense_manager_shell(client, app):
    with app.app_context():
        manager = _user("queue_boss", "management")
        _user("queue_driver", "driver", first_name="Driver", last_name="WithLongName")
        _move_request(manager.id)

    _login(client, "queue_boss")
    response = client.get("/manager/move-requests")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "mq-shell" in body
    assert "Manager Console" in body
    assert "Move Request Queue" in body
    assert "Raleigh East North Overflow Staging Lane With Long Name" in body
    assert ".queue-table { background:#fff; border:1px solid #e2e8f0; border-radius:12px; overflow:auto;" in body

    empty_response = client.get("/manager/move-requests?status=cancelled")
    assert empty_response.status_code == 200
    empty_body = empty_response.get_data(as_text=True)
    assert "No move requests in this queue. New requests and dispatch captures will appear here." in empty_body


def test_production_flow_board_accepts_underscore_alias(client, app):
    with app.app_context():
        _user("flow_boss", "management")

    _login(client, "flow_boss")
    response = client.get("/production_flow_board")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Plant Floor Board" in body
    assert "production-flow--plant-floor" in body


def test_driver_dashboard_visible_board_removes_loads_parts_group(client, app):
    with app.app_context():
        driver = _user("layout_driver", "driver")
        _driver_log(
            driver,
            plant_name="RE",
            arrive_time="2026-06-05 08:00:00",
            depart_time="08:15",
            load_size="Empty",
            depart_load_size="Paint Central Load",
            part_number="LP-LAYOUT-001",
        )
        _driver_log(
            driver,
            plant_name="PC",
            arrive_time="2026-06-05 09:00:00",
            depart_time="09:20",
            load_size="Paint Central Load",
            depart_load_size="Empty",
        )
        _plant_transfer(driver)

    _login(client, "layout_driver")
    response = client.get("/mobile")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    workspace = body[
        body.index('<section class="desktop-ops-workspace"'):
        body.index("<script>", body.index('<section class="desktop-ops-workspace"'))
    ]
    visible_board = workspace[: workspace.index('<div class="desktop-main-column">')]
    assert "Live Ops Board" in visible_board
    assert "Loads / Parts" not in visible_board
    assert "desktop-load-" not in visible_board
    assert "desktop-transfer-" not in visible_board
    assert "Route Packet" in workspace
