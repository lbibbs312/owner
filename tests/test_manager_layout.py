"""Layout and route smoke tests for manager ops-board surfaces."""
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


def _driver_log_document(log, uploader, **kw):
    from app.extensions import db
    from app.models import DriverLogPhoto

    base = dict(
        driver_log_id=log.id,
        filename="route-doc-layout.jpg",
        original_filename="route-doc-layout.jpg",
        content_type="image/jpeg",
        source="bol_manifest",
        document_type="bol_manifest",
        note="Stamped route sheet photo",
        uploaded_by_id=uploader.id,
    )
    base.update(kw)
    photo = DriverLogPhoto(**base)
    db.session.add(photo)
    db.session.commit()
    return photo


def _pretrip(driver, **kw):
    from app.extensions import db
    from app.models import PreTrip

    base = dict(
        user_id=driver.id,
        truck_number="MD-TRUCK-44",
        trailer_number="MD-TRAILER-77",
        pretrip_date=date.today(),
        shift="AM",
        start_mileage=128400,
        truck_type="box",
        gc_no_defects=True,
        incab_no_defects=True,
        ec_no_defects=True,
        exterior_no_defects=True,
        towed_no_defects=True,
        damage_report="Left mirror marker scuff noted before route.",
    )
    base.update(kw)
    pretrip = PreTrip(**base)
    db.session.add(pretrip)
    db.session.commit()
    return pretrip


def _damage_report(driver, log, **kw):
    from app.extensions import db
    from app.models import DamageReport

    base = dict(
        reported_by_id=driver.id,
        driver_log_id=log.id,
        truck_number="MD-TRUCK-44",
        trailer_number="MD-TRAILER-77",
        plant_name="Paint Central Door 4",
        description="Fork nick on return rack needs manager review.",
        status="open",
    )
    base.update(kw)
    report = DamageReport(**base)
    db.session.add(report)
    db.session.commit()
    return report


def _ifta_worksheet(driver, **kw):
    from app.extensions import db
    from app.models import IftaWorksheet

    base = dict(
        reporting_period_quarter="Q2",
        reporting_year=2026,
        driver_id=driver.id,
        truck="IFTA-TRUCK-9",
        vin_or_vehicle_unit_number="IFTA-UNIT-9",
        carrier_name="MoveDefense Carrier",
        review_status="Needs Review",
        created_by_id=driver.id,
    )
    base.update(kw)
    worksheet = IftaWorksheet(**base)
    db.session.add(worksheet)
    db.session.commit()
    return worksheet


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
    assert "Manager Workspace" in body
    assert "Driver Routes" in body
    assert "AlexandriaLongRouteName OperationsDriverWithLongName14" in body
    assert ".mc-main { flex:1 1 auto; min-width:0; display:flex; flex-direction:column; min-height:100vh; }" in body
    assert "font-family:'Montserrat',system-ui,sans-serif;" in body
    assert "data-manager-workspace" in body
    assert "workspace-section active" in body
    assert "record-table" in body
    header = body.split('<header class="mc-header"', 1)[1].split("</header>", 1)[0]
    assert "Driver Routes" not in header
    assert "mc-header-r" not in body
    assert "btn-action" not in body
    nav = body.split('<nav class="mc-nav"', 1)[1].split("</nav>", 1)[0]
    assert '<button class="active" type="button" data-workspace-target="routes"' in nav
    assert 'data-workspace-target="documents"' in nav
    assert "mc-nav-badge" in nav
    assert 'href="' not in nav
    for old_layout in (
        "summary-grid",
        "summary-tile",
        "Live Work Areas",
        "side-link",
        "lower-grid",
        "workspace-index",
        "workspace-link",
        "records-grid",
        "border-left:4px solid",
    ):
        assert old_layout not in body
    assert "Live Flow Map" not in body
    assert 'style="grid-template-columns:repeat(' not in body


