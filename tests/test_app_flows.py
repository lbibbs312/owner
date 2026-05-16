import os

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("MANAGER_REGISTRATION_PIN", "0000")
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

    login(client, "driver1")
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
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import ActivityEvent, PreTrip, ShiftRecord

        pretrip = PreTrip.query.filter_by(truck_number="BT-1").one()
        assert pretrip.truck_type == "Box Truck"
        pretrip_id = pretrip.id
        shift = ShiftRecord.query.filter_by(pretrip_id=pretrip_id, end_time=None).one()
        assert shift.user_id == pretrip.user_id
        assert ActivityEvent.query.filter_by(
            target_type="pretrip", target_id=pretrip_id, action="created"
        ).count() == 1

    edit_page = client.get(f"/edit_pretrip_entry/{pretrip_id}")
    assert edit_page.status_code == 200
    assert b"Truck / Tractor #" in edit_page.data
    assert b"No Defects" in edit_page.data

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
    assert b"Review the DVIR first" in printable.data
    assert b"Driver One" in printable.data
    assert "&#10003;".encode() in printable.data

    activity = client.get("/recent_activity")
    assert activity.status_code == 200
    assert b"PreTrip saved" in activity.data
    assert b"PreTrip printed" not in activity.data

    mark_printed = client.post(f"/pretrip_printable/{pretrip_id}/mark_printed")
    assert mark_printed.status_code == 200
    assert mark_printed.get_json()["ok"] is True

    activity = client.get("/recent_activity")
    assert b"PreTrip printed" in activity.data


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
    assert b"Only 1 min from Paint East to Raleigh West" in response.data

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
            "arrive_time": "5:45pm",
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
        assert log.hot_parts is True
        assert log.arrive_time.endswith("21:45:00")
        assert log.depart_time is None

    edit_page = client.get(f"/edit_driver_log/{log_id}")
    assert b"5:45pm" in edit_page.data
    assert b"driver-log-conditionals.js" in edit_page.data
    assert b"+ Add Missed Stop" not in edit_page.data
    assert b"Pickup" not in edit_page.data
    assert b"Depart Now" not in edit_page.data

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
        db.session.add_all([completed_log, log])
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
    assert b"Print / Save Route" in filtered_logs.data
    assert b"Download Route PDF" in filtered_logs.data
    route_print = client.get(f"/manager/driver-logs/route-print?driver_id={driver_id}&date={date.today().isoformat()}")
    assert route_print.status_code == 200
    assert b"Driver Route Audit Sheet" in route_print.data

    dashboard = client.get(f"/manager/dashboard?driver_id={driver_id}")
    assert dashboard.status_code == 200
    assert b"Live Routes &amp; Stops" in dashboard.data
    assert b"Open stop - needs departure" in dashboard.data

    driver_page_attempt = client.get("/driver_logs", follow_redirects=False)
    assert driver_page_attempt.status_code == 302
    assert "required_role=driver" in driver_page_attempt.headers["Location"]

    login(client, "manager1")
    edit_attempt = client.get(f"/edit_driver_log/{log_id}", follow_redirects=False)
    assert edit_attempt.status_code == 302
    assert "required_role=driver" in edit_attempt.headers["Location"]


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
        from app.models import DriverLog, PlantTransfer, PreTrip

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

    arrived_helios = client.post(
        "/new_driving_log",
        data={"plant_name": "Helios", "load_size": "Helios Load", "unloaded_on_arrival": "yes"},
        follow_redirects=False,
    )
    assert arrived_helios.status_code == 302

    with app.app_context():
        from app.models import DriverLog

        helios_log = DriverLog.query.filter_by(plant_name="Helios").one()
        assert helios_log.load_size == "Helios Load"
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
        data={"got_loaded": "no", "destination": "", "secondary_destination": "Helios"},
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
            "secondary_dropped_on_arrival": "yes",
        },
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
    assert b"Only 1 min from Paint East to Raleigh West" in page.data
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
        db.session.commit()

    print_response = client.get("/driver_logs_print")
    assert print_response.status_code == 200
    assert b"5:45pm" in print_response.data
    assert b"17:45" not in print_response.data

    eod_print = client.get("/end_of_day_print")
    assert eod_print.status_code == 200
    assert b"5:45pm" in eod_print.data
    assert b"17:45" not in eod_print.data

    eod_attachment = client.get("/end_of_day_print/attachment")
    assert eod_attachment.status_code == 200
    assert eod_attachment.headers["Content-Type"] == "application/pdf"

    eod_response = client.post("/end_of_day_summary", data={}, follow_redirects=False)
    assert eod_response.status_code == 302

    activity = client.get("/recent_activity")
    assert activity.status_code == 200
    assert b"Driver log submitted" in activity.data
    assert b"Driver logs printed" in activity.data
    assert b"End of day finalized" in activity.data

    unread = client.get("/count_unread").get_json()
    assert unread["action_count"] >= 3
    assert unread["unread_count"] >= unread["action_count"]


