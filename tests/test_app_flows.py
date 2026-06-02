from io import BytesIO
import os

import pytest


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("MANAGER_REGISTRATION_PIN", "0000")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        DAMAGE_UPLOAD_FOLDER=str(tmp_path / "damage_uploads"),
        DRIVER_LOG_PHOTO_UPLOAD_FOLDER=str(tmp_path / "driver_log_photo_uploads"),
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def create_user(username, email, role="driver", password="password1", **attrs):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=email, role=role, **attrs)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, login_name, password="password1"):
    return client.post(
        "/login",
        data={"login_name": login_name, "password": password},
        follow_redirects=False,
    )


BANNED_PRINT_PHRASES = (
    b"Review the DVIR first",
    b"Use Edit PreTrip",
    b"Print / Save as PDF",
    b"Download PDF Attachment",
    b"Use Letter paper",
    b"disable browser headers",
    b"Edit Gallery",
    b"Delete Photo",
    b"Debug",
    b"Forecast",
)


def assert_official_record_output(data):
    assert b"Document No:" in data
    assert b"Generated:" in data
    for phrase in BANNED_PRINT_PHRASES:
        assert phrase not in data


def test_autosave_draft_round_trip_is_user_scoped(client, app):
    with app.app_context():
        driver = create_user("draft_driver", "draft@example.com")
        other = create_user("other_draft_driver", "otherdraft@example.com")
        driver_id = driver.id
        other_id = other.id

    login(client, "draft_driver")
    payload = {
        "plant_name": {"type": "select-one", "value": "PE"},
        "damage_report": {"type": "textarea", "value": "Scrape on trailer door"},
        "hot_parts": {"type": "checkbox", "checked": True, "value": "y"},
    }
    response = client.post(
        "/drafts/autosave",
        json={
            "draft_key": "movedefense:draft:test:/new_pretrip:pretrip-new",
            "form_id": "pretrip-new",
            "path": "/new_pretrip",
            "payload": payload,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "saved"

    with app.app_context():
        from app.models import DraftEntry

        saved = DraftEntry.query.filter_by(user_id=driver_id).one()
        assert saved.payload["damage_report"]["value"] == "Scrape on trailer door"
        assert DraftEntry.query.filter_by(user_id=other_id).count() == 0

    loaded = client.get(
        "/drafts/autosave",
        query_string={"draft_key": "movedefense:draft:test:/new_pretrip:pretrip-new"},
    )
    assert loaded.status_code == 200
    assert loaded.get_json()["found"] is True
    assert loaded.get_json()["payload"] == payload

    missing = client.get("/drafts/autosave", query_string={"draft_key": "other-key"})
    assert missing.status_code == 200
    assert missing.get_json()["found"] is False

    cleared = client.post(
        "/drafts/clear",
        json={"draft_key": "movedefense:draft:test:/new_pretrip:pretrip-new"},
    )
    assert cleared.status_code == 200
    with app.app_context():
        from app.models import DraftEntry

        assert DraftEntry.query.filter_by(user_id=driver_id).count() == 0


def test_driver_entry_forms_load_autosave(client, app):
    with app.app_context():
        create_user("autosave_driver", "autosave@example.com")

    login(client, "autosave_driver")
    pretrip_page = client.get("/new_pretrip")
    assert pretrip_page.status_code == 200
    assert b'data-autosave="true"' in pretrip_page.data
    assert b'data-autosave-key="pretrip-new"' in pretrip_page.data
    assert b"js/autosave-drafts.js" in pretrip_page.data
    assert b"/drafts/autosave" in pretrip_page.data

    damage_page = client.get("/damage_reports/new")
    assert damage_page.status_code == 200
    assert b'data-autosave-key="damage-report-new"' in damage_page.data
    assert b"js/autosave-drafts.js" in damage_page.data


def test_new_driver_log_ignores_stale_hidden_cargo(client, app):
    with app.app_context():
        driver = create_user("stale_cargo_driver", "stale-cargo@example.com")
        driver_id = driver.id

    login(client, "stale_cargo_driver")
    page = client.get("/new_driving_log")
    assert page.status_code == 200
    assert b'name="load_size" value="Empty" data-no-autosave="true"' in page.data

    response = client.post(
        "/new_driving_log",
        data={
            "plant_name": "RE",
            "load_size": "Kraft Plant Load",
            "secondary_load": "PPL Load",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(driver_id=driver_id).one()
        assert log.plant_name == "RE"
        assert log.load_size == "Empty"
        assert log.secondary_load is None


def test_registration_uses_manager_pin(client, app):
    response = client.post(
        "/register",
        data={
            "username": "manager1",
            "email": "manager1@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "management",
            "manager_pin": "0000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app.app_context():
        from app.models import User

        user = User.query.filter_by(username="manager1").one()
        assert user.role == "management"


def test_password_hash_column_fits_werkzeug_hashes(app):
    with app.app_context():
        from app.models import User

        user = User(username="driver1", email="driver1@example.com", role="driver")
        user.set_password("password1")
        column_length = User.__table__.c.password_hash.type.length

        assert column_length >= 255
        assert len(user.password_hash) <= column_length


def test_login_redirects_by_role(client, app):
    with app.app_context():
        create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="RE",
        )
        create_user("manager1", "manager1@example.com", "management")

    driver_response = login(client, "driver1")
    assert driver_response.status_code == 302
    assert driver_response.headers["Location"].endswith("/dashboard")

    client.get("/logout")
    manager_response = login(client, "manager1")
    assert manager_response.status_code == 302
    assert manager_response.headers["Location"].endswith("/manager/dashboard")


def test_login_checks_password_against_all_matching_usernames_and_emails(client, app):
    with app.app_context():
        create_user("driver1", "shared@example.com", "driver", password="firstpass")
        create_user(
            "shared@example.com",
            "driver2@example.com",
            "driver",
            password="secondpass",
        )

    response = login(client, "shared@example.com", "secondpass")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_registration_rejects_username_email_cross_collision(client, app):
    with app.app_context():
        create_user("driver1", "shared@example.com", "driver")

    response = client.post(
        "/register",
        data={
            "username": "shared@example.com",
            "email": "new@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "driver",
            "manager_pin": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    with app.app_context():
        from app.models import User

        assert User.query.filter_by(email="new@example.com").first() is None


def test_authenticated_user_cannot_view_login_or_register(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")

    login(client, "driver1")
    login_page = client.get("/login", follow_redirects=False)
    register_page = client.get("/register", follow_redirects=False)
    assert login_page.status_code == 302
    assert login_page.headers["Location"].endswith("/dashboard")
    assert register_page.status_code == 302
    assert register_page.headers["Location"].endswith("/dashboard")

    client.get("/logout")
    login(client, "manager1")
    manager_login_page = client.get("/login", follow_redirects=False)
    assert manager_login_page.status_code == 302
    assert manager_login_page.headers["Location"].endswith("/manager/dashboard")


def test_cross_role_access_requires_matching_credentials(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")

    login(client, "driver1")
    manager_page = client.get("/manager/dashboard", follow_redirects=False)
    assert manager_page.status_code == 302
    assert "/login" in manager_page.headers["Location"]
    assert "required_role=management" in manager_page.headers["Location"]

    manager_login = client.post(
        "/login?required_role=management&next=/manager/dashboard",
        data={"login_name": "manager1", "password": "password1"},
        follow_redirects=False,
    )
    assert manager_login.status_code == 302
    assert manager_login.headers["Location"].endswith("/manager/dashboard")

    driver_page = client.get("/new_driving_log", follow_redirects=False)
    assert driver_page.status_code == 302
    assert "/login" in driver_page.headers["Location"]
    assert "required_role=driver" in driver_page.headers["Location"]

    client.get("/logout")
    login(client, "manager1")
    driver_page_without_driver_login = client.get("/new_driving_log", follow_redirects=False)
    assert driver_page_without_driver_login.status_code == 302
    assert "/login" in driver_page_without_driver_login.headers["Location"]
    assert "required_role=driver" in driver_page_without_driver_login.headers["Location"]

    wrong_role_login = client.post(
        "/login?required_role=driver&next=/new_driving_log",
        data={"login_name": "manager1", "password": "password1"},
        follow_redirects=False,
    )
    assert wrong_role_login.status_code == 302
    assert wrong_role_login.headers["Location"].endswith("/manager/dashboard")


def test_detroit_time_display_uses_12_hour_local_time(client, app):
    from datetime import datetime

    with app.app_context():
        from app.extensions import db
        from app.models import Task

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        create_user("manager1", "manager1@example.com", "management")
        task = Task(
            title="Time format check",
            details="Verify display time",
            status="pending",
            assigned_to=driver.id,
            created_at=datetime(2026, 5, 13, 16, 5),
        )
        db.session.add(task)
        db.session.commit()

    login(client, "manager1")
    page = client.get("/manager/dashboard")
    assert page.status_code == 200
    assert b"2026-05-13 12:05pm EDT" in page.data
    assert b"16:05" not in page.data


def test_manager_assigns_task_and_driver_updates_status(client, app):
    with app.app_context():
        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        create_user("manager1", "manager1@example.com", "management")
        driver_id = driver.id

    login(client, "manager1")
    manager_page = client.get("/manager/dashboard")
    assert manager_page.status_code == 200
    assert b"Live Dispatch" in manager_page.data
    assert b"Dispatch Queue" in manager_page.data
    assert b"Create Hot Move" in manager_page.data
    assert b"From Plant" in manager_page.data
    assert b"To Plant" in manager_page.data
    assert b"Part Number" in manager_page.data
    assert b"Open for any driver" in manager_page.data
    assert b"Driver One" in manager_page.data
    assert b"Plastic Plate" in manager_page.data
    assert b"Badge 1001" in manager_page.data
    assert b">driver1<" not in manager_page.data
    assert b'id="fullscreenOverlay"' not in manager_page.data
    assert b'class="nav-link openOverlayLink"' not in manager_page.data
    assert b"swal(" not in manager_page.data

    response = client.post(
        "/manager/create_task_from_dashboard",
        data={
            "title": "Move trailer",
            "route_from": "RW",
            "route_to": "KP",
            "part_number": "P0903110",
            "details": "Dock 4",
            "shift": "1st",
            "assigned_to": str(driver_id),
            "is_hot": "y",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import Task

        task = Task.query.filter_by(title="RW to KP").one()
        assert task.assigned_to == driver_id
        assert task.status == "pending"
        assert task.is_hot is True
        assert task.part_number == "P0903110"
        assert "Move trailer" in task.details
        task_id = task.id

    manage_page = client.get(f"/manager/tasks/{task_id}")
    assert manage_page.status_code == 200
    assert b"Manage Move" in manage_page.data
    assert b"Assign / Reassign Driver" in manage_page.data
    assert b"Print Audit Log" in manage_page.data
    assert b"Driver One | Plastic Plate | Badge 1001" in manage_page.data

    updated = client.post(
        f"/manager/tasks/{task_id}",
        data={
            "assigned_to": str(driver_id),
            "status": "pending",
            "shift": "2nd",
            "details": "Dock 5 part P-1 trailer TR-1",
            "is_hot": "y",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 302
    with app.app_context():
        from app.models import Task

        task = Task.query.get(task_id)
        assert task.assigned_to == driver_id
        assert task.shift == "2nd"
        assert task.details == "Dock 5 part P-1 trailer TR-1"
        assert task.is_hot is True

    client.get("/logout")
    login(client, "driver1")

    detail_page = client.get(f"/tasks/{task_id}")
    assert detail_page.status_code == 200
    assert b"Dispatch Details" in detail_page.data
    assert b"Completed" in detail_page.data

    accept = client.post(f"/tasks/{task_id}/accept", follow_redirects=False)
    assert accept.status_code == 302
    with app.app_context():
        from app.models import Task

        assert Task.query.get(task_id).status == "in-progress"

    complete = client.post(f"/tasks/{task_id}/complete", follow_redirects=False)
    assert complete.status_code == 302
    with app.app_context():
        from app.models import Task

        task = Task.query.get(task_id)
        assert task.status == "completed"
        assert task.completed_by_id == driver_id
        assert task.completed_at is not None

    completed_detail = client.get(f"/tasks/{task_id}")
    assert completed_detail.status_code == 200
    assert b"Completed By:" in completed_detail.data
    assert b"Driver One" in completed_detail.data
    assert b"Plastic Plate" in completed_detail.data

    client.get("/logout")
    login(client, "manager1")
    open_response = client.post(
        "/manager/create_task_from_dashboard",
        data={
            "title": "Open move",
            "route_from": "PC",
            "route_to": "RE",
            "part_number": "OPEN-123",
            "details": "Any available driver",
            "shift": "1st",
            "assigned_to": "0",
        },
        follow_redirects=False,
    )
    assert open_response.status_code == 302
    with app.app_context():
        from app.models import Task

        open_task = Task.query.filter_by(part_number="OPEN-123").one()
        assert open_task.assigned_to is None
        open_task_id = open_task.id

    client.get("/logout")
    login(client, "driver1")
    open_detail = client.get(f"/tasks/{open_task_id}")
    assert open_detail.status_code == 200
    assert b"Open for any driver" in open_detail.data
    open_complete = client.post(f"/tasks/{open_task_id}/complete", follow_redirects=False)
    assert open_complete.status_code == 302
    with app.app_context():
        from app.models import Task

        open_task = Task.query.get(open_task_id)
        assert open_task.assigned_to == driver_id
        assert open_task.status == "completed"


def test_manager_move_request_queue_create_edit_and_actions(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, AuditEvent, MoveRequest

        driver = create_user(
            "queue_driver",
            "queue-driver@example.com",
            "driver",
            first_name="Queue",
            last_name="Driver",
            employee_id="Q1",
        )
        manager = create_user("queue_manager", "queue-manager@example.com", "management")
        driver_id = driver.id
        manager_id = manager.id

    login(client, "queue_manager")
    queue_page = client.get("/manager/move-requests")
    assert queue_page.status_code == 200
    assert b"Move Request Queue" in queue_page.data
    assert b"New Request" in queue_page.data

    created = client.post(
        "/manager/move-requests/new",
        data={
            "raw_text": "PMT has 10 skids for the DC please",
            "source": "text",
            "requested_by": "Production",
            "requested_at": "2026-05-27T13:35",
            "request_type": "move",
            "priority": "normal",
            "origin_location_text": "PMT",
            "destination_location_text": "DC",
            "cargo_text": "",
            "part_number": "",
            "quantity_value": "10",
            "quantity_unit": "skids",
            "quantity_text": "10 skids",
            "due_time_text": "",
            "notes": "Confirmed by supervisor.",
            "status": "open",
            "assigned_driver_id": "0",
            "assigned_driver_text": "",
            "equipment_id": "",
            "equipment_text": "",
            "linked_driver_log_id": "0",
            "linked_route_id": "",
            "linked_plant_transfer_id": "0",
            "linked_document_id": "",
            "parsed_confidence": "high",
            "parse_warnings": "",
        },
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        req = MoveRequest.query.one()
        assert req.request_number == "MOVE-REQ-20260527-001"
        assert req.created_by_id == manager_id
        assert req.origin_location_text == "PMT"
        assert req.destination_location_text == "DC"
        assert req.quantity_text == "10 skids"
        request_id = req.id
        assert ActivityEvent.query.filter_by(target_type="move_request", target_id=request_id, action="created").count() == 1
        assert AuditEvent.query.filter_by(target_type="move_request", target_id=request_id, action="created").count() == 1

    page = client.get("/manager/move-requests")
    assert b"MOVE-REQ-20260527-001" in page.data
    assert b"PMT has 10 skids for the DC please" in page.data
    assert b"Production" in page.data
    assert b"PMT" in page.data
    assert b"DC" in page.data
    assert b"10 skids" in page.data

    edit_page = client.get(f"/manager/move-requests/{request_id}/edit")
    assert edit_page.status_code == 200
    assert b"Original Request / Message" in edit_page.data

    edited = client.post(
        f"/manager/move-requests/{request_id}/edit",
        data={
            "raw_text": "PMT has 10 skids for the DC please",
            "source": "text",
            "requested_by": "Production Lead",
            "requested_at": "2026-05-27T13:35",
            "request_type": "move",
            "priority": "high",
            "origin_location_text": "PMT",
            "destination_location_text": "DC",
            "cargo_text": "",
            "part_number": "P1234",
            "quantity_value": "10",
            "quantity_unit": "skids",
            "quantity_text": "10 skids",
            "due_time_text": "today",
            "notes": "Updated priority.",
            "status": "open",
            "assigned_driver_id": "0",
            "assigned_driver_text": "",
            "equipment_id": "",
            "equipment_text": "",
            "linked_driver_log_id": "0",
            "linked_route_id": "route-manual-1",
            "linked_plant_transfer_id": "0",
            "linked_document_id": "",
            "parsed_confidence": "high",
            "parse_warnings": "",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 302

    assigned = client.post(
        f"/manager/move-requests/{request_id}/assign",
        data={"assigned_driver_id": str(driver_id), "equipment_text": "ST4"},
        follow_redirects=False,
    )
    assert assigned.status_code == 302

    blocked = client.post(
        f"/manager/move-requests/{request_id}/mark-blocked",
        data={"blocked_reason": "Waiting on trailer."},
        follow_redirects=False,
    )
    assert blocked.status_code == 302

    completed = client.post(
        f"/manager/move-requests/{request_id}/mark-completed",
        data={"closed_reason": "Moved by driver."},
        follow_redirects=False,
    )
    assert completed.status_code == 302

    cancelled = client.post(
        f"/manager/move-requests/{request_id}/cancel",
        data={"closed_reason": "Cancelled after completion for correction test."},
        follow_redirects=False,
    )
    assert cancelled.status_code == 302

    with app.app_context():
        req = MoveRequest.query.get(request_id)
        assert req.updated_by_id == manager_id
        assert req.priority == "high"
        assert req.part_number == "P1234"
        assert req.linked_route_id == "route-manual-1"
        assert req.assigned_driver_id == driver_id
        assert req.equipment_text == "ST4"
        assert req.blocked_reason == "Waiting on trailer."
        assert req.status == "cancelled"
        assert req.closed_reason == "Cancelled after completion for correction test."
        for action in ["updated", "assigned", "blocked", "completed", "cancelled"]:
            assert ActivityEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 1
            assert AuditEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 1


def test_phase1a_group_chat_request_acknowledgement_and_transfer_link(client, app):
    from datetime import date

    missing_quantity_warning = "Quantity not found. Confirm amount from document or driver."
    raw_text = "PW has parts for RE please P0916"

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, AuditEvent, MoveRequest, PlantTransfer, PlantTransferLine

        driver = create_user("phase1a_driver", "phase1a-driver@example.com", "driver")
        manager = create_user("phase1a_manager", "phase1a-manager@example.com", "management")
        transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="809716",
            transfer_date=date(2026, 5, 28),
            ship_from="1018",
            ship_to="3036",
            trailer_number="stl1",
            driver_name="Phase 1A Driver",
            transfer_time="14:36",
            loaded_by="stl1",
        )
        transfer.lines.append(
            PlantTransferLine(
                line_number=1,
                side="left",
                part_number="P0916165188",
                quantity="1",
                remarks="Visible item line related to P0916 request.",
            )
        )
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id
        manager_id = manager.id

    login(client, "phase1a_manager")
    parse_response = client.post("/manager/move-requests/parse", data={"raw_text": raw_text})
    assert parse_response.status_code == 200
    parsed = parse_response.get_json()
    assert parsed["suggestions"]["request_type"] == "move"
    assert parsed["suggestions"]["origin_location_text"] == "PW"
    assert parsed["suggestions"]["destination_location_text"] == "RE"
    assert parsed["suggestions"]["cargo_text"] == "parts"
    assert parsed["suggestions"]["part_number"] == "P0916"
    assert parsed["suggestions"]["priority"] == "normal"
    assert parsed["suggestions"]["quantity_text"] is None
    assert parsed["warnings"] == [missing_quantity_warning]

    created = client.post(
        "/manager/move-requests/new",
        data={
            "raw_text": raw_text,
            "source": "text",
            "requested_by": "Group Chat",
            "requested_at": "2026-05-28T14:20",
            "request_type": "move",
            "priority": "normal",
            "origin_location_text": "PW",
            "destination_location_text": "RE",
            "cargo_text": "parts",
            "part_number": "P0916",
            "quantity_value": "",
            "quantity_unit": "",
            "quantity_text": "",
            "due_time_text": "",
            "notes": "Transfer document later supplied site, LP, item, and quantity details.",
            "status": "open",
            "assigned_driver_id": "0",
            "assigned_driver_text": "",
            "equipment_id": "",
            "equipment_text": "",
            "linked_driver_log_id": "0",
            "linked_route_id": "",
            "linked_plant_transfer_id": "0",
            "linked_document_id": "",
            "parsed_confidence": "high",
            "parse_warnings": missing_quantity_warning,
        },
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        req = MoveRequest.query.filter_by(raw_text=raw_text).one()
        request_id = req.id
        assert req.quantity_text is None
        assert req.parse_warnings == missing_quantity_warning
        assert ActivityEvent.query.filter_by(
            target_type="move_request", target_id=request_id, action="created"
        ).count() == 1

    acknowledged = client.post(
        f"/manager/move-requests/{request_id}/acknowledge",
        data={"acknowledged_by_text": "Dispatch group chat"},
        follow_redirects=False,
    )
    assert acknowledged.status_code == 302

    linked = client.post(
        f"/manager/move-requests/{request_id}/link-evidence",
        data={"linked_plant_transfer_id": str(transfer_id), "linked_document_id": ""},
        follow_redirects=False,
    )
    assert linked.status_code == 302

    with app.app_context():
        req = MoveRequest.query.get(request_id)
        assert req.linked_plant_transfer_id == transfer_id
        ack_event = ActivityEvent.query.filter_by(
            target_type="move_request", target_id=request_id, action="acknowledged"
        ).one()
        assert ack_event.user_id == manager_id
        assert "Dispatch group chat" in ack_event.details
        assert ack_event.created_at is not None
        link_event = ActivityEvent.query.filter_by(
            target_type="move_request", target_id=request_id, action="evidence_linked"
        ).one()
        assert "Plant Transfer 809716" in link_event.details
        assert AuditEvent.query.filter_by(
            target_type="move_request", target_id=request_id, action="acknowledged"
        ).count() == 1
        assert AuditEvent.query.filter_by(
            target_type="move_request", target_id=request_id, action="evidence_linked"
        ).count() == 1

    queue_page = client.get("/manager/move-requests")
    assert queue_page.status_code == 200
    assert b"PW has parts for RE please P0916" in queue_page.data
    assert b"Plant Transfer #809716" in queue_page.data
    assert b"Ack " in queue_page.data


def test_dispatch_capture_inbox_saves_raw_text_and_converts_with_audit(client, app):
    with app.app_context():
        from app.models import AuditEvent, DispatchCapture, MoveRequest

        manager = create_user("capture_mgr", "capture_mgr@example.com", "management")
        manager_id = manager.id

    login(client, "capture_mgr")
    raw_text = "KP is really full so both of you work on it before shutdown."
    created = client.post(
        "/manager/dispatch-captures",
        data={"raw_text": raw_text, "capture_type": "delay_no_parts"},
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        capture = DispatchCapture.query.one()
        capture_id = capture.id
        assert capture.raw_text == raw_text
        assert capture.captured_by == manager_id
        assert capture.status == "needs_triage"
        assert capture.guessed_type == "delay_no_parts"
        assert capture.extracted_from_node == "Kraft Plater"

    dashboard = client.get("/manager/dashboard")
    assert dashboard.status_code == 200
    assert raw_text.encode() in dashboard.data
    assert b"Universal Dispatch Capture Inbox" in dashboard.data
    assert b"Captured Requests" in dashboard.data
    assert b"Needs owner/action" in dashboard.data

    converted = client.post(
        f"/manager/dispatch-captures/{capture_id}/convert",
        data={"entity_type": "move_request"},
        follow_redirects=False,
    )
    assert converted.status_code == 302

    with app.app_context():
        capture = DispatchCapture.query.get(capture_id)
        req = MoveRequest.query.one()
        assert capture.status == "converted"
        assert capture.converted_entity_type == "MoveRequest"
        assert capture.converted_entity_id == req.id
        assert req.raw_text == raw_text
        assert req.source == "dispatch_capture"
        conversion_audit = AuditEvent.query.filter_by(
            target_type="dispatch_capture", target_id=capture_id, action="converted"
        ).one()
        assert raw_text in conversion_audit.reason


def test_driver_mobile_shows_full_parts_queue_and_route_task_events(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, Task

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        assigned = Task(
            title="KP to RE",
            details="Assigned hot part for Raleigh East",
            part_number="P-HOT-1",
            is_hot=True,
            status="pending",
            assigned_to=driver.id,
            created_at=datetime(2026, 5, 16, 12, 0),
        )
        open_task = Task(
            title="PC to RW",
            details="Open plant move",
            part_number="P-OPEN-1",
            is_hot=False,
            status="pending",
            created_at=datetime(2026, 5, 16, 12, 5),
        )
        db.session.add_all([assigned, open_task])
        db.session.commit()
        driver_id = driver.id
        assigned_id = assigned.id

    login(client, "driver1")
    queue_page = client.get("/mobile")
    assert queue_page.status_code == 200
    assert b"LIVE FLOW BOARD" in queue_page.data
    assert b"Parts Queue" not in queue_page.data
    assert b'<span class="flow-status status-hot">HOT</span>' in queue_page.data
    assert b'<span class="flow-detail"><strong>KP to RE</strong>' in queue_page.data
    assert b"P-HOT-1" in queue_page.data
    assert b"P-OPEN-1" in queue_page.data
    assert b"Open for any driver" in queue_page.data

    accepted = client.post(f"/tasks/{assigned_id}/accept?next=mobile", follow_redirects=False)
    assert accepted.status_code == 302
    assert accepted.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        route_date = date.today()
        first_stop = DriverLog(
            driver_id=driver_id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            depart_time="08:15",
            dock_wait_minutes=12,
            arrive_time=f"{route_date.isoformat()} 12:00:00",
        )
        second_stop = DriverLog(
            driver_id=driver_id,
            date=route_date,
            plant_name="RE",
            load_size="Raleigh East Load",
            depart_load_size="Empty",
            depart_time="09:05",
            arrive_time=f"{route_date.isoformat()} 13:00:00",
        )
        db.session.add_all([first_stop, second_stop])
        db.session.commit()

    completed = client.post(f"/tasks/{assigned_id}/complete?next=mobile", follow_redirects=False)
    assert completed.status_code == 302

    route_page = client.get("/mobile")
    assert route_page.status_code == 200
    assert b"Task T" not in route_page.data
    assert b"Hot Part: P-HOT-1" not in route_page.data
    assert b"Raleigh East Load" in route_page.data
    assert b"DROPPED" in route_page.data


def test_departure_dock_wait_feeds_manager_dashboard_cards(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        create_user("manager1", "manager1@example.com", "management")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="KP",
            load_size="Empty",
            arrive_time=(datetime.utcnow() - timedelta(minutes=17)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(client, "driver1")
    departed = client.post(
        f"/driver_logs/{log_id}/depart",
        data={"got_loaded": "no", "destination": ""},
        follow_redirects=False,
    )
    assert departed.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        saved = DriverLog.query.get(log_id)
        assert saved.dock_wait_minutes >= 17
        assert saved.depart_load_size == "Empty"

    client.get("/logout")
    login(client, "manager1")
    dashboard = client.get("/manager/dashboard?focus=routes")
    assert dashboard.status_code == 200
    assert dashboard.headers["Cache-Control"].startswith("no-store")
    assert client.get("/manager/delays").status_code == 404
    assert b"Avg Dock Wait" not in dashboard.data
    assert b"Trim Division" not in dashboard.data
    assert b"Plastics Division" not in dashboard.data
    assert b"Delay" in dashboard.data
    assert b"17 min" in dashboard.data or b"18 min" in dashboard.data
    assert b"focus=delays" not in dashboard.data
    assert b"focus-panel" in dashboard.data


def test_service_stop_closes_without_cargo_questions_and_preserves_load(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog
        from app.services.load_state import build_driver_log_route_context, current_load_after_logs

        driver = create_user("service_stop_driver", "service-stop@example.com", "driver")
        route_date = date.today()
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="Ryder Rentals",
            load_size="Raleigh East Load",
            arrive_time=(datetime.utcnow() - timedelta(minutes=9)).strftime("%Y-%m-%d %H:%M:%S"),
            maintenance=True,
            downtime_reason="Truck issue: CEL light",
            fuel_mileage=123456,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(client, "service_stop_driver")
    page = client.get(f"/driver_logs/{log_id}/depart")
    assert page.status_code == 200
    assert b"Close Maintenance stop" in page.data
    assert b"cargo questions are skipped" in page.data
    assert b"Did you get loaded?" not in page.data
    assert b"Did you get unloaded?" not in page.data
    assert b"Cargo Scan Verification" not in page.data

    departed = client.post(f"/driver_logs/{log_id}/depart", data={}, follow_redirects=False)
    assert departed.status_code == 302

    with app.app_context():
        saved = DriverLog.query.get(log_id)
        assert saved.depart_time is not None
        assert saved.depart_load_size == "Raleigh East Load"
        assert saved.no_pickup is False
        assert saved.dock_wait_minutes >= 9

        routes = build_driver_log_route_context([saved])
        route = routes[saved.id]
        assert route["service_stop"] is True
        assert route["action"] == "Maintenance stop"
        assert route["unloaded_on_arrival"] is False
        assert route["unload_blocked"] is False
        assert current_load_after_logs([saved])["value"] == "Raleigh East Load"


def test_plant_load_timing_uses_today_average_on_driver_and_manager_dashboards(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user(
            "timing_driver",
            "timing@example.com",
            "driver",
            first_name="Timing",
            last_name="Driver",
        )
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        logs = [
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="RE Load",
                arrive_time="08:00",
                depart_time="10:00",
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="PE Load",
                arrive_time="10:30",
                depart_time="11:30",
                created_at=datetime(2026, 5, 19, 10, 30),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Empty",
                arrive_time="12:00",
                created_at=datetime(2026, 5, 19, 12, 0),
            ),
        ]
        db.session.add_all(logs)
        db.session.commit()
        driver_id = driver.id

    login(client, "timing_driver")
    mobile = client.get("/mobile")
    assert mobile.status_code == 200
    assert b"LIVE FLOW BOARD" in mobile.data
    assert b"Kraft Plater Load Timing" not in mobile.data
    assert b"Today Average" not in mobile.data
    assert b"Ready Estimate" not in mobile.data
    assert b"Kraft Plater" in mobile.data
    assert b"Raleigh East Load" in mobile.data
    assert b"forecast" not in mobile.data.lower()

    client.get("/logout")
    login(client, "manager1")
    manager = client.get(f"/manager/dashboard?driver_id={driver_id}&focus=routes")
    assert manager.status_code == 200
    assert b"Plant load timing" in manager.data
    assert b"Kraft Plater" in manager.data
    assert b"1h 30m" in manager.data
    assert b"forecast" not in manager.data.lower()


def test_driver_route_print_summarizes_report_types_and_pending_mileage(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DamageReport, DriverLog

        driver = create_user("print_driver", "print-driver@example.com", "driver")
        route_date = date.today()
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="KP Load",
                arrive_time="08:00",
                depart_time="09:00",
                dock_wait_minutes=15,
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="KP Load",
                arrive_time="10:00",
                created_at=datetime(2026, 5, 19, 10, 0),
            ),
            DamageReport(
                reported_by_id=driver.id,
                plant_name="RE",
                stage="before",
                description="Trailer scrape",
            ),
            DamageReport(
                reported_by_id=driver.id,
                plant_name="Other",
                stage="before",
                description="Incident note",
            ),
        ])
        db.session.commit()

    login(client, "print_driver")
    page = client.get("/driver_logs_print")
    assert page.status_code == 200
    assert b"Pending posttrip mileage" in page.data
    assert b"1 incident report, 1 damage report filed" in page.data
    assert b"Incident - Other" in page.data
    assert b"Damage - RE" in page.data
    assert b"Timing status pending" not in page.data
    assert b"Wait Time" in page.data
    assert b"Raleigh East: Wait 15 min" in page.data
    assert b"<strong>Raleigh East:</strong> Pickup." in page.data
    assert b"Loaded Kraft Plater Load." in page.data
    assert b"Wait 15 min." in page.data
    assert b"Wait time:</strong> Wait 15 min" not in page.data
    assert b"Movement segment" not in page.data
    assert_official_record_output(page.data)
    assert b"Plant Legend" in page.data
    assert b"PPL = PPL" in page.data
    assert b"RE = Raleigh East" in page.data
    assert b"DC = 52nd Street DC" in page.data
    assert b"KP = Kraft Plater" in page.data
    assert b"PC = Paint Central" in page.data

    attachment = client.get("/driver_logs_print/attachment")
    assert attachment.status_code == 200
    assert b"Wait 15 min" in attachment.data


def test_manager_route_review_is_decision_copy_not_driver_receipt(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, DriverLogPhoto, PostTrip, PreTrip

        driver = create_user("lamar_review", "lamar-review@example.com", "driver", first_name="Lamar", last_name="Bibbs")
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        logs = [
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RW", load_size="Empty", depart_load_size="Empty", no_pickup=True, arrive_time="13:50", depart_time="13:55", created_at=datetime(2026, 5, 19, 13, 50)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="H", load_size="Empty", depart_load_size="Raleigh East Load", secondary_load="PPL Load", arrive_time="14:01", depart_time="14:17", created_at=datetime(2026, 5, 19, 14, 1)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="PPL Load", arrive_time="14:25", depart_time="14:35", created_at=datetime(2026, 5, 19, 14, 25)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PPL", load_size="PPL Load", depart_load_size="Empty", no_pickup=True, arrive_time="14:51", depart_time="14:58", created_at=datetime(2026, 5, 19, 14, 51)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PC", load_size="Empty", depart_load_size="Raleigh East Load", arrive_time="15:07", depart_time="16:09", dock_wait_minutes=15, created_at=datetime(2026, 5, 19, 15, 7)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="Empty", no_pickup=True, arrive_time="16:23", depart_time="16:43", created_at=datetime(2026, 5, 19, 16, 23)),
        ]
        db.session.add_all(logs)
        db.session.flush()
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="Truck 12", start_mileage=0)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(PostTrip(pretrip_id=pretrip.id, end_mileage=121970))
        upload_dir = os.path.abspath(app.config["DRIVER_LOG_PHOTO_UPLOAD_FOLDER"])
        os.makedirs(upload_dir, exist_ok=True)
        filename = "paint-central-cargo-proof.jpg"
        with open(os.path.join(upload_dir, filename), "wb") as fh:
            fh.write(b"cargo-photo")
        db.session.add(DriverLogPhoto(
            driver_log_id=logs[4].id,
            filename=filename,
            original_filename="paint-central-cargo-proof.jpg",
            content_type="image/jpeg",
            source="departure_gallery",
            note="the load is un-balanced , this is what causes skid to tip over.",
            uploaded_by_id=driver.id,
            uploaded_at=datetime(2026, 5, 19, 21, 34),
        ))
        db.session.commit()
        driver_id = driver.id

    login(client, "manager1")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert response.status_code == 200
    assert b"Manager Route Review" in response.data
    assert b"Driver Route Audit Sheet" not in response.data
    assert b"Review Status" in response.data
    assert b"Correction Required" in response.data
    assert b"Lamar has 6 recorded stop events" in response.data
    assert b"The route is complete and awaiting final review" in response.data
    assert b"Mileage needs correction before approval" in response.data
    assert b"one Paint Central cargo-safety photo requiring classification" in response.data
    assert b"No formal damage report was filed" in response.data
    assert b"Correct route mileage before approving route" in response.data
    assert b"Review/classify Paint Central cargo photo" in response.data
    assert b"Finalize route after confirming final unload" in response.data
    assert b"Collect missing signatures" in response.data
    assert b"Beginning odometer is missing or zero" in response.data
    assert b"ending odometer 121,970 mi cannot be used as route miles" in response.data
    assert b"121,970 miles is outside normal route range" not in response.data
    assert b"Cargo safety review" in response.data
    assert b"The load is unbalanced. This is what causes skids to tip over." in response.data
    assert b"Uploaded 5:34pm EDT" in response.data
    assert b"Cargo / Manifest Review" in response.data
    assert b"Clean" in response.data
    assert b"Manifest linked" in response.data
    assert b"No" in response.data
    assert b"No shipper/manifest record is linked" in response.data
    assert b"No cargo mismatch was detected from driver-entered route data" in response.data
    assert b"Appears complete" not in response.data
    assert b"Picked Up / Departed With" not in response.data
    assert b"Manifest Linked: Yes" not in response.data
    assert b"Scan records are attached to this route." not in response.data
    assert b"Delay / Dock Time Review" in response.data
    assert b"First-time stop - no historical baseline for dock time" in response.data
    assert b"Not enough plant history yet" not in response.data
    assert b"Collecting samples" not in response.data
    assert b"No baseline" not in response.data
    assert b"No in-route damage/incidents reported" not in response.data
    assert_official_record_output(response.data)

    pdf = client.get(f"/manager/driver-logs/route-attachment?driver_id={driver_id}&date={date.today().isoformat()}")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Type"] == "application/pdf"
    assert b"Manager Route Review" in pdf.data
    assert b"Document No:" in pdf.data
    assert b"Generated:" in pdf.data
    assert b"Review Status: Correction Required" in pdf.data
    assert_official_record_output(pdf.data)


def test_manager_route_print_calculates_mileage_from_start_and_end_odometer(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("mileage_driver", "mileage-driver@example.com", "driver", first_name="Lamar")
        create_user("mileage_manager", "mileage-manager@example.com", "management")
        route_date = date.today()
        pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=route_date,
            truck_number="ST2",
            start_mileage=122000,
        )
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            PostTrip(pretrip_id=pretrip.id, end_mileage=122007, miles_driven=7),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                arrive_time="2026-05-19 08:00:00",
                depart_time="08:20",
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "mileage_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Mileage Review" in response.data
    assert b"122,000 mi" in response.data
    assert b"122,007 mi" in response.data
    assert b"7 miles" in response.data
    assert b"122,007 miles is outside normal route range" not in response.data
    assert b"Correct mileage before approving route" not in response.data


def test_next_load_prediction_unknown_does_not_promote_actual_cargo(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("intent_unknown_driver", "intent-unknown@example.com", "driver", first_name="Lamar")
        create_user("intent_unknown_manager", "intent-unknown-manager@example.com", "management")
        route_date = date.today()
        current = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            depart_load_size=None,
            arrive_time=f"{route_date.isoformat()} 14:00:00",
            created_at=datetime(2026, 5, 20, 14, 0),
        )
        db.session.add(current)
        db.session.commit()
        driver_id = driver.id
        current_id = current.id

    login(client, "intent_unknown_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Final Approval Not Yet Available" in response.data
    assert b"Current Active Stop: Paint Central" in response.data
    assert b"Next Load Unknown" in response.data
    assert b"Scan shipper barcode or select destination before departure" in response.data
    assert b"Raleigh East Load" not in response.data
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(current_id).depart_load_size is None


def test_next_load_prediction_uses_dispatch_task_without_actual_cargo(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, Task

        driver = create_user("intent_task_driver", "intent-task@example.com", "driver", first_name="Lamar")
        create_user("intent_task_manager", "intent-task-manager@example.com", "management")
        route_date = date.today()
        current = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 14:00:00",
            created_at=datetime(2026, 5, 20, 14, 0),
        )
        task = Task(title="PC to RE", part_number="DISPATCH-1", status="in-progress", assigned_to=driver.id)
        db.session.add_all([current, task])
        db.session.commit()
        driver_id = driver.id
        current_id = current.id

    login(client, "intent_task_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Next Load Confirmed" in response.data
    assert b"Raleigh East Load" in response.data
    assert b"dispatch task" in response.data
    assert b"Confirm loaded and record departure before this becomes actual cargo" in response.data
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(current_id).depart_load_size is None


def test_next_load_prediction_uses_active_hot_move_without_actual_cargo(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, HotMove, Task

        driver = create_user("intent_hot_move_driver", "intent-hot-move@example.com", "driver", first_name="Lamar")
        create_user("intent_hot_move_manager", "intent-hot-move-manager@example.com", "management")
        route_date = date.today()
        current = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 14:00:00",
            created_at=datetime(2026, 5, 20, 14, 0),
        )
        task = Task(title="PC to RE", part_number="HOT-1", status="pending")
        db.session.add_all([current, task])
        db.session.flush()
        db.session.add(HotMove(move_id=task.id, driver_id=driver.id, truck_id="st4", status="accepted"))
        db.session.commit()
        driver_id = driver.id
        current_id = current.id

    login(client, "intent_hot_move_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Next Load Confirmed" in response.data
    assert b"Raleigh East Load" in response.data
    assert b"dispatch task" in response.data
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(current_id).depart_load_size is None


def test_next_load_prediction_uses_manifest_scan_without_actual_cargo(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PartMaster, PartScanEvent

        driver = create_user("intent_manifest_driver", "intent-manifest@example.com", "driver", first_name="Lamar")
        create_user("intent_manifest_manager", "intent-manifest-manager@example.com", "management")
        route_date = date.today()
        current = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 14:00:00",
            created_at=datetime(2026, 5, 20, 14, 0),
        )
        part = PartMaster(canonical_part_number="SHIPPER-103", default_origin_plant_id="PC", default_destination_plant_id="RE", status="active")
        db.session.add_all([current, part])
        db.session.flush()
        db.session.add(PartScanEvent(
            raw_value="SHIPPER 1030001",
            normalized_value="SHIPPER1030001",
            part_id=part.id,
            stop_id=current.id,
            driver_id=driver.id,
            plant_id="PC",
            scan_context="shipper_scan",
            validation_status="valid",
            validation_message="Ship To: Raleigh East",
        ))
        db.session.commit()
        driver_id = driver.id
        current_id = current.id

    login(client, "intent_manifest_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Next Load Confirmed" in response.data
    assert b"Raleigh East Load" in response.data
    assert b"manifest scan" in response.data
    assert b"Confidence</strong><span>High" in response.data
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(current_id).depart_load_size is None


def test_next_load_prediction_uses_plant_rule_as_estimate(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PlantPredictionRule

        driver = create_user("intent_rule_driver", "intent-rule@example.com", "driver", first_name="Lamar")
        create_user("intent_rule_manager", "intent-rule-manager@example.com", "management")
        route_date = date.today()
        current = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 14:00:00",
            created_at=datetime(2026, 5, 20, 14, 0),
        )
        rule = PlantPredictionRule(plant_id="PC", predicted_destination_plant_id="RE", confidence="medium", active=True)
        db.session.add_all([current, rule])
        db.session.commit()
        driver_id = driver.id

    login(client, "intent_rule_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Next Load Estimate" in response.data
    assert b"Raleigh East Load" in response.data
    assert b"plant rule" in response.data
    assert b"Predictions do not become actual cargo until confirmed" in response.data


def test_next_load_prediction_uses_historical_pattern_and_requires_delay_reason(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("intent_history_driver", "intent-history@example.com", "driver", first_name="Lamar")
        create_user("intent_history_manager", "intent-history-manager@example.com", "management")
        route_date = date.today() - timedelta(days=1)
        history = []
        for offset in range(1, 4):
            sample_date = route_date - timedelta(days=offset)
            history.append(DriverLog(
                driver_id=driver.id,
                date=sample_date,
                plant_name="PC",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                arrive_time="08:00",
                depart_time="08:30",
                created_at=datetime(2026, 5, 17, 8, offset),
            ))
        route_logs = [
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                arrive_time=f"{route_date.isoformat()} 12:00:00",
                depart_time="12:20",
                created_at=datetime(2026, 5, 20, 12, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Raleigh East Load",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time=f"{route_date.isoformat()} 13:00:00",
                depart_time="13:20",
                created_at=datetime(2026, 5, 20, 13, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PC",
                load_size="Empty",
                depart_load_size=None,
                arrive_time=f"{route_date.isoformat()} 14:00:00",
                created_at=datetime(2026, 5, 20, 14, 0),
            ),
        ]
        db.session.add_all(history + route_logs)
        db.session.commit()
        driver_id = driver.id

    login(client, "intent_history_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={route_date.isoformat()}")

    assert response.status_code == 200
    assert b"The previous cargo cycle appears complete" in response.data
    assert b"currently at Paint Central awaiting departure/load-out" in response.data
    assert b"Next Load Estimate" in response.data
    assert b"Raleigh East Load" in response.data
    assert b"historical pattern" in response.data
    assert b"Confidence</strong><span>Medium" in response.data
    assert b"Driver delay reason missing" in response.data
    assert b"Add delay reason for Paint Central before final approval" in response.data


def test_manager_route_review_regression_multistop_secondary_cargo_is_normal(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user("cargo_cycle_driver", "cargo-cycle@example.com", "driver", first_name="Lamar")
        create_user("cargo_cycle_manager", "cargo-cycle-manager@example.com", "management")
        route_date = date.today()
        logs = [
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="Helios",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                secondary_load="PPL Load",
                arrive_time="2026-05-19 08:00:00",
                depart_time="08:20",
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Raleigh East Load",
                depart_load_size="Empty",
                secondary_load="PPL Load",
                arrive_time="2026-05-19 09:00:00",
                depart_time="09:15",
                created_at=datetime(2026, 5, 19, 9, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PPL",
                load_size="Empty",
                depart_load_size="Empty",
                arrive_time="2026-05-19 10:00:00",
                depart_time="10:15",
                created_at=datetime(2026, 5, 19, 10, 0),
            ),
        ]
        db.session.add_all(logs)
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=379386)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)),
            PostTrip(pretrip_id=pretrip.id, end_mileage=379423, miles_driven=37),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "cargo_cycle_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Raleigh East Load" in response.data
    assert b"PPL Load" in response.data
    assert b"later cargo activity" not in response.data
    assert b"Route needs review: final cargo unload" not in response.data
    assert b"Cargo route issue" not in response.data


def test_manager_route_review_regression_current_open_stop_and_completed_rows(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user("open_stop_driver", "open-stop@example.com", "driver", first_name="Lamar")
        create_user("open_stop_manager", "open-stop-manager@example.com", "management")
        route_date = date.today()
        logs = [
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                arrive_time="2026-05-19 08:00:00",
                depart_time="08:15",
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="Helios",
                load_size="Empty",
                depart_load_size="Paint Central Load",
                arrive_time="2026-05-19 09:00:00",
                depart_time="09:20",
                created_at=datetime(2026, 5, 19, 9, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PC",
                load_size="Paint Central Load",
                depart_load_size=None,
                arrive_time="2026-05-19 10:00:00",
                created_at=datetime(2026, 5, 19, 10, 0),
            ),
        ]
        db.session.add_all(logs)
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)),
            PostTrip(pretrip_id=pretrip.id, end_mileage=1020, miles_driven=20),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "open_stop_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Current Active Stop" in response.data
    assert b"Paint Central" in response.data
    assert b"Awaiting load-out/departure" in response.data
    assert b"Correction required" not in response.data
    assert b"<td>Completed</td>" in response.data
    assert response.data.count(b"<td>Active</td>") == 0
    assert b"<td>Current</td>" in response.data or b"<td>Open</td>" in response.data


def test_manager_route_review_regression_missing_posttrip_is_pending_not_correction(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("pending_mileage_driver", "pending-mileage@example.com", "driver", first_name="Lamar")
        create_user("pending_mileage_manager", "pending-mileage-manager@example.com", "management")
        route_date = date.today()
        db.session.add(DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Empty",
            arrive_time="2026-05-19 08:00:00",
            depart_time="08:15",
            created_at=datetime(2026, 5, 19, 8, 0),
        ))
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=379386)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)))
        db.session.commit()
        driver_id = driver.id

    login(client, "pending_mileage_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Pending posttrip mileage" in response.data
    assert b"Mileage pending PostTrip" in response.data
    assert b"Mileage conflict / correction required" not in response.data
    assert b"Correct route mileage before approving route" not in response.data
    assert b"Mileage needs correction" not in response.data


def test_manager_route_review_regression_phantom_scans_excluded_but_real_scans_identified(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PartScanEvent, PostTrip, PreTrip, ShiftRecord

        driver = create_user("scan_scope_driver", "scan-scope@example.com", "driver", first_name="Lamar")
        create_user("scan_scope_manager", "scan-scope-manager@example.com", "management")
        route_date = date.today()
        old_date = route_date - timedelta(days=3)
        current_log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Paint Central Load",
            depart_load_size="Empty",
            arrive_time="2026-05-19 08:00:00",
            depart_time="08:15",
            created_at=datetime(2026, 5, 19, 8, 0),
        )
        old_log = DriverLog(
            driver_id=driver.id,
            date=old_date,
            plant_name="PC",
            load_size="Paint Central Load",
            depart_load_size="Empty",
            arrive_time="2026-05-16 08:00:00",
            depart_time="08:15",
            created_at=datetime(2026, 5, 16, 8, 0),
        )
        db.session.add_all([current_log, old_log])
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)),
            PostTrip(pretrip_id=pretrip.id, end_mileage=1010, miles_driven=10),
            PartScanEvent(raw_value="CURRENT-SCAN-111", normalized_value="CUR111", stop_id=current_log.id, driver_id=driver.id, plant_id="PC", scan_context="drop_scan", validation_status="needs_review"),
            PartScanEvent(raw_value="OLD-TEST-SCAN-222", normalized_value="OLD222", stop_id=old_log.id, driver_id=driver.id, plant_id="PC", scan_context="drop_scan", validation_status="needs_review"),
            PartScanEvent(raw_value="ORPHAN-SCAN-333", normalized_value="ORP333", stop_id=None, driver_id=driver.id, plant_id="PC", scan_context="drop_scan", validation_status="needs_review"),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "scan_scope_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Pending Scan Evidence" in response.data
    assert b"CUR111" in response.data
    assert b"OLD222" not in response.data
    assert b"ORP333" not in response.data
    assert b"OLD-TEST-SCAN" not in response.data
    assert b"ORPHAN-SCAN" not in response.data


def test_manager_route_review_regression_missing_stop_photo_file_blocks_approval(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, DriverLogPhoto, PostTrip, PreTrip, ShiftRecord

        driver = create_user("photo_scope_driver", "photo-scope@example.com", "driver", first_name="Lamar")
        create_user("photo_scope_manager", "photo-scope-manager@example.com", "management")
        route_date = date.today()
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Paint Central Load",
            depart_load_size="Empty",
            arrive_time="2026-05-19 08:00:00",
            depart_time="08:15",
            created_at=datetime(2026, 5, 19, 8, 0),
        )
        db.session.add(log)
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)),
            PostTrip(pretrip_id=pretrip.id, end_mileage=1010, miles_driven=10),
            DriverLogPhoto(
                driver_log_id=log.id,
                filename="missing-stop-proof.jpg",
                original_filename="missing-stop-proof.jpg",
                content_type="image/jpeg",
                source="departure_gallery",
                note="unbalanced load needs manager review",
                uploaded_by_id=driver.id,
                uploaded_at=datetime(2026, 5, 19, 12, 0),
            ),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "photo_scope_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"Photo / Damage / Safety Review" in response.data
    assert b"Photo record exists but file failed to render. Review in system before approval." in response.data
    assert b"Photo ID #" in response.data
    assert b"Cargo safety photo needs classification" in response.data



def test_manager_route_review_separates_route_truck_mileage_from_extra_dvir(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, DriverLogPhoto, PostTrip, PreTrip, ShiftRecord

        driver = create_user("st2_route_driver", "st2-route@example.com", "driver", first_name="Lamar", last_name="Bibbs")
        create_user("st2_route_manager", "st2-route-manager@example.com", "management")
        route_date = date.today()
        plants = ["RW", "H", "RE", "PPL", "PC", "RE", "KP", "RW", "PC", "PPL", "RE"]
        logs = []
        for index, plant in enumerate(plants, start=1):
            logs.append(DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name=plant,
                load_size="Route Load" if index % 2 else "Empty",
                depart_load_size="Route Load" if index < len(plants) else "Empty",
                no_pickup=index in {1, 11},
                arrive_time=f"2026-05-19 {8 + index:02d}:00:00",
                depart_time=f"{8 + index:02d}:15",
                created_at=datetime(2026, 5, 19, 8 + index, 0),
            ))
        db.session.add_all(logs)
        db.session.flush()

        route_pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=379386)
        separate_pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st4", start_mileage=121970)
        db.session.add_all([route_pretrip, separate_pretrip])
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=route_pretrip.id, start_time=datetime(2026, 5, 19, 12, 0)),
            PostTrip(pretrip_id=route_pretrip.id, end_mileage=379423, miles_driven=37),
            PostTrip(pretrip_id=separate_pretrip.id, end_mileage=122007, miles_driven=37),
        ])
        upload_dir = os.path.abspath(app.config["DRIVER_LOG_PHOTO_UPLOAD_FOLDER"])
        os.makedirs(upload_dir, exist_ok=True)
        filename = "paint-central-st2-proof.jpg"
        with open(os.path.join(upload_dir, filename), "wb") as fh:
            fh.write(b"cargo-photo")
        db.session.add(DriverLogPhoto(
            driver_log_id=logs[4].id,
            filename=filename,
            original_filename="paint-central-st2-proof.jpg",
            content_type="image/jpeg",
            source="departure_gallery",
            note="load is unbalanced and needs review",
            uploaded_by_id=driver.id,
            uploaded_at=datetime(2026, 5, 19, 21, 34),
        ))
        db.session.commit()
        driver_id = driver.id

    login(client, "st2_route_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"<strong>Truck:</strong> st2" in response.data
    assert b"<strong>Mileage:</strong> 37 miles" in response.data
    assert b"Lamar has 11 recorded stop events" in response.data
    assert b"Route truck st2 shows 37 miles" in response.data
    assert b"Multiple trucks" not in response.data
    assert b"st4" not in response.data
    assert b"Separate DVIR" not in response.data
    assert b"379,386 mi" in response.data
    assert b"379,423 mi" in response.data
    assert b"Mileage conflict / correction required" not in response.data
    assert b"Approval Blocked By" in response.data
    assert b"2 scans need manager confirmation" not in response.data
    assert b"pending cargo scan" not in response.data
    assert b"Pending Scan Evidence" not in response.data
    assert b"Cargo status" in response.data
    assert b"No cargo mismatch was detected from driver-entered route data" in response.data
    assert b"Cargo verification source: driver route entries + scan records only" in response.data
    assert b"Final cargo approval" in response.data
    assert b"Blocked until scans are confirmed" not in response.data
    assert b"Picked Up / Departed With" not in response.data
    assert b"Photo ID #" in response.data
    assert b"[ ] Cargo loading issue" in response.data
    assert b"Manager Notes - Internal" in response.data
    assert b"Approval unavailable until blocked items are resolved" in response.data
    assert b"Approve route - unavailable" in response.data
    assert b"Route Detail Table" in response.data
    assert response.data.count(b"<tr>") >= 11

    pdf = client.get(f"/manager/driver-logs/route-attachment?driver_id={driver_id}&date={date.today().isoformat()}")
    assert pdf.status_code == 200
    assert b"Approval Blocked By" in pdf.data
    assert b"Route Detail Table" in pdf.data
    assert b"Photo ID #" in pdf.data
    assert_official_record_output(pdf.data)
    assert b"Separate DVIR" not in pdf.data
    assert b"st4" not in pdf.data


def test_manager_route_review_labels_confirmed_multi_truck_route(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user("multi_truck_driver", "multi-truck@example.com", "driver", first_name="Route", last_name="Driver")
        create_user("multi_truck_manager", "multi-truck-manager@example.com", "management")
        route_date = date.today()
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Full",
                depart_load_size="Full",
                arrive_time="2026-05-19 08:00:00",
                depart_time="08:10",
                created_at=datetime(2026, 5, 19, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PC",
                load_size="Empty",
                depart_load_size="Empty",
                arrive_time="2026-05-19 09:00:00",
                depart_time="09:10",
                created_at=datetime(2026, 5, 19, 9, 0),
            ),
        ])
        first_pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st2", start_mileage=1000)
        second_pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st4", start_mileage=2000)
        db.session.add_all([first_pretrip, second_pretrip])
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=first_pretrip.id, start_time=datetime(2026, 5, 19, 7, 30)),
            ShiftRecord(user_id=driver.id, pretrip_id=second_pretrip.id, start_time=datetime(2026, 5, 19, 11, 30)),
            PostTrip(pretrip_id=first_pretrip.id, end_mileage=1010, miles_driven=10),
            PostTrip(pretrip_id=second_pretrip.id, end_mileage=2015, miles_driven=15),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "multi_truck_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")

    assert response.status_code == 200
    assert b"<strong>Truck:</strong> Multiple trucks: st2, st4" in response.data
    assert b"<strong>Mileage:</strong> 25 miles" in response.data
    assert b"Route truck" in response.data
    assert b"Separate DVIR" not in response.data



def test_manager_route_review_resolves_post_unload_non_cargo_stops(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("noncargo_driver", "noncargo@example.com", "driver", first_name="Lamar")
        create_user("noncargo_manager", "noncargo-manager@example.com", "management")
        route_date = date.today()
        logs = [
            DriverLog(driver_id=driver.id, date=route_date, plant_name="KP", load_size="Empty", depart_load_size="Raleigh East Load", arrive_time="13:00", depart_time="14:00", created_at=datetime(2026, 5, 19, 13, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="Empty", no_pickup=True, arrive_time="16:23", depart_time="16:43", created_at=datetime(2026, 5, 19, 16, 23)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PC", load_size="Empty", depart_load_size="Empty", no_pickup=True, arrive_time="17:10", depart_time="17:20", created_at=datetime(2026, 5, 19, 17, 10)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="Ryder Rentals", load_size="Empty", depart_load_size="Empty", no_pickup=True, maintenance=True, downtime_reason="Truck Issue: rental swap", arrive_time="17:45", depart_time="18:05", created_at=datetime(2026, 5, 19, 17, 45)),
        ]
        db.session.add_all(logs)
        db.session.commit()
        driver_id = driver.id

    login(client, "noncargo_manager")
    response = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert response.status_code == 200
    assert b"The route is complete and awaiting final review. Final cargo unload was at Raleigh East 4:43pm" in response.data
    assert b"subsequent stops were non-cargo" in response.data
    assert b"Paint Central drop/no pickup" in response.data
    assert b"Ryder Rentals maintenance" in response.data
    assert b"Final cargo unload appears" not in response.data
    assert b"Manager must confirm whether the extra" not in response.data


def test_damage_evidence_packet_includes_timeline_hashes_related_records_and_warnings(client, app):
    from datetime import date, datetime
    from hashlib import sha256
    from pathlib import Path

    with app.app_context():
        from app.extensions import db
        from app.models import AuditEvent, DamagePhoto, DamageReport, DriverLog, PlantTransfer, PlantTransferLine, PreTrip

        driver = create_user(
            "evidence_driver",
            "evidence@example.com",
            "driver",
            first_name="Evidence",
            last_name="Driver",
        )
        manager = create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="T-42",
            trailer_number="TR-77",
            pretrip_date=route_date,
            start_mileage=1000001,
            damage_report="No new damage at start.",
        )
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            depart_load_size="RE Load",
            arrive_time="08:00",
            depart_time="09:00",
            created_at=datetime(2026, 5, 19, 8, 0),
        )
        transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TX-900",
            transfer_date=route_date,
            ship_from="KP",
            ship_to="RE",
            trailer_number="TR-77",
            driver_name="Evidence Driver",
            driver_initials="ED",
            transfer_time="09:00",
        )
        transfer.lines.append(PlantTransferLine(line_number=1, side="left", part_number="PART-42", quantity="4"))
        db.session.add_all([pretrip, log, transfer])
        db.session.commit()
        report = DamageReport(
            reported_by_id=driver.id,
            driver_log_id=log.id,
            truck_number="T-42",
            trailer_number="TR-77",
            plant_name="KP",
            stage="after",
            move_reference="Stop 1 / dock 4",
            description="Forklift scrape on trailer door",
            status="submitted",
        )
        db.session.add(report)
        db.session.commit()
        upload_root = Path(app.config["DAMAGE_UPLOAD_FOLDER"])
        upload_root.mkdir(parents=True, exist_ok=True)
        photo_bytes = b"evidence-photo-bytes"
        (upload_root / "packet-proof.jpg").write_bytes(photo_bytes)
        photo = DamagePhoto(
            damage_report_id=report.id,
            stage="after",
            filename="packet-proof.jpg",
            original_filename="driver-door.jpg",
            content_type="image/jpeg",
        )
        audit = AuditEvent(
            user_id=manager.id,
            target_type="damage_report",
            target_id=report.id,
            action="reviewed",
            reason="Manager checked trailer damage.",
            before_values="{}",
            after_values="{}",
        )
        db.session.add_all([photo, audit])
        db.session.commit()
        report_id = report.id
        expected_hash = sha256(photo_bytes).hexdigest().encode()

    login(client, "manager1")
    report_page = client.get(f"/manager/damage-reports/{report_id}")
    assert report_page.status_code == 200
    assert b"Print Document" in report_page.data
    assert b"Evidence Packet" in report_page.data

    packet = client.get(f"/manager/damage-reports/{report_id}/evidence-packet")
    assert packet.status_code == 200
    assert b"Evidence Cover Page" in packet.data
    assert b"Full Event Timeline" in packet.data
    assert b"Photo Evidence" in packet.data
    assert b"Chain of Custody" in packet.data
    assert b"Related Route Records" in packet.data
    assert b"PreTrip DVIR created" in packet.data
    assert b"Plant transfer paperwork created" in packet.data
    assert b"Audit: reviewed" in packet.data
    assert expected_hash in packet.data
    assert b"Verify odometer entry" in packet.data
    assert b"No manager/auditor signature field is stored" in packet.data
    assert_official_record_output(packet.data)


def test_driver_profile_cannot_change_role(client, app):
    with app.app_context():
        create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="RE",
        )

    login(client, "driver1")
    response = client.post(
        "/profile",
        data={
            "username": "driver1",
            "email": "driver1@example.com",
            "role": "management",
            "new_password": "",
            "confirm_password": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import User

        assert User.query.filter_by(username="driver1").one().role == "driver"


def test_pretrip_create_and_print_route(client, app):
    with app.app_context():
        create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
        )
        create_user("manager1", "manager1@example.com", "management")

    login(client, "driver1")
    new_page = client.get("/new_pretrip")
    assert new_page.status_code == 200
    assert b'capture="environment"' in new_page.data

    response = client.post(
        "/new_pretrip",
        data={
            "truck_number": "BT-1",
            "trailer_number": "TR-2",
            "pretrip_date": "2026-05-12",
            "shift": "1st",
            "start_mileage": "1000",
            "truck_type": "Box Truck",
            "oil_system_status": "good",
            "tires_status": "good",
            "damage_report": "Scratch on bumper",
            "damage_photo": (BytesIO(b"fake image"), "pretrip-damage.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import ActivityEvent, DamageReport, PreTrip, ShiftRecord

        pretrip = PreTrip.query.filter_by(truck_number="BT-1").one()
        assert pretrip.truck_type == "Box Truck"
        pretrip_id = pretrip.id
        shift = ShiftRecord.query.filter_by(pretrip_id=pretrip_id, end_time=None).one()
        assert shift.user_id == pretrip.user_id
        damage = DamageReport.query.filter_by(move_reference=f"PreTrip #{pretrip_id}").one()
        assert damage.description == "Scratch on bumper"
        assert len(damage.photos) == 1
        assert ActivityEvent.query.filter_by(
            target_type="pretrip", target_id=pretrip_id, action="created"
        ).count() == 1

    edit_page = client.get(f"/edit_pretrip_entry/{pretrip_id}")
    assert edit_page.status_code == 200
    assert b"Truck / Tractor #" in edit_page.data
    assert b"No Defects" in edit_page.data
    assert b'capture="environment"' in edit_page.data

    edited_pretrip = client.post(
        f"/edit_pretrip_entry/{pretrip_id}",
        data={
            "truck_number": "BT-9",
            "trailer_number": "TR-9",
            "pretrip_date": "2026-05-12",
            "shift": "2nd",
            "start_mileage": "1005",
            "truck_type": "Semi",
            "oil_system_status": "good",
            "tires_status": "good",
            "gc_no_defects": "y",
            "incab_no_defects": "y",
            "ec_no_defects": "y",
            "exterior_no_defects": "y",
            "towed_no_defects": "y",
            "damage_report": "updated ok",
        },
        follow_redirects=False,
    )
    assert edited_pretrip.status_code == 302

    with app.app_context():
        from app.models import PreTrip

        pretrip = PreTrip.query.get(pretrip_id)
        assert pretrip.truck_number == "BT-9"
        assert pretrip.shift == "2nd"
        assert pretrip.gc_no_defects is True
        assert pretrip.towed_no_defects is True
        assert pretrip.damage_report == "updated ok"

    client.get("/logout")
    login(client, "manager1")
    manager_pretrip = client.get(f"/manager/pretrips/{pretrip_id}")
    assert manager_pretrip.status_code == 200
    assert b"Working" in manager_pretrip.data
    assert b"Blank" not in manager_pretrip.data
    assert b"PreTrip Damage Evidence" in manager_pretrip.data
    assert b"Scratch on bumper" in manager_pretrip.data
    assert b"/manager/damage-photos/" in manager_pretrip.data
    client.get("/logout")
    login(client, "driver1")

    posttrip = client.post(
        f"/do_posttrip/{pretrip_id}",
        data={"end_mileage": "1125", "remarks": "ok"},
        follow_redirects=False,
    )
    assert posttrip.status_code == 302

    with app.app_context():
        from app.models import PostTrip

        saved_posttrip = PostTrip.query.filter_by(pretrip_id=pretrip_id).one()
        assert saved_posttrip.end_mileage == 1125
        assert saved_posttrip.miles_driven == 120

    printable = client.get(f"/pretrip_printable/{pretrip_id}")
    assert printable.status_code == 200
    assert b"Daily Vehicle Inspection Report" in printable.data
    assert b"Edit PreTrip Before Printing" in printable.data
    assert b"Document No:" in printable.data
    assert b"Generated:" in printable.data
    assert b"Review the DVIR first" not in printable.data
    assert b"Use Edit PreTrip" not in printable.data
    assert b"print on Letter paper" not in printable.data
    assert b"Driver One" in printable.data
    assert b"PreTrip Damage Evidence" in printable.data
    assert b"Scratch on bumper" in printable.data
    assert b"/damage_reports/photos/" in printable.data
    assert "&#10003;".encode() in printable.data
    assert_official_record_output(printable.data)

    pdf = client.get(f"/pretrip_printable/{pretrip_id}/attachment")
    assert pdf.status_code == 200
    assert b"Document No:" in pdf.data
    assert b"Generated:" in pdf.data
    assert b"PreTrip Damage Evidence" in pdf.data
    assert b"Photo ID #" in pdf.data

    activity = client.get("/recent_activity")
    assert activity.status_code == 200
    assert b"PreTrip saved" in activity.data
    assert b"PreTrip printed" not in activity.data

    mark_printed = client.post(f"/pretrip_printable/{pretrip_id}/mark_printed")
    assert mark_printed.status_code == 200
    assert mark_printed.get_json()["ok"] is True

    activity = client.get("/recent_activity")
    assert b"PreTrip printed" in activity.data


def test_posttrip_ends_unlinked_manual_shift_timer(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import PreTrip, ShiftRecord

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One")
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=date.today(),
            start_mileage=1000,
        )
        db.session.add(pretrip)
        db.session.flush()
        shift = ShiftRecord(
            user_id=driver.id,
            pretrip_id=None,
            start_time=datetime.utcnow() - timedelta(hours=81),
        )
        db.session.add(shift)
        db.session.commit()
        pretrip_id = pretrip.id
        shift_id = shift.id
        driver_id = driver.id

    login(client, "driver1")
    response = client.post(
        f"/do_posttrip/{pretrip_id}",
        data={"end_mileage": "1042", "remarks": "done"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        from app.models import ShiftRecord

        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.end_time is not None
        assert saved_shift.total_hours >= 80
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 0


def test_posttrip_submit_reuses_existing_posttrip(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import PreTrip

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One")
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=date.today(),
            start_mileage=1000,
        )
        db.session.add(pretrip)
        db.session.commit()
        pretrip_id = pretrip.id

    login(client, "driver1")
    first = client.post(
        f"/do_posttrip/{pretrip_id}",
        data={"end_mileage": "1042", "remarks": "first submit"},
        follow_redirects=False,
    )
    second = client.post(
        f"/do_posttrip/{pretrip_id}",
        data={"end_mileage": "1060", "remarks": "second submit"},
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        from app.models import PostTrip

        saved = PostTrip.query.filter_by(pretrip_id=pretrip_id).all()
        assert len(saved) == 1
        assert saved[0].end_mileage == 1060
        assert saved[0].miles_driven == 60
        assert saved[0].remarks == "second submit"


def test_driver_log_form_ignores_unchecked_hot_part_and_truck_issue_fields(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    created = client.post(
        "/new_driving_log",
        data={
            "plant_name": "RE",
            "load_size": "Empty",
            "part_number": "P705",
            "truck_issue": "cel",
            "truck_issue_notes": "visible stale field",
        },
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="RE").one()
        assert log.hot_parts is False
        assert log.part_number is None
        assert log.maintenance is False
        assert log.downtime_reason is None


def test_first_driver_log_is_start_location_not_pickup(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    start_page = client.get("/new_driving_log")
    assert start_page.status_code == 200
    assert b"Start Shift Location" in start_page.data
    assert b"Start location" in start_page.data
    assert b"Start Route" in start_page.data
    assert b"Pickup" not in start_page.data

    created = client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=False,
    )
    assert created.status_code == 302

    next_page = client.get("/new_driving_log")
    assert b"Record Next Stop" in next_page.data
    assert b"Start Shift Location" not in next_page.data
    assert b"Active Stop Wait" in next_page.data
    assert b"data-active-wait-minutes" in next_page.data
    assert b"data-active-wait-seconds" in next_page.data
    assert b"driver-active-wait.js?v=2" in next_page.data
    assert b"/mobile?flow=depart" in next_page.data
    assert b"Kraft Plater" in next_page.data


def test_stale_open_stop_does_not_show_as_active_wait_clock(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("stale_wait_driver", "stale-wait@example.com", "driver")
        old_date = date.today() - timedelta(days=5)
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=old_date,
                plant_name="RE",
                load_size="Empty",
                arrive_time=f"{old_date.isoformat()} 21:15:00",
                created_at=datetime.combine(old_date, datetime.min.time()),
            )
        )
        db.session.commit()

    login(client, "stale_wait_driver")
    page = client.get("/mobile")
    assert page.status_code == 200
    assert b"Active Stop Wait" not in page.data
    assert b"data-active-wait-seconds" not in page.data


def test_driver_cannot_create_next_log_until_open_stop_is_departed(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    assert client.post("/new_driving_log", data={"plant_name": "RE", "load_size": "Empty"}).status_code == 302
    blocked = client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=True,
    )
    assert b"Close the open stop at Raleigh East before creating the next stop" in blocked.data

    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.count() == 1


def test_add_missed_stop_does_not_create_hot_cargo_or_mutate_source(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        source = DriverLog(
            driver_id=driver.id,
            date=date(2026, 5, 16),
            plant_name="PE",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            depart_time="12:00",
            arrive_time="2026-05-16 15:45:00",
        )
        db.session.add(source)
        db.session.commit()
        source_id = source.id

    login(client, "driver1")
    response = client.post(
        "/add_stop",
        data={
            "from_log_id": str(source_id),
            "plant_name": "KP",
            "load_size": "Raleigh East Load",
            "arrive_time": "12:30pm",
            "part_number": "P705",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        source = DriverLog.query.get(source_id)
        added = DriverLog.query.filter_by(plant_name="KP").one()
        assert source.secondary_load is None
        assert added.hot_parts is False
        assert added.part_number is None


def test_legacy_driver_log_urls_redirect_to_current_depart_flow(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="KP",
            load_size="Empty",
            arrive_time="2026-05-16 12:00:00",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(client, "driver1")
    assert client.get(f"/depart_driver_log/{log_id}").headers["Location"].endswith(f"/driver_logs/{log_id}/depart")
    assert client.get(f"/pickup_driver_log/{log_id}").headers["Location"].endswith(f"/driver_logs/{log_id}/depart")
    assert client.get(f"/driver_logs/{log_id}/depart/").status_code == 200


def test_new_driving_log_failure_redirects_to_mobile(client, app, monkeypatch):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    def fail_current_load(*args, **kwargs):
        raise RuntimeError("forced driver log failure")

    import app.blueprints.driver.routes as driver_routes

    monkeypatch.setattr(driver_routes, "_current_driver_load", fail_current_load)
    login(client, "driver1")

    response = client.get("/new_driving_log", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mobile")


def test_depart_missing_driver_log_redirects_instead_of_error(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    response = client.get("/driver_logs/999/depart", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/driver_logs")


def test_edit_driver_log_rejects_impossible_depart_to_next_arrival(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        route_date = date(2026, 5, 16)
        first = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PE",
            load_size="Empty",
            arrive_time="2026-05-16 21:28:00",
        )
        second = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RW",
            load_size="Empty",
            arrive_time="2026-05-16 21:32:00",
        )
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    login(client, "driver1")
    response = client.post(
        f"/edit_driver_log/{first_id}",
        data={
            "plant_name": "PE",
            "load_size": "Empty",
            "arrive_time": "5:28pm",
            "depart_time": "5:31pm",
        },
        follow_redirects=True,
    )
    assert b"Only 1 min from Unknown plant / needs confirmation to Raleigh West" in response.data

    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(first_id).depart_time is None


def test_driver_log_edit_and_depart_are_separate_actions(client, app):
    with app.app_context():
        create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="RE",
        )

    login(client, "driver1")
    created = client.post(
        "/new_driving_log",
        data={
            "plant_name": "RE",
            "load_size": "Full",
            "downtime_reason": "",
            "depart_time": "",
        },
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="RE").one()
        log_id = log.id
        assert log.depart_time is None

    list_page = client.get("/driver_logs")
    assert b"Driver One" in list_page.data
    assert b"1001" in list_page.data
    assert b"RE" in list_page.data
    assert b"Edit" in list_page.data
    assert b"Depart" in list_page.data
    assert b"Delete" in list_page.data
    assert b"Depart / Load" in list_page.data

    edited = client.post(
        f"/edit_driver_log/{log_id}",
        data={
            "plant_name": "RW",
            "load_size": "Half",
            "part_number": "P-DOCK",
            "hot_parts": "y",
            "arrive_time": "12:01am",
            "depart_time": "",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.get(log_id)
        assert log.plant_name == "RW"
        assert log.load_size == "Half"
        assert log.part_number == "P-DOCK"
        from app.blueprints.driver.routes import _arrival_utc_to_local_hhmm

        assert log.hot_parts is True
        assert _arrival_utc_to_local_hhmm(log.arrive_time) == "12:01am"
        assert log.depart_time is None

    edit_page = client.get(f"/edit_driver_log/{log_id}")
    assert b"12:01am" in edit_page.data
    assert b"driver-log-conditionals.js" in edit_page.data
    assert b"+ Add Missed Stop" not in edit_page.data
    assert b"Pickup" not in edit_page.data
    assert b"Depart Now" not in edit_page.data

    list_page = client.get("/driver_logs")
    assert b"Clear Hot" in list_page.data
    cleared_hot = client.post(f"/driver_logs/{log_id}/clear-hot", follow_redirects=False)
    assert cleared_hot.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.get(log_id)
        assert log.hot_parts is False
        assert log.part_number is None

    departed = client.post(
        f"/driver_logs/{log_id}/depart",
        data={"got_loaded": "no", "destination": ""},
        follow_redirects=False,
    )
    assert departed.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        departed_log = DriverLog.query.get(log_id)
        assert departed_log.depart_time is not None
        assert departed_log.depart_load_size == "Empty"
        assert departed_log.no_pickup is True


def test_manager_can_view_but_not_edit_driver_logs(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")
        completed_log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="KP",
            load_size="Full",
            arrive_time="2026-05-13 11:00:00",
            depart_time="12:15",
        )
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="RE",
            load_size="Full",
            arrive_time="2026-05-13 12:00:00",
        )
        problem_log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="PW",
            load_size="Empty",
            arrive_time="2026-05-13 13:00:00",
            depart_time="13:20",
            maintenance=True,
            downtime_reason="Truck Issue: CEL light",
        )
        db.session.add_all([completed_log, log, problem_log])
        db.session.commit()
        log_id = log.id
        driver_id = driver.id

    login(client, "manager1")
    page = client.get("/manager/driver-logs")
    assert page.status_code == 200
    assert b"RE" in page.data
    assert b"Cargo In / Out" in page.data
    assert b"At stop" in page.data
    assert b"Open" in page.data
    assert b"Completed" in page.data
    assert b"/edit_driver_log/" not in page.data
    assert b"/depart" not in page.data
    assert b"/pickup" not in page.data
    assert b"/delete" not in page.data

    filtered_logs = client.get(f"/manager/driver-logs?driver_id={driver_id}&date={date.today().isoformat()}")
    assert b"Manager Route Review" in filtered_logs.data
    assert b"Save Manager Review PDF" in filtered_logs.data
    assert b"CSV" in filtered_logs.data
    assert b"Sheets" in filtered_logs.data
    route_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_print.status_code == 200
    assert b"Manager Route Review" in route_print.data
    assert b"Review Status" in route_print.data
    assert b"Driver Route Audit Sheet" not in route_print.data
    assert b"CSV Export" in route_print.data
    assert b"Sheets Export" in route_print.data

    route_csv = client.get(f"/manager/driver-logs/route-export?driver_id={driver_id}&date={date.today().isoformat()}&type=csv")
    assert route_csv.status_code == 200
    assert route_csv.headers["Content-Type"].startswith("text/csv")
    assert b"Stop,Date,Driver" in route_csv.data

    route_sheets = client.get(f"/manager/driver-logs/route-export?driver_id={driver_id}&date={date.today().isoformat()}&type=sheets")
    assert route_sheets.status_code == 200
    assert route_sheets.headers["Content-Type"].startswith("text/tab-separated-values")
    assert b"Stop	Date	Driver" in route_sheets.data

    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}")
    assert dashboard.status_code == 200
    assert b"Live Routes &amp; Stops" in dashboard.data
    assert b"Missing Departure" in dashboard.data
    assert b"Completed" in dashboard.data
    assert b"Needs Attention" in dashboard.data
    assert b"Critical Exceptions" not in dashboard.data
    assert b"Truck Issue" in dashboard.data
    assert b"status-dot open" in dashboard.data
    assert b"status-dot complete" in dashboard.data
    assert b"Needs Attention" in dashboard.data
    assert b'<span class="sbadge problem">Problem</span>' not in dashboard.data
    detail_page = client.get(f"/manager/driver-logs/{log_id}")
    assert detail_page.status_code == 200
    assert b"Avg Dock Wait" not in detail_page.data

    driver_page_attempt = client.get("/driver_logs", follow_redirects=False)
    assert driver_page_attempt.status_code == 302
    assert "required_role=driver" in driver_page_attempt.headers["Location"]

    login(client, "manager1")
    edit_attempt = client.get(f"/edit_driver_log/{log_id}", follow_redirects=False)
    assert edit_attempt.status_code == 302
    assert "required_role=driver" in edit_attempt.headers["Location"]


def test_manager_driver_day_log_uses_management_readout_narrative(client, app):
    from datetime import date, datetime
    from pathlib import Path

    with app.app_context():
        from app.extensions import db
        from app.models import DamagePhoto, DamageReport, DriverLog, PreTrip

        driver = create_user(
            "lbibbs312",
            "lbibbs312@example.com",
            "driver",
            first_name="Lamar",
            last_name="Bibbs",
        )
        create_user("manager1", "manager1@example.com", "management")
        route_date = date(2026, 5, 18)
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="st4",
            pretrip_date=route_date,
            start_mileage=11111111,
        )
        first = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="KP Load",
            arrive_time="2026-05-19 08:00:00",
            depart_time="08:20",
            downtime_reason="Truck Issue: Truck regen",
            maintenance=True,
            created_at=datetime(2026, 5, 19, 8, 0),
        )
        second = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="KP Load",
            depart_load_size="PE Load",
            arrive_time="2026-05-19 09:00:00",
            depart_time="09:30",
            downtime_reason="Second-stop cargo not dropped: forgot",
            created_at=datetime(2026, 5, 19, 9, 0),
        )
        third = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PE",
            load_size="PE Load",
            arrive_time="2026-05-19 10:00:00",
            fuel=True,
            created_at=datetime(2026, 5, 19, 10, 0),
        )
        db.session.add_all([pretrip, first, second, third])
        db.session.commit()
        damage = DamageReport(
            reported_by_id=driver.id,
            driver_log_id=third.id,
            plant_name="PE",
            description="Open scuff report",
            status="open",
        )
        db.session.add(damage)
        db.session.commit()
        upload_root = Path(app.config["DAMAGE_UPLOAD_FOLDER"])
        upload_root.mkdir(parents=True, exist_ok=True)
        (upload_root / "damage-proof.jpg").write_bytes(b"fake image bytes")
        photo = DamagePhoto(
            damage_report_id=damage.id,
            stage="after",
            filename="damage-proof.jpg",
            original_filename="driver-uploaded-proof.jpg",
        )
        db.session.add(photo)
        db.session.commit()
        log_id = third.id
        photo_id = photo.id

    login(client, "manager1")
    page = client.get(f"/manager/driver-logs/{log_id}")

    assert page.status_code == 200
    assert "MOVEDEFENSE — ROUTE AUDIT".encode() in page.data
    assert b"Viewing stop #" not in page.data
    assert b"Route Summary" in page.data
    assert b"Management Readout" not in page.data
    assert b"Driver Day Log" not in page.data
    assert b"Lamar Bibbs" in page.data
    assert b"No division" not in page.data
    assert b"Badge No badge" not in page.data
    assert b"Driver Day Summary" not in page.data
    assert b"Truck ID" not in page.data
    assert b"Lamar completed 2 of 3 stops." in page.data
    assert b"Current Active Stop" in page.data
    assert b"Current Active Stop: Unknown plant / needs confirmation" in page.data
    assert b"Open Route Stop" not in page.data
    assert b"Stop #3 - Unknown plant / needs confirmation" in page.data
    assert b"Damage / Delay" in page.data
    assert b"Damage Evidence" not in page.data
    assert b"Cargo Scan Proof" not in page.data
    assert b"Signature / Audit Footer" in page.data
    assert b"Selected Stop" in page.data
    assert b"Stop #1 - Raleigh East" in page.data
    assert b"Stop #3 - Unknown plant / needs confirmation" in page.data
    assert b"2 delay events and 1 damage report need review" in page.data
    assert b"Delay Event" in page.data
    assert b"Damage Event" in page.data
    assert b"second-stop cargo was not dropped" in page.data
    assert b"Review why forgot" not in page.data
    assert b"Evidence References" not in page.data
    assert b"Full Route Table" in page.data
    assert b"Open scuff report" in page.data
    assert f'/manager/damage-photos/{photo_id}'.encode() in page.data
    assert b"damage-proof.jpg" not in page.data
    assert b"11,111,111 mi is unusually high" in page.data

    photo_response = client.get(f"/manager/damage-photos/{photo_id}")
    assert photo_response.status_code == 200
    assert photo_response.data == b"fake image bytes"


def test_manager_route_audit_treats_latest_open_stop_as_current_activity(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PartScanEvent

        driver = create_user(
            "route_audit_driver",
            "route_audit_driver@example.com",
            "driver",
            first_name="Lamar",
            last_name="Bibbs",
        )
        create_user("route_audit_manager", "route_audit_manager@example.com", "management")
        route_date = date(2026, 5, 18)
        stops = [
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Raleigh East Load",
                depart_load_size="Kraft Load",
                arrive_time="2026-05-18 12:00:00",
                depart_time="08:20",
                created_at=datetime(2026, 5, 18, 8, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Kraft Load",
                depart_load_size="Raleigh West Load",
                arrive_time="2026-05-18 13:00:00",
                depart_time="09:25",
                created_at=datetime(2026, 5, 18, 9, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RW",
                load_size="Raleigh West Load",
                depart_load_size="Kraft Load",
                arrive_time="2026-05-18 14:00:00",
                depart_time="10:30",
                created_at=datetime(2026, 5, 18, 10, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Kraft Load",
                depart_load_size="Paint Central Load",
                arrive_time="2026-05-18 15:00:00",
                depart_time="11:40",
                created_at=datetime(2026, 5, 18, 11, 0),
            ),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PC",
                load_size="Paint Central Load",
                arrive_time="2026-05-18 19:07:00",
                created_at=datetime(2026, 5, 18, 15, 7),
            ),
        ]
        db.session.add_all(stops)
        db.session.commit()
        current_stop_id = stops[-1].id
        db.session.add_all(
            [
                PartScanEvent(
                    raw_value="PC-PENDING-100",
                    normalized_value="100",
                    stop_id=current_stop_id,
                    driver_id=driver.id,
                    plant_id="PC",
                    scan_context="departure_scan",
                    validation_status="pending_part",
                    validation_message="Unknown part saved as a pending record for manager confirmation.",
                ),
                PartScanEvent(
                    raw_value="PC-VERIFY-200",
                    normalized_value="200",
                    stop_id=current_stop_id,
                    driver_id=driver.id,
                    plant_id="PC",
                    scan_context="pickup_scan",
                    validation_status="needs_review",
                    validation_message="Dispatcher should verify this part against the move.",
                ),
            ]
        )
        db.session.commit()

    login(client, "route_audit_manager")
    page = client.get(f"/manager/driver-logs/{current_stop_id}")

    assert page.status_code == 200
    assert b"Lamar completed 4 of 5 stops. He is currently at Paint Central getting loaded. No delay or damage events were reported today. Two cargo scans need manager confirmation." in page.data
    assert b"Current Active Stop: Paint Central" in page.data
    assert b"Driver arrived at 3:07pm and is getting loaded / awaiting departure." in page.data
    assert b"Needs Review" in page.data
    assert b"2 cargo scans require manager confirmation." in page.data
    assert b"Cargo Review" in page.data
    assert b"Damage Evidence" not in page.data
    assert b"Damage Reports (0)" not in page.data
    assert b"Delay Events (0)" not in page.data
    assert b"Damage / Delay" not in page.data
    assert b"Critical Exceptions" not in page.data
    assert b"Open Route Stop" not in page.data
    assert b"No damage reports were filed" not in page.data
    assert b"No delay events were reported for this route" not in page.data


def test_manager_driver_log_uses_plain_stop_progress_and_named_task(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, Task

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        first = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            depart_time="08:15",
            part_number="P-HOT-1",
            hot_parts=True,
            arrive_time=f"{route_date.isoformat()} 12:00:00",
        )
        second = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Raleigh East Load",
            arrive_time=f"{route_date.isoformat()} 13:00:00",
        )
        task = Task(
            title="KP to RE",
            details="Raleigh hot part",
            part_number="P-HOT-1",
            is_hot=True,
            status="in-progress",
            assigned_to=driver.id,
            accepted_at=datetime.utcnow(),
            accepted_by_id=driver.id,
        )
        db.session.add_all([first, second, task])
        db.session.commit()
        log_id = first.id

    login(client, "manager1")
    page = client.get(f"/manager/driver-logs/{log_id}")
    assert page.status_code == 200
    assert b"Stop Progress" in page.data
    assert b"Arrival and departure recorded" in page.data
    assert b"Route position 1 of 2" in page.data
    assert b"Hot Part" in page.data
    assert b"P-HOT-1" in page.data
    assert b"Stop Status meaning" not in page.data
    assert b"Task T" not in page.data


def test_manager_search_suggest_learns_from_driver_logs(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One", employee_id="D-9")
        create_user("manager1", "manager1@example.com", "management")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="KP",
            load_size="Empty",
            depart_load_size="Helios Load",
            part_number="P0903110",
            arrive_time="2026-05-13 12:00:00",
        )
        db.session.add(log)
        db.session.commit()

    login(client, "manager1")
    part_suggestions = client.get("/manager/search/suggest?q=P090")
    assert part_suggestions.status_code == 200
    assert any(item["term"] == "P0903110" for item in part_suggestions.get_json()["results"])

    driver_suggestions = client.get("/manager/search/suggest?q=Driver")
    assert any(item["category"] == "driver" and "Driver One" in item["term"] for item in driver_suggestions.get_json()["results"])


def test_manager_exception_complete_and_delete_are_history(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, OperationalFollowUp

        driver = create_user("driver1", "driver1@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="KP",
            load_size="Full",
            arrive_time="2026-05-13 12:00:00",
        )
        followup = OperationalFollowUp(
            created_by_id=driver.id,
            kind="delay",
            plant_name="KP",
            details="Check dock delay pattern.",
        )
        db.session.add_all([log, followup])
        db.session.commit()
        log_id = log.id
        followup_id = followup.id

    login(client, "manager1")
    review_page = client.get("/manager/review")
    assert b"Followup" in review_page.data
    assert b"Check dock delay pattern" in review_page.data

    complete = client.post(
        "/manager/exceptions/reviewed",
        data={
            "review_key": f"followup:{followup_id}:Manager follow-up",
            "target_type": "followup",
            "target_id": str(followup_id),
            "category": "Manager follow-up",
            "label": "KP",
            "review_action": "reviewed",
        },
        follow_redirects=True,
    )
    assert b"Exception reviewed" in complete.data

    delete = client.post(
        "/manager/exceptions/reviewed",
        data={
            "review_key": f"driver_log:{log_id}:No pre-trip",
            "target_type": "driver_log",
            "target_id": str(log_id),
            "category": "No pre-trip",
            "label": "Driver at KP",
            "review_action": "deleted",
        },
        follow_redirects=True,
    )
    assert b"Exception deleted" in delete.data
    assert b"Deleted" in delete.data

    with app.app_context():
        from app.models import ActivityEvent, OperationalFollowUp

        assert OperationalFollowUp.query.get(followup_id).status == "closed"
        assert ActivityEvent.query.filter_by(category="exception", action="reviewed").count() == 1
        assert ActivityEvent.query.filter_by(category="exception", action="deleted").count() == 1


def test_drivers_can_delete_only_same_day_records(client, app):
    from datetime import date, timedelta

    today = date.today()
    yesterday = today - timedelta(days=1)

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PlantTransfer, PreTrip

        driver = create_user("driver1", "driver1@example.com", "driver")
        today_log = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="RE",
            load_size="Full",
            arrive_time="2026-05-13 12:00:00",
        )
        old_log = DriverLog(
            driver_id=driver.id,
            date=yesterday,
            plant_name="RW",
            load_size="Half",
            arrive_time="2026-05-12 12:00:00",
        )
        today_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=today,
            shift="1st",
        )
        old_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-2",
            pretrip_date=yesterday,
            shift="1st",
        )
        today_transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TRX-1",
            transfer_date=today,
            ship_to="RE",
            ship_from="RW",
            driver_name="Driver One",
        )
        old_transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TRX-2",
            transfer_date=yesterday,
            ship_to="RE",
            ship_from="RW",
            driver_name="Driver One",
        )
        db.session.add_all(
            [today_log, old_log, today_pretrip, old_pretrip, today_transfer, old_transfer]
        )
        db.session.commit()
        ids = {
            "today_log": today_log.id,
            "old_log": old_log.id,
            "today_pretrip": today_pretrip.id,
            "old_pretrip": old_pretrip.id,
            "today_transfer": today_transfer.id,
            "old_transfer": old_transfer.id,
        }

    login(client, "driver1")
    assert client.post(f"/driver_logs/{ids['today_log']}/delete").status_code == 302
    assert client.post(f"/driver_logs/{ids['old_log']}/delete").status_code == 302
    assert client.post(f"/pretrips/{ids['today_pretrip']}/delete").status_code == 302
    assert client.post(f"/pretrips/{ids['old_pretrip']}/delete").status_code == 302
    assert client.post(f"/plant_transfers/{ids['today_transfer']}/delete").status_code == 302
    assert client.post(f"/plant_transfers/{ids['old_transfer']}/delete").status_code == 302

    with app.app_context():
        from app.models import DriverLog, PlantTransfer, PreTrip, SearchCorpus

        today_log = DriverLog.query.get(ids["today_log"])
        old_log = DriverLog.query.get(ids["old_log"])
        today_pretrip = PreTrip.query.get(ids["today_pretrip"])
        old_pretrip = PreTrip.query.get(ids["old_pretrip"])
        today_transfer = PlantTransfer.query.get(ids["today_transfer"])
        old_transfer = PlantTransfer.query.get(ids["old_transfer"])

        assert today_log is not None and today_log.deleted_at is not None
        assert old_log is not None and old_log.deleted_at is None
        assert today_pretrip is not None and today_pretrip.deleted_at is not None
        assert old_pretrip is not None and old_pretrip.deleted_at is None
        assert today_transfer is not None and today_transfer.deleted_at is not None
        assert old_transfer is not None and old_transfer.deleted_at is None
        assert SearchCorpus.query.count() == 0


def test_search_corpus_fts_sync_is_sqlite_only(client, app, monkeypatch):
    with app.app_context():
        from app.extensions import db
        from app.models import SearchCorpus
        from app.services import search_corpus

        row = SearchCorpus(
            category="plant",
            term="Raleigh East",
            normalized_term="raleigh east",
            context_key="plant:RE",
        )
        db.session.add(row)
        db.session.flush()
        monkeypatch.setattr(search_corpus, "_session_dialect_name", lambda: "postgresql")

        def fail_execute(*args, **kwargs):
            raise AssertionError("Postgres must not touch the SQLite FTS table")

        monkeypatch.setattr(db.session, "execute", fail_execute)
        search_corpus._sync_fts_row(row)


def test_driver_can_upload_stop_photos_from_edit_and_depart_gallery(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("photo_driver", "photo_driver@example.com", "driver")
        create_user("photo_manager", "photo_manager@example.com", "management")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="PC",
            load_size="Paint Central Load",
            arrive_time="2026-05-19 19:07:00",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        driver_id = driver.id

    login(client, "photo_driver")
    edit_page = client.get(f"/edit_driver_log/{log_id}")
    assert edit_page.status_code == 200
    assert b"Add Picture To This Stop" in edit_page.data
    assert b"Why are you adding this picture?" in edit_page.data
    assert b"Upload From Gallery" in edit_page.data
    assert b'data-stop-photo-input="edit_gallery"' in edit_page.data
    assert b'capture="environment" data-stop-photo-input="edit_camera"' in edit_page.data

    missing_note = client.post(
        f"/driver_logs/{log_id}/photos",
        data={"source": "edit_gallery", "photo": (BytesIO(b"edit-gallery-photo"), "edit-gallery.jpg")},
        headers={"Accept": "application/json"},
    )
    assert missing_note.status_code == 400
    assert "reason" in missing_note.get_json()["error"]

    first_upload = client.post(
        f"/driver_logs/{log_id}/photos",
        data={
            "source": "edit_gallery",
            "note": "Loaded seal photo from gallery",
            "photo": (BytesIO(b"edit-gallery-photo"), "edit-gallery.jpg"),
        },
        headers={"Accept": "application/json"},
    )
    assert first_upload.status_code == 200
    first_photo = first_upload.get_json()["photo"]
    assert first_photo["source"] == "Edit Gallery"
    assert first_photo["note"] == "Loaded seal photo from gallery"
    driver_photo = client.get(first_photo["url"])
    assert driver_photo.status_code == 200
    assert driver_photo.data == b"edit-gallery-photo"

    depart_page = client.get(f"/driver_logs/{log_id}/depart")
    assert depart_page.status_code == 200
    assert b"Add Picture To This Stop" in depart_page.data
    assert b"Why are you adding this picture?" in depart_page.data
    assert b"Upload From Gallery" in depart_page.data
    assert b'data-stop-photo-input="departure_gallery"' in depart_page.data
    assert b"Upload Label Photo" not in depart_page.data
    assert b"galleryScanImage" not in depart_page.data

    second_upload = client.post(
        f"/driver_logs/{log_id}/photos",
        data={
            "source": "departure_gallery",
            "note": "Departing load proof from gallery",
            "photo": (BytesIO(b"departure-gallery-photo"), "departure-gallery.png"),
        },
        headers={"Accept": "application/json"},
    )
    assert second_upload.status_code == 200
    second_photo = second_upload.get_json()["photo"]
    assert second_photo["source"] == "Departure Gallery"
    assert second_photo["note"] == "Departing load proof from gallery"

    driver_list = client.get("/driver_logs")
    assert driver_list.status_code == 200
    assert b"Photo proof 1" in driver_list.data
    assert b"Loaded seal photo from gallery" in driver_list.data
    assert b"Departing load proof from gallery" in driver_list.data

    driver_detail = client.get(f"/view_driver_log/{log_id}")
    assert driver_detail.status_code == 200
    assert b"Stop Photo Proof" in driver_detail.data
    assert b"Loaded seal photo from gallery" in driver_detail.data
    assert b"Remove Photo" in driver_detail.data

    driver_print = client.get("/driver_logs_print")
    assert driver_print.status_code == 200
    assert b"3. Photo Proof" in driver_print.data
    assert b"4. Plant Legend" in driver_print.data
    assert b"5. Signatures" in driver_print.data
    assert b"Loaded seal photo from gallery" in driver_print.data
    assert b"Departing load proof from gallery" in driver_print.data
    assert b"Photo proof review" in driver_print.data
    assert b"Uploaded " in driver_print.data
    assert b" UTC" not in driver_print.data
    assert b"Timing status pending" not in driver_print.data

    with app.app_context():
        from app.models import DriverLogPhoto

        photos = DriverLogPhoto.query.order_by(DriverLogPhoto.id.asc()).all()
        assert len(photos) == 2
        first_photo_id = photos[0].id
        second_photo_id = photos[1].id

    client.get("/logout")
    login(client, "photo_manager")
    manager_list = client.get(f"/manager/driver-logs?date={date.today().isoformat()}")
    assert manager_list.status_code == 200
    assert b"Proof" in manager_list.data
    assert b"Loaded seal photo from gallery" in manager_list.data
    assert b"Departing load proof from gallery" in manager_list.data

    manager_dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}&focus=routes")
    assert manager_dashboard.status_code == 200
    assert b"Cargo Photo Proof" in manager_dashboard.data
    assert b"Departing load proof from gallery" in manager_dashboard.data
    assert f"/manager/driver-log-photos/{second_photo_id}".encode() in manager_dashboard.data

    manager_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_print.status_code == 200
    assert b"Photo / Damage / Safety Review" in manager_print.data
    assert b"Departing load proof from gallery" in manager_print.data
    assert b"height:2.15in" in manager_print.data
    assert b"Timing status pending" not in manager_print.data

    manager_page = client.get(f"/manager/driver-logs/{log_id}")
    assert manager_page.status_code == 200
    assert b"Stop Photo Proof" in manager_page.data
    assert b"Cargo Photo Proof" in manager_page.data
    assert b"Two stop photo proofs were attached" in manager_page.data
    assert b"Latest proof from Paint Central says: Departing load proof from gallery" in manager_page.data
    assert b"Loaded seal photo from gallery" in manager_page.data
    assert b"Remove Photo" in manager_page.data
    assert f"/manager/driver-log-photos/{first_photo_id}".encode() in manager_page.data
    assert f"/manager/driver-log-photos/{second_photo_id}".encode() in manager_page.data
    manager_photo = client.get(f"/manager/driver-log-photos/{second_photo_id}")
    assert manager_photo.status_code == 200
    assert manager_photo.data == b"departure-gallery-photo"

    manager_delete = client.post(
        f"/manager/driver-log-photos/{first_photo_id}/delete",
        data={"next": f"/manager/driver-logs/{log_id}"},
        follow_redirects=False,
    )
    assert manager_delete.status_code == 302
    manager_page_after_delete = client.get(f"/manager/driver-logs/{log_id}")
    assert b"Loaded seal photo from gallery" not in manager_page_after_delete.data
    assert b"Departing load proof from gallery" in manager_page_after_delete.data
    assert client.get(f"/manager/driver-log-photos/{first_photo_id}").status_code == 404

    with app.app_context():
        missing_photo = DriverLogPhoto.query.get(second_photo_id)
        missing_path = os.path.abspath(
            os.path.join(
                app.root_path,
                os.pardir,
                app.config["DRIVER_LOG_PHOTO_UPLOAD_FOLDER"],
                missing_photo.filename,
            )
        )
        os.remove(missing_path)

    manager_page_missing_file = client.get(f"/manager/driver-logs/{log_id}")
    assert manager_page_missing_file.status_code == 200
    assert b"Photo file missing" in manager_page_missing_file.data
    assert b"Delete this missing proof record" in manager_page_missing_file.data

    manager_print_missing_file = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_print_missing_file.status_code == 200
    assert b"Photo record exists but file failed to render" in manager_print_missing_file.data
    assert b"Review in system before approval" in manager_print_missing_file.data

    client.get("/logout")
    login(client, "photo_driver")
    driver_edit_missing_file = client.get(f"/edit_driver_log/{log_id}")
    assert driver_edit_missing_file.status_code == 200
    assert b"Photo file missing" in driver_edit_missing_file.data
    assert b"Remove Photo" in driver_edit_missing_file.data

    driver_delete = client.post(
        f"/driver_logs/photos/{second_photo_id}/delete",
        data={"next": "/driver_logs"},
        follow_redirects=False,
    )
    assert driver_delete.status_code == 302
    assert client.get(first_photo["url"]).status_code == 404
    assert client.get(second_photo["url"]).status_code == 404
    with app.app_context():
        assert DriverLogPhoto.query.count() == 0


def test_driver_can_record_auditable_part_scan_and_depart_with_pending_cargo_review(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver_scan", "driver_scan@example.com", "driver")
        create_user("scan_manager", "scan-manager@example.com", "management")
        route_date = date.today()
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PE",
            load_size="PE Load",
            arrive_time=f"{route_date.isoformat()} 04:00:00",
            created_at=datetime(2026, 5, 20, 8, 0),
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        driver_id = driver.id

    login(client, "driver_scan")
    depart_page = client.get(f"/driver_logs/{log_id}/depart")
    assert depart_page.status_code == 200
    assert b"Scan Unloaded / Dropped Cargo" in depart_page.data
    assert b"Scan Loaded / Departing Cargo" in depart_page.data
    assert b"Scan Arriving Cargo" not in depart_page.data
    assert b"Scan Picked-Up Cargo" not in depart_page.data
    assert b"Add Picture To This Stop" in depart_page.data
    assert b"Upload From Gallery" in depart_page.data
    assert b'data-stop-photo-input="departure_gallery"' in depart_page.data
    assert b"Upload Label Photo" not in depart_page.data
    assert b"galleryScanImage" not in depart_page.data
    assert b"@zxing/browser" in depart_page.data
    assert b"Manager review / override note" in depart_page.data

    scan = client.post(
        f"/driver_logs/{log_id}/part-scans",
        json={"raw_value": "PART-L861-PE", "scan_context": "drop_scan", "barcode_format": "code_128"},
    )
    assert scan.status_code == 200
    payload = scan.get_json()["scan"]
    assert payload["normalized_value"] == "L861"
    assert payload["validation_status"] == "pending_part"

    departed = client.post(
        f"/driver_logs/{log_id}/depart",
        data={"unloaded_on_departure": "yes", "got_loaded": "no", "destination": "", "secondary_destination": ""},
        follow_redirects=False,
    )
    assert departed.status_code == 302

    with app.app_context():
        from app.models import ActivityEvent, DriverLog, PartAlias, PartMaster, PartScanEvent

        assert DriverLog.query.get(log_id).depart_time is not None
        assert PartScanEvent.query.count() == 1
        assert PartAlias.query.filter_by(normalized_value="L861").count() == 1
        assert PartMaster.query.filter_by(canonical_part_number="L861", status="pending").count() == 1
        review = ActivityEvent.query.filter_by(
            category="part_scan", action="needs_review", title="Cargo scan needs manager review"
        ).one()
        assert "L861" in review.details

    client.get("/logout")
    login(client, "scan_manager")
    manager_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_print.status_code == 200
    assert b"Cargo / Manifest Review" in manager_print.data
    assert b"Cargo status" in manager_print.data
    assert b"Needs Review" in manager_print.data
    assert b"Verification level" in manager_print.data
    assert b"Route-entered + scans only" in manager_print.data
    assert b"Manifest linked" in manager_print.data
    assert b"No" in manager_print.data
    assert b"1 scan needs manager confirmation" in manager_print.data
    assert b"Pending Scan Evidence" in manager_print.data
    assert b"Drop Scan" in manager_print.data
    assert b"pending part" in manager_print.data
    assert b"L861" in manager_print.data
    assert b"Picked Up / Departed With" not in manager_print.data


def test_driver_hot_part_proof_one_tap_flags_missing_scan_for_manager(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, HotPartEvent, HotMove, PreTrip, Task

        driver = create_user("hot_driver", "hot_driver@example.com", "driver", first_name="Hot", last_name="Driver")
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="ST4", trailer_number="TR9")
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            hot_parts=True,
            part_number="L861",
            arrive_time=f"{route_date.isoformat()} 08:00:00",
        )
        task = Task(
            title="KP to RE",
            details="Move hot part L861",
            part_number="L861",
            is_hot=True,
            status="pending",
            assigned_to=driver.id,
        )
        db.session.add_all([pretrip, log, task])
        db.session.commit()
        driver_id = driver.id
        task_id = task.id
        log_id = log.id

    login(client, "hot_driver")
    page = client.get(f"/tasks/{task_id}")
    assert page.status_code == 200
    assert b"Hot Part Proof" in page.data
    assert b"Hot Part: L861" in page.data
    assert b"Scan Part Label" in page.data
    assert b"Picked Up" in page.data
    assert b"Dropped Off" in page.data
    assert b"Can't Find Part" in page.data
    assert b"Wrong Part" in page.data
    assert b"Report Delay" in page.data
    assert b"manifest lines" not in page.data.lower()
    assert b"expected pallet" not in page.data.lower()
    assert b"bol line" not in page.data.lower()

    picked = client.post(f"/tasks/{task_id}/hot-proof", json={"event_type": "picked_up"})
    assert picked.status_code == 200
    payload = picked.get_json()
    assert payload["proof"]["has_scan_proof"] is False
    assert payload["proof"]["proof_sentence"] == "No hot-part scan proof was recorded for this route."

    with app.app_context():
        hot_move = HotMove.query.filter_by(move_id=task_id).one()
        events = HotPartEvent.query.filter_by(hot_move_id=hot_move.id).order_by(HotPartEvent.id).all()
        assert hot_move.status == "picked_up"
        assert events[-1].event_type == "picked_up"
        assert events[-1].driver_id == driver_id
        assert events[-1].truck_id == "ST4"
        assert events[-1].stop_id == log_id
        assert events[-1].plant_id == "KP"

    client.get("/logout")
    login(client, "manager1")
    manager_page = client.get(f"/manager/driver-logs/{log_id}")
    assert manager_page.status_code == 200
    assert b"Hot Part Proof" in manager_page.data
    assert b"Hot Part Number" in manager_page.data
    assert b"L861" in manager_page.data
    assert b"No hot-part scan proof was recorded for this route." in manager_page.data


def test_driver_hot_part_scan_builds_manager_narrative_and_unknown_alias(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, Task

        driver = create_user("scan_hot", "scan_hot@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            hot_parts=True,
            part_number="L861",
            arrive_time=f"{route_date.isoformat()} 08:00:00",
        )
        task = Task(title="KP to RE", part_number="L861", is_hot=True, status="pending", assigned_to=driver.id)
        db.session.add_all([log, task])
        db.session.commit()
        task_id = task.id
        log_id = log.id

    login(client, "scan_hot")
    scanned = client.post(
        f"/tasks/{task_id}/hot-proof",
        json={"event_type": "label_scanned", "raw_scan_value": "PART-L861-KP", "barcode_format": "code_128"},
    )
    assert scanned.status_code == 200
    assert scanned.get_json()["event"]["normalized_scan_value"] == "L861"

    picked = client.post(f"/tasks/{task_id}/hot-proof", json={"event_type": "picked_up"})
    assert picked.status_code == 200
    assert picked.get_json()["proof"]["proof_sentence"] == "Driver scanned hot part L861 and marked it picked up."

    with app.app_context():
        from app.models import PartAlias, PartMaster

        part = PartMaster.query.filter_by(canonical_part_number="L861").one()
        alias = PartAlias.query.filter_by(part_id=part.id, normalized_value="L861").first()
        assert alias is not None
        assert alias.raw_scan_value == "PART-L861-KP"
        assert alias.label_format == "code_128"

    client.get("/logout")
    login(client, "manager1")
    manager_page = client.get(f"/manager/driver-logs/{log_id}")
    assert b"Driver scanned hot part L861 and marked it picked up." in manager_page.data
    assert b"No hot-part scan proof was recorded for this route." not in manager_page.data


def test_hot_part_exception_routes_to_manager_followup(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, Task

        driver = create_user("exception_hot", "exception_hot@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        log = DriverLog(driver_id=driver.id, date=route_date, plant_name="KP", load_size="Empty", arrive_time=f"{route_date.isoformat()} 08:00:00")
        task = Task(title="KP to RE", part_number="L861", is_hot=True, status="pending", assigned_to=driver.id)
        db.session.add_all([log, task])
        db.session.commit()
        task_id = task.id

    login(client, "exception_hot")
    response = client.post(f"/tasks/{task_id}/hot-proof", json={"event_type": "cant_find_part"})
    assert response.status_code == 200
    assert response.get_json()["proof"]["open_exception"] == "Can't Find Part"

    with app.app_context():
        from app.models import ActivityEvent, OperationalFollowUp

        followup = OperationalFollowUp.query.filter_by(kind="hot_part_exception", status="open").one()
        assert "Dispatch review is required" in followup.details
        assert ActivityEvent.query.filter_by(category="exception", action="cant_find_part").count() == 1


def test_completed_hot_moves_suggest_but_do_not_overwrite_default_route(app):
    with app.app_context():
        from app.extensions import db
        from app.models import PartMaster, PartRouteProfile, Task
        from app.services.hot_parts import ensure_hot_move_for_task, record_hot_part_event

        driver = create_user("route_hot", "route_hot@example.com", "driver")
        for index in range(3):
            task = Task(
                title="KP to RE",
                part_number="L861",
                is_hot=True,
                status="in-progress",
                assigned_to=driver.id,
            )
            db.session.add(task)
            db.session.flush()
            hot_move = ensure_hot_move_for_task(task, driver_id=driver.id, source="dispatch")
            record_hot_part_event(hot_move, "dropped_off", driver_id=driver.id)
        db.session.commit()

        part = PartMaster.query.filter_by(canonical_part_number="L861").one()
        profile = PartRouteProfile.query.filter_by(part_id=part.id, origin_plant_id="KP", destination_plant_id="RE").one()
        assert profile.times_completed == 3
        assert profile.status == "suggested"
        assert profile.confidence_score >= 0.65
        assert part.default_origin_plant_id is None
        assert part.default_destination_plant_id is None


def test_driver_log_departure_names_load_by_destination_and_arrival_unloads(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    arrived_kraft = client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=False,
    )
    assert arrived_kraft.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        kraft_log = DriverLog.query.filter_by(plant_name="KP").one()
        kraft_id = kraft_log.id

    depart_page = client.get(f"/driver_logs/{kraft_id}/depart")
    assert depart_page.status_code == 200
    assert b"Did you get loaded?" in depart_page.data
    assert b"Primary destination" in depart_page.data

    departed = client.post(
        f"/driver_logs/{kraft_id}/depart",
        data={"got_loaded": "yes", "destination": "Helios"},
        follow_redirects=False,
    )
    assert departed.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        kraft_log = DriverLog.query.get(kraft_id)
        assert kraft_log.depart_load_size == "Helios Load"
        assert kraft_log.no_pickup is False

    arrival_page = client.get("/new_driving_log")
    assert b"In truck now" in arrival_page.data
    assert b"Helios Load" in arrival_page.data
    assert b"Did you get unloaded?" not in arrival_page.data

    arrived_helios = client.post(
        "/new_driving_log",
        data={"plant_name": "Helios", "load_size": "Helios Load"},
        follow_redirects=False,
    )
    assert arrived_helios.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        helios_log = DriverLog.query.filter_by(plant_name="Helios").one()
        helios_id = helios_log.id
        assert helios_log.load_size == "Helios Load"
        assert helios_log.downtime_reason is None

    helios_depart_page = client.get(f"/driver_logs/{helios_id}/depart")
    assert b"Did you get unloaded?" in helios_depart_page.data
    assert b"Current wait:" in helios_depart_page.data

    assert client.post(
        f"/driver_logs/{helios_id}/depart",
        data={"unloaded_on_departure": "yes", "got_loaded": "no", "destination": ""},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        helios_log = DriverLog.query.get(helios_id)
        assert helios_log.depart_load_size == "Empty"
        assert helios_log.dock_wait_minutes is not None
        assert helios_log.downtime_reason is None

    print_page = client.get("/driver_logs_print")
    assert b"Helios Load" in print_page.data
    assert b"Kraft Plant Load" not in print_page.data


def test_mixed_cargo_deviation_preserves_primary_and_drops_hot_part(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    assert client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        kraft_id = DriverLog.query.filter_by(plant_name="KP").one().id

    assert client.post(
        f"/driver_logs/{kraft_id}/depart",
        data={"got_loaded": "yes", "destination": "Trim DC", "secondary_destination": ""},
        follow_redirects=False,
    ).status_code == 302

    assert client.post(
        "/new_driving_log",
        data={"plant_name": "PW", "load_size": "Trim DC Load"},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        paint_west_id = DriverLog.query.filter_by(plant_name="PW").one().id

    assert client.post(
        f"/driver_logs/{paint_west_id}/depart",
        data={"got_loaded": "no", "destination": "", "secondary_destination": "Helios", "secondary_load_type": "hot"},
        follow_redirects=False,
    ).status_code == 302

    arrival_page = client.get("/new_driving_log")
    assert b"Trim DC Load + Helios Hot Part" in arrival_page.data

    assert client.post(
        "/new_driving_log",
        data={
            "plant_name": "Helios",
            "load_size": "Trim DC Load",
            "secondary_load": "Helios Hot Part",
        },
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        helios_id = DriverLog.query.filter_by(plant_name="Helios").one().id

    helios_depart_page = client.get(f"/driver_logs/{helios_id}/depart")
    assert b"Did you drop off the second-stop cargo?" in helios_depart_page.data
    assert client.post(
        f"/driver_logs/{helios_id}/depart",
        data={"secondary_dropped_on_departure": "yes", "got_loaded": "no", "destination": ""},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog
        from app.services.load_state import current_load_after_logs

        helios_log = DriverLog.query.filter_by(plant_name="Helios").one()
        assert helios_log.load_size == "Trim DC Load"
        assert helios_log.secondary_load is None
        logs = DriverLog.query.order_by(DriverLog.created_at.asc()).all()
        current_load = current_load_after_logs(logs)
        assert current_load["cargo_display"] == "Trim DC Load"

    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    assert b"Trim DC Load + Helios Hot Part" in print_page.data
    assert b"Deviation" in print_page.data


def test_depart_second_stop_can_be_regular_load_and_finalized_route_shows_canonical_stop_summaries(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    assert client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        kraft_id = DriverLog.query.filter_by(plant_name="KP").one().id

    assert client.post(
        f"/driver_logs/{kraft_id}/depart",
        data={
            "got_loaded": "yes",
            "destination": "Trim DC",
            "secondary_destination": "Helios",
            "secondary_load_type": "load",
        },
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        kraft_log = DriverLog.query.get(kraft_id)
        assert kraft_log.depart_load_size == "Trim DC Load"
        assert kraft_log.secondary_load == "Helios Load"

    arrival_page = client.get("/new_driving_log")
    assert b"Trim DC Load + Helios Load" in arrival_page.data
    assert b"Helios Hot Part" not in arrival_page.data

    assert client.post(
        "/new_driving_log",
        data={
            "plant_name": "Helios",
            "load_size": "Trim DC Load",
            "secondary_load": "Helios Load",
        },
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        from app.models import DriverLog

        helios_id = DriverLog.query.filter_by(plant_name="Helios").one().id

    assert client.post(
        f"/driver_logs/{helios_id}/depart",
        data={"secondary_dropped_on_departure": "yes", "got_loaded": "no", "destination": ""},
        follow_redirects=False,
    ).status_code == 302

    finalized = client.post(
        "/end_of_day_summary",
        data={"driver_signature": "data:image/png;base64,abc"},
        follow_redirects=True,
    )
    assert finalized.status_code == 200
    assert b"Trim DC Load + Helios Load" in finalized.data
    assert b"Loaded Trim DC Load." in finalized.data
    assert b"Loaded Helios Load." in finalized.data
    assert b"Delivered Helios Load." in finalized.data
    assert b"Continuing with Trim DC Load." in finalized.data
    assert b"First stop after departure" not in finalized.data
    assert b"Route finalized" in finalized.data


def test_truck_issue_records_odometer_without_fuel_stop(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    response = client.post(
        "/new_driving_log",
        data={
            "plant_name": "RE",
            "load_size": "Empty",
            "maintenance": "y",
            "truck_issue": "cel",
            "truck_issue_notes": "warning light",
            "fuel_mileage": "12345",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="RE").one()
        assert log.maintenance is True
        assert log.fuel is False
        assert log.fuel_mileage == 12345

    page = client.get("/driver_logs")
    assert b"Truck Issue - 12,345 mi" in page.data


def test_new_log_load_state_ignores_previous_days_and_finalized_route(client, app):
    from datetime import timedelta

    with app.app_context():
        from app.blueprints.driver.routes import _today_local_date
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        today = _today_local_date()
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today - timedelta(days=1),
                plant_name="KP",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                secondary_load="PPL Hot Part",
                depart_time="14:00",
            )
        )
        db.session.commit()

    login(client, "driver1")
    page = client.get("/new_driving_log")
    assert b"In truck now" in page.data
    assert b"Empty" in page.data
    assert b"Raleigh East Load + PPL Hot Part" not in page.data
    assert b"conditional-panel" in page.data
    assert b"No truck issue" not in page.data

    with app.app_context():
        from app.blueprints.driver.routes import _today_local_date
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, User

        driver = User.query.filter_by(username="driver1").one()
        today = _today_local_date()
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                secondary_load="PPL Hot Part",
                depart_time="14:00",
            )
        )
        db.session.add(
            ActivityEvent(
                user_id=driver.id,
                category="eod",
                action="finalized",
                title="End of day finalized",
                details=f"Reviewed 1 driver log(s), 0 pretrip(s), and 0 plant transfer(s) for {today}.",
                target_type="end_of_day",
            )
        )
        db.session.commit()

    finalized_page = client.get("/new_driving_log")
    assert b"Empty" in finalized_page.data
    assert b"Raleigh East Load + PPL Hot Part" not in finalized_page.data


def test_premature_finalized_event_does_not_lock_active_shift_new_logs(client, app):
    from datetime import datetime

    with app.app_context():
        from app.blueprints.driver.routes import _today_local_date
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, PreTrip, ShiftRecord

        driver = create_user("active_after_final", "active-after-final@example.com", "driver", first_name="Active")
        today = _today_local_date()
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()))
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Raleigh West Load",
                arrive_time="08:00",
                depart_time="08:15",
                created_at=datetime.utcnow(),
            )
        )
        db.session.add(
            ActivityEvent(
                user_id=driver.id,
                category="eod",
                action="finalized",
                title="Route finalized",
                details=f"Route finalized for {today}",
                target_type="end_of_day",
            )
        )
        db.session.commit()

    login(client, "active_after_final")
    mobile = client.get("/mobile")
    assert mobile.status_code == 200
    body = mobile.get_data(as_text=True)
    assert b"Continue route" in mobile.data
    assert b"Add Stop" in mobile.data
    assert body.count('data-flow-panel-title="Add Stop"') == 1
    assert b"Finalize Route" not in mobile.data

    new_log = client.get("/new_driving_log")
    assert new_log.status_code == 200
    assert b"Raleigh West Load" in new_log.data


def test_driver_logs_flags_impossible_plant_transfer_timing(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        route_date = date(2026, 5, 16)
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PE",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                depart_time="17:31",
                arrive_time="2026-05-16 21:28:00",
            )
        )
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RW",
                load_size="Raleigh East Load",
                arrive_time="2026-05-16 21:32:00",
            )
        )
        db.session.commit()

    login(client, "driver1")
    page = client.get("/driver_logs?date=2026-05-16")
    assert page.status_code == 200
    assert b"Only 1 min from Unknown plant / needs confirmation to Raleigh West" in page.data
    assert b"Open stop - record departure/load before creating the next stop" in page.data


def test_driver_logs_prints_and_eod_create_activity_history(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    log_response = client.post(
        "/new_driving_log",
        data={
            "plant_name": "RE",
            "load_size": "Full",
            "downtime_reason": "",
            "depart_time": "",
        },
        follow_redirects=False,
    )
    assert log_response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        from app.extensions import db

        log = DriverLog.query.filter_by(plant_name="RE").one()
        log.depart_time = "17:45"
        log.dock_wait_minutes = 12
        db.session.commit()

    print_response = client.get("/driver_logs_print")
    assert print_response.status_code == 200
    assert b"Driver Route Sheet" in print_response.data
    assert b"Driver Route Audit Sheet" not in print_response.data
    assert b"5:45pm" in print_response.data
    assert b"Wait 12 min" in print_response.data
    assert b"17:45" not in print_response.data
    assert b"2. Stop Timeline" in print_response.data
    assert b"Stop #" in print_response.data
    assert b"Stop / Movement" in print_response.data
    assert b"3. Plant Legend" in print_response.data
    assert b"4. Signatures" in print_response.data
    assert b"Leg #" not in print_response.data
    assert b"9. Signatures" not in print_response.data
    assert_official_record_output(print_response.data)

    eod_print = client.get("/end_of_day_print")
    assert eod_print.status_code == 200
    assert b"5:45pm" in eod_print.data
    assert b"Wait 12 min" in eod_print.data
    assert b"17:45" not in eod_print.data
    assert_official_record_output(eod_print.data)

    eod_attachment = client.get("/end_of_day_print/attachment")
    assert eod_attachment.status_code == 200
    assert eod_attachment.headers["Content-Type"] == "application/pdf"
    assert b"Wait 12 min" in eod_attachment.data
    assert_official_record_output(eod_attachment.data)

    eod_response = client.post("/submit_end_of_day", follow_redirects=False)
    assert eod_response.status_code == 302

    activity = client.get("/recent_activity")
    assert activity.status_code == 200
    assert b"Driver log submitted" in activity.data
    assert b"Driver logs printed" in activity.data
    assert b"End of day finalized" in activity.data

    unread = client.get("/count_unread").get_json()
    assert unread["action_count"] >= 3
    assert unread["unread_count"] >= unread["action_count"]


def test_driver_logs_page_exposes_selected_date_print_and_pdf_actions(client, app):
    from datetime import date

    selected_date = date(2026, 5, 20)
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("dated_print_driver", "dated-print@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=selected_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time="2026-05-20 21:12:00",
                depart_time="22:00",
            )
        )
        db.session.commit()

    login(client, "dated_print_driver")
    logs_page = client.get(f"/driver_logs?date={selected_date.isoformat()}")
    assert logs_page.status_code == 200
    assert b"driver-ledger-active" in logs_page.data
    assert b"AUDIT LEDGER" in logs_page.data
    assert b"PAST ROUTE" in logs_page.data
    assert b"REPLAY MODE" in logs_page.data
    assert b"LIVE FLOW BOARD" not in logs_page.data
    assert b"md-ledger-board compact-route-map md-flow-board" in logs_page.data
    assert b"md-ledger-row md-flow-row tone-completed" in logs_page.data
    assert b"md-row-code flow-code" not in logs_page.data
    assert b"md-row-detail flow-detail" in logs_page.data
    assert b'<span class="md-row-state">' not in logs_page.data
    assert b"md-row-status flow-status empty status-empty" not in logs_page.data
    assert b"<span>Route</span>" in logs_page.data
    assert b"md-ledger-ticker md-flow-ticker" in logs_page.data
    assert b'content:"["' not in logs_page.data
    assert b"content:'['" not in logs_page.data
    assert b"calc(100% - 8px)" not in logs_page.data
    assert b"calc(100% - 10px)" not in logs_page.data
    assert b"border-left:3px solid rgba(91,157,255" not in logs_page.data
    assert b"border-left:3px solid rgba(255,178,36" not in logs_page.data
    assert b"border-left:3px solid rgba(255,82,71" not in logs_page.data
    assert b"Print Route Record" in logs_page.data
    assert f"/driver_logs_print?date={selected_date.isoformat()}".encode() in logs_page.data
    assert f"/driver_logs_print?date={selected_date.isoformat()}&amp;autoprint=1".encode() in logs_page.data

    print_page = client.get(f"/driver_logs_print?date={selected_date.isoformat()}")
    assert print_page.status_code == 200
    assert b"Raleigh East" in print_page.data
    assert selected_date.isoformat().encode() in print_page.data

    pdf_response = client.get(f"/driver_logs_print/attachment?date={selected_date.isoformat()}")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["Content-Type"] == "application/pdf"
    assert b"DRIVER ROUTE SHEET" in pdf_response.data
    assert b"DRIVER ROUTE AUDIT SHEET" not in pdf_response.data
    assert b"2. Stop Timeline" in pdf_response.data
    assert b"Stop #" in pdf_response.data
    assert b"Leg #" not in pdf_response.data


def test_end_of_day_signature_saves_after_posttrip_and_prints_for_manager(client, app):
    from datetime import date, datetime

    signature = "data:image/png;base64,abc123signature"
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            employee_id="1001",
            department="Plastic Plate",
        )
        create_user("manager1", "manager1@example.com", "management")
        route_date = date.today()
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=route_date,
            shift="1st",
            start_mileage=1000,
        )
        db.session.add(pretrip)
        db.session.flush()
        shift = ShiftRecord(
            user_id=driver.id,
            pretrip_id=pretrip.id,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            total_hours=8.0,
        )
        db.session.add_all([
            shift,
            PostTrip(pretrip_id=pretrip.id, end_mileage=1100, miles_driven=100),
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="Empty",
                depart_time="08:15",
                arrive_time=f"{route_date.isoformat()} 12:00:00",
            ),
        ])
        db.session.commit()
        driver_id = driver.id
        shift_id = shift.id

    login(client, "driver1")
    signature_page = client.get("/end_of_day_summary")
    assert signature_page.status_code == 200
    assert b"pointerdown" in signature_page.data
    assert b"form.addEventListener('submit'" in signature_page.data
    assert b"signatureSection" in signature_page.data
    assert b"showSignatureWarning" in signature_page.data
    assert b"blankSignatureData" in signature_page.data
    assert b'data-no-autosave="true"' in signature_page.data
    assert b"form.submit()" not in signature_page.data
    assert b"Please sign before submitting" not in signature_page.data

    response = client.post(
        "/end_of_day_summary",
        data={"driver_signature": signature},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/driver_logs_print")

    with app.app_context():
        from app.models import ShiftRecord

        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.driver_signature == signature
        assert saved_shift.signature_timestamp is not None

    unsigned = client.post("/end_of_day_summary", data={}, follow_redirects=False)
    assert unsigned.status_code == 302
    assert unsigned.headers["Location"].endswith("/driver_logs_print")

    warning_page = client.get("/end_of_day_summary?signature_required=1")
    assert warning_page.status_code == 200
    assert b"Sign in the Driver Signature box" in warning_page.data
    assert b"swal({ title: \"Warning\"" not in warning_page.data

    driver_print = client.get("/driver_logs_print")
    assert driver_print.status_code == 200
    assert signature.encode() in driver_print.data
    assert b"Not yet signed" not in driver_print.data
    assert b" UTC" not in driver_print.data

    driver_pdf = client.get("/driver_logs_print/attachment")
    assert driver_pdf.status_code == 200
    assert driver_pdf.headers["Content-Type"] == "application/pdf"
    assert b"Driver e-signature captured" in driver_pdf.data

    eod_print = client.get("/end_of_day_print")
    assert eod_print.status_code == 200
    assert signature.encode() in eod_print.data
    assert b" UTC" not in eod_print.data

    eod_pdf = client.get("/end_of_day_print/attachment")
    assert eod_pdf.status_code == 200
    assert eod_pdf.headers["Content-Type"] == "application/pdf"
    assert b"Driver e-signature captured" in eod_pdf.data

    client.get("/logout")
    login(client, "manager1")
    manager_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_print.status_code == 200
    assert signature.encode() in manager_print.data
    assert b"Not yet signed" not in manager_print.data
    assert b" UTC" not in manager_print.data

    manager_pdf = client.get(f"/manager/driver-logs/route-attachment?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_pdf.status_code == 200
    assert manager_pdf.headers["Content-Type"] == "application/pdf"
    assert b"Driver e-signature captured" in manager_pdf.data


def test_end_of_day_can_finalize_without_signature_when_capture_fails(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver2", "driver2@example.com", "driver")
        route_date = date.today()
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                depart_time="17:15",
                arrive_time=f"{route_date.isoformat()} 17:00:00",
            )
        )
        db.session.commit()
        driver_id = driver.id

    login(client, "driver2")
    response = client.post("/end_of_day_summary", data={}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/driver_logs_print")

    with app.app_context():
        from app.models import ActivityEvent, ShiftRecord

        assert ActivityEvent.query.filter_by(user_id=driver_id, category="eod", action="finalized").count() == 1
        assert all(not shift.driver_signature for shift in ShiftRecord.query.filter_by(user_id=driver_id).all())

    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    assert b"Not yet signed" in print_page.data


def test_end_of_day_recovers_signature_from_autosave_draft(client, app):
    from datetime import date

    signature = "data:image/png;base64,recoveredsignature"
    with app.app_context():
        from app.extensions import db
        from app.models import DraftEntry, DriverLog

        driver = create_user("driver3", "driver3@example.com", "driver")
        route_date = date.today()
        draft_key = f"movedefense:draft:v1:{driver.id}:/end_of_day_summary:end-of-day-{driver.id}"
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                depart_time="17:15",
                arrive_time=f"{route_date.isoformat()} 17:00:00",
            ),
            DraftEntry(
                user_id=driver.id,
                draft_key=draft_key,
                path="/end_of_day_summary",
                payload={"driver_signature": {"type": "hidden", "value": signature}},
            ),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "driver3")
    response = client.post("/end_of_day_summary", data={}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/driver_logs_print")

    with app.app_context():
        from app.models import ShiftRecord

        saved_shift = ShiftRecord.query.filter_by(user_id=driver_id).one()
        assert saved_shift.driver_signature == signature
        assert saved_shift.signature_timestamp is not None


def test_end_of_day_signature_submit_ends_open_shift_timer(client, app):
    from datetime import date, datetime, timedelta

    signature = "data:image/png;base64,endshift"
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("shift_sign_driver", "shift-sign@example.com", "driver")
        route_date = date.today()
        pretrip = PreTrip(user_id=driver.id, truck_number="BT-1", pretrip_date=route_date, start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        shift = ShiftRecord(
            user_id=driver.id,
            pretrip_id=pretrip.id,
            start_time=datetime.utcnow() - timedelta(hours=9),
        )
        db.session.add_all([
            shift,
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                depart_time="17:15",
                arrive_time=f"{route_date.isoformat()} 17:00:00",
            ),
        ])
        db.session.commit()
        driver_id = driver.id
        shift_id = shift.id

    login(client, "shift_sign_driver")
    response = client.post(
        "/end_of_day_summary",
        data={"driver_signature": signature},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        from app.models import ShiftRecord

        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.driver_signature == signature
        assert saved_shift.end_time is not None
        assert saved_shift.total_hours >= 8
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 0


def test_pretrip_printout_highlights_defects_and_written_remarks(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import PreTrip

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
        )
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-RED",
            trailer_number="TR-RED",
            pretrip_date=date.today(),
            shift="1st",
            start_mileage=1200,
            cab_doors_windows=True,
            service_brakes=True,
            towed_tires=True,
            damage_report="Air leak under trailer",
        )
        db.session.add(pretrip)
        db.session.commit()
        pretrip_id = pretrip.id

    login(client, "driver1")
    printable = client.get(f"/pretrip_printable/{pretrip_id}")
    assert printable.status_code == 200
    assert printable.data.count(b"defect-marked") >= 3
    assert b"remarks-written" in printable.data
    assert b"Air leak under trailer" in printable.data

    pdf = client.get(f"/pretrip_printable/{pretrip_id}/attachment")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Type"] == "application/pdf"
    assert b"Defects Marked" in pdf.data
    assert b"Air leak under trailer" in pdf.data
    assert b"0.690 0.000 0.125 rg" in pdf.data


def test_manager_can_delete_old_damage_report_test_records(client, app):
    from datetime import datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DamageReport

        driver = create_user("driver1", "driver1@example.com", "driver")
        create_user("manager1", "manager1@example.com", "management")
        old_stamp = datetime.utcnow() - timedelta(days=30)
        report = DamageReport(
            reported_by_id=driver.id,
            truck_number="TEST-1",
            trailer_number="TEST-TR",
            plant_name="RE",
            damage_time=old_stamp,
            created_at=old_stamp,
            stage="before",
            move_reference="old test",
            description="Old damage report test",
            status="submitted",
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    login(client, "manager1")
    review = client.get("/manager/review")
    assert review.status_code == 200
    assert f"/manager/damage-reports/{report_id}/delete".encode() in review.data

    detail = client.get(f"/manager/damage-reports/{report_id}")
    assert detail.status_code == 200
    assert b"Delete Report" in detail.data

    deleted = client.post(
        f"/manager/damage-reports/{report_id}/delete",
        data={"next": "/manager/review"},
        follow_redirects=False,
    )
    assert deleted.status_code == 302
    assert deleted.headers["Location"].endswith("/manager/review")

    with app.app_context():
        from app.models import ActivityEvent, AuditEvent, DamageReport

        assert DamageReport.query.get(report_id) is None
        audit = AuditEvent.query.filter_by(
            target_type="damage_report", target_id=report_id, action="manager_deleted"
        ).one()
        assert "Old damage report test" in audit.before_values
        activity = ActivityEvent.query.filter_by(
            target_type="damage_report", target_id=report_id, action="deleted"
        ).one()
        assert activity.title == "Damage report deleted by manager"


def test_damage_report_edit_delete_submit_and_eod_lock(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")

    new_damage_page = client.get("/damage_reports/new")
    assert new_damage_page.status_code == 200
    assert b'capture="environment"' in new_damage_page.data

    create_response = client.post(
        "/damage_reports/new",
        data={
            "truck_number": "T1",
            "trailer_number": "TR1",
            "plant_name": "RE",
            "stage": "before",
            "move_reference": "Dock 4",
            "description": "Scuffed bumper",
            "photo": (BytesIO(b"damage image"), "damage.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        report = DamageReport.query.filter_by(description="Scuffed bumper").one()
        report_id = report.id
        assert len(report.photos) == 1

    edit_page = client.get(f"/damage_reports/{report_id}/edit")
    assert edit_page.status_code == 200
    assert b'capture="environment"' in edit_page.data

    edit_response = client.post(
        f"/damage_reports/{report_id}/edit",
        data={
            "truck_number": "T2",
            "trailer_number": "TR1",
            "plant_name": "RE",
            "stage": "after",
            "move_reference": "Dock 5",
            "description": "Scuffed bumper updated",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        report = DamageReport.query.get(report_id)
        assert report.truck_number == "T2"
        assert report.description == "Scuffed bumper updated"

    submit_response = client.post(f"/damage_reports/{report_id}/submit", follow_redirects=False)
    assert submit_response.status_code == 302

    delete_submitted = client.post(f"/damage_reports/{report_id}/delete", follow_redirects=False)
    assert delete_submitted.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        report = DamageReport.query.get(report_id)
        assert report is not None
        assert report.status == "submitted"

    second_response = client.post(
        "/damage_reports/new",
        data={
            "truck_number": "T3",
            "trailer_number": "TR2",
            "plant_name": "Helios",
            "stage": "before",
            "move_reference": "Dock 7",
            "description": "Broken crate",
        },
        follow_redirects=False,
    )
    assert second_response.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        second_id = DamageReport.query.filter_by(description="Broken crate").one().id

    assert client.post("/submit_end_of_day", follow_redirects=False).status_code == 302
    locked_delete = client.post(f"/damage_reports/{second_id}/delete", follow_redirects=False)
    assert locked_delete.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        assert DamageReport.query.get(second_id) is not None


def test_plant_transfer_flow_and_eod_includes_transfer(client, app):
    from datetime import date

    transfer_date = date.today().isoformat()

    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    response = client.post(
        "/plant_transfers/new",
        data={
            "transfer_number": "809716",
            "transfer_date": transfer_date,
            "ship_to": "RE",
            "ship_from": "RW",
            "trailer_number": "TR-9",
            "driver_name": "driver1",
            "transfer_time": "13:30",
            "loaded_by": "Loader",
            "part_number_0": "GAUGE-1",
            "quantity_0": "10",
            "skids_0": "1",
            "remarks_0": "Gauge transfer",
            "lp_ids_0": "LP-100 LP-101",
            "part_number_10": "GAUGE-2",
            "quantity_10": "5",
            "skids_10": "1",
            "remarks_10": "Second gauge",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import PlantTransfer

        transfer = PlantTransfer.query.filter_by(transfer_number="809716").one()
        assert transfer.ship_to == "RE"
        assert transfer.ship_from == "RW"
        assert len(transfer.lines) == 2
        assert "LP IDs: LP-100 LP-101" in transfer.lines[0].remarks
        transfer_id = transfer.id

    detail = client.get(f"/plant_transfers/{transfer_id}")
    assert detail.status_code == 200
    assert b"LP-100 LP-101" in detail.data

    printable = client.get(f"/plant_transfers/{transfer_id}/print")
    assert printable.status_code == 200
    assert b"White - DATA INPUT" in printable.data
    assert b"Canary - RECEIVING PLANT" in printable.data
    assert b"Pink - DRIVER" in printable.data
    assert b"Blue - SHIPPING PLANT" in printable.data
    assert b"GAUGE-1" in printable.data
    assert b"1:30pm" in printable.data
    assert b"13:30" not in printable.data
    assert_official_record_output(printable.data)

    attachment = client.get(f"/plant_transfers/{transfer_id}/attachment?copy=blue")
    assert attachment.status_code == 200
    assert attachment.headers["Content-Type"] == "application/pdf"
    assert attachment.headers["Content-Disposition"].startswith("attachment;")
    assert attachment.headers["Content-Disposition"].endswith('.pdf"')
    assert attachment.data.startswith(b"%PDF")
    assert_official_record_output(attachment.data)

    mark_printed = client.post(f"/plant_transfers/{transfer_id}/mark_printed")
    assert mark_printed.status_code == 200
    assert mark_printed.get_json()["ok"] is True

    activity = client.get("/recent_activity")
    assert b"Plant Transfer PDF downloaded" in activity.data
    assert b"Plant Transfer printed" in activity.data

    eod = client.get("/end_of_day_summary")
    assert eod.status_code == 200
    assert b"Today's Plant Transfer" in eod.data
    assert b"809716" in eod.data

    eod_print = client.get("/end_of_day_print")
    assert eod_print.status_code == 200
    assert b"Plant Transfers" in eod_print.data
    assert b"809716" in eod_print.data



def test_driver_mobile_dashboard_renders_real_workflow(client, app):
    from datetime import date, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PlantTransfer, PlantTransferLine, PreTrip, Task

        driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Driver",
            last_name="One",
            department="ST4",
        )
        create_user("manager1", "manager1@example.com", "management")
        task = Task(
            title="RW to KP hot move",
            details="Part P0903110 needs trailer assignment.",
            is_hot=True,
            status="pending",
            assigned_to=driver.id,
        )
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST4",
            trailer_number="TR-2",
            pretrip_date=date.today(),
            shift="1st",
        )
        transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TRX-100",
            transfer_date=date.today(),
            ship_to="KP",
            ship_from="RW",
            trailer_number="TR-9",
            driver_name="Driver One",
            transfer_time="13:30",
        )
        transfer.lines.append(
            PlantTransferLine(line_number=1, side="left", part_number="P0903110")
        )
        past_date = date.today() - timedelta(days=1)
        past_transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TRX-099",
            transfer_date=past_date,
            ship_to="RE",
            ship_from="PC",
            trailer_number="TR-8",
            driver_name="Driver One",
            transfer_time="08:15",
        )
        past_transfer.lines.append(
            PlantTransferLine(
                line_number=1,
                side="left",
                part_number="OLD-PART",
                skids="2",
                quantity="18",
            )
        )
        today_log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="RE",
            load_size="Half",
            arrive_time=f"{date.today().isoformat()} 15:30:00",
        )
        past_log = DriverLog(
            driver_id=driver.id,
            date=past_date,
            plant_name="DC",
            load_size="Full",
            arrive_time=f"{past_date.isoformat()} 20:05:00",
            depart_time="17:45",
        )
        db.session.add_all([task, pretrip, transfer, past_transfer, today_log, past_log])
        db.session.commit()

    login(client, "driver1")
    dashboard_redirect = client.get("/dashboard", follow_redirects=False)
    assert dashboard_redirect.status_code == 302
    assert dashboard_redirect.headers["Location"].endswith("/mobile")

    page = client.get("/mobile")
    assert page.status_code == 200
    assert b"MoveDefense Mobile" in page.data
    assert b"RW to KP hot move" in page.data
    assert page.data.count(b"RW to KP hot move") == 1
    assert b"Part P0903110 needs trailer assignment." in page.data
    assert b"PostTrip Due" not in page.data
    assert b"Logout" in page.data
    assert b"Parts Queue" not in page.data
    assert b"RW to KP" in page.data
    assert b"Ryder Service" in page.data
    assert b"Active Stop Wait" in page.data
    assert b"Raleigh East" in page.data
    assert b"data-active-wait-minutes" in page.data
    assert b"data-active-wait-seconds" in page.data
    assert b"driver-active-wait.js?v=2" in page.data
    assert b"/mobile?flow=depart" in page.data
    assert b"Save Ryder Status" in page.data
    assert b"CEL light" in page.data
    assert b"Need tow" in page.data
    assert b"Headed to Ryder" in page.data
    assert b"Up Next" not in page.data
    assert b"Recent Transfers" not in page.data
    assert b"Previous Reports" not in page.data
    assert b"All history" not in page.data

    history = client.get("/mobile/history")
    assert history.status_code == 200
    assert b"Reports" in history.data
    assert b"Active Stop Wait" in history.data
    assert b"TRX" not in history.data

    day_report = client.get(f"/mobile/history/{past_date.isoformat()}")
    assert day_report.status_code == 200
    assert b"PC to RE" in day_report.data
    assert b"TRX-099" in day_report.data
    assert b"TR-8" in day_report.data
    assert b"OLD-PART" in day_report.data
    assert b"2 skid(s)" in day_report.data
    assert b"qty 18" in day_report.data
    assert b"52nd Street DC" in day_report.data
    assert b"4:05pm" in day_report.data
    assert b"5:45pm" in day_report.data
    assert past_date.isoformat().encode() not in day_report.data
    assert b"17:45" not in day_report.data
    assert b"/edit_driver_log/" not in day_report.data
    assert b"/pickup" not in day_report.data
    assert b"/depart" not in day_report.data
    assert b"/delete" not in day_report.data

    today_report = client.get(f"/mobile/history/{date.today().isoformat()}")
    assert today_report.status_code == 200
    assert b"Raleigh East" in today_report.data
    assert b"Active Stop Wait" in today_report.data
    assert b"Active wait" in today_report.data
    assert b"Edit" in today_report.data
    assert b"Pickup" not in today_report.data
    assert b"Depart / Load" in today_report.data
    assert b"/mobile?flow=depart" in today_report.data
    assert b"Delete" in today_report.data
    assert b"13:30" not in today_report.data

    headed_response = client.post(
        "/mobile/ryder-service",
        data={
            "truck_number": "ST4",
            "issue": "leak",
            "outcome": "headed",
            "notes": "Taking it to Ryder now.",
        },
        follow_redirects=False,
    )
    assert headed_response.status_code == 302

    pending_ryder_page = client.get("/mobile")
    assert b"Ryder timer running" in pending_ryder_page.data
    assert b"Leak" in pending_ryder_page.data

    blocked_log = client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=True,
    )
    assert b"Ryder follow-up required before the next stop" in blocked_log.data

    ryder_response = client.post(
        "/mobile/ryder-service",
        data={
            "truck_number": "ST4",
            "issue": "leak",
            "outcome": "rental",
            "notes": "Left unit at Ryder and took rental R-18.",
            "next": "new_log",
        },
        follow_redirects=False,
    )
    assert ryder_response.status_code == 302
    assert ryder_response.headers["Location"].endswith("/new_driving_log")

    unblocked_log = client.get("/new_driving_log")
    assert b"Ryder follow-up required before the next stop" not in unblocked_log.data

    ryder_page = client.get("/mobile")
    assert b"Rental picked up" in ryder_page.data
    assert b"Leak" in ryder_page.data
    assert b"Ryder time" in ryder_page.data
    assert b"rental R-18" in ryder_page.data

    assert page.data.count(b"Create Driver Log") == 0
    assert b"Record Departure" in page.data
    assert b"Start Shift" not in page.data
    assert b"End Shift" not in page.data



def test_driver_mobile_pages_share_single_five_tab_bottom_nav(client, app):
    with app.app_context():
        create_user(
            "nav_driver",
            "nav-driver@example.com",
            "driver",
            first_name="Nav",
            last_name="Driver",
        )

    login(client, "nav_driver")

    expected_items = [
        "<strong>HM</strong><span>Home</span>",
        "<strong>PT</strong><span>Transfer</span>",
        "<strong>DL</strong><span>Logs</span>",
        "<strong>DR</strong><span>Damage</span>",
        "<strong>PI</strong><span>PreTrip</span>",
    ]
    pages = [
        ("/mobile", "Home"),
        ("/plant_transfers", "Transfer"),
        ("/driver_logs", "Logs"),
        ("/damage_reports", "Damage"),
        ("/new_pretrip", "PreTrip"),
        ("/profile", "Home"),
    ]

    for path, active_label in pages:
        response = client.get(path)
        assert response.status_code == 200
        body = response.data.decode()
        assert body.count('<nav class="md-driver-bottom-nav"') == 1
        nav_start = body.index('<nav class="md-driver-bottom-nav"')
        nav_end = body.index("</nav>", nav_start)
        nav = body[nav_start:nav_end]
        positions = [nav.index(item) for item in expected_items]
        assert positions == sorted(positions)
        assert nav.count('class="md-nav-link active"') == 1
        active_start = nav.index('class="md-nav-link active"')
        active_end = nav.index("</a>", active_start)
        assert f"<span>{active_label}</span>" in nav[active_start:active_end]
        assert "<span>Driver</span>" not in nav
        assert '<nav class="bottom-nav"' not in body
        assert ".bottom-nav" not in body
        assert "side-nav" not in body


def test_completed_posttrip_route_shows_ended_across_driver_and_manager_surfaces(client, app):
    from datetime import date, datetime

    route_date = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("completed_route_driver", "completed-route@example.com", "driver", first_name="Lamar")
        create_user("completed_route_manager", "completed-route-manager@example.com", "management")
        pretrip = PreTrip(user_id=driver.id, truck_number="st4", pretrip_date=route_date, start_mileage=244914)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(PostTrip(pretrip_id=pretrip.id, end_mileage=244951, miles_driven=37))
        rows = [
            ("RE", "13:47", "13:47", "Empty", "Empty", True),
            ("H", "14:04", "14:18", "Empty", "Raleigh East Load + PPL Load", False),
            ("RE", "14:21", "14:25", "Raleigh East Load + PPL Load", "PPL Load", False),
            ("PPL", "15:15", "15:24", "PPL Load", "Empty", True),
            ("PC", "15:28", "17:00", "Empty", "Raleigh East Load", False),
            ("RE", "17:13", "17:38", "Raleigh East Load", "Empty", True),
            ("Ryder", "17:47", "17:52", "Empty", "Empty", True),
            ("PC", "17:57", "18:21", "Empty", "PPL Load", False),
            ("PPL", "18:39", "18:53", "PPL Load", "Empty", True),
            ("RE", "19:05", "20:15", "Empty", "Kraft Plant Load", False),
            ("KP", "20:35", "20:36", "Kraft Plant Load", "Empty", True),
            ("PC", "20:44", "20:45", "Empty", "Empty", True),
            ("RE", "21:12", "22:00", "Empty", "Empty", True),
        ]
        for plant, arrive, depart, cargo_in, cargo_out, no_pickup in rows:
            db.session.add(DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name=plant,
                arrive_time=f"{route_date.isoformat()} {arrive}:00",
                depart_time=depart,
                load_size=cargo_in,
                depart_load_size=cargo_out,
                no_pickup=no_pickup,
            ))
        db.session.commit()
        driver_id = driver.id

    login(client, "completed_route_driver")
    mobile = client.get("/mobile")
    assert mobile.status_code == 200
    assert b"LIVE FLOW BOARD" in mobile.data
    assert b"Route Complete" not in mobile.data
    assert b"Ready To Finalize" in mobile.data
    assert b"here now" not in mobile.data
    assert b"Likely destination" not in mobile.data
    assert b"Source: historical pattern" not in mobile.data
    assert b"Paint Central" in mobile.data
    assert b"Out: No Pickup" in mobile.data

    driver_print = client.get("/driver_logs_print")
    assert driver_print.status_code == 200
    assert b"Route completed / awaiting final review" in driver_print.data
    assert b"Route open / not finalized" not in driver_print.data

    client.get("/logout")
    login(client, "completed_route_manager")
    manager_review = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={route_date.isoformat()}")
    assert manager_review.status_code == 200
    assert b"Route Status:</strong> Completed" in manager_review.data
    assert b"The route is complete and awaiting final review" in manager_review.data
    assert b"still marked open" not in manager_review.data
    assert b"Current Active Stop" not in manager_review.data


def test_mobile_dashboard_route_panel_falls_back_to_latest_route_when_today_is_empty(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One")
        route_date = date.today() - timedelta(days=3)
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST2",
            pretrip_date=route_date,
            start_mileage=379164,
        )
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all(
            [
                PostTrip(
                    pretrip_id=pretrip.id,
                    end_mileage=379202,
                    miles_driven=38,
                    created_at=datetime(2026, 5, 15, 20, 55, 0),
                ),
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="RE",
                    load_size="Empty",
                    arrive_time=f"{route_date.isoformat()} 15:21:00",
                    depart_time="11:21",
                ),
            ]
        )
        db.session.commit()

    login(client, "driver1")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"Last Route" not in page.data
    assert b"REPLAY MODE" in page.data
    assert b"ACTIONS DISABLED" in page.data
    assert b"Last Route Replay" not in page.data
    assert b"Last Route / Route Replay" not in page.data
    assert b"Live route actions are hidden" not in page.data
    assert b'<div class="md-flow-top-actions"' not in page.data
    assert b'data-flow-panel-title="Add Stop"' not in page.data
    assert b"1 stop" in page.data
    assert b"Raleigh East" in page.data
    assert f"/driver_logs?date={route_date.isoformat()}".encode() in page.data
    assert b"No stops logged yet today." not in page.data
    assert b"Start shift with PreTrip" not in page.data


def test_mobile_dashboard_selected_date_renders_route_replay(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("replay_driver", "replay@example.com", "driver", first_name="Replay", last_name="Driver")
        route_date = date(2026, 5, 28)
        db.session.add_all(
            [
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="RE",
                    load_size="Empty",
                    depart_load_size="Plastic West Load",
                    arrive_time="08:00",
                    depart_time="08:15",
                    created_at=datetime(2026, 5, 28, 8, 0),
                ),
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="PW",
                    load_size="Plastic West Load",
                    depart_load_size="Empty",
                    arrive_time="08:30",
                    depart_time="08:45",
                    created_at=datetime(2026, 5, 28, 8, 30),
                ),
            ]
        )
        db.session.commit()

    login(client, "replay_driver")
    page = client.get("/mobile?date=2026-05-28")

    assert page.status_code == 200
    assert b"REPLAY MODE" in page.data
    assert b"ACTIONS DISABLED" in page.data
    assert b"Last Route Replay" not in page.data
    assert b"Last Route / Route Replay" not in page.data
    assert b"Live route actions are hidden" not in page.data
    assert b'<div class="md-flow-top-actions"' not in page.data
    assert b'data-flow-panel-title="Add Stop"' not in page.data
    assert b"Raleigh East" in page.data
    assert b"/driver_logs?date=2026-05-28" in page.data
    assert b"Finalize Route" not in page.data


def test_mobile_dashboard_finalized_route_with_missing_proof_uses_attach_document(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog

        driver = create_user("proof_driver", "proof@example.com", "driver", first_name="Proof", last_name="Driver")
        route_date = date.today()
        db.session.add_all(
            [
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="RE",
                    load_size="Empty",
                    depart_load_size="Plastic West Load",
                    arrive_time="08:00",
                    depart_time="08:15",
                    created_at=datetime(2026, 5, 28, 8, 0),
                ),
                ActivityEvent(
                    user_id=driver.id,
                    category="eod",
                    action="finalized",
                    title="Route finalized",
                    details=f"Route finalized for {route_date}",
                    target_type="end_of_day",
                ),
            ]
        )
        db.session.commit()

    login(client, "proof_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"Attach Document" in page.data
    assert b"Finalize Route" not in page.data


def test_mobile_dashboard_finalized_route_with_proof_hides_finalize(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, PlantTransfer

        driver = create_user("final_done_driver", "final-done@example.com", "driver", first_name="Final", last_name="Done")
        route_date = date.today()
        db.session.add_all(
            [
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="RE",
                    load_size="Empty",
                    depart_load_size="Plastic West Load",
                    arrive_time="08:00",
                    depart_time="08:15",
                    created_at=datetime(2026, 5, 28, 8, 0),
                ),
                PlantTransfer(
                    user_id=driver.id,
                    transfer_date=route_date,
                    ship_from="RE",
                    ship_to="PW",
                    driver_name="Final Done",
                ),
                ActivityEvent(
                    user_id=driver.id,
                    category="eod",
                    action="finalized",
                    title="Route finalized",
                    details=f"Route finalized for {route_date}",
                    target_type="end_of_day",
                ),
            ]
        )
        db.session.commit()

    login(client, "final_done_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"No action needed" in page.data
    assert b"Print Route" in page.data
    assert b"Finalize Route" not in page.data
    assert b"Attach Document" not in page.data


def test_mobile_dashboard_uses_open_shift_route_date_for_progress(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One")
        route_date = date.today() - timedelta(days=1)
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST2",
            pretrip_date=route_date,
            start_mileage=379164,
        )
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all(
            [
                ShiftRecord(
                    user_id=driver.id,
                    pretrip_id=pretrip.id,
                    start_time=datetime.utcnow() - timedelta(hours=4),
                ),
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="KP",
                    load_size="Empty",
                    arrive_time=f"{route_date.isoformat()} 23:45:00",
                ),
            ]
        )
        db.session.commit()

    login(client, "driver1")
    page = client.get("/mobile")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "LIVE FLOW BOARD" in body
    assert "Active Route" not in body
    assert b"1 stop" in page.data
    assert b"Kraft" in page.data
    assert b"PostTrip Due" not in page.data
    assert "Production Flow" not in body
    assert 'data-flow-open-panel="depart"' in body
    assert "data-depart-wizard" in body
    assert body.count('data-flow-panel-title="Add Stop"') <= 1
    assert 'name="next" value="mobile"' in body
    assert "md-flow-work-scrim" in body
    assert "Did you get unloaded?" in body
    assert "driver-active-wait-action" in body
    assert "Depart / Load" in body
    assert "→" in body
    assert "&middot;" in body
    assert "flow-arrow" in body
    assert ".md-flow-ticker-track span::after" in body
    assert "animation: liveTicker 32s linear infinite" in body
    assert ".md-flow-ticker-track span + span { display: inline-flex; }" in body
    assert "animation: none" not in body
    assert "America/Detroit" in body
    assert "hour12: true" in body
    assert "setupFlowAutoScroll" in body
    assert "window.requestAnimationFrame(step)" in body
    assert "openRequestedFlowPanel" in body
    assert "calc(100% - 8px)" not in body
    assert "calc(100% - 10px)" not in body
    assert "border-left: 3px solid rgba(91,157,255" not in body
    assert "border-left: 3px solid rgba(255,178,36" not in body
    assert "border-left: 3px solid rgba(255,82,71" not in body
    assert "content: none!important" in body
    assert ".md-flow-action-tab::before" in body
    assert "animation: actionDotPulse 1.9s ease-in-out infinite" in body
    assert "@keyframes actionDotPulse" in body
    assert "grid-template-columns: 9px max-content" in body
    assert "border: 1px solid rgba(91,157,255,.28)" not in body
    assert "linear-gradient(180deg, rgba(47,109,240,.22)" not in body
    assert "inset 0 0 18px rgba(91,157,255,.04)" not in body
    assert ".md-flow-track::-webkit-scrollbar { display: none; width: 0; height: 0; }" in body
    assert "scrollbar-color: rgba(91,157,255,.34)" not in body
    assert "ROUTE LOGS &nbsp; PLANT TRANSFERS" not in body
    assert "NEEDS DEPARTURE" in body
    assert "&diams;" not in body
    assert ".md-flow-work-card::before" in body
    assert ".flow-status::after" in body
    assert page.data.count(b"PostTrip Due") == 0


def test_mobile_dashboard_shows_posttrip_due_after_route_close_not_as_board_row(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip

        driver = create_user("posttrip_due_driver", "posttrip-due@example.com", "driver")
        db.session.add(PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000))
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                depart_time="08:20",
            )
        )
        db.session.commit()

    login(client, "posttrip_due_driver")
    page = client.get("/mobile")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert b"PostTrip Due" in page.data
    assert "POSTTRIP NEEDED" not in body
    assert "<strong>TRUCK</strong>" not in body


def test_mobile_route_map_fragment_refresh_uses_route_state(client, app):
    from datetime import date

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("fragment_driver", "fragment-driver@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                arrive_time=f"{today.isoformat()} 08:00:00",
            )
        )
        db.session.commit()

    login(client, "fragment_driver")
    fragment = client.get(f"/mobile/route-map-fragment?date={today.isoformat()}")

    assert fragment.status_code == 200
    body = fragment.get_data(as_text=True)
    assert "compact-route-map md-flow-board" in body
    assert "data-route-refresh-url=" in body
    assert "NEEDS DEPARTURE" in body
    assert "ROUTE LOGS &nbsp; PLANT TRANSFERS" not in body
    assert "<html" not in body.lower()


def test_mobile_quick_depart_returns_to_live_board_without_full_depart_form(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("quick_depart_driver", "quick-depart@example.com", "driver", first_name="Quick", last_name="Depart")
        quick_log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="RE",
            load_size="Empty",
            arrive_time="00:01",
        )
        invalid_log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="PW",
            load_size="Empty",
            arrive_time="00:02",
        )
        db.session.add_all([quick_log, invalid_log])
        db.session.commit()
        quick_id = quick_log.id
        invalid_id = invalid_log.id

    login(client, "quick_depart_driver")
    response = client.post(
        f"/driver_logs/{quick_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "no",
            "destination": "",
            "secondary_destination": "",
            "secondary_load_type": "load",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(quick_id).depart_time

    invalid_response = client.post(
        f"/driver_logs/{invalid_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "destination": "",
        },
        follow_redirects=False,
    )

    assert invalid_response.status_code == 302
    assert invalid_response.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(invalid_id).depart_time is None


def test_new_driver_log_uses_today_when_open_shift_route_date_is_stale(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("route_date_log_driver", "route-date-log@example.com", "driver", first_name="Route", last_name="Date")
        today = date.today()
        stale_route_date = today - timedelta(days=1)
        stale_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST2",
            pretrip_date=stale_route_date,
            start_mileage=379164,
        )
        today_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST4",
            pretrip_date=today,
            start_mileage=380000,
        )
        db.session.add_all([stale_pretrip, today_pretrip])
        db.session.flush()
        db.session.add(
            ShiftRecord(
                user_id=driver.id,
                pretrip_id=stale_pretrip.id,
                start_time=datetime.utcnow() - timedelta(hours=20),
            )
        )
        db.session.commit()
        driver_id = driver.id

    login(client, "route_date_log_driver")
    response = client.post(
        "/new_driving_log",
        data={"plant_name": "KP", "load_size": "Empty"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/driver_logs?date={today.isoformat()}")
    with app.app_context():
        saved = DriverLog.query.filter_by(driver_id=driver_id, date=today, plant_name="KP").one()
        assert saved.load_size == "Empty"

    route_page = client.get(f"/driver_logs?date={today.isoformat()}")
    assert route_page.status_code == 200
    assert b"Kraft" in route_page.data


def test_mobile_dashboard_repairs_today_logs_saved_under_old_route_date(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip

        driver = create_user("repair_route_driver", "repair-route@example.com", "driver", first_name="Repair", last_name="Route")
        today = date.today()
        stale_route_date = today - timedelta(days=1)
        db.session.add(
            PreTrip(
                user_id=driver.id,
                truck_number="ST4",
                pretrip_date=today,
                start_mileage=380000,
            )
        )
        drifted_log = DriverLog(
            driver_id=driver.id,
            date=stale_route_date,
            plant_name="KP",
            load_size="Empty",
            arrive_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.session.add(drifted_log)
        db.session.commit()
        driver_id = driver.id
        log_id = drifted_log.id

    login(client, "repair_route_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"Kraft" in page.data
    with app.app_context():
        saved = DriverLog.query.get(log_id)
        assert saved.driver_id == driver_id
        assert saved.date == today


def test_mobile_shift_time_button_ends_shift_and_returns_mobile(client, app):
    from datetime import datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import ShiftRecord

        driver = create_user("driver1", "driver1@example.com", "driver", first_name="Driver", last_name="One")
        shift = ShiftRecord(
            user_id=driver.id,
            pretrip_id=None,
            start_time=datetime.utcnow() - timedelta(hours=2, minutes=15),
        )
        db.session.add(shift)
        db.session.commit()
        driver_id = driver.id
        shift_id = shift.id

    login(client, "driver1")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"End Shift" in page.data
    assert b"/end_shift?next=mobile" in page.data

    response = client.post("/end_shift?next=mobile", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import ActivityEvent, ShiftRecord

        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.end_time is not None
        assert saved_shift.total_hours >= 2
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 0
        assert ActivityEvent.query.filter_by(user_id=driver_id, category="shift", action="ended").count() == 1


def test_mobile_dashboard_shows_truck_maintenance_history_from_previous_posttrips(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        current_driver = create_user(
            "driver1",
            "driver1@example.com",
            "driver",
            first_name="Current",
            last_name="Driver",
        )
        prior_driver = create_user(
            "driver2",
            "driver2@example.com",
            "driver",
            first_name="Prior",
            last_name="Driver",
        )
        other_driver = create_user("driver3", "driver3@example.com", "driver")
        today = date.today()
        prior_date = today - timedelta(days=1)

        current_pretrip = PreTrip(
            user_id=current_driver.id,
            truck_number="ST4",
            pretrip_date=today,
            start_mileage=13000,
        )
        prior_pretrip = PreTrip(
            user_id=prior_driver.id,
            truck_number="ST4",
            pretrip_date=prior_date,
            start_mileage=12000,
        )
        other_pretrip = PreTrip(
            user_id=other_driver.id,
            truck_number="ST5",
            pretrip_date=prior_date,
            start_mileage=8000,
        )
        db.session.add_all([current_pretrip, prior_pretrip, other_pretrip])
        db.session.flush()
        db.session.add_all(
            [
                PostTrip(
                    pretrip_id=prior_pretrip.id,
                    end_mileage=12160,
                    miles_driven=160,
                    remarks="Regen completed and cleared.",
                    created_at=datetime(2026, 5, 17, 21, 30, 0),
                ),
                PostTrip(
                    pretrip_id=other_pretrip.id,
                    end_mileage=8088,
                    miles_driven=88,
                    remarks="Other truck issue should not show.",
                    created_at=datetime(2026, 5, 17, 20, 30, 0),
                ),
                DriverLog(
                    driver_id=prior_driver.id,
                    date=prior_date,
                    plant_name="RW",
                    load_size="Empty",
                    arrive_time=f"{prior_date.isoformat()} 16:30:00",
                    fuel=True,
                    fuel_mileage=12050,
                ),
                DriverLog(
                    driver_id=prior_driver.id,
                    date=prior_date,
                    plant_name="DC",
                    load_size="Empty",
                    arrive_time=f"{prior_date.isoformat()} 17:00:00",
                    maintenance=True,
                    downtime_reason="Truck issue: Truck regen: forced regen completed",
                    fuel_mileage=12080,
                ),
                DriverLog(
                    driver_id=other_driver.id,
                    date=prior_date,
                    plant_name="RE",
                    load_size="Empty",
                    arrive_time=f"{prior_date.isoformat()} 18:00:00",
                    maintenance=True,
                    downtime_reason="Truck issue: Leak: other truck",
                    fuel_mileage=8010,
                ),
            ]
        )
        db.session.commit()

    login(client, "driver1")

    dashboard = client.get("/mobile")
    assert dashboard.status_code == 200
    assert b"Truck Maintenance History" in dashboard.data
    assert b"Truck ST4" in dashboard.data
    assert b"Prior Driver" in dashboard.data
    assert b"Truck regen: forced regen completed" in dashboard.data
    assert b"12,080 mi" in dashboard.data
    assert b"12,050 mi" in dashboard.data
    assert b"Closed on PostTrip" in dashboard.data
    assert b'target="_blank"' in dashboard.data
    assert b"Other truck issue should not show" not in dashboard.data

    detail = client.get("/truck-maintenance-history?truck_number=ST4")
    assert detail.status_code == 200
    assert b"Issues Opened / Closed" in detail.data
    assert b"Regen" in detail.data
    assert b"Fuel Stops" in detail.data
    assert b"Regen completed and cleared." in detail.data
    assert b"Other truck issue should not show" not in detail.data


def test_knowledge_base_uses_shared_app_shell(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    page = client.get("/knowledge_base")
    assert page.status_code == 200
    assert b"Knowledge Base" in page.data
    assert b"MoveDefense - Dynamic" not in page.data
    assert b"openPanelBtn" not in page.data



def test_manager_trim_dashboard_removed_and_live_dispatch_filters_driver(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user(
            "trimdriver",
            "trimdriver@example.com",
            "driver",
            first_name="Trim",
            last_name="Driver",
            department="Trim DC",
            employee_id="T-77",
        )
        create_user("manager1", "manager1@example.com", "management")
        log = DriverLog(
            driver_id=driver.id,
            date=date.today(),
            plant_name="Trim DC",
            load_size="Full",
            arrive_time="2026-05-13 12:00:00",
        )
        db.session.add(log)
        db.session.commit()
        driver_id = driver.id

    login(client, "manager1")
    page = client.get("/manager/trim-dashboard", follow_redirects=False)
    assert page.status_code == 302
    assert page.headers["Location"].endswith("/manager/dashboard")

    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}")
    assert dashboard.status_code == 200
    assert b"Trim Dashboard" not in dashboard.data
    assert b"Live Routes &amp; Stops" in dashboard.data
    assert b"Trim DC" in dashboard.data
    assert b"Stop 1" in dashboard.data


def test_active_stop_is_current_not_missing_departure(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("active_pc", "active-pc@example.com", "driver")
        create_user("manager_active_pc", "manager-active-pc@example.com", "management")
        route_date = date.today()
        db.session.add(DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time="08:00",
            created_at=datetime(2026, 5, 20, 8, 0),
        ))
        db.session.commit()
        driver_id = driver.id

    login(client, "manager_active_pc")
    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}&focus=routes")
    assert dashboard.status_code == 200
    assert b"Current Active Stop" in dashboard.data
    assert b"Missing Departure" not in dashboard.data
    assert b"Missing time" not in dashboard.data

    route_review = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_review.status_code == 200
    assert b"Current Active Stop" in route_review.data
    assert b"Awaiting load-out/departure" in route_review.data
    assert b"Pickup estimate:" in route_review.data


def test_finalized_route_with_missing_departure_requires_correction(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog

        driver = create_user("final_missing", "final-missing@example.com", "driver")
        create_user("manager_final_missing", "manager-final-missing@example.com", "management")
        route_date = date.today()
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="PC",
                load_size="Empty",
                arrive_time="08:00",
                created_at=datetime(2026, 5, 20, 8, 0),
            ),
            ActivityEvent(
                user_id=driver.id,
                category="eod",
                action="finalized",
                title="Route finalized",
                details=f"Route finalized for {route_date}",
                target_type="end_of_day",
            ),
        ])
        db.session.commit()
        driver_id = driver.id

    login(client, "manager_final_missing")
    route_review = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_review.status_code == 200
    assert b"Missing Departure" in route_review.data
    assert b"Correction required" in route_review.data


def test_route_report_excludes_same_plant_scan_from_other_route(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PartScanEvent

        current_driver = create_user("scan_current", "scan-current@example.com", "driver")
        other_driver = create_user("scan_other", "scan-other@example.com", "driver")
        create_user("scan_manager", "scan-manager@example.com", "management")
        route_date = date.today()
        current_log = DriverLog(
            driver_id=current_driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time="08:00",
            depart_time="08:30",
            created_at=datetime(2026, 5, 20, 8, 0),
        )
        old_log = DriverLog(
            driver_id=other_driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time="09:00",
            depart_time="09:30",
            created_at=datetime(2026, 5, 20, 9, 0),
        )
        db.session.add_all([current_log, old_log])
        db.session.flush()
        db.session.add(PartScanEvent(
            raw_value="OLD-PC-SCAN",
            normalized_value="OLD-PC-SCAN",
            stop_id=old_log.id,
            driver_log_id=old_log.id,
            driver_id=other_driver.id,
            plant_id="PC",
            scan_context="manual_entry",
            validation_status="needs_review",
        ))
        db.session.commit()
        driver_id = current_driver.id

    login(client, "scan_manager")
    page = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert page.status_code == 200
    assert b"OLD-PC-SCAN" not in page.data


def test_repeated_plant_and_truck_issues_roll_up_to_cases(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("case_driver", "case-driver@example.com", "driver")
        create_user("case_manager", "case-manager@example.com", "management")
        today = date.today()
        yesterday = today - timedelta(days=1 if today.weekday() > 0 else 0)
        db.session.add_all([
            DriverLog(driver_id=driver.id, date=today, plant_name="PC", load_size="Empty", arrive_time="08:00", depart_time="08:20", dock_wait_minutes=59, created_at=datetime(2026, 5, 20, 8, 0)),
            DriverLog(driver_id=driver.id, date=today, plant_name="PC", load_size="Empty", arrive_time="09:00", depart_time="09:20", dock_wait_minutes=42, created_at=datetime(2026, 5, 20, 9, 0)),
            DriverLog(driver_id=driver.id, date=today, plant_name="PC", load_size="Empty", arrive_time="10:00", depart_time="10:20", dock_wait_minutes=25, created_at=datetime(2026, 5, 20, 10, 0)),
            DriverLog(driver_id=driver.id, date=today, plant_name="RE", load_size="Empty", arrive_time="11:00", depart_time="11:30", maintenance=True, downtime_reason="Truck issue: CEL light", created_at=datetime(2026, 5, 20, 11, 0)),
            DriverLog(driver_id=driver.id, date=yesterday, plant_name="RE", load_size="Empty", arrive_time="11:00", depart_time="11:30", maintenance=True, downtime_reason="Truck issue: Belt issue", created_at=datetime(2026, 5, 19, 11, 0)),
        ])
        pretrip_today = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="st4")
        pretrip_yesterday = PreTrip(user_id=driver.id, pretrip_date=yesterday, truck_number="st4")
        db.session.add_all([pretrip_today, pretrip_yesterday])
        db.session.flush()
        db.session.add_all([
            PostTrip(pretrip_id=pretrip_today.id, end_mileage=1010),
            PostTrip(pretrip_id=pretrip_yesterday.id, end_mileage=1000),
        ])
        db.session.commit()

    login(client, "case_manager")
    page = client.get("/manager/review")
    assert page.status_code == 200
    assert b"Paint Central delay pattern today" in page.data
    assert b"Paint Central has 3 delayed stops today" in page.data
    assert b"Truck st4 has 2 related maintenance reports this week" in page.data



def test_pickup_origin_stop_roles_gate_plant_timing_samples(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog
        from app.services.load_state import build_driver_log_route_context, stop_role_details
        from app.services.plant_time import stop_time_sample

        driver = create_user("role_driver", "role-driver@example.com", "driver")
        route_date = date(2026, 5, 20)
        logs = [
            DriverLog(driver_id=driver.id, date=route_date, plant_name="H", load_size="Empty", depart_load_size="Raleigh East Load", secondary_load="PPL Load", arrive_time="08:00", depart_time="08:20", created_at=datetime(2026, 5, 20, 8, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="PPL Load", arrive_time="08:30", depart_time="08:45", created_at=datetime(2026, 5, 20, 8, 30)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PPL", load_size="PPL Load", depart_load_size="Empty", no_pickup=True, arrive_time="09:00", depart_time="09:15", created_at=datetime(2026, 5, 20, 9, 0)),
        ]
        db.session.add_all(logs)
        db.session.commit()
        routes = build_driver_log_route_context(logs)

        helios = stop_role_details(logs[0], routes[logs[0].id])
        raleigh = stop_role_details(logs[1], routes[logs[1].id])
        ppl = stop_role_details(logs[2], routes[logs[2].id])

        assert helios["stop_role"] == "pickup_origin"
        assert set(helios["cargo_added"]) == {"Raleigh East Load", "PPL Load"}
        assert raleigh["stop_role"] == "multi_stop_drop"
        assert ppl["stop_role"] == "drop_only"
        assert stop_time_sample(logs[0], route=routes[logs[0].id])["included"] is True
        assert stop_time_sample(logs[1], route=routes[logs[1].id])["included"] is False
        assert stop_time_sample(logs[2], route=routes[logs[2].id])["included"] is False


def test_edit_departed_stop_can_clear_departure_cargo_and_sync_current_stop(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("kp_edit_driver", "kp-edit@example.com", "driver")
        route_date = date.today()
        raleigh = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Kraft Plant Load",
            arrive_time="19:05",
            depart_time="20:15",
            created_at=datetime(2026, 5, 20, 19, 5),
        )
        kraft = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Kraft Plant Load",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time="20:35",
            depart_time="20:36",
            created_at=datetime(2026, 5, 20, 20, 35),
        )
        paint_central = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Kraft Plant Load",
            depart_load_size="Kraft Plant Load",
            arrive_time="20:44",
            depart_time="20:45",
            created_at=datetime(2026, 5, 20, 20, 44),
        )
        current_re = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Kraft Plant Load",
            arrive_time="21:12",
            created_at=datetime(2026, 5, 20, 21, 12),
        )
        db.session.add_all([raleigh, kraft, paint_central, current_re])
        db.session.commit()
        paint_id = paint_central.id
        current_id = current_re.id

    login(client, "kp_edit_driver")
    response = client.post(
        f"/edit_driver_log/{paint_id}",
        data={
            "plant_name": "PC",
            "load_size": "Empty",
            "departure_destination": "",
            "secondary_departure_dest": "",
            "secondary_departure_type": "load",
            "arrive_time": "8:44pm",
            "depart_time": "8:45pm",
            "edit_reason": "corrected stale KP cargo",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        paint = DriverLog.query.get(paint_id)
        current = DriverLog.query.get(current_id)
        assert paint.load_size == "Empty"
        assert paint.depart_load_size == "Empty"
        assert paint.no_pickup is True
        assert current.load_size == "Empty"
        assert current.secondary_load is None


def test_no_pickup_correction_syncs_next_open_stop_arrival_cargo(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.blueprints.driver.routes import _sync_next_open_stop_arrival_cargo
        from app.extensions import db
        from app.models import DriverLog
        from app.services.load_state import build_driver_log_route_context

        driver = create_user("kp_sync_driver", "kp-sync@example.com", "driver")
        route_date = date(2026, 5, 20)
        raleigh = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Kraft Plant Load",
            arrive_time="19:05",
            depart_time="20:15",
            hot_parts=True,
            part_number="P3503210",
            created_at=datetime(2026, 5, 20, 19, 5),
        )
        kraft = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Kraft Plant Load",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time="20:35",
            depart_time="20:36",
            created_at=datetime(2026, 5, 20, 20, 35),
        )
        paint_central = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Kraft Plant Load",
            arrive_time="20:44",
            created_at=datetime(2026, 5, 20, 20, 44),
        )
        db.session.add_all([raleigh, kraft, paint_central])
        db.session.commit()

        changed = _sync_next_open_stop_arrival_cargo(kraft)
        assert changed.id == paint_central.id
        assert paint_central.load_size == "Empty"
        assert paint_central.secondary_load is None

        routes = build_driver_log_route_context([raleigh, kraft, paint_central])
        assert routes[paint_central.id]["arrive_cargo_desc"] == "Empty"
        assert routes[paint_central.id]["after_arrival_primary"] == "Empty"


def test_route_context_golden_route_current_open_stop_is_not_final_or_missing(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord
        from app.services.route_context import build_route_context

        driver = create_user("lamar_context", "lamar-context@example.com", "driver", first_name="Lamar")
        route_date = date(2026, 5, 20)
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st4", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime(2026, 5, 20, 7, 0)))
        logs = [
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Empty", depart_load_size="Empty", no_pickup=True, arrive_time="08:00", depart_time="08:10", created_at=datetime(2026, 5, 20, 8, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="H", load_size="Empty", depart_load_size="Raleigh East Load", secondary_load="PPL Load", arrive_time="08:20", depart_time="08:40", created_at=datetime(2026, 5, 20, 8, 20)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="PPL Load", arrive_time="09:00", depart_time="09:10", created_at=datetime(2026, 5, 20, 9, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PPL", load_size="PPL Load", depart_load_size="Empty", no_pickup=True, arrive_time="09:30", depart_time="09:40", created_at=datetime(2026, 5, 20, 9, 30)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PC", load_size="Empty", depart_load_size="Raleigh East Load", arrive_time="10:00", depart_time="10:20", created_at=datetime(2026, 5, 20, 10, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Raleigh East Load", depart_load_size="Empty", no_pickup=True, arrive_time="10:45", depart_time="10:55", created_at=datetime(2026, 5, 20, 10, 45)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RW", load_size="Empty", depart_load_size="Empty", no_pickup=True, maintenance=True, arrive_time="11:10", depart_time="11:20", created_at=datetime(2026, 5, 20, 11, 10)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PC", load_size="Empty", depart_load_size="PPL Load", arrive_time="12:00", depart_time="12:20", created_at=datetime(2026, 5, 20, 12, 0)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="PPL", load_size="PPL Load", depart_load_size="Empty", no_pickup=True, arrive_time="12:40", depart_time="12:50", created_at=datetime(2026, 5, 20, 12, 40)),
            DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Empty", arrive_time="2026-05-20 23:05:00", created_at=datetime(2026, 5, 20, 23, 5)),
        ]
        db.session.add_all(logs)
        db.session.commit()

        snapshot = build_route_context(driver_id=driver.id, route_date=route_date, truck_id="st4")
        assert snapshot.route_status == "active"
        assert snapshot.current_stop.id == logs[-1].id
        assert snapshot.current_stop_status == "current"
        assert snapshot.current_activity_label == "Awaiting departure / load intent"
        assert snapshot.previous_cargo_cycle_status == "complete"
        assert snapshot.current_cargo["cargo_display"] == "Empty"
        assert snapshot.next_load_intent_status == "unknown"
        assert snapshot.posttrip_status == "not due until route close"
        assert snapshot.signature_status == "pending route close"
        assert snapshot.approval_status == "final approval not available while route active"
        current_row = snapshot.rows[-1]
        assert current_row["status"] == "Current"
        assert current_row["stop_role"] == "current_open"
        assert "Missing Departure" not in {row["status"] for row in snapshot.rows if row["log_id"] == logs[-1].id}


def test_current_open_stop_wording_parity_across_rendered_surfaces(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("render_context_driver", "render-context@example.com", "driver", first_name="Lamar")
        create_user("render_context_manager", "render-context-manager@example.com", "management")
        route_date = date.today()
        pretrip = PreTrip(user_id=driver.id, pretrip_date=route_date, truck_number="st4", start_mileage=1000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()))
        db.session.add(DriverLog(driver_id=driver.id, date=route_date, plant_name="RE", load_size="Empty", arrive_time=f"{route_date.isoformat()} 19:05:00", created_at=datetime.utcnow()))
        db.session.commit()
        driver_id = driver.id

    login(client, "render_context_driver")
    mobile = client.get("/mobile")
    assert mobile.status_code == 200
    assert b"Record Departure" in mobile.data
    assert b"Final Location" not in mobile.data
    assert b"forecast" not in mobile.data.lower()
    client.get("/logout")

    login(client, "render_context_manager")
    manager = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={route_date.isoformat()}")
    assert manager.status_code == 200
    assert b"Current Active Stop" in manager.data
    assert b"Final Location" not in manager.data
    assert b"forecast" not in manager.data.lower()
    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}&focus=routes")
    assert dashboard.status_code == 200
    assert b"Current Active Stop" in dashboard.data
    assert b"Missing Departure" not in dashboard.data
    assert b"forecast" not in dashboard.data.lower()

    debug = client.get(f"/debug/route-context/driver:{driver_id}:date:{route_date.isoformat()}")
    assert debug.status_code == 200
    payload = debug.get_json()
    assert payload["route_status"] == "active"
    assert payload["current_stop_status"] == "current"
    assert payload["route_id"].startswith(f"driver:{driver_id}:date:{route_date.isoformat()}:truck:st4")
    assert payload["rows"][-1]["status"] == "Current"

    client.get("/logout")
    login(client, "render_context_driver")
    denied_debug = client.get(f"/debug/route-context/driver:{driver_id}:date:{route_date.isoformat()}")
    assert denied_debug.status_code == 404


def test_manager_review_queue_lists_and_resolves_flagged_stop(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, ExceptionEvent

        manager = create_user(
            "review_manager", "review_manager@example.com", role="management",
            first_name="Reggie", last_name="Manager",
        )
        driver = create_user(
            "review_driver", "review_driver@example.com",
            first_name="Dana", last_name="Driver",
        )
        manager_id = manager.id
        driver_id = driver.id
        route_date = date.today()

        log = DriverLog(
            driver_id=driver_id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            depart_load_size="Raleigh East Load",
            arrive_time="08:00",
            depart_time="08:30",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

        # Driver flags the stop for manager review (the contract event).
        db.session.add(ExceptionEvent(
            event_type="manager_review_requested",
            severity="medium",
            stop_id=log_id,
            driver_log_id=log_id,
            driver_id=driver_id,
            plant_name="KP",
            event_date=route_date,
            summary="Driver requested manager review",
            details="Skid looked unbalanced before departure.",
        ))
        db.session.commit()

    login(client, "review_manager")

    # 1) The flagged stop appears in the dedicated review queue.
    queue = client.get("/manager/reviews")
    assert queue.status_code == 200
    assert b"Stops Awaiting Manager Review" in queue.data
    assert b"Skid looked unbalanced before departure." in queue.data
    assert b"Dana Driver" in queue.data
    # Cargo arrived -> departed is shown.
    assert b"Empty" in queue.data
    assert b"Raleigh East Load" in queue.data

    # Pending-review count surfaces on the manager dashboard as a badge.
    dashboard = client.get("/manager/dashboard")
    assert dashboard.status_code == 200
    assert b"Pending Reviews" in dashboard.data

    # 2) Resolving creates a manager_review_resolved event.
    resolved = client.post(
        f"/manager/reviews/{log_id}/resolve",
        data={"note": "Checked with driver; load was fine."},
        follow_redirects=True,
    )
    assert resolved.status_code == 200

    with app.app_context():
        from app.models import ExceptionEvent

        resolved_events = ExceptionEvent.query.filter_by(
            event_type="manager_review_resolved", stop_id=log_id,
        ).all()
        assert len(resolved_events) == 1
        event = resolved_events[0]
        assert event.driver_log_id == log_id
        assert event.driver_id == manager_id
        assert event.summary == "Manager resolved review"
        assert event.details == "Checked with driver; load was fine."

    # 3) After resolving, the stop is gone from the queue.
    queue_after = client.get("/manager/reviews")
    assert queue_after.status_code == 200
    assert b"Skid looked unbalanced before departure." not in queue_after.data
    assert b"No stops are awaiting manager review" in queue_after.data


def test_manager_review_resolve_requires_management_role(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, ExceptionEvent

        create_user("rq_manager", "rq_manager@example.com", role="management")
        driver = create_user("rq_driver", "rq_driver@example.com")
        driver_id = driver.id
        route_date = date.today()

        log = DriverLog(
            driver_id=driver_id, date=route_date, plant_name="RE",
            load_size="Empty", depart_load_size="Empty",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        db.session.add(ExceptionEvent(
            event_type="manager_review_requested", severity="medium",
            stop_id=log_id, driver_log_id=log_id, driver_id=driver_id,
            plant_name="RE", event_date=route_date,
            summary="Driver requested manager review",
        ))
        db.session.commit()

    # A driver may not reach the manager-gated resolve endpoint; the manager
    # before_request bounces them to login with the management role required.
    login(client, "rq_driver")
    denied = client.post(f"/manager/reviews/{log_id}/resolve", follow_redirects=False)
    assert denied.status_code in (301, 302)
    location = denied.headers.get("Location", "")
    assert "/login" in location
    assert "required_role=management" in location

    with app.app_context():
        from app.models import ExceptionEvent

        assert ExceptionEvent.query.filter_by(
            event_type="manager_review_resolved", stop_id=log_id,
        ).count() == 0