def test_manager_dashboard_v2_shell_uses_driver_workflow_records(client, app):
    with app.app_context():
        manager = _user("workspace_boss", "management")
        driver = _user("workspace_driver", "driver", first_name="Dana", last_name="Route")
        log = _driver_log(driver, plant_name="PC", load_size="Raleigh East Load")
        _move_request(
            manager.id,
            request_number="MR-WORKSPACE-1",
            origin_location_text="Raleigh East",
            destination_location_text="Paint Central",
            cargo_text="Rack load",
        )
        _plant_transfer(driver, transfer_number="TRX-WORKSPACE")
        _driver_log_document(log, driver)
        _pretrip(driver)
        _damage_report(driver, log)
        _ifta_worksheet(driver)

    _login(client, "workspace_boss")
    response = client.get("/manager/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for label in (
        "Manager Workspace",
        "Open Items",
        "Driver Routes",
        "Route Packets",
        "IFTA Support Worksheets",
        "Documents",
        "Damage / Incidents",
        "Inspections",
    ):
        assert label in body
    assert "MR-WORKSPACE-1" not in body
    assert "Raleigh East to Paint Central" not in body
    assert "TRX-WORKSPACE" in body
    assert "IFTA Support Worksheet #1" in body
    assert "IFTA-TRUCK-9" in body
    assert "Stamped route sheet photo" in body
    assert "MD-TRUCK-44" in body
    assert "Left mirror marker scuff noted before route." in body
    assert "Fork nick on return rack needs manager review." in body
    assert "mc-nav-badge::before" in body
    assert "mc-nav-badge has-count danger-count" in body
    assert 'danger-count">+1</span>' in body
    for old_label in (
        "Live Flow Map",
        "Live Work Areas",
        "FlowMapDashboard",
        "Production Flow",
        "Dispatch Queue",
        "summary-tile",
        "summary-grid",
        "side-link",
        "lower-grid",
        "workspace-index",
        "workspace-link",
        "records-grid",
        "border-left:4px solid",
        "Evidence",
        "Audit",
    ):
        assert old_label not in body


def test_move_requests_uses_movedefense_manager_shell(client, app):
    with app.app_context():
        manager = _user("queue_boss", "management")
        driver = _user("queue_driver", "driver", first_name="Driver", last_name="WithLongName")
        log = _driver_log(driver)
        _damage_report(driver, log)
        _move_request(manager.id)

    _login(client, "queue_boss")
    response = client.get("/manager/move-requests")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "mq-shell" in body
    assert "data-manager-workspace" in body
    assert "MoveDefense" in body
    assert "Move Requests" in body
    assert "Driver Routes" in body
    assert "Documents" in body
    assert "Open Items" in body
    assert "Route Packets" in body
    assert "Damage / Incidents" in body
    assert "Inspections" in body
    nav = body.split('<nav class="mq-nav"', 1)[1].split("</nav>", 1)[0]
    assert "mq-nav-badge" in nav
    assert "mq-nav-badge::before" in body
    assert "mq-nav-badge has-count danger-count" in nav
    assert 'danger-count">+1</span>' in nav
    assert 'class="active" href="/manager/move-requests"' in nav
    for old_label in (
        "Manager Console",
        "Move Request Queue",
        "Review Queue",
        "Link Evidence",
        "Evidence",
        "Audit",
        "Dispatch Queue",
        "Production Flow",
        "Live Flow Map",
        "FlowMapDashboard",
        "Workspace</a>",
        "queue-header",
    ):
        assert old_label not in body
    assert "Raleigh East North Overflow Staging Lane With Long Name" in body
    assert ".queue-table { background:#fff; border:1px solid #e2e8f0; border-radius:8px; overflow:auto;" in body
    assert "letter-spacing:-" not in body

    empty_response = client.get("/manager/move-requests?status=cancelled")
    assert empty_response.status_code == 200
    empty_body = empty_response.get_data(as_text=True)
    assert "No move requests match this view. New requests will appear here." in empty_body


def test_legacy_operations_board_alias_redirects_to_manager_workspace(client, app):
    with app.app_context():
        _user("flow_boss", "management")

    _login(client, "flow_boss")
    for path in ("/operations-board", "/operations_board"):
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/manager/dashboard")


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