def test_damage_report_edit_delete_submit_and_eod_lock(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")

    create_response = client.post(
        "/damage_reports/new",
        data={
            "truck_number": "T1",
            "trailer_number": "TR1",
            "plant_name": "RE",
            "stage": "before",
            "move_reference": "Dock 4",
            "description": "Scuffed bumper",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        from app.models import DamageReport

        report = DamageReport.query.filter_by(description="Scuffed bumper").one()
        report_id = report.id

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

    assert client.post("/end_of_day_summary", data={}, follow_redirects=False).status_code == 302
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
        transfer_id = transfer.id

    printable = client.get(f"/plant_transfers/{transfer_id}/print")
    assert printable.status_code == 200
    assert b"White - DATA INPUT" in printable.data
    assert b"Canary - RECEIVING PLANT" in printable.data
    assert b"Pink - DRIVER" in printable.data
    assert b"Blue - SHIPPING PLANT" in printable.data
    assert b"GAUGE-1" in printable.data
    assert b"1:30pm" in printable.data
    assert b"13:30" not in printable.data

    attachment = client.get(f"/plant_transfers/{transfer_id}/attachment?copy=blue")
    assert attachment.status_code == 200
    assert attachment.headers["Content-Type"] == "application/pdf"
    assert attachment.headers["Content-Disposition"].startswith("attachment;")
    assert attachment.headers["Content-Disposition"].endswith('.pdf"')
    assert attachment.data.startswith(b"%PDF")

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
    assert b"LacksDrivers Mobile" in page.data
    assert b"RW to KP hot move" in page.data
    assert b"Part P0903110 needs trailer assignment." in page.data
    assert b"PostTrip Due" in page.data
    assert b"RW to KP" in page.data
    assert b"Ryder Service" in page.data
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
    assert b"TRX" not in history.data

    day_report = client.get(f"/mobile/history/{past_date.isoformat()}")
    assert day_report.status_code == 200
    assert b"PC to RE" in day_report.data
    assert b"TRX-099" in day_report.data
    assert b"TR-8" in day_report.data
    assert b"OLD-PART" in day_report.data
    assert b"2 skid(s)" in day_report.data
    assert b"qty 18" in day_report.data
    assert b"Distribution Center" in day_report.data
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
    assert b"Edit" in today_report.data
    assert b"Pickup" in today_report.data
    assert b"Depart" in today_report.data
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

    assert page.data.count(b"Create Driver Log") == 1
    assert b"Start Shift" not in page.data
    assert b"End Shift" not in page.data



def test_knowledge_base_uses_shared_app_shell(client, app):
    with app.app_context():
        create_user("driver1", "driver1@example.com", "driver")

    login(client, "driver1")
    page = client.get("/knowledge_base")
    assert page.status_code == 200
    assert b"Knowledge Base" in page.data
    assert b"LacksDrivers - Dynamic" not in page.data
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
