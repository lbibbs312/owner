from io import BytesIO
import os
import re
from urllib.parse import parse_qs, urlsplit

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


def allow_registration(client, **overrides):
    checkout = {
        "session_id": "cs_test_verified",
        "plan_key": "solo-driver",
        "plan_name": "Solo Driver",
        "customer": "cus_test",
        "customer_email": "",
    }
    checkout.update(overrides)
    with client.session_transaction() as sess:
        sess["registration_checkout"] = checkout


def assert_login_redirect(response, next_value, required_role):
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/login?")
    parsed = urlsplit(location)
    params = parse_qs(parsed.query)
    assert params["next"] == [next_value]
    assert params["required_role"] == [required_role]


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
    assert (
        b"Document No:" in data
        or b"Route Sheet No:" in data
        or b"Driver Log No:" in data
    )
    assert b"Generated:" in data
    for phrase in BANNED_PRINT_PHRASES:
        assert phrase not in data


def assert_driver_route_sheet_output(data):
    assert_official_record_output(data)
    lowered = data.lower()
    assert b"audit" not in lowered
    assert b"Transit Cargo" not in data
    # Both the HTML log sheet and the PDF now use the combined DRIVER LOG SHEET
    # columns (Time / Wait, Load Flow), not the legacy In Truck / Out Truck split.
    assert b"DRIVER LOG SHEET" in data
    assert b"Time / Wait" in data
    assert b"Load Flow" in data
    assert b"In Truck" not in data
    assert b"Out Truck" not in data
    assert b"Manager and Reviewer Signature" in data
    assert b"Manager / Auditor" not in data


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


def test_public_registration_requires_verified_checkout(client, app):
    response = client.get("/register", follow_redirects=False)

    assert response.status_code == 403
    assert b"Checkout required" in response.data

    post_response = client.post(
        "/register",
        data={
            "username": "driver_unpaid",
            "email": "driver-unpaid@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "driver",
        },
        follow_redirects=False,
    )

    assert post_response.status_code == 403
    assert b"Checkout required" in post_response.data
    with app.app_context():
        from app.models import User

        assert User.query.filter_by(username="driver_unpaid").first() is None


def test_public_registration_does_not_offer_manager_role(client):
    allow_registration(client)

    response = client.get("/register")

    assert response.status_code == 200
    assert b"Management" not in response.data
    assert b"Manager PIN" not in response.data
    assert b'value="driver"' in response.data


