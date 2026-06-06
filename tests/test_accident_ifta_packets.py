import re

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
        PACKET_UPLOAD_FOLDER=str(tmp_path / "packet_media"),
        IFTA_UPLOAD_FOLDER=str(tmp_path / "ifta_receipts"),
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


def visible_text(html):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def test_accident_form_trigger_logic_is_not_forced_for_regular_damage():
    from app.services.accident_packets import accident_form_required

    assert accident_form_required(packet_type="damage_issue", answers={}) is False
    assert accident_form_required(packet_type="accident_incident", answers={}) is True
    assert accident_form_required(packet_type="damage_issue", answers={"police_called": "yes"}) is True
    assert accident_form_required(packet_type="damage_issue", answers={"anyone_hurt": "unknown"}) is False


def test_accident_packet_contains_review_sections_without_driver_legal_conclusion(client, app):
    with app.app_context():
        create_user("accident_driver", "accident@example.com", "driver", first_name="Alex", last_name="Driver")

    login(client, "accident_driver")
    response = client.post(
        "/accident-incident/new",
        data={
            "packet_type": "accident_incident",
            "incident_date_time": "2026-06-06T08:30",
            "truck": "T-9",
            "trailer": "TR-2",
            "route_id": "route-1",
            "plant_or_location": "Yard",
            "exact_location_text": "North dock",
            "nearest_city_or_town": "Detroit",
            "state": "MI",
            "anyone_hurt": "no",
            "police_called": "yes",
            "police_called_quick": "yes",
            "driver_statement": "Truck was stopped at the dock when the contact happened.",
            "facts_only_acknowledgement": "yes",
            "public_road_in_commerce": "yes",
            "number_of_injuries": "0",
            "number_of_fatalities": "0",
            "required_reports_attached": "no",
            "loss_of_human_life": "yes",
            "alcohol_test_review": "needs_review",
            "controlled_substance_test_review": "needs_review",
            "photos_required_complete": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    packet = client.get("/accident-incident/1/packet")
    assert packet.status_code == 200
    body = packet.get_data(as_text=True)
    text = visible_text(body)

    assert "Accident / Incident Packet" in text
    assert "DOT / FMCSA Review Screen" in text
    assert "Post-accident testing review" in text
    assert "Number of injuries" in text
    assert "Number of fatalities" in text
    assert "Copies of required state/government/insurer reports attached" in text
    assert "DOT review needed" in text
    assert "DOT reportable: Yes" not in text
    assert "failed" not in text.lower()
    assert "Photo not available in upload storage" in text
    assert "Manager signature not captured" in text
    assert "Needs Review" in text
    assert "Complete" not in text
    assert body.index("Photo / Media Evidence") < body.index("Accident / Incident Details")
    assert body.index("Photo / Media Evidence") < body.index("Appendix B")


def test_ifta_packet_includes_support_fields_and_missing_receipt_state(client, app):
    with app.app_context():
        create_user("ifta_driver", "ifta@example.com", "driver", first_name="Ifta", last_name="Driver")

    login(client, "ifta_driver")
    response = client.post(
        "/ifta-worksheet/new",
        data={
            "reporting_period_quarter": "Q2",
            "reporting_year": "2026",
            "truck": "T-22",
            "trailer": "TR-9",
            "vin_or_vehicle_unit_number": "VIN123",
            "base_jurisdiction": "MI",
            "carrier_name": "MoveDefense Demo Carrier",
            "trip_start_date": "2026-04-01",
            "trip_end_date": "2026-04-02",
            "origin_city": "Detroit",
            "origin_state": "MI",
            "destination_city": "Toledo",
            "destination_state": "OH",
            "route_traveled": "I-75",
            "beginning_odometer": "1000",
            "ending_odometer": "1120",
            "total_trip_distance": "120",
            "jurisdiction": "OH",
            "jurisdiction_distance": "50",
            "taxable_distance": "50",
            "nontaxable_distance": "0",
            "purchase_date": "2026-04-01",
            "seller_name": "Fuel Stop",
            "fuel_city": "Toledo",
            "state_or_province": "OH",
            "gallons_or_liters": "30",
            "fuel_type": "diesel",
            "vehicle_unit_number": "VIN123",
            "purchaser_name": "Ifta Driver",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    packet = client.get("/ifta-worksheet/1/packet")
    assert packet.status_code == 200
    text = visible_text(packet.get_data(as_text=True))

    assert "IFTA Support Worksheet" in text
    assert "IFTA Return" not in text
    assert "VIN123" in text
    assert "Detroit" in text
    assert "Toledo" in text
    assert "I-75" in text
    assert "1000" in text
    assert "1120" in text
    assert "120" in text
    assert "50" in text
    assert "Fuel Stop" in text
    assert "diesel" in text
    assert "Photo not available in upload storage" in text
    assert "Missing receipt rows" in text


def test_new_packet_outputs_avoid_banned_visible_terms(client, app):
    with app.app_context():
        create_user("copy_driver", "copy@example.com", "driver")

    login(client, "copy_driver")
    client.post(
        "/accident-incident/new",
        data={"packet_type": "accident_incident", "driver_statement": "Facts only.", "facts_only_acknowledgement": "yes"},
    )
    client.post(
        "/ifta-worksheet/new",
        data={"reporting_period_quarter": "Q1", "reporting_year": "2026", "truck": "T1"},
    )
    accident_text = visible_text(client.get("/accident-incident/1/packet").get_data(as_text=True))
    ifta_text = visible_text(client.get("/ifta-worksheet/1/packet").get_data(as_text=True))
    combined = f"{accident_text} {ifta_text}"
    lowered = combined.lower()
    for word in ("critical", "exception", "gap", "warning"):
        assert word not in lowered
    assert "FCSMA" not in combined
