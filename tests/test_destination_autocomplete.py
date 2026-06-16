"""Destination autocomplete + details: service shape, endpoints, persistence,
START ROUTE gating, and graceful manual fallback when Google is unavailable.

Coordinates here are synthetic test fixtures (not real driver GPS).
"""
import pytest

from app.services import google_places


# ----- fixtures --------------------------------------------------------------
@pytest.fixture()
def app(monkeypatch, tmp_path):
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


def _make_day_driver(username="dd_dest", email=None):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=email or f"{username}@example.com", role="driver")
    user.set_password("password1")
    user.day_driver = True
    user.route_type = "general_freight"
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username="dd_dest"):
    return client.post("/login", data={"login_name": username, "password": "password1"}, follow_redirects=False)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


# ----- service-level (Google request shape) ----------------------------------
def test_autocomplete_service_sends_session_token_and_origin(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, json))
        return FakeResponse(
            {
                "suggestions": [
                    {
                        "placePrediction": {
                            "placeId": "place-123",
                            "text": {"text": "Founders Brewing Co, Grand Rapids, MI"},
                            "structuredFormat": {
                                "mainText": {"text": "Founders Brewing Co"},
                                "secondaryText": {"text": "Grand Rapids, MI"},
                            },
                            "distanceMeters": 5000,
                        }
                    },
                    {"queryPrediction": {"text": {"text": "ignored"}}},
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    with flask_app.app_context():
        result = google_places.autocomplete_destination(
            "founders", lat=42.96, lng=-85.67, session_token="tok-1"
        )

    assert calls[0][0] == google_places.AUTOCOMPLETE_URL
    sent = calls[0][1]
    assert sent["input"] == "founders"
    assert sent["sessionToken"] == "tok-1"
    assert sent["origin"] == {"latitude": 42.96, "longitude": -85.67}
    assert sent["locationBias"]["circle"]["center"] == {"latitude": 42.96, "longitude": -85.67}

    assert result["ok"] is True
    assert result["session_token"] == "tok-1"
    assert result["suggestions"] == [
        {
            "place_id": "place-123",
            "main_text": "Founders Brewing Co",
            "secondary_text": "Grand Rapids, MI",
            "formatted_address": "Founders Brewing Co, Grand Rapids, MI",
            "distance_meters": 5000,
            "source": "google_places",
        }
    ]


def test_autocomplete_service_restricts_to_gas_stations_when_fuel_only(monkeypatch):
    # The fuel page's station-name field must only suggest fuel stations, while
    # every other place field keeps the general business/address search.
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(json)
        return FakeResponse({"suggestions": []})

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    with flask_app.app_context():
        google_places.autocomplete_destination("mob", session_token="tok-f", fuel_only=True)
        google_places.autocomplete_destination("mob", session_token="tok-f")

    assert calls[0]["includedPrimaryTypes"] == ["gas_station"]
    assert "includedPrimaryTypes" not in calls[1]


def test_fuel_autocomplete_sorts_closest_station_first(monkeypatch):
    # On the fuel page the driver wants the nearest pump, so fuel suggestions
    # must be ordered by distance rather than Google's text-relevance order.
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"

    def fake_post(url, *, headers, json, timeout):
        return FakeResponse(
            {
                "suggestions": [
                    {"placePrediction": {"placeId": "far", "structuredFormat": {"mainText": {"text": "Marathon Far"}}, "distanceMeters": 9000}},
                    {"placePrediction": {"placeId": "near", "structuredFormat": {"mainText": {"text": "Marathon Near"}}, "distanceMeters": 300}},
                    {"placePrediction": {"placeId": "mid", "structuredFormat": {"mainText": {"text": "Marathon Mid"}}, "distanceMeters": 1500}},
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    with flask_app.app_context():
        result = google_places.autocomplete_destination("marathon", lat=42.9, lng=-85.6, fuel_only=True)

    assert [s["main_text"] for s in result["suggestions"]] == ["Marathon Near", "Marathon Mid", "Marathon Far"]


def test_place_details_service_returns_minimal_fields_and_raw(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    calls = []

    def fake_get(url, *, headers, params, timeout):
        calls.append((url, headers.get("X-Goog-FieldMask"), params))
        return FakeResponse(
            {
                "id": "place-123",
                "displayName": {"text": "Founders Brewing Co"},
                "formattedAddress": "235 Grandville Ave SW, Grand Rapids, MI 49503, USA",
                "location": {"latitude": 42.95, "longitude": -85.67},
                "types": ["brewery", "point_of_interest"],
                "primaryType": "brewery",
                "businessStatus": "OPERATIONAL",
                "googleMapsUri": "https://maps.google.com/?cid=1",
                "parkingOptions": {"freeParkingLot": True},
            }
        )

    monkeypatch.setattr(google_places.requests, "get", fake_get)
    with flask_app.app_context():
        result = google_places.destination_place_details("place-123", session_token="tok-1")

    assert result["ok"] is True
    place = result["place"]
    assert place["name"] == "Founders Brewing Co"
    assert place["address"] == "235 Grandville Ave SW, Grand Rapids, MI 49503"
    assert place["lat"] == pytest.approx(42.95)
    assert place["lng"] == pytest.approx(-85.67)
    assert place["primary_type"] == "brewery"
    assert result["raw"]["parkingOptions"] == {"freeParkingLot": True}
    # Review/AI fields not requested unless enabled.
    assert "reviews" not in calls[0][1]
    assert calls[0][2]["sessionToken"] == "tok-1"


def test_place_details_retries_without_optional_fields_on_error(monkeypatch):
    # Turning the review/AI flags on must never break destination selection when a
    # key/region can't serve those fields: the call retries with minimal fields.
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    masks = []

    def fake_get(url, *, headers, params, timeout):
        mask = headers.get("X-Goog-FieldMask")
        masks.append(mask)
        if "reviews" in mask or "generativeSummary" in mask:
            return FakeResponse({"error": {"status": "INVALID_ARGUMENT", "message": "unsupported field"}}, status_code=400)
        return FakeResponse(
            {
                "id": "p1",
                "displayName": {"text": "Receiver Yard"},
                "formattedAddress": "1 Dock Rd, City, MI, USA",
                "location": {"latitude": 42.0, "longitude": -85.0},
            }
        )

    monkeypatch.setattr(google_places.requests, "get", fake_get)
    with flask_app.app_context():
        result = google_places.destination_place_details("p1", include_reviews=True, include_generative=True)

    assert result["ok"] is True
    assert result["place"]["name"] == "Receiver Yard"
    assert len(masks) == 2  # first attempt (with optional fields) failed, retried minimal
    assert "reviews" in masks[0]
    assert "reviews" not in masks[1] and "generativeSummary" not in masks[1]


def test_route_summary_uses_google_routes_api(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json))
        return FakeResponse(
            {
                "routes": [
                    {
                        "duration": "753s",
                        "distanceMeters": 4828,
                        "description": "US-131 S",
                    }
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    with flask_app.app_context():
        result = google_places.route_summary(42.929224, -85.662701, 42.95, -85.67)

    assert calls[0][0] == google_places.ROUTES_URL
    assert calls[0][1]["X-Goog-FieldMask"] == "routes.duration,routes.distanceMeters,routes.description"
    assert calls[0][2]["travelMode"] == "DRIVE"
    assert result == {
        "ok": True,
        "distance_text": "3.0 mi",
        "duration_text": "13 min",
        "route_text": "via US-131 S",
    }


def test_nearby_truck_services_returns_closest_fuel(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["GOOGLE_MAPS_API_KEY"] = "test-key"
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json))
        return FakeResponse(
            {
                "places": [
                    {
                        "displayName": {"text": "Speedway"},
                        "location": {"latitude": 42.951, "longitude": -85.67},
                        "types": ["gas_station", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    with flask_app.app_context():
        result = google_places.nearby_truck_services(42.95, -85.67, limit=5)

    assert calls[0][0] == google_places.NEARBY_URL
    assert calls[0][2]["includedTypes"] == ["gas_station"]
    assert calls[0][2]["maxResultCount"] == 5
    assert calls[0][2]["locationRestriction"]["circle"]["radius"] == google_places.NEARBY_FUEL_RADIUS_M
    assert result[0]["name"] == "Speedway"
    assert result[0]["type"] == "fuel nearby"
    assert result[0]["distance_text"]


def test_review_and_generative_summary_flags_default_on(app):
    assert app.config["ENABLE_GOOGLE_REVIEW_SUMMARY"] is True
    assert app.config["ENABLE_GOOGLE_GENERATIVE_SUMMARY"] is True
    assert app.config["ENABLE_TRUCKER_PLACE_SUMMARY"] is True


# ----- endpoint-level --------------------------------------------------------
def test_autocomplete_endpoint_returns_suggestions_with_session_token(client, app, monkeypatch):
    with app.app_context():
        _make_day_driver()
    seen = {}

    def fake_autocomplete(text, *, lat=None, lng=None, session_token="", limit=6):
        seen["text"] = text
        seen["session_token"] = session_token
        seen["lat"] = lat
        return {
            "ok": True,
            "session_token": session_token,
            "suggestions": [
                {"place_id": "p1", "main_text": "Warehouse " + text, "secondary_text": "City",
                 "formatted_address": "1 Dock Rd", "distance_meters": 1200, "source": "google_places"}
            ],
        }

    monkeypatch.setattr("app.blueprints.driver.routes.autocomplete_destination", fake_autocomplete)
    _login(client)

    first = client.post("/api/places/destination-autocomplete",
                        json={"input": "foun", "session_token": "tok-9", "lat": 42.9, "lng": -85.5})
    assert first.status_code == 200
    data = first.get_json()
    assert data["ok"] is True
    assert seen["session_token"] == "tok-9"
    assert data["suggestions"][0]["main_text"] == "Warehouse foun"

    # Suggestions update as the input changes (test 9).
    second = client.post("/api/places/destination-autocomplete",
                         json={"input": "founders", "session_token": "tok-9"})
    assert second.get_json()["suggestions"][0]["main_text"] == "Warehouse founders"


def test_geo_suggest_endpoint_threads_fuel_only_flag(client, app, monkeypatch):
    # The one-driver page's /api/geo/suggest proxy must forward the fuel_only
    # flag so the fuel station-name field is restricted to gas stations.
    captured = []

    def fake_autocomplete(text, *, lat=None, lng=None, session_token="", limit=6, fuel_only=False):
        captured.append(fuel_only)
        return {"ok": True, "session_token": session_token, "suggestions": []}

    monkeypatch.setattr("app.blueprints.public.routes.autocomplete_destination", fake_autocomplete)

    fuel = client.post("/api/geo/suggest", json={"input": "mob", "fuel_only": True})
    assert fuel.status_code == 200
    assert captured[0] is True

    general = client.post("/api/geo/suggest", json={"input": "mob"})
    assert general.status_code == 200
    assert captured[1] is False


def test_details_endpoint_populates_destination_and_driver_summary(client, app, monkeypatch):
    with app.app_context():
        _make_day_driver()

    def fake_details(place_id, *, session_token="", include_reviews=False, include_generative=False):
        return {
            "ok": True,
            "place": {
                "place_id": place_id,
                "name": "Founders Brewing Co",
                "address": "235 Grandville Ave SW, Grand Rapids, MI 49503",
                "lat": 42.95,
                "lng": -85.67,
                "types": ["brewery"],
                "primary_type": "brewery",
                "business_status": "OPERATIONAL",
                "google_maps_uri": "https://maps.google.com/?cid=1",
                "source": "google_places",
            },
            "raw": {"parkingOptions": {"freeParkingLot": True}, "currentOpeningHours": {"openNow": True}},
        }

    monkeypatch.setattr("app.blueprints.driver.routes.destination_place_details", fake_details)
    monkeypatch.setattr(
        "app.blueprints.driver.routes.route_summary",
        lambda *args: {"ok": True, "duration_text": "12 min", "distance_text": "4.1 mi", "route_text": "via US-131"},
    )
    monkeypatch.setattr(
        "app.blueprints.driver.routes.nearby_truck_services",
        lambda *args: [{"name": "Speedway", "distance_text": "0.4 mi"}],
    )
    _login(client)

    response = client.post("/api/places/destination-details",
                           json={"place_id": "place-123", "session_token": "tok-9", "lat": 42.929, "lng": -85.662})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    dest = data["destination"]
    assert dest["place_name"] == "Founders Brewing Co"
    assert dest["address"] == "235 Grandville Ave SW, Grand Rapids, MI 49503"
    assert dest["lat"] == pytest.approx(42.95)
    assert dest["place_id"] == "place-123"
    assert dest["source"] == "google_places"
    assert dest["confirmed"] is True
    # Maps driver summary card is filled from route, official parking/hours fields, and nearby fuel.
    assert data["driver_summary"]["driver_summary_lines"] == [
        "12 min away via US-131",
        "Open now",
        "Free parking lot on site",
        "Fuel nearby: Speedway (0.4 mi)",
    ]
    assert data["driver_summary"]["nearby_driver_places"][0]["name"] == "Speedway"
    assert "driver_notes" not in data


def test_details_endpoint_missing_place_id_is_graceful(client, app):
    with app.app_context():
        _make_day_driver()
    _login(client)
    response = client.post("/api/places/destination-details", json={"place_id": ""})
    assert response.status_code == 200
    assert response.get_json()["ok"] is False


# ----- persistence + gating + manual fallback --------------------------------
def test_new_log_persists_selected_destination_fields(client, app):
    with app.app_context():
        _make_day_driver()
    _login(client)
    created = client.post(
        "/new_driving_log",
        data={
            "location_address": "1916 Jefferson Ave SE, Grand Rapids, MI 49507",
            "location": "Start Yard",
            "destination_place_name": "Founders Brewing Co",
            "destination_address": "235 Grandville Ave SW, Grand Rapids, MI 49503",
            "destination_lat": "42.95",
            "destination_lng": "-85.67",
            "destination_place_id": "place-123",
            "destination_source": "google_places",
            "destination_confirmed": "true",
        },
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)
    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="Start Yard").one()
        assert log.destination_place_name == "Founders Brewing Co"
        assert log.destination_address == "235 Grandville Ave SW, Grand Rapids, MI 49503"
        assert log.destination_lat == pytest.approx(42.95)
        assert log.destination_lng == pytest.approx(-85.67)
        assert log.destination_place_id == "place-123"
        assert log.destination_source == "google_places"
        assert log.destination_confirmed is True


def test_start_route_button_disabled_until_destination_on_first_stop(client, app):
    with app.app_context():
        _make_day_driver()
    _login(client)
    page = client.get("/new_driving_log")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'id="destinationSection"' in body
    assert "Next destination name / location" in body
    assert "(optional)" in body
    assert "Business name or address" in body
    assert "Use this when you know the next stop." in body
    assert "No next destination" in body
    assert 'data-gate-start="1"' in body
    assert 'id="startRouteBtn"' in body
    assert "disabled" in body  # Start Route is gated until location plus destination or a deliberate skip
    assert "/api/places/destination-autocomplete" in body
    assert "/api/places/destination-details" in body
    assert "Maps driver summary" in body
    assert "driverSummaryLines" in body
    assert "driverNotesList" not in body
    assert "body.md-shell #destinationSelected .card-body" in body
    assert "background: transparent !important" in body
    assert "function suggestionLabel" in body
    assert "input.value = resolvedName" in body
    assert "applyDestination(data.destination, s)" in body
    assert "function selectedDestinationVisible" in body
    assert "function repairDestinationFieldsFromCard" in body
    assert "function confirmSelectedDestination" in body
    assert "function cancelSelectedDestination" in body
    assert "function skipDestination" in body
    assert "function destinationSkipped" in body
    assert "function typedDestinationReady" in body
    assert "function startRouteButton" in body
    assert "function ensureDestinationBeforeSubmit" in body
    assert "destinationConfirmed() || typedDestinationReady() || destinationSkipped()" in body
    assert "routeForm.addEventListener('submit', ensureDestinationBeforeSubmit)" in body
    assert "document.addEventListener('DOMContentLoaded', syncStartButton)" in body
    assert 'id="destinationCancelBtn"' in body
    assert 'aria-label="Cancel selected destination"' in body
    assert 'id="destinationSkipBtn"' in body
    assert 'id="destination_skipped"' in body
    assert "selected.addEventListener('click', confirmSelectedDestination)" in body
    assert "skipBtn.addEventListener('click', skipDestination)" in body
    assert "if (destinationConfirmed()) clearSelection();" in body
    assert "destinationChangeBtn" not in body


def test_manual_destination_saved_when_google_unavailable(client, app):
    # With no usable Google key, autocomplete reports failure gracefully, but the
    # driver can still type and confirm a manual destination.
    app.config["GOOGLE_MAPS_API_KEY"] = ""  # force the unavailable path (no network)
    with app.app_context():
        _make_day_driver()
    _login(client)

    auto = client.post("/api/places/destination-autocomplete", json={"input": "anywhere", "session_token": "t"})
    assert auto.status_code == 200
    assert auto.get_json()["ok"] is False  # graceful, not a 500

    created = client.post(
        "/new_driving_log",
        data={
            "location_address": "1916 Jefferson Ave SE, Grand Rapids, MI",
            "location": "Start Yard",
            "destination_place_name": "Smith Family Warehouse",
            "destination_source": "manual",
            "destination_confirmed": "true",
        },
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)
    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="Start Yard").one()
        assert log.destination_place_name == "Smith Family Warehouse"
        assert log.destination_source == "manual"
        assert log.destination_confirmed is True


def test_day_driver_can_start_route_with_no_next_destination(client, app):
    with app.app_context():
        _make_day_driver()
    _login(client)

    created = client.post(
        "/new_driving_log",
        data={
            "location_address": "1916 Jefferson Ave SE, Grand Rapids, MI",
            "location": "Start Yard",
            "destination_skipped": "true",
        },
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)
    with app.app_context():
        from app.models import DriverLog

        log = DriverLog.query.filter_by(plant_name="Start Yard").one()
        assert log.destination_place_name is None
        assert log.destination_address is None
        assert log.destination_source is None
        assert log.destination_confirmed is False
