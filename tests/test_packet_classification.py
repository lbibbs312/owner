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


def _create_user(username, email, role="driver", password="password1", **attrs):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=email, role=role, **attrs)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username, password="password1"):
    return client.post(
        "/login",
        data={"login_name": username, "password": password},
        follow_redirects=False,
    )


def _create_report(driver, description):
    from app.extensions import db
    from app.models import DamageReport

    report = DamageReport(
        reported_by_id=driver.id,
        truck_number="UNIT-12",
        trailer_number="TRL-9",
        plant_name="Route stop",
        stage="after",
        description=description,
        status="submitted",
    )
    db.session.add(report)
    db.session.commit()
    return report


def test_low_fuel_packet_renders_ifta_label_not_damage_record(client, app):
    from app.services.packet_classification import classify_packet_text

    result = classify_packet_text("low fuel reported at fuel stop")
    assert result.packet_type == "fuel_odo_ifta"
    assert result.label == "Fuel / Odometer / IFTA Worksheet"

    with app.app_context():
        driver = _create_user("packet_driver", "packet-driver@example.com", first_name="Packet", last_name="Driver")
        _create_user("packet_manager", "packet-manager@example.com", "management")
        report = _create_report(driver, "low fuel after route fuel stop")
        report_id = report.id

    _login(client, "packet_manager")
    response = client.get(f"/manager/damage-reports/{report_id}/evidence-packet")

    assert response.status_code == 200
    assert b"Fuel / Odometer / IFTA Worksheet" in response.data
    assert b"Damage Proof Record" not in response.data
    assert b"DAMAGE PROOF RECORD" not in response.data


def test_damage_and_accident_terms_keep_correct_packet_labels():
    from app.services.packet_classification import classify_packet_text

    damage = classify_packet_text("Dent and broken mirror on trailer damage report.")
    assert damage.packet_type == "damage_issue"
    assert damage.label == "Damage Issue Packet"

    accident = classify_packet_text("Backing incident hit other vehicle. Police called.")
    assert accident.packet_type == "accident_incident"
    assert accident.label == "Accident / Incident Packet"


def test_uncertain_packet_result_asks_one_short_question():
    from app.services.packet_classification import classify_packet_text

    result = classify_packet_text("Driver needs help with this note.")
    assert result.packet_type == "other_issue"
    assert result.needs_clarification is True
    assert result.question == "What type of record should this be?"


def test_packet_media_page_comes_before_full_event_timeline_and_missing_file_text(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import DamagePhoto

        driver = _create_user("media_driver", "media-driver@example.com", first_name="Media", last_name="Driver")
        _create_user("media_manager", "media-manager@example.com", "management")
        report = _create_report(driver, "Scratch on trailer door.")
        db.session.add(
            DamagePhoto(
                damage_report_id=report.id,
                stage="after",
                filename="missing-photo.jpg",
                original_filename="missing-photo.jpg",
                content_type="image/jpeg",
            )
        )
        db.session.commit()
        report_id = report.id

    _login(client, "media_manager")
    response = client.get(f"/manager/damage-reports/{report_id}/evidence-packet")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert body.index("Photo / Media Evidence") < body.index("Full Event Timeline")
    assert "Photo not available in upload storage" in body