def test_public_registration_forces_driver_role(client, app):
    allow_registration(client)

    response = client.post(
        "/register",
        data={
            "username": "driver1",
            "email": "driver1@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "management",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app.app_context():
        from app.models import User

        user = User.query.filter_by(username="driver1").one()
        assert user.role == "driver"


def test_registration_email_must_match_checkout_email(client, app):
    allow_registration(client, customer_email="paid@example.com")

    response = client.post(
        "/register",
        data={
            "username": "driver_mismatch",
            "email": "other@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "driver",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Use the same email address from checkout" in response.data
    with app.app_context():
        from app.models import User

        assert User.query.filter_by(username="driver_mismatch").first() is None


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


def assert_login_page_is_standalone(data, subtitle):
    assert b"<title>MoveDefense Sign In</title>" in data
    assert b"Account Access" in data
    assert b"<h1>Sign In</h1>" in data
    assert b"<h2>Account Details</h2>" in data
    assert subtitle in data
    assert b"MoveDefense Access" not in data
    assert b"Operations Sign In" not in data
    assert b"OPERATIONS SIGN IN" not in data.upper()
    assert b"NEEDS REVIEW" not in data.upper()
    assert b"Driver credentials required" not in data
    assert b"md-shell" not in data
    assert b"_driver_active_wait_banner" not in data
    assert b"md-driver-bottom-nav" not in data
    assert b"compact-route-map" not in data
    assert b"LIVE FLOW BOARD" not in data
    assert b"navbar" not in data
    assert b"hamburger" not in data.lower()
    assert b"sidebar" not in data.lower()
    assert data.count(b'href="/#pricing"') == 1
    assert b'href="/register"' not in data
    assert_login_page_has_responsive_auth_guards(data)


def assert_login_page_has_responsive_auth_guards(data):
    compact = re.sub(rb"\s+", b"", data)
    assert b"box-sizing:border-box" in compact
    assert compact.count(b"overflow-x:hidden") >= 3
    assert b"max-width:100%" in compact
    assert b".md-auth-wrap{width:100%;max-width:440px" in compact
    assert b"grid-template-columns" not in data
    assert b"position:absolute" not in compact
    css_without_text_transform = re.sub(rb"text-transform:[^;]+;", b"", compact)
    assert b"transform:" not in css_without_text_transform


@pytest.mark.parametrize(
    ("path", "subtitle"),
    [
        ("/login", b"Sign in to continue."),
        ("/login?next=/mobile&required_role=driver", b"Driver access required."),
        ("/login?next=/reports&required_role=driver", b"Driver access required."),
    ],
)
def test_login_pages_use_standalone_auth_layout(client, path, subtitle):
    login_page = client.get(path)
    assert login_page.status_code == 200
    assert_login_page_is_standalone(login_page.data, subtitle)


def test_driver_auth_redirect_uses_sign_in_required_language(client):
    response = client.get("/mobile", follow_redirects=True)
    assert response.status_code == 200
    assert b"SIGN IN REQUIRED" in response.data
    assert b"Driver access required. Sign in to continue." in response.data
    assert_login_page_is_standalone(response.data, b"Driver access required.")


def test_register_page_uses_movedefense_shell(client):
    allow_registration(client)

    register_page = client.get("/register")
    assert register_page.status_code == 200
    assert b"md-shell" in register_page.data
    assert b"MOVEDEFENSE SETUP" in register_page.data
    assert b"Create Access" in register_page.data
    assert b"checkout you just completed" in register_page.data
    assert b"Required only for manager accounts." not in register_page.data
    assert b"Manager PIN" not in register_page.data


def test_unauthenticated_auth_errors_render_flash_messages(client, monkeypatch):
    blocked_response = client.post(
        "/register",
        data={
            "username": "driver_unpaid_visible",
            "email": "driver-unpaid-visible@example.com",
            "password": "password1",
            "confirm_password": "password1",
            "role": "driver",
        },
        follow_redirects=True,
    )
    assert blocked_response.status_code == 403
    assert b"Complete checkout before creating a MoveDefense account." in blocked_response.data
    assert blocked_response.data.count(b"Complete checkout before creating a MoveDefense account.") == 1

    login_response = client.post(
        "/login",
        data={"login_name": "missing-user", "password": "bad-password"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert b"Invalid credentials." in login_response.data
    assert login_response.data.count(b"Invalid credentials.") == 1


def test_registration_validation_errors_render_inline_feedback(client, monkeypatch):
    monkeypatch.setenv("MANAGER_REGISTRATION_PIN", "2468")
    allow_registration(client)

    response = client.post(
        "/register",
        data={
            "username": "mgr_bad_form",
            "email": "not-an-email",
            "password": "short",
            "confirm_password": "different",
            "role": "driver",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"CHECK REQUIRED FIELDS" in response.data
    assert b"Review the highlighted fields and try again." in response.data
    assert b"Check Required Fields" in response.data
    assert b"Email:" in response.data
    assert b"Invalid email address." in response.data
    assert b"Confirm Password:" in response.data
    assert b"Field must be equal to password." in response.data
    assert b'id="email-errors"' in response.data
    assert b"is-invalid" in response.data


def test_login_validation_errors_render_inline_feedback(client):
    response = client.post(
        "/login",
        data={"login_name": "", "password": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"CHECK REQUIRED FIELDS" in response.data
    assert b"Username or Email:" in response.data
    assert b"Password:" in response.data
    assert b"This field is required." in response.data
    assert b'id="login_name-errors"' in response.data


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
    allow_registration(client)

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


def test_onesignal_worker_serves_nested_static_asset(client):
    response = client.get("/OneSignalSDKWorker.js")

    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert b"OneSignalSDK.sw.js" in response.data


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


def test_logged_out_reports_and_manager_dashboard_redirect_to_role_login(client):
    assert_login_redirect(
        client.get("/reports", follow_redirects=False),
        "/reports",
        "driver",
    )
    assert_login_redirect(
        client.get("/reports?tab=recent", follow_redirects=False),
        "/reports?tab=recent",
        "driver",
    )
    assert_login_redirect(
        client.get("/manager/dashboard", follow_redirects=False),
        "/manager/dashboard",
        "management",
    )


def test_logout_clears_driver_session_and_protects_mobile(client, app):
    with app.app_context():
        create_user("logout_driver", "logout-driver@example.com", "driver")

    login(client, "logout_driver")
    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)

    assert mobile.status_code == 200
    assert 'href="/logout">Logout</a>' in body
    assert ".board-only-shell .topbar," not in body
    assert ".logout-link { display: none; }" not in body

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "_user_id" not in sess
        assert "driver_user_id" not in sess
        assert "management_user_id" not in sess

    assert_login_redirect(
        client.get("/mobile", follow_redirects=False),
        "/mobile",
        "driver",
    )


def test_direct_messages_with_inbox_render_without_dead_reply_endpoint(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import DirectMessage

        sender = create_user("dm_sender", "dm-sender@example.com", "driver")
        receiver = create_user("dm_receiver", "dm-receiver@example.com", "driver")
        db.session.add(
            DirectMessage(
                sender_id=sender.id,
                receiver_id=receiver.id,
                content="Bring packet to dispatch.",
            )
        )
        db.session.commit()

    login(client, "dm_receiver")
    response = client.get("/direct_messages")

    assert response.status_code == 200
    assert b"Bring packet to dispatch." in response.data
    assert b"reply_dm" not in response.data


def test_socketio_rejects_anonymous_clients(client, app):
    from app.extensions import socketio

    socket_client = socketio.test_client(app, flask_test_client=client)

    assert not socket_client.is_connected()


def test_socketio_accepts_authenticated_global_room_only(client, app):
    with app.app_context():
        user = create_user("socket_driver", "socket-driver@example.com", "driver")
        user_id = user.id

    login(client, "socket_driver")

    from app.extensions import socketio

    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()

    socket_client.emit("chat_message", {"content": "Global check", "room": "global"})
    socket_client.emit("join", {"room": "dispatch"})
    socket_client.emit("chat_message", {"content": "Dispatch leak", "room": "dispatch"})

    received_events = socket_client.get_received()
    assert any(event["name"] == "chat_error" for event in received_events)
    with app.app_context():
        from app.models import ChatMessage

        global_message = ChatMessage.query.filter_by(
            user_id=user_id,
            room="global",
            content="Global check",
        ).one()
        assert global_message.content == "Global check"
        assert ChatMessage.query.filter_by(room="dispatch").count() == 0


def test_detroit_time_display_uses_12_hour_local_time(client, app):
    from datetime import datetime

    with app.app_context():
        from app.extensions import db
        from app.models import MoveRequest

        manager = create_user("manager1", "manager1@example.com", "management")
        request_row = MoveRequest(
            raw_text="Time format check",
            created_by_id=manager.id,
            status="open",
            origin_location_text="RW",
            destination_location_text="KP",
            requested_at=datetime(2026, 5, 13, 16, 5),
        )
        db.session.add(request_row)
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
    assert b"Manager Workspace" in manager_page.data
    assert b"Move Requests" in manager_page.data
    assert b"Driver Routes" in manager_page.data
    assert b"Live Flow Map" not in manager_page.data
    assert b"Dispatch Queue" not in manager_page.data
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
    assert b"Assign or Reassign Driver" in manage_page.data
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
    assert b"Move Requests" in queue_page.data
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
    assert b"Original Request and Message" in edit_page.data

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
        assert req.status == "completed"
        assert req.closed_reason == "Moved by driver."
        for action in ["updated", "assigned", "blocked", "completed"]:
            assert ActivityEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 1
            assert AuditEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 1
        assert ActivityEvent.query.filter_by(target_type="move_request", target_id=request_id, action="cancelled").count() == 0
        assert AuditEvent.query.filter_by(target_type="move_request", target_id=request_id, action="cancelled").count() == 0


def test_manager_move_request_lifecycle_blocks_closed_requests_and_requires_reasons(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, AuditEvent, MoveRequest

        manager = create_user("queue_guard_manager", "queue-guard-manager@example.com", "management")
        driver = create_user("queue_guard_driver", "queue-guard-driver@example.com", "driver")
        open_request = MoveRequest(
            created_by_id=manager.id,
            request_number="MOVE-REQ-GUARD-OPEN",
            raw_text="Open request for guard test.",
            status="open",
        )
        completed_request = MoveRequest(
            created_by_id=manager.id,
            request_number="MOVE-REQ-GUARD-COMPLETE",
            raw_text="Completed request for guard test.",
            status="completed",
            closed_reason="Already moved.",
        )
        cancelled_request = MoveRequest(
            created_by_id=manager.id,
            request_number="MOVE-REQ-GUARD-CANCEL",
            raw_text="Cancelled request for guard test.",
            status="cancelled",
            closed_reason="Plant cancelled.",
        )
        db.session.add_all([open_request, completed_request, cancelled_request])
        db.session.commit()
        open_request_id = open_request.id
        completed_request_id = completed_request.id
        cancelled_request_id = cancelled_request.id
        driver_id = driver.id

    login(client, "queue_guard_manager")

    for endpoint, data in [
        ("mark-blocked", {"blocked_reason": ""}),
        ("mark-completed", {"closed_reason": ""}),
        ("cancel", {"closed_reason": ""}),
    ]:
        response = client.post(
            f"/manager/move-requests/{open_request_id}/{endpoint}",
            data=data,
            follow_redirects=False,
        )
        assert response.status_code == 302

    closed_actions = [
        ("assign", {"assigned_driver_id": str(driver_id), "equipment_text": "ST9"}),
        ("acknowledge", {"acknowledged_by_text": "Dispatch"}),
        ("mark-blocked", {"blocked_reason": "Trailer unavailable."}),
        ("mark-completed", {"closed_reason": "Duplicate completion."}),
        ("cancel", {"closed_reason": "Duplicate cancel."}),
    ]
    for request_id in [completed_request_id, cancelled_request_id]:
        for endpoint, data in closed_actions:
            response = client.post(
                f"/manager/move-requests/{request_id}/{endpoint}",
                data=data,
                follow_redirects=False,
            )
            assert response.status_code == 302

    with app.app_context():
        open_request = MoveRequest.query.get(open_request_id)
        completed_request = MoveRequest.query.get(completed_request_id)
        cancelled_request = MoveRequest.query.get(cancelled_request_id)
        assert open_request.status == "open"
        assert open_request.blocked_reason is None
        assert open_request.closed_reason is None
        assert completed_request.status == "completed"
        assert completed_request.closed_reason == "Already moved."
        assert completed_request.assigned_driver_id is None
        assert cancelled_request.status == "cancelled"
        assert cancelled_request.closed_reason == "Plant cancelled."
        assert cancelled_request.assigned_driver_id is None
        for request_id in [open_request_id, completed_request_id, cancelled_request_id]:
            for action in ["assigned", "acknowledged", "blocked", "completed", "cancelled"]:
                assert ActivityEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 0
                assert AuditEvent.query.filter_by(target_type="move_request", target_id=request_id, action=action).count() == 0


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
    assert b"Manager Workspace" in dashboard.data
    assert raw_text.encode() not in dashboard.data
    assert b"Universal Dispatch Capture Inbox" not in dashboard.data

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
    # A stop that arrived loaded and departed empty renders as DELIVERED on the
    # live board (status taxonomy updated 2026-06; was "DROPPED").
    assert b"DELIVERED" in route_page.data


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
    assert b"Dock time:" in dashboard.data
    assert b"17 min" in dashboard.data or b"18 min" in dashboard.data
    assert b"focus=delays" not in dashboard.data


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
    assert b"Expected wait" in manager.data
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
    # Pending mileage: no odometer captured, so the Miles column and Mileage card are hidden, not "Pending posttrip" filler.
    assert b"Miles Since Last Stop" not in page.data
    assert b"Mileage Summary" not in page.data
    assert b"Pending posttrip" not in page.data
    # Damage/incident facts still surface (now inside the log summary cards, not a standalone section).
    assert b"Incident - Other" in page.data
    assert b"Damage - RE" in page.data
    assert b"Timing status pending" not in page.data
    assert b"15 min" in page.data
    assert b"Raleigh East" in page.data
    assert b"Kraft Plater Load" in page.data
    assert b"Load Flow" in page.data
    assert b"Wait time:</strong> Wait 15 min" not in page.data
    assert b"Movement segment" not in page.data
    assert_driver_route_sheet_output(page.data)
    assert b"Plant Legend" not in page.data
    assert b"PPL = PPL" not in page.data

    attachment = client.get("/driver_logs_print/attachment")
    assert attachment.status_code == 200
    assert b"15 min" in attachment.data
    assert_driver_route_sheet_output(attachment.data)


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
    assert b"Cargo and Manifest Review" in response.data
    assert b"Clean" in response.data
    assert b"Manifest linked" in response.data
    assert b"No" in response.data
    assert b"No shipper/manifest record is linked" in response.data
    assert b"No cargo mismatch was detected from driver-entered route data" in response.data
    assert b"Appears complete" not in response.data
    assert b"Picked Up / Departed With" not in response.data
    assert b"Manifest Linked: Yes" not in response.data
    assert b"Scan records are attached to this route." not in response.data
    assert b"Delay and Dock Time Review" in response.data
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
    assert (
        b"Predictions do not become actual cargo until confirmed" in response.data
        or b"Driver delay reason required" in response.data
    )


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
    assert b"Photo, Damage, and Safety Review" in response.data
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
    assert b"Proof Record" in report_page.data

    packet = client.get(f"/manager/damage-reports/{report_id}/evidence-packet")
    assert packet.status_code == 200
    assert b"Packet Cover Page" in packet.data
    assert b"Full Event Timeline" in packet.data
    assert b"Photo and Media Evidence" in packet.data
    assert b"Chain of Custody" in packet.data
    assert b"Related Route Records" in packet.data
    assert b"PreTrip DVIR created" in packet.data
    assert b"Plant transfer paperwork created" in packet.data
    assert b"Audit: reviewed" in packet.data
    assert expected_hash in packet.data
    assert b"Verify odometer entry" in packet.data
    assert b"Manager signature not captured" in packet.data
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
    from datetime import date

    today_value = date.today().isoformat()
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
    assert b'enctype="multipart/form-data"' in new_page.data
    assert b'capture="environment"' in new_page.data

    response = client.post(
        "/new_pretrip",
        data={
            "truck_number": "BT-1",
            "trailer_number": "TR-2",
            "pretrip_date": today_value,
            "shift": "1st",
            "start_mileage": "1000",
            "start_fuel_level": "3/4",
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
    assert response.headers["Location"].endswith("/list_pretrips")

    with app.app_context():
        from app.models import ActivityEvent, DamageReport, PreTrip, ShiftRecord

        pretrip = PreTrip.query.filter_by(truck_number="BT-1").one()
        assert pretrip.truck_type == "Box Truck"
        assert pretrip.start_fuel_level == "3/4"
        pretrip_id = pretrip.id
        shift = ShiftRecord.query.filter_by(pretrip_id=pretrip_id, end_time=None).one()
        assert shift.user_id == pretrip.user_id
        damage = DamageReport.query.filter_by(move_reference=f"PreTrip #{pretrip_id}").one()
        assert damage.description == "Scratch on bumper"
        assert len(damage.photos) == 1
        assert ActivityEvent.query.filter_by(
            target_type="pretrip", target_id=pretrip_id, action="created"
        ).count() == 1

    list_page = client.get("/list_pretrips")
    assert b"Damage Photos" in list_page.data
    assert b"1 attached" in list_page.data

    edit_page = client.get(f"/edit_pretrip_entry/{pretrip_id}")
    assert edit_page.status_code == 200
    assert b'enctype="multipart/form-data"' in edit_page.data
    assert b"Truck and Tractor #" in edit_page.data
    assert b"No Defects" in edit_page.data
    assert b'capture="environment"' in edit_page.data

    edited_pretrip = client.post(
        f"/edit_pretrip_entry/{pretrip_id}",
        data={
            "truck_number": "BT-9",
            "trailer_number": "TR-9",
            "pretrip_date": today_value,
            "shift": "2nd",
            "start_mileage": "1005",
            "start_fuel_level": "1/2",
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
        assert pretrip.start_fuel_level == "1/2"
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
        data={"end_mileage": "1125", "end_fuel_level": "1/4", "remarks": "ok"},
        follow_redirects=False,
    )
    assert posttrip.status_code == 302

    with app.app_context():
        from app.models import PostTrip

        saved_posttrip = PostTrip.query.filter_by(pretrip_id=pretrip_id).one()
        assert saved_posttrip.end_mileage == 1125
        assert saved_posttrip.end_fuel_level == "1/4"
        assert saved_posttrip.miles_driven == 120

    printable = client.get(f"/pretrip_printable/{pretrip_id}")
    assert printable.status_code == 200
    assert b"Daily Vehicle Inspection Report" in printable.data
    assert b"Fuel Level" in printable.data
    assert b"Start 1/2" in printable.data
    assert b"End 1/4" in printable.data
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
    assert b"md-shell md-standalone" in activity.data
    assert b"md-driver-bottom-nav" in activity.data
    assert b"PreTrip saved" in activity.data
    assert b"PreTrip printed" not in activity.data

    mark_printed = client.post(f"/pretrip_printable/{pretrip_id}/mark_printed")
    assert mark_printed.status_code == 200
    assert mark_printed.get_json()["ok"] is True

    activity = client.get("/recent_activity")
    assert b"md-shell md-standalone" in activity.data
    assert b"PreTrip printed" in activity.data


def test_new_pretrip_blank_date_uses_local_route_date(client, app, monkeypatch):
    from datetime import date

    from app.blueprints.driver import routes as driver_routes

    local_route_date = date(2026, 6, 4)
    monkeypatch.setattr(driver_routes, "_today_local_date", lambda: local_route_date)

    with app.app_context():
        create_user("local_pretrip_driver", "local-pretrip@example.com", "driver")

    login(client, "local_pretrip_driver")
    page = client.get("/new_pretrip")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert 'name="pretrip_date" type="date" value="2026-06-04"' in body

    response = client.post(
        "/new_pretrip",
        data={
            "truck_number": "ST4",
            "trailer_number": "",
            "pretrip_date": "",
            "shift": "1st",
            "start_mileage": "379000",
            "start_fuel_level": "3/4",
            "truck_type": "Box Truck",
            "oil_system_status": "good",
            "tires_status": "good",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        from app.models import PreTrip

        pretrip = PreTrip.query.filter_by(truck_number="ST4").one()
        assert pretrip.pretrip_date == local_route_date


def test_mobile_dashboard_repairs_pretrip_saved_under_utc_tomorrow(client, app, monkeypatch):
    from datetime import date, datetime

    import pytz

    from app.blueprints.driver import routes as driver_routes

    local_tz = pytz.timezone("America/Detroit")
    local_now = local_tz.localize(datetime(2026, 6, 4, 21, 15))
    utc_now = local_now.astimezone(pytz.utc).replace(tzinfo=None)
    monkeypatch.setattr(driver_routes, "_now_local_and_utc", lambda: (local_now, utc_now))

    with app.app_context():
        from app.extensions import db
        from app.models import PreTrip

        driver = create_user("utc_pretrip_driver", "utc-pretrip@example.com", "driver")
        pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=date(2026, 6, 5),
            truck_number="ST4",
            start_mileage=379000,
            created_at=utc_now,
        )
        db.session.add(pretrip)
        db.session.commit()
        pretrip_id = pretrip.id

    login(client, "utc_pretrip_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    with app.app_context():
        from app.models import PreTrip

        repaired = PreTrip.query.get(pretrip_id)
        assert repaired.pretrip_date == date(2026, 6, 4)


def _make_closed_pretrip(driver_id, truck, pretrip_date, start_mileage):
    """Persist a PreTrip with a completed PostTrip (a closed past route)."""
    from app.extensions import db
    from app.models import PostTrip, PreTrip

    pretrip = PreTrip(
        user_id=driver_id,
        truck_number=truck,
        pretrip_date=pretrip_date,
        start_mileage=start_mileage,
    )
    db.session.add(pretrip)
    db.session.flush()
    db.session.add(PostTrip(pretrip_id=pretrip.id, end_mileage=start_mileage + 100))
    db.session.commit()
    return pretrip.id


def test_closed_routes_on_other_trucks_stay_in_inspection_list(client, app, monkeypatch):
    """Closed routes on a different truck must remain reachable from the driver
    inspection list, both before and after the 2026-06-05 feature cutover.

    Regression: scoping the inspection list to the "current" truck dropped every
    closed, non-today truck so older PreTrip/PostTrip records disappeared even
    though they persisted in the database.
    """
    from datetime import date

    from app.blueprints.driver import routes as driver_routes

    monkeypatch.setattr(driver_routes, "_today_local_date", lambda: date(2026, 6, 9))

    with app.app_context():
        driver = create_user("multi_truck_driver", "multi-truck@example.com", "driver")
        before_id = _make_closed_pretrip(driver.id, "ST4", date(2026, 6, 4), 379000)
        after_id = _make_closed_pretrip(driver.id, "BT7", date(2026, 6, 6), 412000)

        # The inspection list (include_closed) must offer BOTH trucks, no dupes.
        choices = driver_routes._driver_inspection_truck_choices(driver.id, include_closed=True)
        truck_numbers = sorted(choice["truck_number"] for choice in choices)
        assert truck_numbers == ["BT7", "ST4"]
        assert len(truck_numbers) == len(set(truck_numbers))
        # Cross-driver auth / maintenance-history stay scoped to the current
        # truck: with no today-or-open route, the gated default collapses to one.
        gated = driver_routes._driver_inspection_truck_choices(driver.id)
        assert len(gated) == 1

        # Both records still persist and resolve by id.
        from app.models import PreTrip

        assert PreTrip.query.get(before_id).truck_number == "ST4"
        assert PreTrip.query.get(after_id).truck_number == "BT7"

    login(client, "multi_truck_driver")
    page = client.get("/list_pretrips")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    # Both trucks appear in the rendered inspection page (selector), not just one.
    assert "ST4" in body
    assert "BT7" in body


def test_driver_mobile_bottom_action_bar(client, app):
    """Driver mobile has ONE bottom action bar with distinct workflow targets."""
    with app.app_context():
        create_user("nav_driver", "nav-driver@example.com", "driver")
    login(client, "nav_driver")

    home = client.get("/mobile")
    body = home.get_data(as_text=True)
    assert home.status_code == 200
    # Exactly one bottom bar, and no separate Quick Log card.
    assert body.count('<nav class="md-driver-bottom-nav"') == 1
    assert "md-quick-log" not in body
    # The five action items, in order.
    order = [label for label in ("Home", "Breaks", "Fuel", "Service", "Inspections")
             if f"<span>{label}</span>" in body]
    assert order == ["Home", "Breaks", "Fuel", "Service", "Inspections"]
    # Transfer / Logs / Reports are not bottom-bar items.
    assert "<span>Transfer</span>" not in body
    assert "<strong>DL</strong>" not in body
    assert "<strong>RP</strong>" not in body

    # Bottom actions now land on distinct operational surfaces.
    assert "/ifta-worksheet/new" in body
    assert "/mobile/breaks" in body
    assert "/mobile/break/start" not in body
    assert "/mobile?flow=maintenance" in body
    assert "/list_pretrips" in body
    fuel_page = client.get("/ifta-worksheet/new")
    assert fuel_page.status_code == 200
    assert "Fuel Records" in fuel_page.get_data(as_text=True)
    service_page = client.get("/mobile?flow=maintenance")
    assert service_page.status_code == 200
    service_body = service_page.get_data(as_text=True)
    assert 'data-flow-open-panel="maintenance"' in service_body
    assert "Ryder Service" in service_body
    inspections_page = client.get("/list_pretrips")
    assert inspections_page.status_code == 200
    assert "Truck Inspections" in inspections_page.get_data(as_text=True)

    # Logout stays in the top header.
    assert "logout" in body.lower()
    # Plant transfer backend stays intact (reachable from Route Packet/context).
    assert client.get("/plant_transfers").status_code == 200


def test_driver_bottom_nav_break_toggles(client, app):
    """The bottom-bar Break tab opens a confirmation/detail page, not a direct POST."""
    with app.app_context():
        create_user("brk_driver", "brk-driver@example.com", "driver")
    login(client, "brk_driver")

    body = client.get("/mobile").get_data(as_text=True)
    assert "md-quick-log" not in body            # no separate quick-log area
    assert body.count('<nav class="md-driver-bottom-nav"') == 1
    assert "<span>Breaks</span>" in body
    assert 'href="/mobile/breaks"' in body
    assert "/mobile/break/start" not in body

    breaks_page = client.get("/mobile/breaks").get_data(as_text=True)
    assert "<h1>Break Log</h1>" in breaks_page
    assert "Start Break" in breaks_page
    assert "Break Details" in breaks_page
    assert "No breaks recorded for this route date." in breaks_page

    # Starting a break is explicit from the Break Log page.
    start = client.post("/mobile/break/start", data={"next": "breaks"})
    assert start.status_code == 302
    assert start.headers["Location"].endswith("/mobile/breaks")
    on_break = client.get("/mobile").get_data(as_text=True)
    # Nav button shows the on-break state (glow) but NO timer text anymore.
    assert "<span>On Break</span>" in on_break
    assert "md-nav-link on" in on_break
    assert 'href="/mobile/breaks"' in on_break
    assert "<span>Breaks</span>" not in on_break
    # The big CTA takes over with the live timer + one-tap end-break, so a driver
    # can't forget they're on break.
    assert "md-flow-primary-cta on-break" in on_break
    assert "data-break-timer" in on_break
    assert "data-break-seconds" in on_break
    assert "Tap to end break" in on_break
    assert "/mobile/break/end" in on_break

    open_break_page = client.get("/mobile/breaks").get_data(as_text=True)
    assert "Current Break" in open_break_page
    assert "End Break" in open_break_page
    assert "data-break-detail-timer" in open_break_page
    assert "Open" in open_break_page
    # State is consistent on other driver pages (context processor), still one bar.
    pretrip = client.get("/new_pretrip").get_data(as_text=True)
    assert "<span>On Break</span>" in pretrip
    assert "data-break-timer" in pretrip
    assert pretrip.count('<nav class="md-driver-bottom-nav"') == 1
    # End the break -> back to Break.
    end = client.post("/mobile/break/end", data={"next": "breaks"})
    assert end.status_code == 302
    assert end.headers["Location"].endswith("/mobile/breaks")
    after = client.get("/mobile").get_data(as_text=True)
    assert "<span>Breaks</span>" in after
    assert "<span>On Break</span>" not in after


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


def test_open_stop_edit_hides_departure_fields_and_directs_to_depart_and_load(client, app):
    """Editing an OPEN stop must not show the 'Departed With' field — it was
    silently ignored there (saved but nothing changed). Drivers record a pickup
    via Depart & Load, which is what the open-stop edit page now points to. A
    departed stop still exposes the departure field."""
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("open_edit_driver", "open-edit@example.com", "driver")
        today = date.today()
        open_stop = DriverLog(driver_id=driver.id, date=today, plant_name="Paint Central",
                              load_size="Empty", arrive_time=f"{today.isoformat()} 09:00:00", depart_time=None)
        departed_stop = DriverLog(driver_id=driver.id, date=today, plant_name="RE", load_size="Empty",
                                  depart_load_size="Empty", arrive_time=f"{today.isoformat()} 08:00:00", depart_time="08:05")
        db.session.add_all([open_stop, departed_stop])
        db.session.commit()
        open_id, departed_id = open_stop.id, departed_stop.id

    login(client, "open_edit_driver")
    open_edit = client.get(f"/edit_driver_log/{open_id}").get_data(as_text=True)
    assert 'name="departure_destination"' not in open_edit
    assert "Depart" in open_edit and "Load" in open_edit  # guidance to Depart & Load
    # A departed stop still lets you correct the departure load.
    departed_edit = client.get(f"/edit_driver_log/{departed_id}").get_data(as_text=True)
    assert 'name="departure_destination"' in departed_edit


def test_edit_driver_log_rejects_impossible_depart_to_next_arrival(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver1", "driver1@example.com", "driver")
        route_date = date.today()
        first = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PE",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 21:28:00",
        )
        second = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RW",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 21:32:00",
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
    assert b"Depart and Load" in list_page.data

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
        first_log_id = completed_log.id
        log_id = log.id
        driver_id = driver.id

    login(client, "manager1")
    page = client.get("/manager/driver-logs")
    assert page.status_code == 200
    assert b"RE" in page.data
    assert b"Cargo In and Out" in page.data
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
    assert f"/manager/driver-logs/route-attachment?driver_id={driver_id}&amp;date={date.today().isoformat()}".encode() in route_print.data
    assert f"/manager/driver-logs/route-print?driver_id={driver_id}&amp;date={date.today().isoformat()}&amp;autoprint=1".encode() not in route_print.data

    route_csv = client.get(f"/manager/driver-logs/route-export?driver_id={driver_id}&date={date.today().isoformat()}&type=csv")
    assert route_csv.status_code == 200
    assert route_csv.headers["Content-Type"].startswith("text/csv")
    assert b"Stop,Date,Driver" in route_csv.data

    route_sheets = client.get(f"/manager/driver-logs/route-export?driver_id={driver_id}&date={date.today().isoformat()}&type=sheets")
    assert route_sheets.status_code == 200
    assert route_sheets.headers["Content-Type"].startswith("text/tab-separated-values")
    assert b"Stop	Date	Driver" in route_sheets.data

    route_pdf = client.get(f"/manager/driver-logs/route-attachment?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_pdf.status_code == 200
    assert route_pdf.headers["Content-Type"] == "application/pdf"

    with app.app_context():
        from app.models import ActivityEvent

        pdf_activity = ActivityEvent.query.filter_by(
            category="download",
            action="manager_pdf_attachment",
            target_type="driver_log",
            target_id=first_log_id,
        ).one()
        assert "manager-route-review" in pdf_activity.details
        csv_activity = ActivityEvent.query.filter_by(
            category="download",
            action="manager_route_export",
            target_type="driver_log",
            target_id=first_log_id,
        ).first()
        assert csv_activity is not None

    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}")
    assert dashboard.status_code == 200
    assert b"Driver Routes" in dashboard.data
    assert b"Missing Departure" in dashboard.data
    assert b"Completed" in dashboard.data
    assert b"Needs Attention" in dashboard.data
    assert b"Critical Exceptions" not in dashboard.data
    assert b"Truck Issue" in dashboard.data
    assert b"status-pill open" in dashboard.data
    assert b"status-pill complete" in dashboard.data
    assert b"Needs Attention" in dashboard.data
    assert b'<span class="sbadge problem">Problem</span>' not in dashboard.data
    focused_dashboard = client.get(
        f"/manager/dashboard?driver_id={driver_id}&focus=routes&target=attention"
    )
    assert focused_dashboard.status_code == 200
    assert b"Driver Routes" in focused_dashboard.data
    assert b"Live Flow Map" not in focused_dashboard.data
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
    assert b"Damage and Delay" in page.data
    assert b"Damage Evidence" not in page.data
    assert b"Cargo Scan Proof" not in page.data
    assert b"Signature and Record Footer" in page.data
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
    assert b"Driver arrived at 3:07pm and is getting loaded and awaiting departure." in page.data
    assert b"Needs Review" in page.data
    assert b"2 cargo scans require manager confirmation." in page.data
    assert b"Cargo Review" in page.data
    assert b"Damage Evidence" not in page.data
    assert b"Damage Reports (0)" not in page.data
    assert b"Delay Events (0)" not in page.data
    assert b"Damage and Delay" not in page.data
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


def test_manager_exception_complete_and_acknowledge_are_history_without_hiding_source(client, app):
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

    acknowledge = client.post(
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
    assert b"Exception acknowledged" in acknowledge.data
    assert b"No pre-trip" in acknowledge.data

    with app.app_context():
        from app.models import ActivityEvent, OperationalFollowUp

        assert OperationalFollowUp.query.get(followup_id).status == "closed"
        assert ActivityEvent.query.filter_by(category="exception", action="reviewed").count() == 1
        assert ActivityEvent.query.filter_by(category="exception", action="deleted").count() == 1


def test_manager_task_reassignment_requires_driver_or_unassigned(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Task

        create_user("task_manager", "task-manager@example.com", "management")
        driver = create_user("task_driver", "task-driver@example.com", "driver")
        other_driver = create_user("other_task_driver", "other-task-driver@example.com", "driver")
        manager_assignee = create_user("manager_assignee", "manager-assignee@example.com", "management")
        task = Task(title="Move RE to KP", details="Initial note", assigned_to=driver.id, status="pending")
        db.session.add(task)
        db.session.commit()
        task_id = task.id
        other_driver_id = other_driver.id
        manager_assignee_id = manager_assignee.id

    login(client, "task_manager")

    valid = client.post(
        f"/manager/tasks/{task_id}",
        data={"assigned_to": str(other_driver_id), "status": "pending", "shift": "1st", "details": "Assigned"},
        follow_redirects=False,
    )
    assert valid.status_code == 302
    with app.app_context():
        from app.models import Task

        assert Task.query.get(task_id).assigned_to == other_driver_id

    unassigned = client.post(
        f"/manager/tasks/{task_id}",
        data={"assigned_to": "0", "status": "pending", "shift": "1st", "details": "Open"},
        follow_redirects=False,
    )
    assert unassigned.status_code == 302
    with app.app_context():
        from app.models import Task

        assert Task.query.get(task_id).assigned_to is None

    invalid_manager = client.post(
        f"/manager/tasks/{task_id}",
        data={"assigned_to": str(manager_assignee_id), "status": "pending", "shift": "1st", "details": "Bad"},
        follow_redirects=False,
    )
    assert invalid_manager.status_code == 302
    with app.app_context():
        from app.models import Task

        assert Task.query.get(task_id).assigned_to is None

    missing_user = client.post(
        f"/manager/tasks/{task_id}",
        data={"assigned_to": "999999", "status": "pending", "shift": "1st", "details": "Bad"},
        follow_redirects=False,
    )
    assert missing_user.status_code == 302
    with app.app_context():
        from app.models import Task

        assert Task.query.get(task_id).assigned_to is None


def test_manager_dashboard_does_not_offer_fake_print_audit_log_action(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Task

        manager = create_user("audit_button_manager", "audit-button-manager@example.com", "management")
        db.session.add(Task(title="Move PC to RE", details="Dashboard row", status="pending", assigned_to=None))
        db.session.commit()

    login(client, "audit_button_manager")
    dashboard = client.get("/manager/dashboard")
    assert dashboard.status_code == 200
    assert b"Print Audit Log" not in dashboard.data
    assert b"openAuditPrintView" not in dashboard.data


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
    assert b"Add Paperwork and Proof Photo" in edit_page.data
    assert b"Why are you adding this picture?" not in edit_page.data
    assert b"BOL and Manifest" in edit_page.data
    assert b"Optional note" in edit_page.data
    assert b"Upload From Gallery" in edit_page.data
    assert b'data-stop-photo-input="edit_gallery"' in edit_page.data
    assert b'capture="environment" data-stop-photo-input="edit_camera"' in edit_page.data

    missing_file_upload = client.post(
        f"/driver_logs/{log_id}/photos",
        data={"source": "edit_gallery"},
        headers={"Accept": "application/json"},
    )
    assert missing_file_upload.status_code == 400
    assert missing_file_upload.get_json()["error"] == "File was not saved. Try again."

    paperwork_upload = client.post(
        f"/driver_logs/{log_id}/photos",
        data={
            "document_type": "bol_manifest",
            "source": "edit_gallery",
            "photo": (BytesIO(b"edit-gallery-photo"), "edit-gallery.jpg"),
        },
        headers={"Accept": "application/json"},
    )
    assert paperwork_upload.status_code == 200
    paperwork_photo = paperwork_upload.get_json()["photo"]
    assert paperwork_photo["source"] == "Bol Manifest Edit Gallery"
    assert paperwork_photo["note"] == "BOL and manifest paperwork"

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
    assert b"Add Paperwork and Proof Photo" in depart_page.data
    assert b"Why are you adding this picture?" not in depart_page.data
    assert b"BOL and Manifest" in depart_page.data
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
    assert b"BOL and manifest paperwork" in driver_list.data
    assert b"Loaded seal photo from gallery" in driver_list.data
    assert b"Departing load proof from gallery" in driver_list.data

    driver_detail = client.get(f"/view_driver_log/{log_id}")
    assert driver_detail.status_code == 200
    assert b"Stop Photo Proof" in driver_detail.data
    assert b"BOL and manifest paperwork" in driver_detail.data
    assert b"Loaded seal photo from gallery" in driver_detail.data
    assert b"Remove Photo" in driver_detail.data

    driver_print = client.get("/driver_logs_print")
    assert driver_print.status_code == 200
    assert b'data-print-document' in driver_print.data
    assert b'data-save-pdf' in driver_print.data
    assert b"Print dialog opened." in driver_print.data
    assert b"Preparing PDF..." in driver_print.data
    assert b"Plant Legend" not in driver_print.data
    assert b"Signatures" in driver_print.data
    # Attached photos/documents now surface inside the Notes / Events log summary card.
    assert b"Loaded seal photo from gallery" in driver_print.data
    assert b"Departing load proof from gallery" in driver_print.data
    assert b"Photo proof review" not in driver_print.data
    assert b" UTC" not in driver_print.data
    assert b"Timing status pending" not in driver_print.data
    assert_driver_route_sheet_output(driver_print.data)

    with app.app_context():
        from app.models import DriverLogPhoto

        photos = DriverLogPhoto.query.order_by(DriverLogPhoto.id.asc()).all()
        assert len(photos) == 3
        paperwork_photo_id = photos[0].id
        first_photo_id = photos[1].id
        second_photo_id = photos[2].id

    client.get("/logout")
    login(client, "photo_manager")
    manager_list = client.get(f"/manager/driver-logs?date={date.today().isoformat()}")
    assert manager_list.status_code == 200
    assert b"Proof" in manager_list.data
    assert b"BOL and manifest paperwork" in manager_list.data
    assert b"Loaded seal photo from gallery" in manager_list.data
    assert b"Departing load proof from gallery" in manager_list.data

    manager_dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}&focus=routes")
    assert manager_dashboard.status_code == 200
    assert b"Documents" in manager_dashboard.data
    assert b"Departing load proof from gallery" in manager_dashboard.data
    assert f"/manager/driver-logs/{log_id}".encode() in manager_dashboard.data

    manager_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert manager_print.status_code == 200
    assert b"Photo, Damage, and Safety Review" in manager_print.data
    assert b"Departing load proof from gallery" in manager_print.data
    assert b"height:2.15in" in manager_print.data
    assert b"Timing status pending" not in manager_print.data

    manager_page = client.get(f"/manager/driver-logs/{log_id}")
    assert manager_page.status_code == 200
    assert b"Stop Photo Proof" in manager_page.data
    assert b"Cargo Photo Proof" in manager_page.data
    assert b"Three stop photo proofs were attached" in manager_page.data
    assert b"Latest proof from Paint Central says: Departing load proof from gallery" in manager_page.data
    assert b"BOL and manifest paperwork" in manager_page.data
    assert b"Loaded seal photo from gallery" in manager_page.data
    assert b"Remove Photo" in manager_page.data
    assert f"/manager/driver-log-photos/{paperwork_photo_id}".encode() in manager_page.data
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
    assert b"BOL and manifest paperwork" in manager_page_after_delete.data
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
    driver_paperwork_delete = client.post(
        f"/driver_logs/photos/{paperwork_photo_id}/delete",
        data={"next": "/driver_logs"},
        follow_redirects=False,
    )
    assert driver_paperwork_delete.status_code == 302
    assert client.get(f"/driver_logs/photos/{paperwork_photo_id}").status_code == 404
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
    assert b"Scan Unloaded and Dropped Cargo" in depart_page.data
    assert b"Scan Loaded and Departing Cargo" in depart_page.data
    assert b"Scan Arriving Cargo" not in depart_page.data
    assert b"Scan Picked-Up Cargo" not in depart_page.data
    assert b"Add Paperwork and Proof Photo" in depart_page.data
    assert b"Upload From Gallery" in depart_page.data
    assert b'data-stop-photo-input="departure_gallery"' in depart_page.data
    assert b"Upload Label Photo" not in depart_page.data
    assert b"galleryScanImage" not in depart_page.data
    assert b"@zxing/browser" in depart_page.data
    assert b"Manager review override note" in depart_page.data

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
    assert b"Cargo and Manifest Review" in manager_print.data
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
    assert b"Picked up Trim DC Load." in finalized.data
    assert b"Picked up Helios Load." in finalized.data
    assert b"Delivered Helios Load." in finalized.data
    assert b"Continued with Trim DC Load onboard." in finalized.data
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
    # Truck-issue odometer renders as "Truck issue: ... · 12,345 mi"
    # (label format updated 2026-06; was "Truck Issue - 12,345 mi").
    assert b"Truck issue:" in page.data
    assert b"12,345 mi" in page.data


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
    assert finalized_page.status_code == 302
    assert finalized_page.headers["Location"].endswith(f"/driver_logs?date={today.isoformat()}")


def test_finalized_event_locks_active_shift_new_logs(client, app):
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
    assert "Add Stop" not in body
    assert b"md-flow-action-tab primary add-stop-action" not in mobile.data
    assert b'<a class="md-flow-primary-cta add-stop-action"' not in mobile.data

    new_log = client.get("/new_driving_log", follow_redirects=True)
    assert new_log.status_code == 200
    assert b"That route is finalized. Driver Log entries cannot be changed." in new_log.data
    assert b"Save Changes" not in new_log.data


def test_finalized_route_blocks_driver_mutating_urls_and_controls(client, app):
    from datetime import datetime

    with app.app_context():
        from app.blueprints.driver.routes import _today_local_date
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, DriverLogPhoto, PreTrip, ShiftRecord

        driver = create_user("finalized_lock_driver", "finalized-lock@example.com", "driver")
        create_user("finalized_lock_manager", "finalized-lock-manager@example.com", "management")
        today = _today_local_date()
        pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=today,
            truck_number="H-12",
            start_mileage=1200,
        )
        db.session.add(pretrip)
        db.session.flush()
        shift = ShiftRecord(
            user_id=driver.id,
            pretrip_id=pretrip.id,
            start_time=datetime.utcnow(),
        )
        db.session.add(shift)
        log = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="H",
            load_size="Empty",
            arrive_time="2026-06-05 12:00:00",
            created_at=datetime.utcnow(),
        )
        db.session.add(log)
        db.session.flush()
        photo = DriverLogPhoto(
            driver_log_id=log.id,
            filename="locked-proof.jpg",
            original_filename="locked-proof.jpg",
            source="proof",
            note="Loaded seal photo",
            uploaded_by_id=driver.id,
        )
        db.session.add(photo)
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
        log_id = log.id
        photo_id = photo.id
        pretrip_id = pretrip.id
        shift_id = shift.id
        today_value = today.isoformat()

    login(client, "finalized_lock_driver")

    edit_page = client.get(f"/edit_driver_log/{log_id}", follow_redirects=True)
    assert edit_page.status_code == 200
    assert b"That route is finalized. Driver Log entries cannot be changed." in edit_page.data
    assert b"Save Changes" not in edit_page.data
    assert b"Upload From Gallery" not in edit_page.data
    assert b"Take New Photo" not in edit_page.data

    edit_post = client.post(
        f"/edit_driver_log/{log_id}",
        data={
            "plant_name": "RE",
            "load_size": "Raleigh East Load",
            "arrive_time": "8:00am",
            "depart_time": "8:15am",
            "departure_destination": "KP",
            "secondary_departure_dest": "",
            "secondary_departure_type": "load",
        },
        follow_redirects=True,
    )
    assert b"That route is finalized. Driver Log entries cannot be changed." in edit_post.data

    quick_depart = client.post(
        f"/driver_logs/{log_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "destination": "RE",
            "secondary_destination": "",
            "secondary_load_type": "load",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert quick_depart.status_code == 403
    assert "That route is finalized" in quick_depart.get_json()["error"]

    proof_upload = client.post(
        f"/driver_logs/{log_id}/photos",
        data={"source": "proof", "photo": (BytesIO(b"proof"), "proof.jpg")},
        headers={"Accept": "application/json"},
    )
    assert proof_upload.status_code == 403
    assert "That route is finalized" in proof_upload.get_json()["error"]

    proof_delete = client.post(
        f"/driver_logs/photos/{photo_id}/delete",
        data={"next": "/driver_logs"},
        follow_redirects=True,
    )
    assert b"That route is finalized. Driver Log entries cannot be changed." in proof_delete.data

    add_stop = client.post(
        "/add_stop",
        data={"plant_name": "RE", "load_size": "Empty", "arrive_time": "8:30am"},
        follow_redirects=True,
    )
    assert b"That route is finalized. Driver Log entries cannot be changed." in add_stop.data

    transfer = client.post(
        "/plant_transfers/new",
        data={
            "transfer_number": "LOCK-1",
            "transfer_date": today_value,
            "ship_to": "RE",
            "ship_from": "H",
            "driver_name": "finalized_lock_driver",
            "part_number_0": "LOCKED",
            "quantity_0": "1",
        },
        follow_redirects=True,
    )
    assert b"That route is finalized. Plant Transfer entries cannot be changed." in transfer.data

    damage = client.get("/damage_reports/new", follow_redirects=True)
    assert b"That route is finalized. Damage Report entries cannot be changed." in damage.data

    pickup_page = client.get(f"/driver_logs/{log_id}/pickup", follow_redirects=True)
    assert b"That route is finalized. Driver Log entries cannot be changed." in pickup_page.data
    assert b"Record Load" not in pickup_page.data

    posttrip_page = client.get(f"/do_posttrip/{pretrip_id}", follow_redirects=True)
    assert b"That route is finalized. PostTrip entries cannot be changed." in posttrip_page.data
    assert b"Complete PostTrip" not in posttrip_page.data

    posttrip_submit = client.post(
        f"/do_posttrip/{pretrip_id}",
        data={"end_mileage": "1225", "end_fuel_level": "1/2", "remarks": "locked route"},
        follow_redirects=True,
    )
    assert b"That route is finalized. PostTrip entries cannot be changed." in posttrip_submit.data

    eod_submit = client.post(
        "/end_of_day_summary",
        data={"driver_signature": "data:image/png;base64,lockedroute"},
        follow_redirects=False,
    )
    assert eod_submit.status_code == 302
    assert "/driver_logs_print" in eod_submit.headers["Location"]

    legacy_eod_submit = client.post("/submit_end_of_day", follow_redirects=True)
    assert b"That route is finalized. Route closeout cannot be changed." in legacy_eod_submit.data

    view_page = client.get(f"/view_driver_log/{log_id}")
    assert view_page.status_code == 200
    assert b"Remove Photo" not in view_page.data
    assert f"/edit_driver_log/{log_id}".encode() not in view_page.data

    list_page = client.get("/driver_logs")
    assert list_page.status_code == 200
    assert b"Remove Photo" not in list_page.data
    assert b"Record Current Stop" not in list_page.data
    assert f"/edit_driver_log/{log_id}".encode() not in list_page.data
    assert f"/driver_logs/photos/{photo_id}/delete".encode() not in list_page.data

    mobile_page = client.get("/mobile")
    assert mobile_page.status_code == 200
    assert b'<a href="/new_driving_log">Add Stop</a>' not in mobile_page.data
    assert b'<a href="/damage_reports/new">Damage</a>' not in mobile_page.data
    assert b'<a class="md-flow-primary-cta add-stop-action"' not in mobile_page.data

    client.get("/logout")
    login(client, "finalized_lock_manager")
    manager_view = client.get(f"/manager/driver-logs/{log_id}")
    assert manager_view.status_code == 200
    assert b"Remove Photo" not in manager_view.data

    manager_delete = client.post(
        f"/manager/driver-log-photos/{photo_id}/delete",
        data={"next": f"/manager/driver-logs/{log_id}"},
        follow_redirects=True,
    )
    assert b"That route is finalized. Stop photo proof cannot be changed." in manager_delete.data

    with app.app_context():
        from app.models import DamageReport, DriverLog, DriverLogPhoto, PlantTransfer, PostTrip, ShiftRecord

        saved = DriverLog.query.get(log_id)
        assert saved.plant_name == "H"
        assert saved.load_size == "Empty"
        assert saved.depart_time is None
        assert DriverLog.query.filter_by(driver_id=saved.driver_id, date=saved.date).count() == 1
        assert DriverLogPhoto.query.get(photo_id) is not None
        assert DriverLogPhoto.query.count() == 1
        assert PostTrip.query.filter_by(pretrip_id=pretrip_id).count() == 0
        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.driver_signature is None
        assert saved_shift.end_time is None
        assert ActivityEvent.query.filter_by(user_id=saved.driver_id, category="eod", action="finalized").count() == 1
        assert PlantTransfer.query.count() == 0
        assert DamageReport.query.count() == 0


def test_plant_transfer_edit_cannot_move_record_to_locked_date(client, app):
    from datetime import date, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, PlantTransfer, PlantTransferLine

        driver = create_user("transfer_target_lock_driver", "transfer-target-lock@example.com", "driver")
        today = date.today()
        locked_date = today - timedelta(days=1)
        transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="MOVE-DATE",
            transfer_date=today,
            ship_from="KP",
            ship_to="RE",
            driver_name="transfer_target_lock_driver",
        )
        transfer.lines.append(PlantTransferLine(line_number=1, side="left", part_number="OK-1", quantity="1"))
        db.session.add_all([
            transfer,
            ActivityEvent(
                user_id=driver.id,
                category="eod",
                action="finalized",
                title="Route finalized",
                details=f"Route finalized for {locked_date}",
                target_type="end_of_day",
            ),
        ])
        db.session.commit()
        transfer_id = transfer.id

    login(client, "transfer_target_lock_driver")
    response = client.post(
        f"/plant_transfers/{transfer_id}/edit",
        data={
            "transfer_number": "MOVE-DATE",
            "transfer_date": locked_date.isoformat(),
            "ship_to": "RE",
            "ship_from": "KP",
            "driver_name": "transfer_target_lock_driver",
            "part_number_0": "MOVED",
            "quantity_0": "9",
            "edit_reason": "move date",
        },
        follow_redirects=True,
    )
    assert b"Only same-day Plant Transfer entries can be changed." in response.data

    with app.app_context():
        from app.models import PlantTransfer

        saved = PlantTransfer.query.get(transfer_id)
        assert saved.transfer_date == today
        assert saved.lines[0].part_number == "OK-1"


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
    assert b"DRIVER LOG SHEET" in print_response.data
    assert b"5:45pm" in print_response.data
    assert b"Dock time: 12 min" in print_response.data
    assert b"17:45" not in print_response.data
    assert b"Stop Timeline" in print_response.data
    assert b"Location" in print_response.data
    assert b"Stop / Movement" not in print_response.data
    assert b"Plant Legend" not in print_response.data
    assert b"Signatures" in print_response.data
    assert b"Leg #" not in print_response.data
    assert b"9. Signatures" not in print_response.data
    assert_driver_route_sheet_output(print_response.data)

    eod_print = client.get("/end_of_day_print")
    assert eod_print.status_code == 200
    assert b"5:45pm" in eod_print.data
    assert b"Dock time: 12 min" in eod_print.data
    assert b"17:45" not in eod_print.data
    assert_official_record_output(eod_print.data)

    eod_attachment = client.get("/end_of_day_print/attachment")
    assert eod_attachment.status_code == 200
    assert eod_attachment.headers["Content-Type"] == "application/pdf"
    assert b"Dock time: 12 min" in eod_attachment.data
    assert_official_record_output(eod_attachment.data)

    eod_response = client.post("/submit_end_of_day", follow_redirects=False)
    assert eod_response.status_code == 302

    activity = client.get("/recent_activity")
    assert activity.status_code == 200
    assert b"md-shell md-standalone" in activity.data
    assert b"Driver log submitted" in activity.data
    assert b"Driver logs printed" in activity.data
    assert b"End of day finalized" in activity.data

    unread = client.get("/count_unread").get_json()
    assert unread["action_count"] >= 3
    assert unread["unread_count"] >= unread["action_count"]


def test_global_delta_component_formats_additions_and_subtractions(app):
    with app.app_context():
        delta_value = app.jinja_env.get_template("partials/_delta.html").module.delta_value
        rendered = f"{delta_value(12, 'mi')} {delta_value(-8, 'mi')}"

    assert "▲ +12 mi" in rendered
    assert "▼ -8 mi" in rendered
    assert "app-delta--up font-mono" in rendered
    assert "app-delta--down font-mono" in rendered


def test_driver_logs_page_exposes_selected_date_print_and_pdf_actions(client, app):
    from datetime import date, datetime, timedelta

    selected_date = date(2026, 5, 20)
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("dated_print_driver", "dated-print@example.com", "driver")
        prior_driver = create_user("prior_truck_driver", "prior-truck@example.com", "driver")
        prior_pretrip = PreTrip(
            user_id=prior_driver.id,
            truck_number="BT-1",
            pretrip_date=selected_date,
            start_mileage=900,
            start_fuel_level="Full",
            created_at=datetime(2026, 5, 20, 6, 0, 0),
        )
        current_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=selected_date,
            start_mileage=1000,
            created_at=datetime(2026, 5, 20, 14, 0, 0),
        )
        previous_day_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=selected_date - timedelta(days=1),
            start_mileage=800,
            created_at=datetime(2026, 5, 19, 8, 0, 0),
        )
        older_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=selected_date - timedelta(days=2),
            start_mileage=700,
            created_at=datetime(2026, 5, 18, 8, 0, 0),
        )
        imported_odometer_pretrip = PreTrip(
            user_id=driver.id,
            truck_number="BT-1",
            pretrip_date=selected_date - timedelta(days=3),
            start_mileage=1,
            created_at=datetime(2026, 5, 17, 8, 0, 0),
        )
        db.session.add_all([
            prior_pretrip,
            current_pretrip,
            previous_day_pretrip,
            older_pretrip,
            imported_odometer_pretrip,
        ])
        db.session.flush()
        fuel_log = DriverLog(
            driver_id=driver.id,
            date=selected_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time="2026-05-20 21:12:00",
            depart_time="22:00",
            fuel=True,
            fuel_mileage=1045,
        )
        db.session.add_all([
            PostTrip(
                pretrip_id=prior_pretrip.id,
                end_mileage=980,
                end_fuel_level="1/4",
                miles_driven=80,
                created_at=datetime(2026, 5, 20, 13, 0, 0),
            ),
            PostTrip(
                pretrip_id=current_pretrip.id,
                end_mileage=1120,
                end_fuel_level="3/4",
                miles_driven=120,
                created_at=datetime(2026, 5, 20, 22, 0, 0),
            ),
            PostTrip(
                pretrip_id=previous_day_pretrip.id,
                end_mileage=50908,
                miles_driven=108,
                created_at=datetime(2026, 5, 19, 18, 0, 0),
            ),
            PostTrip(
                pretrip_id=older_pretrip.id,
                end_mileage=90790,
                miles_driven=90,
                created_at=datetime(2026, 5, 18, 18, 0, 0),
            ),
            PostTrip(
                pretrip_id=imported_odometer_pretrip.id,
                end_mileage=999999,
                miles_driven=17465,
                created_at=datetime(2026, 5, 17, 18, 0, 0),
            ),
            fuel_log,
        ])
        db.session.flush()
        current_pretrip_id = current_pretrip.id
        fuel_log_id = fuel_log.id
        db.session.commit()

    login(client, "dated_print_driver")
    logs_page = client.get(f"/driver_logs?date={selected_date.isoformat()}")
    assert logs_page.status_code == 200
    assert b"driver-ledger-active" in logs_page.data
    assert b"@media (min-width: 768px)" in logs_page.data
    assert b"#pageContent > .navbar {" in logs_page.data
    assert b"z-index: 2500;" in logs_page.data
    assert b"#pageContent > .navbar .dropdown-menu {" in logs_page.data
    assert b"z-index: 2510;" in logs_page.data
    assert b'body.md-shell .navbar .nav-link[aria-label="Recent activity"].d-md-none' in logs_page.data
    assert b"display:none !important;" in logs_page.data
    assert b"body.driver-ledger-active .driver-active-wait-action" in logs_page.data
    assert b"background:rgba(91,157,255,.08)" in logs_page.data
    assert b"body.driver-ledger-active .md-driver-bottom-nav {\n        display:none !important;" in logs_page.data
    assert b"ROUTE HISTORY" in logs_page.data
    assert b"DRIVER LOG" in logs_page.data
    assert b"DRIVER LOGS" not in logs_page.data
    assert b"AUDIT LEDGER" not in logs_page.data
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
    assert b"Numbered Stops" in logs_page.data
    assert b"Route Miles" in logs_page.data
    assert b"grid-template-columns:repeat(4,minmax(0,1fr))" in logs_page.data
    assert b".md-ledger-row:target" in logs_page.data
    assert b".md-ledger-list:target" in logs_page.data
    assert b".md-ledger-row.has-warning {\n      border-color:rgba(255,178,36,.26);\n      box-shadow:none;" in logs_page.data
    assert b'href="#route-stops" aria-label="View numbered stops"' in logs_page.data
    assert f'href="/pretrip_printable/{current_pretrip_id}" aria-label="View route mileage inspection record"'.encode() in logs_page.data
    assert b'href="/list_pretrips?truck_number=BT-1" aria-label="View truck inspections"' in logs_page.data
    assert f'href="#route-stop-{fuel_log_id}" aria-label="View fuel details"'.encode() in logs_page.data
    assert b'id="route-stops" class="md-ledger-list md-flow-window"' in logs_page.data
    assert f'id="route-stop-{fuel_log_id}"'.encode() in logs_page.data
    assert b"120 mi" in logs_page.data
    assert "▲ +12 mi".encode() in logs_page.data
    assert b"md-route-audit-slot md-route-mile-slot" in logs_page.data
    assert b"app-delta app-delta--up font-mono md-mileage-delta" in logs_page.data
    assert b".md-route-mile-slot .md-mileage-delta.app-delta--up" in logs_page.data
    assert b"color:var(--status-green)" in logs_page.data
    assert b"--status-green:oklch(0.72 0.17 150)" in logs_page.data
    assert b"--status-red:oklch(0.65 0.22 25)" in logs_page.data
    assert b"Avg: 99 mi/day" in logs_page.data
    assert b"17,465 mi/day" not in logs_page.data
    assert b"No prior day" not in logs_page.data
    assert b"Start 1,000" in logs_page.data
    assert b"End 1,120" in logs_page.data
    assert b"<span>Fuel</span>" in logs_page.data
    assert b"1/4" in logs_page.data
    assert b"1 stop" in logs_page.data
    assert b"Start:" in logs_page.data
    assert b"Previous PostTrip truck BT-1" in logs_page.data
    assert b"1,045 mi" in logs_page.data
    assert b"Stop <strong>1</strong>" in logs_page.data
    assert b"Stop #</span><strong>1 of 1" in logs_page.data
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
    action_start = logs_page.data.index(b'<div class="md-action-rail')
    action_end = logs_page.data.index(b"</div>", action_start)
    action_row = logs_page.data[action_start:action_end]
    assert b'data-md-icon="record-stop"' in action_row
    assert b'data-md-icon="add-stop"' not in action_row
    assert b'data-md-icon="print-route"' in action_row
    assert b'data-md-icon="save-pdf"' in action_row
    assert b"md-flow-action-tab" not in action_row
    assert b"md-ledger-primary" in action_row
    assert b"md-ledger-utility" in action_row
    assert b"Add Missed Stop" not in action_row
    assert b'<span class="md-btn-icon">+</span>' not in action_row
    assert '<span class="md-btn-icon">↧</span>'.encode() not in action_row
    assert b'<span class="md-btn-icon">P</span>' not in action_row
    assert '<span class="md-btn-icon">↓</span>'.encode() not in action_row
    assert (
        f'href="/driver_logs_print?date={selected_date.isoformat()}" class="md-row-action"><span class="md-btn-icon">O</span> View'.encode()
        in logs_page.data
    )
    assert b'<details class="md-row-more-actions">' in logs_page.data
    assert b"Stop actions" in logs_page.data

    first_history_page = client.get(f"/driver_logs?date={(selected_date - timedelta(days=2)).isoformat()}")
    assert first_history_page.status_code == 200
    assert b"90 mi" in first_history_page.data
    assert b"No prior day" in first_history_page.data
    assert "▲ +".encode() not in first_history_page.data
    assert "▼ -".encode() not in first_history_page.data
    assert b"17,465 mi/day" not in first_history_page.data

    print_page = client.get(f"/driver_logs_print?date={selected_date.isoformat()}")
    assert print_page.status_code == 200
    assert b"Raleigh East" in print_page.data
    assert selected_date.isoformat().encode() in print_page.data

    pdf_response = client.get(f"/driver_logs_print/attachment?date={selected_date.isoformat()}")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["Content-Type"] == "application/pdf"
    assert b"DRIVER LOG SHEET" in pdf_response.data
    assert_driver_route_sheet_output(pdf_response.data)
    assert b"1. STOP TIMELINE" in pdf_response.data
    assert b"Location" in pdf_response.data
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
    # Capture failed, so the sheet renders the unsigned signature block without
    # the old "Not yet signed" placeholder (only-captured-facts printout).
    assert b"Driver Signature" in print_page.data
    assert b"Not yet signed" not in print_page.data


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
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

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
            PostTrip(pretrip_id=pretrip.id, end_mileage=1100, miles_driven=100),
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


def test_manager_archives_damage_report_without_deleting_evidence(client, app):
    from datetime import datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DamagePhoto, DamageReport

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
        db.session.flush()
        db.session.add(DamagePhoto(
            damage_report_id=report.id,
            stage="before",
            filename="old-proof.jpg",
            original_filename="old-proof.jpg",
            content_type="image/jpeg",
        ))
        db.session.commit()
        report_id = report.id

    login(client, "manager1")
    review = client.get("/manager/review")
    assert review.status_code == 200
    assert f"/manager/damage-reports/{report_id}/delete".encode() in review.data

    detail = client.get(f"/manager/damage-reports/{report_id}")
    assert detail.status_code == 200
    assert b"Archive Report" in detail.data

    archived = client.post(
        f"/manager/damage-reports/{report_id}/delete",
        data={"next": "/manager/review"},
        follow_redirects=False,
    )
    assert archived.status_code == 302
    assert archived.headers["Location"].endswith("/manager/review")

    with app.app_context():
        from app.models import ActivityEvent, AuditEvent, DamageReport

        saved = DamageReport.query.get(report_id)
        assert saved is not None
        assert saved.status == "closed"
        assert saved.resolved_at is not None
        assert len(saved.photos) == 1
        assert saved.photos[0].filename == "old-proof.jpg"
        audit = AuditEvent.query.filter_by(
            target_type="damage_report", target_id=report_id, action="manager_archived"
        ).one()
        assert "Old damage report test" in audit.before_values
        assert "old-proof.jpg" in audit.after_values
        activity = ActivityEvent.query.filter_by(
            target_type="damage_report", target_id=report_id, action="archived"
        ).one()
        assert activity.title == "Damage report archived by manager"

    review_after = client.get("/manager/review")
    assert review_after.status_code == 200
    assert f"/manager/damage-reports/{report_id}/delete".encode() not in review_after.data
    detail_after = client.get(f"/manager/damage-reports/{report_id}")
    assert detail_after.status_code == 200


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

    archive_create_response = client.post(
        "/damage_reports/new",
        data={
            "truck_number": "T4",
            "trailer_number": "TR4",
            "plant_name": "KP",
            "stage": "before",
            "move_reference": "Dock 8",
            "description": "Mirror crack",
            "photo": (BytesIO(b"archive damage image"), "archive-damage.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert archive_create_response.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        archived_report = DamageReport.query.filter_by(description="Mirror crack").one()
        archive_report_id = archived_report.id
        assert len(archived_report.photos) == 1

    archive_detail = client.get(f"/damage_reports/{archive_report_id}")
    assert archive_detail.status_code == 200
    assert b"Archive Report" in archive_detail.data
    assert b"Delete this damage report" not in archive_detail.data

    archive_response = client.post(f"/damage_reports/{archive_report_id}/delete", follow_redirects=False)
    assert archive_response.status_code == 302

    with app.app_context():
        from app.models import ActivityEvent, AuditEvent, DamageReport

        archived_report = DamageReport.query.get(archive_report_id)
        assert archived_report is not None
        assert archived_report.status == "closed"
        assert archived_report.resolved_at is not None
        assert len(archived_report.photos) == 1
        audit = AuditEvent.query.filter_by(
            target_type="damage_report", target_id=archive_report_id, action="driver_archived"
        ).one()
        assert "archive-damage.jpg" in audit.after_values
        activity = ActivityEvent.query.filter_by(
            target_type="damage_report", target_id=archive_report_id, action="archived"
        ).one()
        assert activity.title == "Damage report archived"

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
    assert b"md-shell md-standalone" in activity.data
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



def test_mobile_dashboard_stop_clicks_open_audit_ledger_stop_anchor(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("driver_stop_anchor", "driver-stop-anchor@example.com", "driver")
        route_date = date.today()
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            arrive_time=f"{route_date.isoformat()} 10:15:00",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(client, "driver_stop_anchor")
    page = client.get("/mobile")

    expected_href = f"/driver_logs?date={route_date.isoformat()}#route-stop-{log_id}".encode()
    assert page.status_code == 200
    assert expected_href in page.data
    assert f"/view_driver_log/{log_id}".encode() not in page.data


def test_mobile_dashboard_renders_widescreen_ops_workspace(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DamageReport, DriverLog, PlantTransfer, PlantTransferLine, PreTrip

        driver = create_user(
            "desktop_ops_driver",
            "desktop-ops@example.com",
            "driver",
            first_name="Desk",
            last_name="Driver",
            department="ST4",
        )
        route_date = date.today()
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="123",
            trailer_number="TR-Desk",
            pretrip_date=route_date,
            shift="1st",
            start_mileage=120400,
            start_fuel_level="3/4",
        )
        log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="Trim DC",
            load_size="Empty",
            depart_load_size="PPL Parts",
            arrive_time=f"{route_date.isoformat()} 07:10:00",
            downtime_reason="Waiting on dock door 4.",
        )
        transfer = PlantTransfer(
            user_id=driver.id,
            transfer_number="TRX-DESK",
            transfer_date=route_date,
            ship_from="Trim DC",
            ship_to="PPL",
            trailer_number="TR-Desk",
            driver_name="Desk Driver",
            loaded_by="Dock Lead",
            transfer_time="07:44",
        )
        transfer.lines.append(
            PlantTransferLine(
                line_number=1,
                side="left",
                part_number="PART-900",
                skids="10",
                quantity="1600",
                remarks="Lot A19 | LP IDs: LP-778 LP-779",
            )
        )
        db.session.add_all([pretrip, log, transfer])
        db.session.flush()
        damage = DamageReport(
            reported_by_id=driver.id,
            driver_log_id=log.id,
            truck_number="123",
            trailer_number="TR-Desk",
            plant_name="Trim DC",
            stage="after",
            move_reference="Stop 1 / dock 4",
            description="Desk scratch on dock door.",
            status="submitted",
        )
        db.session.add(damage)
        db.session.commit()

    login(client, "desktop_ops_driver")
    page = client.get("/mobile")
    assert page.status_code == 200
    assert b"desktop-header-context" in page.data
    assert b"@media (min-width: 640px) and (min-height: 560px)" in page.data
    assert b"@media (min-width: 1280px) and (min-height: 560px)" in page.data
    assert b"--lov-bg: oklch(0.16 0.018 250)" in page.data
    assert b"--lov-accent: oklch(0.72 0.08 190)" in page.data
    assert b".board-only-shell .desk-detail-stack" in page.data
    assert b".board-only-shell .desktop-ops-grid" in page.data
    assert b"flex-direction:column" in page.data
    assert b"display:contents" in page.data
    assert b"grid-template-columns:minmax(0, 1fr)" in page.data
    assert b".board-only-shell .desk-staged-actions" in page.data
    assert b".board-only-shell .desk-stop-marker" in page.data
    assert b".board-only-shell .desk-active-stop-card" in page.data
    assert b"desktopActiveStopBreathe" not in page.data
    assert b"desktopActiveStopHalo" not in page.data
    assert b".board-only-shell .desk-ops-row.tone-active" in page.data
    assert b".board-only-shell .desk-ops-row.tone-active::after" in page.data
    assert b"animation:boardOpsRowGlowBreath 4.6s ease-in-out infinite" in page.data
    assert b"@keyframes boardOpsRowGlowBreath" in page.data
    assert b"0 0 26px rgba(43,213,118,.08)" in page.data
    assert b".board-only-shell .desk-staged-actions .desk-current-cta.is-go" in page.data
    assert b"animation:boardActionGlowBreath 2.8s ease-in-out infinite" in page.data
    assert b"@keyframes boardActionGlowBreath" in page.data
    assert b"min-width:176px" in page.data
    assert b"min-height:44px" in page.data
    assert b"border-color:rgba(43,213,118,.58)" in page.data
    assert b"justify-content:center" in page.data
    assert b"font-feature-settings:\"ss01\", \"cv11\"" in page.data
    assert b"--md-mono: 'JetBrains Mono', 'IBM Plex Mono'" in page.data
    assert b".md-driver-bottom-nav { display:none !important; }" in page.data
    assert b".board-only-shell main > .ops-console { display:none; }" in page.data
    assert b"setupDesktopOpsWorkspace" in page.data
    assert b"data-desktop-select-template" in page.data
    assert b"nearestScrollableParent" in page.data
    assert b"scrollWorkAreaIntoView" in page.data
    assert b"desk-work-focus-pulse" in page.data
    assert b"desk-work-focus-pulse--alert" in page.data
    assert b"desktopAlertFocusPulse" in page.data
    assert b"isAlertDesktopTarget" in page.data
    assert b".driver-ops-shell.board-only-shell" in page.data
    assert b"body .driver-ops-shell.board-only-shell .md-flow-window" in page.data
    assert b"max-height:none !important" in page.data
    assert b"overflow:visible !important" in page.data

    workspace_start = page.data.index(b'<section class="desktop-ops-workspace"')
    workspace = page.data[workspace_start: page.data.index(b"<script>", workspace_start)]
    assert b"Route Board" in workspace
    assert b"Current Stop" in workspace
    assert b"<strong>Trim DC</strong>" in workspace
    assert b"<span>Stop</span>" in workspace
    assert b"<strong>Stop 1</strong>" in workspace
    assert b"desk-active-stop-card" in workspace
    assert b"desk-staged-actions" in workspace
    assert b"Record Departure" in workspace
    assert b"desk-work-tabs" in workspace
    assert b"Route Packet" in workspace
    assert b"data-desktop-mode-template=\"route-packet\"" in workspace
    assert b"data-desktop-mode-template=\"documents\"" in workspace
    assert b"data-desktop-mode-template=\"issues\"" in workspace
    assert b"data-desktop-mode-template=\"inspections\"" in workspace
    assert b"data-desktop-mode-template=\"log\"" in workspace
    assert b"Stop 1 / Trim DC" not in workspace
    assert b"<span>Transfer Sheets</span>" not in workspace
    assert b"<span>Plant Baseline</span>" not in workspace
    assert b"desktop-main-column" in workspace
    assert workspace.index(b"desktop-ops-board") < workspace.index(b"desktop-main-column")
    assert workspace.index(b"desktop-main-column") < workspace.index(b"desktop-metrics-strip")
    assert b'data-desktop-row' in workspace
    assert b'data-desktop-detail-template="desktop-transfer-' in workspace
    assert b'data-desktop-detail-template="desktop-documents-route"' in workspace
    assert b"TRX-DESK" in workspace
    assert b"desk-overview-card" in workspace
    assert b"Stop Summary" not in workspace
    assert b"Packet Readiness" in workspace
    assert b"Document Types" in workspace
    assert b"Documents" in workspace
    assert b"Attach Document" in workspace
    assert b"Take Photo" in workspace
    assert b"Upload File/Image" in workspace
    assert b"data-route-document-attach" in workspace
    assert b"data-document-row-feedback" in workspace
    assert b'data-document-type="driver_credential"' in workspace
    assert b'data-document-type="truck_document"' in workspace
    assert b"No driver credential attached." in workspace
    assert b"No truck document attached." in workspace
    assert b"BOL" in workspace
    assert b"Transfer Sheet" in workspace
    assert b"Open route audit" not in workspace
    assert b"LP-778 LP-779" in workspace
    assert b"Paperwork / Proof" not in workspace
    assert b"Attach BOL / transfer sheet" not in workspace
    assert b"Take proof photo" not in workspace
    assert b"Upload document image" not in workspace
    assert b"Add damage photo" not in workspace
    assert b"desk-overview-primary-action" in workspace
    assert b"Route</h4>" not in workspace
    assert b"Review</h4>" not in workspace
    assert b"Scan cargo" not in workspace
    assert b"Operations Desk" not in workspace
    assert b"Audit readiness" not in workspace
    assert b"Evidence Coverage" not in workspace
    assert b"desk-overview-timing" in workspace
    assert b"Truck inspections" in workspace
    assert b"Fuel at start" in workspace
    assert b"3/4" in workspace
    assert b"Desk scratch on dock door." in workspace
    assert b"Pickup source unknown" not in workspace
    assert b"Destination needs confirmation" not in workspace
    assert b"Earlier stop" not in workspace
    assert b"Next stop" not in workspace
    assert b"<h3>Documents</h3>" not in workspace
    assert b"<h3>Inspections</h3>" not in workspace

    stop_template_start = workspace.index(b'data-desktop-detail-template="desktop-stop-')
    stop_template = workspace[stop_template_start: workspace.index(b"</template>", stop_template_start)]
    assert b"desk-overview-card" in stop_template
    assert b"Arrive" in stop_template
    assert b"Depart" in stop_template
    assert b"Wait" in stop_template
    assert b"Route Packet:" in stop_template
    assert b"Attach to Route Packet" in stop_template
    assert b"desk-paperwork-section" not in stop_template
    assert b"desk-preview-strip" not in stop_template
    assert b"Transfer Sheet" not in stop_template
    assert b"Proof Photo" not in stop_template
    assert b"Load / Transfer Detail" not in stop_template
    assert b"desk-detail-section" not in stop_template


def test_mobile_dashboard_does_not_render_permanent_packet_workflows_strip(client, app):
    with app.app_context():
        create_user("packet_entry_driver", "packet-entry@example.com", "driver")

    login(client, "packet_entry_driver")
    response = client.get("/mobile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Packet Workflows" not in body
    assert 'class="card packet-workflows"' not in body
    assert 'id="packet-workflows"' not in body
    assert '<div class="md-flow-top-actions"' not in body
    assert "md-flow-action-tab" not in body
    assert "Camera</strong>" not in body
    assert "PreTrip and Shift</strong>" not in body
    assert "Sheet</strong>" not in body


def test_driver_reports_hub_lists_report_choices_with_correct_destinations(client, app):
    with app.app_context():
        create_user("reports_hub_driver", "reports-hub@example.com", "driver")

    login(client, "reports_hub_driver")
    response = client.get("/reports")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<h1>Reports</h1>" in body
    assert "Driver Logs stay as the route ledger." in body
    assert "0 Recent" in body
    choices_start = body.index('<section class="driver-report-list"')
    choices = body[choices_start: body.index("</section>", choices_start)]
    assert 'href="/driver_logs"' not in choices
    assert "driver-report-code" not in choices

    expected_choices = {
        "Fuel / Low Fuel": 'href="/ifta-worksheet/new"',
        "Physical Damage": 'href="/damage_reports/new"',
        "Crash / Safety Incident": 'href="/accident-incident/new"',
        "Truck Issue / Maintenance": 'href="/new_driving_log?report_type=truck_issue"',
        "Route Note / Other": 'href="/new_driving_log?report_type=route_note"',
    }
    for label, href in expected_choices.items():
        assert label in choices
        assert href in choices
        path = href.removeprefix('href="').removesuffix('"')
        assert client.get(path).status_code == 200

    fuel_label_start = choices.index("Fuel / Low Fuel")
    fuel_link_start = choices.rfind("<a ", 0, fuel_label_start)
    fuel_link = choices[fuel_link_start: choices.index("</a>", fuel_label_start)]
    assert 'href="/ifta-worksheet/new"' in fuel_link
    assert 'href="/damage_reports/new"' not in fuel_link


def test_widescreen_driver_actions_have_reports_entry_without_report_shortcut_row(client, app):
    with app.app_context():
        from datetime import date

        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("wide_reports_driver", "wide-reports@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=date.today(),
                plant_name="RE",
                load_size="Empty",
                arrive_time="08:00",
            )
        )
        db.session.commit()

    login(client, "wide_reports_driver")
    response = client.get("/mobile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a class="logout-link desktop-work-link" href="/reports">Reports</a>' in body
    assert '<a class="logout-link" href="/logout">Logout</a>' in body
    assert ".board-only-shell .topbar," not in body
    assert ".logout-link { display: none; }" not in body
    assert 'href="/damage_reports">Physical Damage</a>' not in body
    assert 'href="/ifta-worksheet/new">Fuel Records</a>' not in body


def test_mobile_dashboard_focuses_latest_stop_when_no_current_stop(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user(
            "desktop_latest_stop_driver",
            "desktop-latest-stop@example.com",
            "driver",
            first_name="Latest",
            last_name="Stop",
            department="ST4",
        )
        route_date = date.today()
        raleigh_east = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="Raleigh East",
            load_size="Empty",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time=f"{route_date.isoformat()} 13:42:00",
            depart_time="13:54",
        )
        ppl = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PPL",
            load_size="Empty",
            depart_load_size="Barden Plant Load",
            arrive_time=f"{route_date.isoformat()} 14:12:00",
            depart_time="14:26",
        )
        barden = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="Barden Plant",
            load_size="Barden Plant Load",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time=f"{route_date.isoformat()} 15:02:00",
            depart_time="15:14",
        )
        db.session.add_all([raleigh_east, ppl, barden])
        db.session.commit()
        raleigh_east_id = raleigh_east.id
        ppl_id = ppl.id
        barden_id = barden.id

    login(client, "desktop_latest_stop_driver")
    page = client.get("/mobile")
    assert page.status_code == 200

    workspace_start = page.data.index(b'<section class="desktop-ops-workspace"')
    workspace = page.data[workspace_start: page.data.index(b"<script>", workspace_start)]
    active_card_start = workspace.index(b"desk-active-stop-card")
    active_card = workspace[active_card_start: workspace.index(b"desktop-metrics-strip", active_card_start)]
    assert b"<strong>Barden Plant</strong>" in active_card
    assert b"<strong>Stop 3</strong>" in active_card
    assert b"<strong>Raleigh East</strong>" not in active_card
    assert (
        f'data-detail-template="desktop-stop-{barden_id}" data-desktop-default="true"'.encode()
        in workspace
    )
    assert (
        f'data-detail-template="desktop-stop-{raleigh_east_id}" data-desktop-default="true"'.encode()
        not in workspace
    )
    assert (
        f'data-detail-template="desktop-stop-{ppl_id}" data-desktop-default="true"'.encode()
        not in workspace
    )
    assert b"Transfer sheet needed" in workspace
    assert b"EN ROUTE" in workspace
    assert b"LOADED" in workspace
    assert b"DROPPED" in workspace
    assert b'data-detail-template="desktop-route-packet-transfer-sheet"' in workspace
    assert b'data-desktop-detail-template="desktop-route-packet-transfer-sheet"' in workspace
    assert b'data-desktop-select-template="desktop-route-packet-transfer-sheet"' in workspace
    assert b"1 required flagged" in workspace
    assert b"has no transfer sheet or route transfer record attached" in workspace
    assert b"Missing transfer sheet" in workspace
    assert b"No open issues" not in workspace


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
    assert b'data-flow-open-panel="depart"' in page.data
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
    assert (
        b"Dock time:" in today_report.data
        or b"Long wait" in today_report.data
        or b"Extended wait" in today_report.data
    )
    assert b"Edit" in today_report.data
    assert b"Pickup" not in today_report.data
    assert b"Depart and Load" in today_report.data
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
        "<strong>BR</strong><span>Breaks</span>",
        "<strong>FL</strong><span>Fuel</span>",
        "<strong>SV</strong><span>Service</span>",
        "<strong>IN</strong><span>Inspections</span>",
    ]
    pages = [
        ("/mobile", "Home"),
        ("/mobile/breaks", "Breaks"),
        ("/ifta-worksheet/new", "Fuel"),
        ("/mobile?flow=maintenance", "Service"),
        ("/list_pretrips", "Inspections"),
        ("/new_pretrip", "Inspections"),
        ("/profile", "Home"),
    ]

    for path, active_label in pages:
        response = client.get(path)
        assert response.status_code == 200
        body = response.data.decode()
        # Exactly one bottom action bar, and NO separate Quick Log row.
        assert body.count('<nav class="md-driver-bottom-nav"') == 1
        assert "md-quick-log" not in body
        nav_start = body.index('<nav class="md-driver-bottom-nav"')
        nav_end = body.index("</nav>", nav_start)
        nav = body[nav_start:nav_end]
        positions = [nav.index(item) for item in expected_items]
        assert positions == sorted(positions)
        # Actions land on distinct workflow surfaces; Break is a POST button.
        assert 'href="/list_pretrips"' in nav
        assert 'href="/ifta-worksheet/new"' in nav
        assert 'href="/mobile?flow=maintenance"' in nav
        assert "report_type=fuel" not in nav
        assert "report_type=truck_issue" not in nav
        # Break opens the deliberate Break Log screen; start/end happen there.
        assert 'href="/mobile/breaks"' in nav
        assert "/mobile/break/start" not in nav
        assert "/mobile/break/end" not in nav
        if path == "/mobile/breaks":
            assert "Start a break" in body
            assert 'value="Off-duty"' in body
            assert 'value="Sleeper berth"' in body
            assert "On-Duty Wait" in body
        if path == "/mobile?flow=maintenance":
            assert "No active service" in body
            assert "Add service note" in body
            assert "data-ryder-form-wrap hidden" in body
        # Logs and Reports are no longer in the bottom bar.
        assert "<strong>DL</strong>" not in nav
        assert "<strong>RP</strong>" not in nav
        # Exactly one navigated tab is active for these pages.
        assert nav.count('class="md-nav-link active"') == 1
        active_start = nav.index('class="md-nav-link active"')
        active_end = nav.index("</a>", active_start)
        assert f"<span>{active_label}</span>" in nav[active_start:active_end]
        assert '<nav class="bottom-nav"' not in body
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
    assert b"Finalize Route" in mobile.data
    assert b"here now" not in mobile.data
    assert b"Likely destination" not in mobile.data
    assert b"Source: historical pattern" not in mobile.data
    assert b"Paint Central" in mobile.data
    assert b"Out: No Pickup" in mobile.data

    driver_print = client.get("/driver_logs_print")
    assert driver_print.status_code == 200
    assert b"Route completed and awaiting final review" in driver_print.data
    assert b"Route open / not finalized" not in driver_print.data

    client.get("/logout")
    login(client, "completed_route_manager")
    manager_review = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={route_date.isoformat()}")
    assert manager_review.status_code == 200
    assert b"Route Status:</strong> Completed" in manager_review.data
    assert b"The route is complete and awaiting final review" in manager_review.data
    assert b"still marked open" not in manager_review.data
    assert b"Current Active Stop" not in manager_review.data


def test_mobile_dashboard_defaults_to_today_when_today_is_empty(client, app):
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
    assert b"REPLAY MODE" not in page.data
    assert b"ACTIONS DISABLED" not in page.data
    assert b"Last Route Replay" not in page.data
    assert b"Last Route / Route Replay" not in page.data
    assert b"Live route actions are hidden" not in page.data
    assert b"START DAY" in page.data
    assert b"Today \xc2\xb7 0 stops" in page.data
    assert b"Start Day" in page.data
    assert b"No stops logged yet today. Start day by recording the first stop." in page.data
    assert b"1 stop" not in page.data
    assert b"Raleigh East" not in page.data
    assert f"/driver_logs?date={route_date.isoformat()}".encode() not in page.data
    assert b'data-flow-panel-title="Add Stop"' in page.data

    fragment = client.get("/mobile/route-map-fragment")
    assert fragment.status_code == 200
    assert b"START DAY" in fragment.data
    assert b"No stops logged yet today. Start day by recording the first stop." in fragment.data
    assert b"Raleigh East" not in fragment.data


def test_mobile_dashboard_ignores_stale_open_pretrip_when_off_duty(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("stale_pretrip_driver", "stale-pretrip@example.com", "driver", first_name="Stale", last_name="PreTrip")
        today = date.today()
        old_route_date = today - timedelta(days=2)
        pretrip = PreTrip(
            user_id=driver.id,
            truck_number="ST2",
            pretrip_date=old_route_date,
            start_mileage=379164,
        )
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(
            ShiftRecord(
                user_id=driver.id,
                pretrip_id=pretrip.id,
                start_time=datetime.combine(old_route_date, datetime.min.time()).replace(hour=7),
                end_time=datetime.combine(old_route_date, datetime.min.time()).replace(hour=17),
            )
        )
        db.session.add_all(
            [
                DriverLog(
                    driver_id=driver.id,
                    date=old_route_date,
                    plant_name="RE",
                    load_size="Empty",
                    arrive_time=f"{old_route_date.isoformat()} 07:30:00",
                    depart_time="08:00",
                ),
                DriverLog(
                    driver_id=driver.id,
                    date=old_route_date,
                    plant_name="PPL",
                    load_size="Parts",
                    depart_load_size="Empty",
                    arrive_time=f"{old_route_date.isoformat()} 09:15:00",
                    depart_time="09:45",
                ),
            ]
        )
        db.session.commit()

    login(client, "stale_pretrip_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"START DAY" in page.data
    assert b"Today \xc2\xb7 0 stops" in page.data
    assert b"No stops logged yet today. Start day by recording the first stop." in page.data
    assert b"COMPLETE" not in page.data
    assert b"Raleigh East" not in page.data
    assert b"PPL" not in page.data


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
    # Finalized route: non-mutating CTA only (rule I).
    assert b"View Route Packet" in page.data
    assert b"Finalize Route" not in page.data
    assert b"Record Departure" not in page.data
    assert b"Add Stop" not in page.data
    assert b"Proof Needed" not in page.data


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
    assert 'data-flow-open-panel="depart"' in body
    assert "data-depart-wizard" in body
    assert body.count('data-flow-panel-title="Add Stop"') <= 1
    assert 'name="next" value="mobile"' in body
    assert "md-flow-work-scrim" in body
    assert "Did you get unloaded?" in body
    assert "driver-active-wait-action" in body
    assert "animation:activeStopWaitBreath 4.6s ease-in-out infinite" in body
    assert "@keyframes activeStopWaitBreath" in body
    assert "Record Departure" in body
    assert "md-flow-primary-cta" in body
    assert "Required driver action" in body
    assert "record departure" in body
    assert '<div class="md-flow-top-actions"' not in body
    assert "md-flow-action-tab" not in body
    assert 'flow-status status-attention">NEEDS DEPARTURE' not in body
    assert '<div class="md-flow-ticker" aria-hidden="true">' not in body
    assert ".md-flow-board .md-flow-row.tone-active" in body
    assert "animation: activebreathe 4.6s ease-in-out infinite" in body
    assert "@keyframes activebreathe" in body
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
    assert ".md-flow-action-tab::before" not in body
    assert "animation: actionDotPulse 1.9s ease-in-out infinite" not in body
    assert ".md-flow-action-tab.is-next-required:not(.add-stop-action)" not in body
    assert "animation: actionButtonBreath 2.6s ease-in-out infinite" not in body
    assert "@keyframes actionButtonBreath" not in body
    assert "addStopBreath 2.45s ease-in-out infinite" in body
    assert "@keyframes addStopBreath" in body
    assert "animation: primaryFlowActionBreath 2.6s ease-in-out infinite" in body
    assert "@keyframes primaryFlowActionBreath" in body
    assert "@keyframes actionDotPulse" not in body
    assert "grid-template-columns: 9px max-content" not in body
    assert "border: 1px solid rgba(91,157,255,.28)" not in body
    assert "linear-gradient(180deg, rgba(47,109,240,.22)" not in body
    assert "inset 0 0 18px rgba(91,157,255,.04)" not in body
    assert ".md-flow-track::-webkit-scrollbar { display: none; width: 0; height: 0; }" in body
    assert "scrollbar-color: rgba(91,157,255,.34)" not in body
    assert "ROUTE LOGS &nbsp; PLANT TRANSFERS" not in body
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
        # A real closed route: delivered a load (arrived with cargo, departed
        # empty), so this is an actual route close -> End Shift, not an empty start.
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Trim DC Load",
                depart_load_size="Empty",
                arrive_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                depart_time="08:20",
            )
        )
        db.session.commit()

    login(client, "posttrip_due_driver")
    page = client.get("/mobile")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    # All stops closed, PostTrip missing: the CTA is End Shift, NOT PostTrip Due.
    # PostTrip becomes required inside the End Shift flow (rules 4 & 5).
    assert b"End Shift" in page.data
    assert b"PostTrip Due" not in page.data
    assert b"Finalize Route" not in page.data
    assert b"Ready To Finalize" not in page.data
    assert "POSTTRIP NEEDED" not in body
    assert "<strong>TRUCK</strong>" not in body


def test_mobile_dashboard_does_not_show_finalize_after_closed_delivery_without_posttrip(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog

        driver = create_user("closed_delivery_no_posttrip", "closed-delivery-no-posttrip@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Raleigh East Load",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                depart_time="08:20",
            )
        )
        db.session.commit()
        driver_id = driver.id

    login(client, "closed_delivery_no_posttrip")
    page = client.get("/mobile")

    assert page.status_code == 200
    # The CTA is End Shift (which uses the end-route form), but it must NOT
    # finalize without a PostTrip...
    assert b"End Shift" in page.data
    assert b"Finalize Route" not in page.data
    assert b"Sign & Submit Route" not in page.data

    response = client.post("/mobile/end-route", follow_redirects=True)

    # ...instead it routes the driver to complete the PostTrip first.
    assert response.status_code == 200
    assert b"Complete PostTrip before finishing the route." in response.data
    with app.app_context():
        assert ActivityEvent.query.filter_by(
            user_id=driver_id,
            category="eod",
            action="finalized",
            target_type="end_of_day",
        ).count() == 0


def test_mobile_dashboard_active_shift_without_stops_keeps_add_stop_primary(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import PreTrip, ShiftRecord

        driver = create_user("route_started_driver", "route-started@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()))
        db.session.commit()

    login(client, "route_started_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"PostTrip Due" not in page.data
    assert b'<a class="md-flow-primary-cta add-stop-action"' in page.data
    assert b"<strong>Add Stop</strong>" in page.data
    assert b'<div class="md-flow-top-actions"' not in page.data
    assert b"md-flow-action-tab" not in page.data


def test_mobile_dashboard_active_between_stops_prioritizes_add_stop_over_posttrip(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("between_stops_driver", "between-stops@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Raleigh West Load",
                arrive_time="08:00",
                depart_time="08:15",
                created_at=datetime.utcnow(),
            ),
        ])
        db.session.commit()

    login(client, "between_stops_driver")
    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"PostTrip Due" not in page.data
    assert b'<a class="md-flow-primary-cta add-stop-action"' in page.data
    # In transit with cargo: destination-named continuation (D) or add-destination (E).
    assert b"Arrive at Raleigh West" in page.data or b"Add Destination Stop" in page.data
    assert b"Finalize Route" not in page.data
    assert b'<div class="md-flow-top-actions"' not in page.data
    assert b"md-flow-action-tab" not in page.data


def test_end_of_day_summary_shows_posttrip_due_when_finalizing_without_posttrip(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("eod_missing_posttrip_driver", "eod-missing-posttrip@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time="08:00",
                depart_time="08:15",
                created_at=datetime.utcnow(),
            ),
        ])
        db.session.commit()
        pretrip_id = pretrip.id

    login(client, "eod_missing_posttrip_driver")
    page = client.get("/end_of_day_summary")

    assert page.status_code == 200
    assert b"POSTTRIP DUE" in page.data
    assert b"Complete PostTrip before final route closeout." in page.data
    assert f"/do_posttrip/{pretrip_id}".encode() in page.data


def test_end_of_day_summary_hides_posttrip_due_after_posttrip_complete(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user("eod_posttrip_complete_driver", "eod-posttrip-complete@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            PostTrip(pretrip_id=pretrip.id, end_mileage=379025, miles_driven=25),
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time="08:00",
                depart_time="08:15",
                created_at=datetime.utcnow(),
            ),
        ])
        db.session.commit()

    login(client, "eod_posttrip_complete_driver")
    page = client.get("/end_of_day_summary")

    assert page.status_code == 200
    assert b"POSTTRIP DUE" not in page.data
    assert b"Complete PostTrip before final route closeout." not in page.data


def test_mobile_dashboard_allows_finalize_after_posttrip_complete(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        driver = create_user("posttrip_complete_driver", "posttrip-complete@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(PostTrip(pretrip_id=pretrip.id, end_mileage=379025, miles_driven=25))
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
        pretrip_id = pretrip.id
        driver_id = driver.id

    login(client, "posttrip_complete_driver")
    posttrip_record = client.get(f"/do_posttrip/{pretrip_id}")
    assert posttrip_record.status_code == 200
    assert b"PostTrip Record" in posttrip_record.data

    page = client.get("/mobile")

    assert page.status_code == 200
    assert b"Finalize Route" in page.data
    assert b'action="/mobile/end-route" method="POST"' in page.data
    assert b"PostTrip Due" not in page.data
    assert b"Ready To Finalize" not in page.data

    response = client.post("/mobile/end-route", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import ActivityEvent
        from app.services.route_context import build_route_context

        assert ActivityEvent.query.filter_by(
            user_id=driver_id,
            category="eod",
            action="finalized",
            target_type="end_of_day",
        ).count() == 1
        assert build_route_context(driver_id=driver_id, route_date=today).route_status == "finalized"
        finalized_snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert finalized_snapshot.route_finalized_at is not None
        assert finalized_snapshot.route_summary["open_stops"] == 0

    route_sheet = client.get(f"/driver_logs_print?date={today.isoformat()}")
    assert route_sheet.status_code == 200
    assert b"Route finalized" in route_sheet.data
    assert b"Route open and not finalized" not in route_sheet.data


def test_mobile_dashboard_allows_route_end_at_current_final_stop(client, app):
    from datetime import date, datetime, timedelta

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, PostTrip, PreTrip, ShiftRecord

        driver = create_user("final_stop_closeout_driver", "final-stop-closeout@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            PostTrip(pretrip_id=pretrip.id, end_mileage=379025, miles_driven=25),
            ShiftRecord(
                user_id=driver.id,
                pretrip_id=pretrip.id,
                start_time=datetime.utcnow() - timedelta(hours=8),
                week_ending=None,
            ),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                arrive_time=(datetime.utcnow() - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"),
                created_at=datetime.utcnow() - timedelta(minutes=45),
            ),
        ])
        db.session.commit()
        driver_id = driver.id
        log_id = DriverLog.query.filter_by(driver_id=driver.id).first().id

    login(client, "final_stop_closeout_driver")
    page = client.get("/mobile")
    assert page.status_code == 200
    assert b"End Route Here" in page.data
    assert b"Use the current stop as the route end" in page.data
    assert b'action="/mobile/end-route" method="POST"' in page.data
    assert b"PostTrip Due" not in page.data

    get_response = client.get("/mobile/end-route", follow_redirects=False)
    assert get_response.status_code == 302
    assert get_response.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import ActivityEvent, DriverLog, ShiftRecord

        saved_log = DriverLog.query.get(log_id)
        assert saved_log.depart_time is None
        assert saved_log.dock_wait_minutes is None
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 1
        assert ActivityEvent.query.filter_by(
            user_id=driver_id,
            category="eod",
            action="finalized",
            target_type="end_of_day",
        ).count() == 0

    response = client.post("/mobile/end-route", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import ActivityEvent, DriverLog, ShiftRecord
        from app.services.route_context import build_route_context

        saved_log = DriverLog.query.get(log_id)
        assert saved_log.depart_time is None
        assert saved_log.dock_wait_minutes is None
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 0
        assert ActivityEvent.query.filter_by(
            user_id=driver_id,
            category="eod",
            action="finalized",
            target_type="end_of_day",
        ).count() == 1
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.route_status == "finalized"
        assert snapshot.current_stop is None
        assert snapshot.current_stop_status == "finalized"
        assert snapshot.rows[-1]["status"] == "Finalized"
        assert snapshot.rows[-1]["note"] == "Route finalized at final stop."

    finalized_page = client.get("/mobile").get_data(as_text=True)
    assert "ROUTE END" in finalized_page
    assert "route end" in finalized_page.lower()
    assert "needs departure" not in finalized_page.lower()

    route_sheet = client.get(f"/driver_logs_print?date={today.isoformat()}")
    assert route_sheet.status_code == 200
    assert b"25 mi" in route_sheet.data
    assert b"Route finalized" in route_sheet.data
    assert b"Route open and not finalized" not in route_sheet.data


def test_shift_get_routes_do_not_mutate_shift_state(client, app):
    from datetime import datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, ShiftRecord

        driver = create_user("shift_get_driver", "shift-get@example.com", "driver")
        open_shift = ShiftRecord(
            user_id=driver.id,
            start_time=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(open_shift)
        db.session.commit()
        driver_id = driver.id
        shift_id = open_shift.id

    login(client, "shift_get_driver")

    start_get = client.get("/start_shift", follow_redirects=False)
    assert start_get.status_code == 302
    end_get = client.get("/end_shift?next=mobile", follow_redirects=False)
    assert end_get.status_code == 302
    assert end_get.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import ActivityEvent, ShiftRecord

        saved_shift = ShiftRecord.query.get(shift_id)
        assert saved_shift.end_time is None
        assert ShiftRecord.query.filter_by(user_id=driver_id, end_time=None).count() == 1
        assert ActivityEvent.query.filter_by(user_id=driver_id, category="shift").count() == 0


def test_request_manager_review_is_driver_owned_and_active_log_only(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        owner = create_user("review_owner", "review-owner@example.com", "driver")
        create_user("review_other", "review-other@example.com", "driver")
        create_user("review_manager", "review-manager@example.com", "management")
        owned_log = DriverLog(
            driver_id=owner.id,
            date=today,
            plant_name="RE",
            load_size="Empty",
            arrive_time="08:00",
        )
        deleted_log = DriverLog(
            driver_id=owner.id,
            date=today,
            plant_name="KP",
            load_size="Empty",
            arrive_time="09:00",
            deleted_at=datetime.utcnow(),
        )
        db.session.add_all([owned_log, deleted_log])
        db.session.commit()
        owner_log_id = owned_log.id
        deleted_log_id = deleted_log.id
        owner_id = owner.id

    login(client, "review_other")
    other_response = client.post(f"/driver_logs/{owner_log_id}/request_review", follow_redirects=False)
    assert other_response.status_code == 302

    with app.app_context():
        from app.models import ExceptionEvent

        assert ExceptionEvent.query.filter_by(driver_log_id=owner_log_id).count() == 0

    client.get("/logout")
    login(client, "review_manager")
    manager_response = client.post(f"/driver_logs/{owner_log_id}/request_review", follow_redirects=False)
    assert manager_response.status_code == 302

    with app.app_context():
        from app.models import ExceptionEvent

        assert ExceptionEvent.query.filter_by(driver_log_id=owner_log_id).count() == 0

    client.get("/logout")
    login(client, "review_owner")
    missing_response = client.post(f"/driver_logs/{deleted_log_id}/request_review", follow_redirects=False)
    assert missing_response.status_code == 404

    success_response = client.post(f"/driver_logs/{owner_log_id}/request_review", follow_redirects=False)
    assert success_response.status_code == 302
    assert success_response.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import ExceptionEvent

        event = ExceptionEvent.query.filter_by(driver_log_id=owner_log_id).one()
        assert event.event_type == "manager_review_requested"
        assert event.driver_id == owner_id


def test_driver_log_mutations_block_past_and_finalized_routes(client, app):
    from datetime import date, timedelta

    today = date.today()
    yesterday = today - timedelta(days=1)
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog

        driver = create_user("guarded_driver", "guarded-driver@example.com", "driver")
        past_log = DriverLog(
            driver_id=driver.id,
            date=yesterday,
            plant_name="RE",
            load_size="Empty",
            arrive_time="08:00",
        )
        finalized_log = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="KP",
            load_size="Empty",
            arrive_time="09:00",
        )
        active_log = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="PW",
            load_size="Empty",
            arrive_time="00:01",
        )
        db.session.add_all([past_log, finalized_log, active_log])
        db.session.flush()
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
        past_log_id = past_log.id
        finalized_log_id = finalized_log.id
        active_log_id = active_log.id

    login(client, "guarded_driver")

    past_response = client.post(f"/driver_logs/{past_log_id}/no_pickup", follow_redirects=False)
    assert past_response.status_code == 302
    finalized_response = client.post(
        f"/driver_logs/{finalized_log_id}/part-scans",
        json={"raw_value": "ABC123", "scan_context": "pickup"},
    )
    assert finalized_response.status_code == 403

    with app.app_context():
        from app.models import ActivityEvent, DriverLog, PartScanEvent

        assert DriverLog.query.get(past_log_id).depart_time is None
        assert PartScanEvent.query.filter_by(stop_id=finalized_log_id).count() == 0

        ActivityEvent.query.filter_by(
            category="eod",
            action="finalized",
            target_type="end_of_day",
        ).delete()
        db.session.commit()

    active_response = client.post(f"/driver_logs/{active_log_id}/no_pickup", follow_redirects=False)
    assert active_response.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(active_log_id).depart_time is not None


def test_dashboard_and_map_are_redirect_only(client, app):
    with app.app_context():
        create_user("redirect_driver", "redirect-driver@example.com", "driver")

    login(client, "redirect_driver")

    dashboard_get = client.get("/dashboard", follow_redirects=False)
    assert dashboard_get.status_code == 302
    assert dashboard_get.headers["Location"].endswith("/mobile")
    assert client.post("/dashboard", follow_redirects=False).status_code == 405

    map_get = client.get("/map", follow_redirects=False)
    assert map_get.status_code == 302
    assert map_get.headers["Location"].endswith("/mobile")


def test_mobile_dashboard_registers_completed_posttrip_with_duplicate_open_pretrip(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog, PlantTransfer, PostTrip, PreTrip

        driver = create_user("duplicate_posttrip_driver", "duplicate-posttrip@example.com", "driver")
        completed_pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=today,
            truck_number="ST4",
            start_mileage=379000,
            created_at=datetime(2026, 6, 4, 12, 0),
        )
        duplicate_open_pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=today,
            truck_number="ST4",
            start_mileage=379000,
            created_at=datetime(2026, 6, 4, 12, 30),
        )
        db.session.add_all([completed_pretrip, duplicate_open_pretrip])
        db.session.flush()
        db.session.add_all([
            PostTrip(
                pretrip_id=completed_pretrip.id,
                end_mileage=379050,
                miles_driven=50,
                created_at=datetime(2026, 6, 4, 20, 30),
            ),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="RE",
                load_size="Empty",
                depart_load_size="Empty",
                no_pickup=True,
                arrive_time="08:00",
                depart_time="08:20",
                created_at=datetime(2026, 6, 4, 8, 0),
            ),
            PlantTransfer(
                user_id=driver.id,
                transfer_date=today,
                ship_from="RE",
                ship_to="RE",
                driver_name="Duplicate PostTrip",
            ),
            ActivityEvent(
                user_id=driver.id,
                category="eod",
                action="finalized",
                title="Route finalized",
                details=f"Route finalized for {today}",
                target_type="end_of_day",
            ),
        ])
        db.session.commit()

    login(client, "duplicate_posttrip_driver")
    page = client.get("/mobile")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "PostTrip Due" not in body
    assert "Complete posttrip" not in body
    # Finalized route: non-mutating view CTA (rule I).
    assert "View Route Packet" in body
    assert "379,050" in body


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
    assert 'flow-status status-attention">NEEDS DEPARTURE' not in body
    assert '<div class="md-flow-ticker" aria-hidden="true">' not in body
    assert "ROUTE LOGS &nbsp; PLANT TRANSFERS" not in body
    assert "<html" not in body.lower()


def test_new_stop_form_does_not_offer_legacy_pe_choice(client, app):
    with app.app_context():
        create_user("no_pe_driver", "no-pe@example.com", "driver")

    login(client, "no_pe_driver")
    page = client.get("/new_driving_log")

    assert page.status_code == 200
    assert b'value="PE"' not in page.data
    assert b"Paint East" not in page.data


def test_driver_logs_ledger_uses_plain_status_text_and_explicit_unknowns(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("ledger_plain_driver", "ledger-plain@example.com", "driver")
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=date.today(),
                plant_name="PC",
                load_size="Empty",
                depart_load_size="Mystery Load",
                arrive_time="2026-05-28 08:00:00",
                depart_time="08:15",
                dock_wait_minutes=1,
            ),
            DriverLog(
                driver_id=driver.id,
                date=date.today(),
                plant_name="RE",
                load_size="Mystery Load",
                depart_load_size="Empty",
                arrive_time="2026-05-28 09:00:00",
                depart_time="09:20",
            ),
        ])
        db.session.commit()

    login(client, "ledger_plain_driver")
    page = client.get("/driver_logs")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "Destination needs confirmation" in body
    assert "Pickup source unknown" in body
    assert "Earlier stop" not in body
    assert "Next stop" not in body
    assert "Wait Wait" not in body
    assert "Dock time: 1 min" in body
    assert 'class="badge bg' not in body
    assert "status-pill" not in body
    assert "severity-pill" not in body
    assert "route-status-badge" not in body


def test_empty_active_stop_quick_depart_starts_at_load_check(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("empty_depart_driver", "empty-depart@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=date.today(),
                plant_name="RE",
                load_size="Empty",
                arrive_time="00:01",
            )
        )
        db.session.commit()

    login(client, "empty_depart_driver")
    page = client.get("/mobile")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert 'data-depart-start-step="1"' in body
    assert '<section class="depart-step " data-depart-step="0">' in body
    assert '<section class="depart-step is-active" data-depart-step="1">' in body
    assert 'name="secondary_destination" data-depart-field="secondary_destination" value=""' in body
    assert '<label for="departSecondaryDestination">Optional second stop</label>' in body
    assert '<option value="">None or not applicable</option>' in body


def test_loaded_quick_depart_keeps_cargo_in_transit_until_add_next_stop(client, app):
    from datetime import date

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("quick_loaded_continue", "quick-loaded-continue@example.com", "driver")
        active = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="H",
            load_size="Empty",
            arrive_time="00:01",
        )
        db.session.add(active)
        db.session.commit()
        active_id = active.id
        driver_id = driver.id

    login(client, "quick_loaded_continue")
    response = client.post(
        f"/driver_logs/{active_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "destination": "RE",
            "secondary_destination": "",
            "secondary_load_type": "load",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["redirect"].endswith("/mobile")
    assert "Next stop opened" not in payload["message"]
    assert "No second stop selected." in payload["message"]
    with app.app_context():
        from app.models import DriverLog, FlowEvent
        from app.services.load_state import current_load_after_logs
        from app.services.route_context import build_route_context

        saved = DriverLog.query.get(active_id)
        assert saved.depart_time
        assert saved.depart_load_size == "Raleigh East Load"
        assert saved.secondary_load is None
        route_logs = DriverLog.query.filter_by(driver_id=saved.driver_id, date=saved.date).order_by(DriverLog.created_at.asc()).all()
        assert len(route_logs) == 1
        assert current_load_after_logs(route_logs)["destination"] == "RE"
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.route_status == "active"
        assert snapshot.current_stop is None
        assert snapshot.current_cargo["value"] == "Raleigh East Load"
        assert snapshot.current_cargo["destination"] == "RE"
        assert FlowEvent.query.filter_by(stop_id=saved.id, event_type="DEPARTED_ORIGIN").count() == 1
        assert FlowEvent.query.filter_by(event_type="ARRIVED_DESTINATION").count() == 0

    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)
    assert mobile.status_code == 200
    assert "Arrive at Raleigh East" in body
    assert 'class="md-flow-primary-cta add-stop-action"' in body
    assert 'href="/new_driving_log?next=mobile' in body
    assert 'expected_destination=RE' in body
    assert "Depart and Load" not in body
    assert 'data-flow-panel-title="Depart Quick Flow"' not in body

    add_stop_form = client.get("/new_driving_log?next=mobile&expected_destination=RE")
    add_stop_body = add_stop_form.get_data(as_text=True)
    assert add_stop_form.status_code == 200
    assert "Add Next Stop" in add_stop_body
    assert "In truck now:" in add_stop_body
    assert "Raleigh East Load" in add_stop_body
    assert 'name="next" value="mobile"' in add_stop_body

    created = client.post("/new_driving_log?next=mobile&expected_destination=RE", data={"plant_name": "RE", "next": "mobile"}, follow_redirects=False)
    assert created.status_code == 302
    assert created.headers["Location"].endswith("/mobile")
    duplicate_retry = client.post("/new_driving_log?next=mobile&expected_destination=RE", data={"plant_name": "RE", "next": "mobile"}, follow_redirects=False)
    assert duplicate_retry.status_code == 302
    assert duplicate_retry.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import DriverLog, FlowEvent

        route_logs = (
            DriverLog.query
            .filter_by(driver_id=driver_id, date=today)
            .order_by(DriverLog.created_at.asc(), DriverLog.id.asc())
            .all()
        )
        assert len(route_logs) == 2
        assert route_logs[0].id == active_id
        assert route_logs[1].plant_name == "RE"
        assert route_logs[1].load_size == "Raleigh East Load"
        assert route_logs[1].depart_time is None
        assert FlowEvent.query.filter_by(stop_id=route_logs[1].id, event_type="ARRIVED_DESTINATION").count() == 1


def test_empty_quick_depart_keeps_route_continuation_without_phantom_stop(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("quick_empty_continue", "quick-empty-continue@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="H",
                load_size="Empty",
                arrive_time="00:01",
            ),
        ])
        db.session.commit()
        first_id = DriverLog.query.filter_by(driver_id=driver.id).one().id
        driver_id = driver.id

    login(client, "quick_empty_continue")
    response = client.post(
        f"/driver_logs/{first_id}/depart",
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
    with app.app_context():
        from app.models import DriverLog, FlowEvent
        from app.services.route_context import build_route_context

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 1
        assert route_logs[0].id == first_id
        assert route_logs[0].depart_time
        assert route_logs[0].depart_load_size == "Empty"
        assert route_logs[0].no_pickup is True
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.current_stop is None
        assert FlowEvent.query.filter_by(event_type="ARRIVED_DESTINATION").count() == 0

    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)
    assert mobile.status_code == 200
    assert 'class="md-flow-primary-cta add-stop-action"' in body
    assert "<strong>Add Stop</strong>" in body
    assert "Depart and Load" not in body


def test_quick_depart_save_error_rolls_back_and_returns_json(client, app, monkeypatch):
    from datetime import date

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("quick_depart_error_driver", "quick-depart-error@example.com", "driver")
        log = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="H",
            load_size="Empty",
            arrive_time="00:01",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    from app.blueprints.driver import routes as driver_routes

    def fail_append(*args, **kwargs):
        raise RuntimeError("flow event write failed")

    monkeypatch.setattr(driver_routes, "_append_driver_log_flow_event", fail_append)

    login(client, "quick_depart_error_driver")
    response = client.post(
        f"/driver_logs/{log_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "destination": "RE",
            "secondary_destination": "",
            "secondary_load_type": "load",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "Departure could not be saved. Try again."
    with app.app_context():
        from app.models import DriverLog, FlowEvent

        saved = DriverLog.query.get(log_id)
        assert saved.depart_time is None
        assert saved.depart_load_size is None
        assert DriverLog.query.filter_by(driver_id=saved.driver_id, date=today).count() == 1
        assert FlowEvent.query.count() == 0


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


def test_mobile_quick_depart_shows_add_next_stop_and_creates_second_stop(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("quick_continue_driver", "quick-continue@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="H",
                load_size="Raleigh East Load",
                arrive_time="00:01",
            ),
        ])
        db.session.commit()
        first_id = DriverLog.query.filter_by(driver_id=driver.id).one().id
        driver_id = driver.id

    login(client, "quick_continue_driver")
    departed = client.post(
        f"/driver_logs/{first_id}/depart",
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

    assert departed.status_code == 302
    assert departed.headers["Location"].endswith("/mobile")
    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)

    assert mobile.status_code == 200
    assert "Arrive at Raleigh East" in body or "Add Destination Stop" in body
    assert body.count('class="md-flow-primary-cta add-stop-action"') == 1
    assert 'href="/new_driving_log?next=mobile' in body
    assert 'expected_destination=RE' in body
    assert 'data-flow-panel-title="Depart Quick Flow"' not in body
    assert 'class="driver-active-wait-action"' not in body

    add_stop_form = client.get("/new_driving_log?next=mobile&expected_destination=RE")
    assert add_stop_form.status_code == 200
    assert b"Plant Name" in add_stop_form.data
    assert b'Add Next Stop' in add_stop_form.data

    created = client.post(
        "/new_driving_log?next=mobile&expected_destination=RE",
        data={"plant_name": "RE", "load_size": "Empty", "next": "mobile"},
        follow_redirects=False,
    )
    assert created.status_code == 302
    assert created.headers["Location"].endswith("/mobile")

    with app.app_context():
        from app.models import DriverLog

        route_logs = (
            DriverLog.query
            .filter_by(driver_id=driver_id, date=today)
            .order_by(DriverLog.created_at.asc(), DriverLog.id.asc())
            .all()
        )
        assert len(route_logs) == 2
        assert route_logs[0].depart_time
        assert route_logs[1].plant_name == "RE"
        assert route_logs[1].load_size == "Raleigh East Load"
        assert route_logs[1].depart_time is None

    refreshed = client.get("/mobile")
    assert refreshed.status_code == 200
    # Open stop with cargo still opens the departure flow, including unload status.
    assert b"Record Departure" in refreshed.data
    assert b"Start Unloading" not in refreshed.data
    assert refreshed.get_data(as_text=True).count('data-flow-panel-title="Depart Quick Flow"') == 1


def test_new_driving_log_save_error_rolls_back_next_stop(client, app, monkeypatch):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("arrival_error_driver", "arrival-error@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="H",
                load_size="Empty",
                depart_load_size="Raleigh East Load",
                depart_time="08:20",
                arrive_time="08:00",
            ),
        ])
        db.session.commit()
        driver_id = driver.id

    from app.blueprints.driver import routes as driver_routes

    def fail_append(*args, **kwargs):
        raise RuntimeError("arrival flow event write failed")

    monkeypatch.setattr(driver_routes, "_append_driver_log_flow_event", fail_append)

    login(client, "arrival_error_driver")
    response = client.post("/new_driving_log", data={"plant_name": "RE"}, follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Arrival could not be saved. Try again." in body
    with app.app_context():
        from app.models import DriverLog, FlowEvent

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 1
        assert route_logs[0].plant_name == "H"
        assert FlowEvent.query.count() == 0


def test_loaded_quick_depart_preserves_secondary_cargo_until_next_stop(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("quick_secondary_continue", "quick-secondary-continue@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="H",
                load_size="Empty",
                arrive_time="00:01",
            ),
        ])
        db.session.commit()
        first_id = DriverLog.query.filter_by(driver_id=driver.id).one().id
        driver_id = driver.id

    login(client, "quick_secondary_continue")
    response = client.post(
        f"/driver_logs/{first_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "destination": "RE",
            "secondary_destination": "RW",
            "secondary_load_type": "hot",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with app.app_context():
        from app.models import DriverLog
        from app.services.load_state import current_load_after_logs
        from app.services.route_context import build_route_context

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 1
        assert route_logs[0].depart_time
        assert route_logs[0].depart_load_size == "Raleigh East Load"
        assert route_logs[0].secondary_load == "Raleigh West Hot Part"
        current_load = current_load_after_logs(route_logs)
        assert current_load["destination"] == "RE"
        assert current_load["secondary_destination"] == "RW"
        assert current_load["secondary_value"] == "Raleigh West Hot Part"
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.current_stop is None
        assert snapshot.current_cargo["value"] == "Raleigh East Load"
        assert snapshot.current_cargo["secondary_value"] == "Raleigh West Hot Part"

    mobile = client.get("/mobile")
    assert b"Arrive at Raleigh East" in mobile.data
    assert b"Depart and Load" not in mobile.data

    add_stop_form = client.get("/new_driving_log?next=mobile&expected_destination=RE")
    add_stop_body = add_stop_form.get_data(as_text=True)
    assert add_stop_form.status_code == 200
    assert 'name="load_size" value="Raleigh East Load"' in add_stop_body
    assert 'name="secondary_load" value="Raleigh West Hot Part"' in add_stop_body
    assert "In truck now:" in add_stop_body
    assert "Raleigh East Load + Raleigh West Hot Part" in add_stop_body

    created = client.post("/new_driving_log?next=mobile&expected_destination=RE", data={"plant_name": "RE", "next": "mobile"}, follow_redirects=False)
    assert created.status_code == 302
    assert created.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 2
        assert route_logs[1].plant_name == "RE"
        assert route_logs[1].load_size == "Raleigh East Load"
        assert route_logs[1].secondary_load == "Raleigh West Hot Part"
        assert route_logs[1].depart_time is None


def test_helios_quick_depart_with_second_stop_uses_mobile_add_next_stop(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("quick_helios_second", "quick-helios-second@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="KP",
                load_size="Empty",
                arrive_time="00:01",
            ),
        ])
        db.session.commit()
        first_id = DriverLog.query.filter_by(driver_id=driver.id).one().id
        driver_id = driver.id

    login(client, "quick_helios_second")
    departed = client.post(
        f"/driver_logs/{first_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "destination": "Trim DC",
            "secondary_destination": "Helios",
            "secondary_load_type": "load",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert departed.status_code == 200
    assert departed.get_json()["redirect"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog
        from app.services.route_context import build_route_context

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 1
        assert route_logs[0].depart_load_size == "Trim DC Load"
        assert route_logs[0].secondary_load == "Helios Load"
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.route_status == "active"
        assert snapshot.current_stop is None
        assert snapshot.current_cargo["value"] == "Trim DC Load"
        assert snapshot.current_cargo["secondary_value"] == "Helios Load"
        assert snapshot.next_stop_context["destination"] == "Trim DC"
        assert snapshot.next_stop_context["secondary_destination"] == "Helios"

    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)
    assert mobile.status_code == 200
    assert "Arrive at Trim DC" in body
    assert 'href="/new_driving_log?next=mobile' in body
    assert "expected_destination=Trim+DC" in body or "expected_destination=Trim%20DC" in body
    assert "Depart and Load" not in body

    add_stop_form = client.get("/new_driving_log?next=mobile&expected_destination=Trim+DC")
    add_stop_body = add_stop_form.get_data(as_text=True)
    assert add_stop_form.status_code == 200
    assert "Add Next Stop" in add_stop_body
    assert "Trim DC Load + Helios Load" in add_stop_body
    assert 'name="load_size" value="Trim DC Load"' in add_stop_body
    assert 'name="secondary_load" value="Helios Load"' in add_stop_body
    assert 'name="next" value="mobile"' in add_stop_body

    created = client.post(
        "/new_driving_log?next=mobile&expected_destination=Trim+DC",
        data={"plant_name": "Trim DC", "next": "mobile"},
        follow_redirects=False,
    )
    assert created.status_code == 302
    assert created.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog, FlowEvent

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 2
        assert route_logs[1].plant_name == "Trim DC"
        assert route_logs[1].load_size == "Trim DC Load"
        assert route_logs[1].secondary_load == "Helios Load"
        assert route_logs[1].depart_time is None
        assert FlowEvent.query.filter_by(stop_id=route_logs[1].id, event_type="ARRIVED_DESTINATION").count() == 1


def test_quick_depart_service_stop_continues_to_add_next_stop_without_truck_issue_route(client, app):
    from datetime import date, datetime

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("quick_service_continue", "quick-service-continue@example.com", "driver")
        pretrip = PreTrip(user_id=driver.id, pretrip_date=today, truck_number="ST4", start_mileage=379000)
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all([
            ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="Ryder Rentals",
                load_size="Raleigh East Load",
                maintenance=True,
                downtime_reason="Truck issue: CEL light",
                arrive_time="00:01",
            ),
        ])
        db.session.commit()
        service_id = DriverLog.query.filter_by(driver_id=driver.id).one().id
        driver_id = driver.id

    login(client, "quick_service_continue")
    response = client.post(
        f"/driver_logs/{service_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "got_loaded": "no",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        from app.models import DriverLog
        from app.services.route_context import build_route_context

        route_logs = DriverLog.query.filter_by(driver_id=driver_id, date=today).order_by(DriverLog.id.asc()).all()
        assert len(route_logs) == 1
        assert route_logs[0].depart_time
        assert route_logs[0].maintenance is True
        assert route_logs[0].depart_load_size == "Raleigh East Load"
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.current_stop is None
        assert snapshot.current_cargo["destination"] == "RE"

    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)
    assert mobile.status_code == 200
    assert 'class="md-flow-primary-cta add-stop-action"' in body
    assert "Arrive at Raleigh East" in body or "Add Destination Stop" in body
    assert 'href="/new_driving_log?next=mobile' in body
    assert 'expected_destination=RE' in body
    assert 'class="md-flow-primary-cta add-stop-action" href="/new_driving_log?report_type=truck_issue"' not in body


def test_mobile_quick_depart_handles_secondary_drop_required(client, app):
    from datetime import date

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog

        driver = create_user("secondary_quick_depart", "secondary-quick@example.com", "driver")
        db.session.add(
            DriverLog(
                driver_id=driver.id,
                date=today,
                plant_name="KP",
                load_size="Empty",
                depart_load_size="Trim DC Load",
                secondary_load="Helios Hot Part",
                arrive_time="00:05",
                depart_time="00:15",
            )
        )
        active = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="Helios",
            load_size="Trim DC Load + Helios Hot Part",
            arrive_time="00:45",
        )
        db.session.add(active)
        db.session.commit()
        active_id = active.id

    login(client, "secondary_quick_depart")
    page = client.get("/mobile")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert 'data-depart-start-step="0"' in body
    assert "Did you drop off this cargo?" in body
    assert 'data-depart-field="secondary_dropped_on_departure" value=""' in body

    missing_secondary = client.post(
        f"/driver_logs/{active_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "",
            "got_loaded": "no",
            "destination": "",
            "secondary_destination": "",
            "secondary_load_type": "load",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert missing_secondary.status_code == 400
    assert missing_secondary.get_json()["error"] == "Please answer whether you dropped off the second-stop cargo."
    with app.app_context():
        from app.models import DriverLog

        assert DriverLog.query.get(active_id).depart_time is None

    saved = client.post(
        f"/driver_logs/{active_id}/depart",
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
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert saved.status_code == 200
    assert saved.get_json()["ok"] is True
    assert saved.get_json()["redirect"].endswith("/mobile")
    with app.app_context():
        from app.models import DriverLog

        active = DriverLog.query.get(active_id)
        assert active.depart_time
        assert active.depart_load_size == "Trim DC Load"
        assert active.secondary_load is None


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
            start_fuel_level="Full",
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
                    end_fuel_level="1/4",
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
    assert b"Start Full" in dashboard.data
    assert b"End 1/4" in dashboard.data
    assert b"12,080 mi" in dashboard.data
    assert b"12,050 mi" in dashboard.data
    assert b"Closed on PostTrip" in dashboard.data
    assert b'target="_blank"' in dashboard.data
    assert b"Other truck issue should not show" not in dashboard.data

    detail = client.get("/truck-maintenance-history?truck_number=ST4")
    assert detail.status_code == 200
    assert b"Issues Opened and Closed" in detail.data
    assert b"Regen" in detail.data
    assert b"Fuel Stops" in detail.data
    assert b"Start Fuel" in detail.data
    assert b"Full" in detail.data
    assert b"End Fuel" in detail.data
    assert b"1/4" in detail.data
    assert b"Regen completed and cleared." in detail.data
    assert b"Other truck issue should not show" not in detail.data


def test_driver_inspections_page_is_scoped_to_current_truck(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PostTrip, PreTrip

        current_driver = create_user(
            "inspection_driver",
            "inspection-driver@example.com",
            "driver",
            first_name="Current",
            last_name="Driver",
        )
        prior_driver = create_user(
            "inspection_prior",
            "inspection-prior@example.com",
            "driver",
            first_name="Prior",
            last_name="Driver",
        )
        other_driver = create_user("inspection_other", "inspection-other@example.com", "driver")
        today = date.today()
        prior_date = today - timedelta(days=1)

        current_pretrip = PreTrip(
            user_id=current_driver.id,
            truck_number="ST4",
            pretrip_date=today,
            start_mileage=13000,
            start_fuel_level="1/2",
        )
        prior_same_truck = PreTrip(
            user_id=prior_driver.id,
            truck_number="ST4",
            pretrip_date=prior_date,
            start_mileage=12000,
            start_fuel_level="Full",
        )
        old_driver_truck = PreTrip(
            user_id=current_driver.id,
            truck_number="ST5",
            pretrip_date=prior_date,
            start_mileage=8000,
        )
        other_truck = PreTrip(
            user_id=other_driver.id,
            truck_number="ST5",
            pretrip_date=prior_date,
            start_mileage=7000,
        )
        db.session.add_all([current_pretrip, prior_same_truck, old_driver_truck, other_truck])
        db.session.flush()
        db.session.add_all(
            [
                PostTrip(
                    pretrip_id=prior_same_truck.id,
                    end_mileage=12140,
                    end_fuel_level="1/4",
                    miles_driven=140,
                    remarks="Same truck low fuel at handoff.",
                    created_at=datetime(2026, 5, 17, 21, 30, 0),
                ),
                PostTrip(
                    pretrip_id=old_driver_truck.id,
                    end_mileage=8080,
                    miles_driven=80,
                    remarks="Old driver truck should not show.",
                    created_at=datetime(2026, 5, 17, 18, 30, 0),
                ),
                PostTrip(
                    pretrip_id=other_truck.id,
                    end_mileage=7100,
                    miles_driven=100,
                    remarks="Other truck issue should not show.",
                    created_at=datetime(2026, 5, 17, 19, 30, 0),
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
                    downtime_reason="Truck issue: Fuel level low at handoff",
                    fuel_mileage=12080,
                ),
                DriverLog(
                    driver_id=other_driver.id,
                    date=prior_date,
                    plant_name="RE",
                    load_size="Empty",
                    arrive_time=f"{prior_date.isoformat()} 18:00:00",
                    maintenance=True,
                    downtime_reason="Truck issue: Other truck issue should not show",
                    fuel_mileage=7010,
                ),
            ]
        )
        db.session.commit()
        prior_same_truck_id = prior_same_truck.id
        other_truck_id = other_truck.id

    login(client, "inspection_driver")

    page = client.get("/list_pretrips")
    assert page.status_code == 200
    assert b"Truck Inspections" in page.data
    assert b"Current action" in page.data
    assert b"PostTrip Due" in page.data
    assert b"Complete PostTrip" in page.data
    assert b"Truck ST4" in page.data
    assert b"PreTrips and PostTrips" in page.data
    assert b"Fuel and Maintenance" in page.data
    # Records stay collapsed behind a segmented switch until the driver picks a section.
    assert b"Inspection Sections" not in page.data
    assert b"data-inspection-switch" in page.data
    assert b'data-insp-target="panel-prepost"' in page.data
    assert b'data-insp-target="panel-maintenance"' in page.data
    assert b'id="panel-prepost"' in page.data
    assert b'aria-label="PreTrip and PostTrip records" hidden' in page.data
    assert b'id="panel-maintenance"' in page.data
    assert b'aria-label="Fuel and maintenance history" hidden' in page.data
    assert b"Current Driver" in page.data
    assert b"Prior Driver" in page.data
    assert b"PostTrip Complete" in page.data
    assert b"Start Fuel" in page.data
    assert b"End Fuel" in page.data
    assert b"1/4" in page.data
    assert b"12,050 mi" in page.data
    assert f"/pretrip_printable/{prior_same_truck_id}".encode() in page.data
    assert b"Open PostTrip" in page.data
    assert f"/pretrip_printable/{prior_same_truck_id}#posttrip-closeout".encode() in page.data
    # The driver's own truck from a prior day stays reachable through the truck
    # switcher so closed PreTrip/PostTrip records never disappear; the body still
    # defaults to the current truck (ST4).
    assert b"inspection-truck-tab" in page.data
    assert b"Truck ST5" in page.data
    # A different driver's record on that truck is not surfaced in the default
    # ST4 view.
    assert b"Other truck issue should not show" not in page.data

    same_truck_posttrip = client.get(f"/do_posttrip/{prior_same_truck_id}")
    assert same_truck_posttrip.status_code == 302
    assert same_truck_posttrip.headers["Location"].endswith(f"/pretrip_printable/{prior_same_truck_id}#posttrip-closeout")

    same_truck_redirect = client.get(f"/view_pretrip/{prior_same_truck_id}")
    assert same_truck_redirect.status_code == 302
    assert same_truck_redirect.headers["Location"].endswith(f"/pretrip_printable/{prior_same_truck_id}")

    same_truck_record = client.get(f"/view_pretrip/{prior_same_truck_id}", follow_redirects=True)
    assert same_truck_record.status_code == 200
    assert b"Daily Vehicle Inspection Report" in same_truck_record.data
    assert b"Truck:</strong> ST4" in same_truck_record.data
    assert b"End 1/4" in same_truck_record.data
    assert b"Same truck low fuel at handoff." in same_truck_record.data
    assert b"Back to Inspections" in same_truck_record.data

    same_truck_pdf = client.get(f"/pretrip_printable/{prior_same_truck_id}/attachment")
    assert same_truck_pdf.status_code == 200
    assert same_truck_pdf.headers["Content-Type"] == "application/pdf"

    blocked = client.get(f"/view_pretrip/{other_truck_id}", follow_redirects=True)
    assert blocked.status_code == 200
    assert b"Not authorized to view that PreTrip." in blocked.data
    assert b"Other truck issue should not show" not in blocked.data

    restricted_history = client.get("/truck-maintenance-history?truck_number=ST5")
    assert restricted_history.status_code == 200
    assert b"Truck ST4" in restricted_history.data
    assert b"Truck ST5" not in restricted_history.data
    assert b"Other truck issue should not show" not in restricted_history.data


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
    assert b"Driver Routes" in dashboard.data
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


def test_finalized_route_can_end_at_arrival_only_final_stop(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog
        from app.services.route_context import build_route_context

        driver = create_user("final_arrival", "final-arrival@example.com", "driver")
        create_user("manager_final_arrival", "manager-final-arrival@example.com", "management")
        route_date = date.today()
        db.session.add_all([
            DriverLog(
                driver_id=driver.id,
                date=route_date,
                plant_name="RE",
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
        snapshot = build_route_context(driver_id=driver_id, route_date=route_date)
        assert snapshot.route_status == "finalized"
        assert snapshot.current_stop is None
        assert snapshot.rows[-1]["status"] == "Finalized"
        assert snapshot.rows[-1]["note"] == "Route finalized at final stop."
        assert "Missing Departure" not in {row["status"] for row in snapshot.rows}

    login(client, "manager_final_arrival")
    route_review = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_review.status_code == 200
    assert b"Missing Departure" not in route_review.data
    assert b"Correction required" not in route_review.data

    client.get("/logout")
    login(client, "final_arrival")
    route_sheet = client.get(f"/driver_logs_print?date={date.today().isoformat()}")
    assert route_sheet.status_code == 200
    assert b"Route End: Raleigh East" in route_sheet.data
    assert b"Finalized Stop: Raleigh East" not in route_sheet.data
    assert b"Missing Departure" not in route_sheet.data


def test_finalized_route_with_prior_missing_departure_requires_correction(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import ActivityEvent, DriverLog
        from app.services.route_context import build_route_context

        driver = create_user("final_prior_missing", "final-prior-missing@example.com", "driver")
        create_user("manager_prior_missing", "manager-prior-missing@example.com", "management")
        route_date = date.today()
        first = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="PC",
            load_size="Empty",
            arrive_time="08:00",
            created_at=datetime(2026, 5, 20, 8, 0),
        )
        second = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Empty",
            no_pickup=True,
            arrive_time="08:30",
            depart_time="08:45",
            created_at=datetime(2026, 5, 20, 8, 30),
        )
        db.session.add_all([
            first,
            second,
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
        snapshot = build_route_context(driver_id=driver_id, route_date=route_date)
        assert snapshot.rows[0]["status"] == "Missing Departure"
        assert snapshot.true_exceptions[0]["label"] == "Missing Departure"

    login(client, "manager_prior_missing")
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
        assert snapshot.current_activity_label == "Awaiting departure and load intent"
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
    assert b"End Route Here" in mobile.data
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
    assert b"Open Items" in dashboard.data
    assert b"mc-nav-badge" in dashboard.data

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


def test_manager_review_resolve_requires_pending_request_newer_than_latest_resolve(client, app):
    from datetime import date, datetime

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, ExceptionEvent

        manager = create_user("stale_review_manager", "stale-review-manager@example.com", role="management")
        driver = create_user("stale_review_driver", "stale-review-driver@example.com")
        route_date = date.today()
        no_request_log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="KP",
            load_size="Empty",
            depart_load_size="Empty",
        )
        stale_log = DriverLog(
            driver_id=driver.id,
            date=route_date,
            plant_name="RE",
            load_size="Empty",
            depart_load_size="Empty",
        )
        db.session.add_all([no_request_log, stale_log])
        db.session.flush()
        db.session.add_all([
            ExceptionEvent(
                event_type="manager_review_requested",
                severity="medium",
                stop_id=stale_log.id,
                driver_log_id=stale_log.id,
                driver_id=driver.id,
                plant_name="RE",
                event_date=route_date,
                summary="Driver requested manager review",
                created_at=datetime(2026, 6, 5, 8, 0),
            ),
            ExceptionEvent(
                event_type="manager_review_resolved",
                severity="medium",
                stop_id=stale_log.id,
                driver_log_id=stale_log.id,
                driver_id=manager.id,
                plant_name="RE",
                event_date=route_date,
                summary="Manager resolved review",
                created_at=datetime(2026, 6, 5, 9, 0),
            ),
        ])
        db.session.commit()
        no_request_log_id = no_request_log.id
        stale_log_id = stale_log.id
        driver_id = driver.id

    login(client, "stale_review_manager")

    no_request = client.post(f"/manager/reviews/{no_request_log_id}/resolve", follow_redirects=True)
    assert no_request.status_code == 200
    assert b"No pending manager review request exists" in no_request.data

    stale = client.post(f"/manager/reviews/{stale_log_id}/resolve", follow_redirects=True)
    assert stale.status_code == 200
    assert b"No pending manager review request exists" in stale.data

    with app.app_context():
        from app.extensions import db
        from app.models import ExceptionEvent

        assert ExceptionEvent.query.filter_by(
            event_type="manager_review_resolved",
            stop_id=no_request_log_id,
        ).count() == 0
        assert ExceptionEvent.query.filter_by(
            event_type="manager_review_resolved",
            stop_id=stale_log_id,
        ).count() == 1
        db.session.add(ExceptionEvent(
            event_type="manager_review_requested",
            severity="medium",
            stop_id=stale_log_id,
            driver_log_id=stale_log_id,
            driver_id=driver_id,
            plant_name="RE",
            event_date=date.today(),
            summary="Driver requested manager review again",
            details="New request after the old resolve.",
            created_at=datetime(2026, 6, 5, 10, 0),
        ))
        db.session.commit()

    queue = client.get("/manager/reviews")
    assert queue.status_code == 200
    assert b"New request after the old resolve." in queue.data

    resolved = client.post(
        f"/manager/reviews/{stale_log_id}/resolve",
        data={"note": "Resolved current request."},
        follow_redirects=True,
    )
    assert resolved.status_code == 200

    with app.app_context():
        from app.models import ExceptionEvent

        assert ExceptionEvent.query.filter_by(
            event_type="manager_review_resolved",
            stop_id=stale_log_id,
        ).count() == 2


def test_hours_check_breaks_and_short_haul_summary(client, app):
    from datetime import date

    with app.app_context():
        create_user("hos_driver", "hos@example.com", "driver", first_name="Lamar")

    login(client, "hos_driver")

    # Start Break stores an open break event with the chosen type.
    start = client.post("/mobile/break/start", data={"break_type": "Lunch"})
    assert start.status_code == 302
    with app.app_context():
        from app.models import RouteBreak

        brk = RouteBreak.query.one()
        assert brk.break_type == "Lunch"
        assert brk.start_time is not None
        assert brk.end_time is None

    # End Break closes the same event.
    end = client.post("/mobile/break/end", data={})
    assert end.status_code == 302
    with app.app_context():
        from app.models import RouteBreak

        assert RouteBreak.query.one().end_time is not None

    # A driving log so the sheet has a route to summarize.
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, User

        driver = User.query.filter_by(username="hos_driver").one()
        db.session.add(DriverLog(
            driver_id=driver.id, date=date.today(), plant_name="RE",
            load_size="Empty", arrive_time="08:00", depart_time="09:00", dock_wait_minutes=20,
        ))
        db.session.commit()

    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    # Short-haul is the default mode; HOS companion card stays hidden unless enabled.
    assert b"<h3>Short-Haul Check</h3>" in print_page.data
    assert b"<h3>HOS Companion</h3>" not in print_page.data
    # The captured break prints; nothing announces missing optional data.
    assert b"Lunch" in print_page.data
    assert b"Not recorded" not in print_page.data
    assert b"Unknown" not in print_page.data
    # Internal-only disclaimer is present as a comment, not user-facing text.
    assert b"is not a certified ELD" in print_page.data


def test_hours_companion_section_appears_only_when_enabled(client, app):
    from datetime import date, datetime, timedelta

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord, User

        create_user("hos_companion_driver", "hosc@example.com", "driver", first_name="Pat")
        driver = User.query.filter_by(username="hos_companion_driver").one()
        pretrip = PreTrip(user_id=driver.id, pretrip_date=date.today(), truck_number="MD-1")
        db.session.add(pretrip)
        db.session.flush()
        db.session.add(ShiftRecord(
            user_id=driver.id, pretrip_id=pretrip.id,
            start_time=datetime.utcnow() - timedelta(hours=6), hos_mode="hos_companion",
        ))
        db.session.add(DriverLog(
            driver_id=driver.id, date=date.today(), plant_name="RE",
            load_size="Empty", arrive_time="08:00", depart_time="09:00", dock_wait_minutes=10,
        ))
        db.session.commit()

    login(client, "hos_companion_driver")
    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    assert b"<h3>HOS Companion</h3>" in print_page.data
    assert b"<h3>Short-Haul Check</h3>" not in print_page.data
    assert b"Not recorded" not in print_page.data


def test_day_driver_profile_toggle_and_workspace_language(client, app):
    with app.app_context():
        create_user("dd_profile", "ddp@example.com", "driver", first_name="Dale")

    login(client, "dd_profile")
    resp = client.post("/profile", data={
        "username": "dd_profile", "email": "ddp@example.com",
        "first_name": "Dale", "day_driver": "y", "route_type": "general_freight",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        from app.models import User
        u = User.query.filter_by(username="dd_profile").one()
        assert u.day_driver is True
        assert u.route_type == "general_freight"
        assert u.day_driver_route_type == "general_freight"

    # New-stop form: commodity/weight replace the Lacks plant/part questions.
    new_log = client.get("/new_driving_log")
    assert new_log.status_code == 200
    assert b'name="commodity"' in new_log.data
    assert b'name="weight"' in new_log.data
    assert b'id="arrivalPlant"' not in new_log.data
    assert b'id="hotPartsCheck"' not in new_log.data

    # Mobile workspace switches to freight/commodity language for day drivers.
    mobile = client.get("/mobile")
    assert mobile.status_code == 200
    assert b"commodity" in mobile.data
    assert b"General Freight" in mobile.data


def test_day_driver_dashboard_quick_toggle(client, app):
    """The dashboard exposes a one-tap day-driver toggle so the mode is testable
    without digging into Profile."""
    with app.app_context():
        create_user("dd_toggle", "ddt@example.com", "driver")
    login(client, "dd_toggle")

    home = client.get("/mobile").get_data(as_text=True)
    assert "dd-mode-toggle" in home
    assert "Freight mode (day-driver) · Off" in home

    # One tap turns it on (defaulting the route type) and the freight banner shows.
    resp = client.post("/mobile/toggle-day-driver", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/mobile")
    with app.app_context():
        from app.models import User
        u = User.query.filter_by(username="dd_toggle").one()
        assert u.day_driver is True
        assert u.route_type == "local_short_haul"
    on = client.get("/mobile").get_data(as_text=True)
    assert "dd-mode-toggle on" in on
    assert "Day-Driver Freight Workspace" in on

    # Tapping again turns it back off.
    client.post("/mobile/toggle-day-driver")
    with app.app_context():
        from app.models import User
        assert User.query.filter_by(username="dd_toggle").one().day_driver is False


def test_day_driver_can_log_stop_without_plant_and_carries_load_forward(client, app):
    with app.app_context():
        from app.models import User
        create_user("dd_freight", "ddf@example.com", "driver", first_name="Frank")
        u = User.query.filter_by(username="dd_freight").one()
        u.day_driver = True
        u.route_type = "general_freight"
        from app.extensions import db
        db.session.commit()

    login(client, "dd_freight")
    # No plant selected — owner-operator logs commodity + weight only.
    created = client.post("/new_driving_log", data={"commodity": "Steel coils", "weight": "42000"}, follow_redirects=False)
    assert created.status_code in (302, 303)
    with app.app_context():
        from app.models import DriverLog
        log = DriverLog.query.filter_by(commodity="Steel coils").one()
        assert log.weight == "42000"
        assert log.plant_name  # defaulted to a clean stop label, never blank

    # The onboard load carries forward to the next stop's form.
    next_form = client.get("/new_driving_log")
    assert b"Steel coils" in next_form.data

    # Printout reads as a day-driver package of captured facts only.
    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    assert b"Steel coils" in print_page.data
    assert b"Not recorded" not in print_page.data
    assert b"Truck not set" not in print_page.data
    # General Freight shows hours facts only — no Short-Haul or HOS Companion card.
    assert b"<h3>Short-Haul Check</h3>" not in print_page.data
    assert b"<h3>HOS Companion</h3>" not in print_page.data


def test_day_driver_gps_address_and_corrected_place_name_are_remembered(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import User

        create_user("dd_gps_place", "dd-gps@example.com", "driver", first_name="Gina")
        user = User.query.filter_by(username="dd_gps_place").one()
        user.day_driver = True
        user.route_type = "general_freight"
        db.session.commit()
        driver_id = user.id

    login(client, "dd_gps_place")
    page = client.get("/new_driving_log")
    body = page.get_data(as_text=True)
    assert 'name="location_address"' in body
    assert "Place / customer name" in body
    assert "GPS address matches" in body
    assert "Customer name matches" in body
    assert "Exact-address matches can fill the name" in body
    assert "/gps/place-candidates" in body
    assert "nominatim.openstreetmap.org" not in body
    assert "Google Places key is missing on the server. Saved places only." in body
    assert "Google Places is blocked for this server key. Saved places only." in body
    assert "No Google places found here - type the address and name" in body
    assert "Google places could not be reached - type the address and name" in body
    assert "m away" in body
    assert "Nearby customer names are suggestions only" in body
    assert "customerChoiceTouched" in body
    assert "applySelectedCustomer(customerChoiceTouched)" in body

    created = client.post(
        "/new_driving_log",
        data={
            "location_address": "2200 Customer Dock Dr, Industrial City, MI 49512",
            "location": "Customer Dock 4",
            "gps_latitude": "42.858001",
            "gps_longitude": "-85.532002",
            "gps_accuracy_m": "18.7",
        },
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)

    with app.app_context():
        from datetime import date
        from app.models import DriverLog, PlaceMemory, User
        from app.services.route_map import build_driver_route_map_context

        log = DriverLog.query.filter_by(driver_id=driver_id).one()
        assert log.plant_name == "Customer Dock 4"
        assert log.location_address == "2200 Customer Dock Dr, Industrial City, MI 49512"
        assert log.gps_latitude == pytest.approx(42.858001)
        assert log.gps_longitude == pytest.approx(-85.532002)
        assert log.gps_accuracy_m == pytest.approx(18.7)
        place = PlaceMemory.query.filter_by(user_id=driver_id).one()
        assert place.label == "Customer Dock 4"
        assert place.center_latitude == pytest.approx(42.858001)
        assert place.center_longitude == pytest.approx(-85.532002)
        route_map = build_driver_route_map_context(driver=User.query.get(driver_id), date=date.today())
        stop = route_map["stops"][0]
        assert stop["plant_name"] == "Customer Dock 4"
        assert stop["location_address"] == "2200 Customer Dock Dr, Industrial City, MI 49512"
        assert stop["location_display"] == "Customer Dock 4 · 2200 Customer Dock Dr, Industrial City, MI 49512"

    next_form = client.get("/new_driving_log").get_data(as_text=True)
    assert '<option value="Customer Dock 4">' in next_form
    print_page = client.get("/driver_logs_print").get_data(as_text=True)
    assert "Customer Dock 4" in print_page
    assert "2200 Customer Dock Dr, Industrial City, MI 49512" in print_page


def test_day_driver_gps_place_candidates_endpoint_returns_google_places(client, app, monkeypatch):
    with app.app_context():
        from app.extensions import db
        from app.models import User

        create_user("dd_gps_candidates", "dd-gps-candidates@example.com", "driver")
        user = User.query.filter_by(username="dd_gps_candidates").one()
        user.day_driver = True
        user.route_type = "general_freight"
        db.session.commit()

    def fake_candidates(lat, lng, *, accuracy_m=None, limit=8, hint=""):
        assert lat == pytest.approx(42.900426)
        assert lng == pytest.approx(-85.530662)
        assert accuracy_m == pytest.approx(8)
        assert hint == "current dock"
        return {
            "ok": True,
            "places": [
                {
                    "name": "Current Dock Manufacturing",
                    "address": "1100 Current Dock Dr, Industrial City, MI 49512",
                    "distance_m": 5,
                    "trusted": True,
                    "source": "google",
                }
            ],
            "address_candidates": [
                {"address": "1100 Current Dock Dr, Industrial City, MI 49512", "source": "google_geocode"}
            ],
            "fallback_address": "1100 Current Dock Dr, Industrial City, MI 49512",
        }

    monkeypatch.setattr("app.blueprints.driver.routes.nearby_place_candidates", fake_candidates)
    login(client, "dd_gps_candidates")
    response = client.get("/gps/place-candidates?lat=42.900426&lng=-85.530662&accuracy=8&hint=current+dock")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["places"][0]["name"] == "Current Dock Manufacturing"
    assert payload["places"][0]["address"] == "1100 Current Dock Dr, Industrial City, MI 49512"
    assert payload["places"][0]["trusted"] is True
    assert payload["address_candidates"][0]["address"] == "1100 Current Dock Dr, Industrial City, MI 49512"


def test_day_driver_destination_lookup_endpoint_returns_business_name(client, app, monkeypatch):
    with app.app_context():
        from app.extensions import db
        from app.models import User

        create_user("dd_dest_lookup", "dd-dest-lookup@example.com", "driver")
        user = User.query.filter_by(username="dd_dest_lookup").one()
        user.day_driver = True
        user.route_type = "general_freight"
        db.session.commit()

    def fake_lookup(query):
        assert query == "1100 Receiver Ave Industrial City"
        return {
            "ok": True,
            "place": {
                "name": "Receiver Warehouse",
                "address": "1100 Receiver Ave, Industrial City, MI 49512",
                "source": "google",
            },
            "places": [
                {
                    "name": "Receiver Warehouse",
                    "address": "1100 Receiver Ave, Industrial City, MI 49512",
                    "source": "google",
                },
                {
                    "name": "Receiver Annex",
                    "address": "1110 Receiver Ave, Industrial City, MI 49512",
                    "source": "google",
                },
            ],
        }

    monkeypatch.setattr("app.blueprints.driver.routes.lookup_destination_place", fake_lookup)
    login(client, "dd_dest_lookup")
    response = client.get("/gps/destination-lookup?query=1100+Receiver+Ave+Industrial+City")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["place"]["name"] == "Receiver Warehouse"
    assert payload["place"]["address"] == "1100 Receiver Ave, Industrial City, MI 49512"
    assert [place["name"] for place in payload["places"]] == ["Receiver Warehouse", "Receiver Annex"]
    assert payload["places"][1]["address"] == "1110 Receiver Ave, Industrial City, MI 49512"


def test_freight_departure_label_drops_zero_weight():
    from app.blueprints.driver.routes import _freight_departure_label

    assert _freight_departure_label("Pallets", "0", "Receiver") == "Pallets -> Receiver"
    assert _freight_departure_label("Pallets", "0.0", "Receiver") == "Pallets -> Receiver"
    assert _freight_departure_label("Pallets", "12000", "Receiver") == "Pallets (12000 lbs) -> Receiver"


def test_day_driver_departure_saves_second_freight_load_and_prefills_arrival(client, app):
    from datetime import date

    today = date.today()
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, User

        driver = create_user("dd_second_load", "dd-second@example.com", "driver")
        user = User.query.filter_by(username="dd_second_load").one()
        user.day_driver = True
        user.route_type = "general_freight"
        previous = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="Previous Shipper",
            load_size="Empty",
            depart_load_size="Pallets -> Recent Receiver",
            destination="Recent Receiver",
            destination_address="1200 Recent Receiver Rd, Industrial City, MI 49512",
            arrive_time="00:00",
            depart_time="00:00",
        )
        active = DriverLog(
            driver_id=driver.id,
            date=today,
            plant_name="Shipper Dock",
            load_size="Empty",
            arrive_time="00:01",
        )
        db.session.add_all([previous, active])
        db.session.commit()
        active_id = active.id
        driver_id = driver.id

    login(client, "dd_second_load")
    depart_screen = client.get("/mobile").get_data(as_text=True)
    assert "Destination address" in depart_screen
    assert "Destination business name" in depart_screen
    assert 'name="destination_address"' in depart_screen
    assert 'name="destination_text"' in depart_screen
    assert "data-destination-suggestions" in depart_screen
    assert depart_screen.count('class="freight-destination-recents" data-destination-recents hidden') == 2
    assert "freight-destination-option" in depart_screen
    assert "freight-destination-recent" in depart_screen
    assert "Recent Receiver" in depart_screen
    assert "1200 Recent Receiver Rd, Industrial City, MI 49512" in depart_screen
    assert "/gps/destination-lookup" in depart_screen

    response = client.post(
        f"/driver_logs/{active_id}/depart",
        data={
            "next": "mobile",
            "source": "live_flow",
            "unloaded_on_departure": "yes",
            "secondary_dropped_on_departure": "yes",
            "got_loaded": "yes",
            "commodity": "Auto parts",
            "weight": "42000",
            "destination_address": "1100 Receiver Ave, Industrial City, MI 49512",
            "destination_text": "Primary Receiver",
            "secondary_commodity": "Pallets",
            "secondary_weight": "12000",
            "secondary_destination_address": "2200 Secondary Ave, Industrial City, MI 49512",
            "secondary_destination_text": "Secondary Receiver",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with app.app_context():
        from app.models import DriverLog
        from app.services.route_context import build_route_context

        saved = DriverLog.query.get(active_id)
        assert saved.depart_time
        assert saved.depart_load_size == "Auto parts (42000 lbs) -> Primary Receiver"
        assert saved.secondary_load == "Pallets (12000 lbs) -> Secondary Receiver"
        assert saved.destination == "Primary Receiver"
        assert saved.destination_address == "1100 Receiver Ave, Industrial City, MI 49512"
        snapshot = build_route_context(driver_id=driver_id, route_date=today)
        assert snapshot.route_status == "active"
        assert snapshot.current_cargo["cargo_display"] == "Auto parts (42000 lbs) + Pallets (12000 lbs)"
        assert snapshot.next_stop_context["destination"] == "Primary Receiver"

    mobile = client.get("/mobile")
    body = mobile.get_data(as_text=True)
    assert "Arrive at Primary Receiver / Secondary Receiver" in body
    assert 'href="/new_driving_log?next=mobile' in body

    add_stop_form = client.get("/new_driving_log?next=mobile&expected_destination=Primary%20Receiver")
    add_stop_body = add_stop_form.get_data(as_text=True)
    assert add_stop_form.status_code == 200
    assert 'value="Primary Receiver"' in add_stop_body
    assert 'value="1100 Receiver Ave, Industrial City, MI 49512"' in add_stop_body
    assert 'name="load_size" value="Auto parts (42000 lbs)"' in add_stop_body
    assert 'name="secondary_load" value="Pallets (12000 lbs)"' in add_stop_body


def test_day_driver_local_route_shows_short_haul_check(client, app):
    from datetime import date

    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, User
        create_user("dd_local", "ddl@example.com", "driver", first_name="Lou")
        u = User.query.filter_by(username="dd_local").one()
        u.day_driver = True
        u.route_type = "local_short_haul"
        db.session.add(DriverLog(driver_id=u.id, date=date.today(), plant_name="Day Route",
                                 load_size="Empty", commodity="Pallets", weight="1000",
                                 arrive_time="08:00", depart_time="09:00", dock_wait_minutes=10))
        db.session.commit()

    login(client, "dd_local")
    print_page = client.get("/driver_logs_print")
    assert print_page.status_code == 200
    assert b"<h3>Short-Haul Check</h3>" in print_page.data
    assert b"Not recorded" not in print_page.data
