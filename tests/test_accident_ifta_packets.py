import re
from datetime import date, datetime
from io import BytesIO

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


def test_driver_packet_entry_pages_use_clear_labels_and_neutral_defaults(client, app):
    with app.app_context():
        create_user("entry_driver", "entry@example.com", "driver")

    login(client, "entry_driver")

    accident = client.get("/accident-incident/new")
    assert accident.status_code == 200
    accident_body = accident.get_data(as_text=True)
    assert "Crash or Safety Incident" in accident_body
    assert "Save Crash or Safety Incident" in accident_body
    assert '<option value="">Select</option>' in accident_body
    assert '<option value="unknown">Unknown</option>' in accident_body
    assert '<option value="needs_review">Needs Review</option>' in accident_body
    assert 'data-conditional-section="other-party" hidden' in accident_body
    assert "DOT review status" not in accident_body
    assert "Post-accident testing review" not in accident_body

    fuel = client.get("/ifta-worksheet/new")
    assert fuel.status_code == 200
    fuel_body = fuel.get_data(as_text=True)
    assert "<h1>Fuel Records</h1>" in fuel_body
    assert "Save Fuel Record" in fuel_body
    assert "Recent records" not in fuel_body
    assert 'data-fuel-type="Diesel"' in fuel_body
    assert 'data-fuel-type="DEF"' in fuel_body
    assert 'data-gps-hint="fuel station truck stop"' in fuel_body
    assert "Nearby fuel stations" in fuel_body
    assert "Suggested nearest fuel station" in fuel_body
    assert "IFTA license number" not in fuel_body
    assert "Base jurisdiction" not in fuel_body
    assert 'name="tax_paid"' not in fuel_body
    assert "Unknown</option>" not in fuel_body

    damage = client.get("/damage_reports/new")
    assert damage.status_code == 200
    damage_body = damage.get_data(as_text=True)
    assert "Physical Damage" in damage_body
    assert "Save Physical Damage" in damage_body


def test_fuel_page_shows_recent_records_first_with_receipt_button(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import IftaFuelRecord, IftaWorksheet

        driver = create_user("fuel_recent_driver", "fuel-recent@example.com", "driver")
        worksheet = IftaWorksheet(driver_id=driver.id, created_by_id=driver.id, truck="T-100")
        db.session.add(worksheet)
        db.session.flush()
        db.session.add(
            IftaFuelRecord(
                worksheet_id=worksheet.id,
                purchase_date=date(2026, 6, 12),
                seller_name="Route Fuel Stop",
                city="Industrial City",
                state_or_province="MI",
                gallons_or_liters=41.5,
                fuel_type="Diesel",
                total_sale_amount=151.23,
                receipt_photo="receipt.jpg",
                receipt_data=b"receipt image",
                receipt_mimetype="image/jpeg",
            )
        )
        db.session.commit()

    login(client, "fuel_recent_driver")
    response = client.get("/ifta-worksheet/new")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert body.index("Recent records") < body.index("Fuel details")
    assert "Route Fuel Stop" in body
    assert "41.5 gal" in body
    assert "$151.23" in body
    assert 'href="/ifta-worksheet/receipt/' in body
    assert 'target="_blank"' in body


def test_blank_fuel_record_labels_use_captured_facts_not_fuel_stop(app):
    with app.app_context():
        from app.blueprints.driver.routes import _fuel_record_label
        from app.models import IftaFuelRecord

        assert _fuel_record_label(IftaFuelRecord(fuel_type="Diesel")) == "Diesel"
        assert _fuel_record_label(IftaFuelRecord()) == "Fuel purchase"


def test_report_forms_prefill_known_route_context_and_hide_admin_fields(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import DriverLog, PreTrip, ShiftRecord

        driver = create_user("prefill_driver", "prefill@example.com", "driver", first_name="Lamar", last_name="Bibbs")
        route_date = date.today()
        pretrip = PreTrip(
            user_id=driver.id,
            pretrip_date=route_date,
            truck_number="ST4",
            trailer_number="TR9",
            shift="1st",
            start_mileage=244914,
        )
        db.session.add(pretrip)
        db.session.flush()
        db.session.add_all(
            [
                ShiftRecord(user_id=driver.id, pretrip_id=pretrip.id, start_time=datetime.utcnow()),
                DriverLog(
                    driver_id=driver.id,
                    date=route_date,
                    plant_name="RE",
                    load_size="Empty",
                    arrive_time="08:00",
                    created_at=datetime.utcnow(),
                ),
            ]
        )
        db.session.commit()

    login(client, "prefill_driver")
    accident_body = client.get("/accident-incident/new").get_data(as_text=True)
    fuel_body = client.get("/ifta-worksheet/new").get_data(as_text=True)

    assert 'name="truck" value="ST4"' in accident_body
    assert 'name="trailer" value="TR9"' in accident_body
    assert "Raleigh East" in accident_body
    assert "3505 Kraft Ave SE" in accident_body
    assert 'name="truck" value="ST4"' in fuel_body
    assert 'name="trailer" value="TR9"' in fuel_body
    assert 'name="vehicle_unit_number" value="ST4"' in fuel_body
    assert 'name="purchaser_name" value="Lamar Bibbs"' in fuel_body
    assert 'name="beginning_odometer" value="244914"' in fuel_body
    assert 'value="244914"' in fuel_body


def test_blank_driver_answers_do_not_save_fake_unknown_values(client, app):
    with app.app_context():
        create_user("blank_driver", "blank@example.com", "driver")

    login(client, "blank_driver")
    accident_response = client.post(
        "/accident-incident/new",
        data={"packet_type": "accident_incident", "driver_statement": "Facts only."},
        follow_redirects=False,
    )
    assert accident_response.status_code == 302
    fuel_response = client.post(
        "/ifta-worksheet/new",
        data={"seller_name": "Fuel Stop", "gallons_or_liters": "10", "fuel_type": "diesel"},
        follow_redirects=False,
    )
    assert fuel_response.status_code == 302

    with app.app_context():
        from app.models import AccidentIncidentReport, IftaFuelRecord

        report = AccidentIncidentReport.query.one()
        fuel = IftaFuelRecord.query.one()
        assert report.anyone_hurt is None
        assert report.police_called_quick is None
        assert report.other_vehicle_involved_quick is None
        assert fuel.tax_paid is None


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

    assert "Accident and Incident Packet" in text
    assert "DOT and FMCSA Review Screen" in text
    assert "Post-accident testing review" in text
    assert "Number of injuries" in text
    assert "Number of fatalities" in text
    assert "Copies of required state, government, or insurer reports attached" in text
    assert "DOT review needed" in text
    assert "DOT reportable: Yes" not in text
    assert "failed" not in text.lower()
    assert "Photo not available in upload storage" in text
    assert "Manager signature not captured" in text
    assert "Needs Review" in text
    assert "Complete" not in text
    assert body.index("Photos and Media") < body.index("Accident and Incident Details")
    assert body.index("Photos and Media") < body.index("Appendix B")


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
            "seller_address": "100 Fuel Way",
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

    view_body = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Receipt not attached" in view_body
    assert "Receipt hash: None" not in view_body

    packet = client.get("/ifta-worksheet/1/packet")
    assert packet.status_code == 200
    text = visible_text(packet.get_data(as_text=True))

    assert "IFTA Support Worksheet" in text
    assert "Fuel / Odometer / IFTA Worksheet Driver:" not in text
    assert "IFTA Support Worksheet Driver:" not in text
    assert "Photo / Media ProofDVIR" not in text
    assert "DVIR / PreTripCargo" not in text
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
    assert "100 Fuel Way" in text
    assert "diesel" in text
    assert "Attach receipt photo for 2026-04-01 Toledo fuel record." in text
    assert "Missing receipt rows" not in text
    assert "Photo not available in upload storage" not in text
    assert "Receipt Photos and File Hashes" not in text
    assert "Accurate Page" not in text


def test_sparse_ifta_packet_is_review_checklist_not_fake_pages(client, app):
    with app.app_context():
        create_user("ifta_sparse_driver", "ifta-sparse@example.com", "driver", first_name="Sparse", last_name="Driver")

    login(client, "ifta_sparse_driver")
    response = client.post(
        "/ifta-worksheet/new",
        data={
            "purchase_date": "2026-06-10",
            "fuel_city": "Grand Rapids",
            "state_or_province": "MI",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    packet = client.get("/ifta-worksheet/1/packet")
    assert packet.status_code == 200
    body = packet.get_data(as_text=True)
    text = visible_text(body)

    assert text.count("Open Items for Review") == 1
    assert "Add base jurisdiction." in text
    assert "Add carrier name." in text
    assert "Add IFTA license number, if applicable." in text
    assert "Add gallons for 2026-06-10 Grand Rapids fuel record." in text
    assert "Attach receipt photo for 2026-06-10 Grand Rapids fuel record." in text
    assert "Add jurisdiction mileage before using this worksheet for IFTA review." in text
    assert "Add trip origin/destination or route miles." in text
    assert "Fuel Records" in text
    assert "Grand Rapids" in text
    assert "Distance by Jurisdiction" not in text
    assert "Receipt Photos and File Hashes" not in text
    assert "Trip Detail" not in text
    assert "Appendix A" not in text
    assert "Appendix B" not in text
    assert "Raw Log" not in text
    assert "Not recorded" not in text
    assert "Photo not available in upload storage" not in text
    assert "Receipt hash" not in text
    assert "Accurate Page" not in text
    assert "<nav" not in body


def test_ifta_receipt_photo_renders_on_view_and_packet(client, app):
    with app.app_context():
        create_user("ifta_photo_driver", "ifta-photo@example.com", "driver", first_name="Ifta", last_name="Photo")

    login(client, "ifta_photo_driver")
    response = client.post(
        "/ifta-worksheet/new",
        data={
            "purchase_date": "2026-06-12",
            "seller_name": "Pilot Fuel",
            "seller_address": "400 Fuel Plaza Dr",
            "fuel_city": "Grand Rapids",
            "state_or_province": "MI",
            "fuel_type": "Diesel",
            "receipt_photo": (BytesIO(b"fake jpg bytes"), "fuel-receipt.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302

    view = client.get(response.headers["Location"])
    body = view.get_data(as_text=True)
    assert "Pilot Fuel" in body
    assert "400 Fuel Plaza Dr" in body
    assert "body.md-shell .ifta-panel" in body
    assert 'class="ifta-receipt-open"' in body
    assert 'class="ifta-receipt-preview"' in body
    assert "Open receipt" in body

    packet = client.get("/ifta-worksheet/1/packet")
    packet_body = packet.get_data(as_text=True)
    assert "Pilot Fuel" in packet_body
    assert "400 Fuel Plaza Dr" in packet_body
    assert 'class="receipt-preview"' in packet_body
    assert "ifta-receipt-1-" in packet_body
    assert ".jpg" in packet_body
    assert "Receipt Photos and File Hashes" in packet_body
    assert "Photo not available in upload storage" not in packet_body


def test_fuel_tank_damage_form_submission_routes_to_fuel_record_with_photo(client, app):
    with app.app_context():
        create_user("fuel_redirect_driver", "fuel-redirect@example.com", "driver", first_name="Fuel", last_name="Redirect")

    login(client, "fuel_redirect_driver")
    response = client.post(
        "/damage_reports/new",
        data={
            "truck_number": "ST4",
            "trailer_number": "TR2",
            "plant_name": "Other",
            "stage": "after",
            "move_reference": "Ryder",
            "description": "Leaving Ryder full fuel tank photo",
            "photo": (BytesIO(b"fuel tank bytes"), "fuel-tank.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ifta-worksheet/1")
    with app.app_context():
        from app.models import DamageReport, IftaFuelRecord, IftaWorksheet

        assert DamageReport.query.count() == 0
        worksheet = IftaWorksheet.query.one()
        fuel = IftaFuelRecord.query.one()
        assert worksheet.truck == "ST4"
        assert worksheet.trailer == "TR2"
        assert fuel.seller_name == "Ryder"
        assert fuel.fuel_type == "Fuel level"
        assert fuel.receipt_photo
        assert fuel.receipt_data == b"fuel tank bytes"

    view = client.get(response.headers["Location"])
    body = view.get_data(as_text=True)
    assert "Ryder" in body
    assert "Fuel level" in body
    assert 'class="ifta-receipt-preview"' in body


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
