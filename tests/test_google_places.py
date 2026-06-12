import pytest
from flask import Flask

from app.services import google_places


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def flask_app():
    app = Flask(__name__)
    app.config["GOOGLE_MAPS_API_KEY"] = "test-google-key"
    return app


def test_precise_gps_filters_far_google_place_and_uses_address(monkeypatch, flask_app):
    post_calls = []
    get_calls = []

    def fake_post(url, *, headers, json, timeout):
        post_calls.append(json)
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "far-supplier",
                        "displayName": {"text": "Far Supplier Warehouse"},
                        "shortFormattedAddress": "900 Far Dock Rd, Industrial City",
                        "location": {"latitude": 42.902476, "longitude": -85.531056},
                        "types": ["manufacturer", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    def fake_get(url, *, params, timeout):
        get_calls.append(params)
        return FakeResponse(
            {
                "status": "OK",
                "results": [
                    {
                        "types": ["street_address"],
                        "formatted_address": "1100 Current Dock Dr, Industrial City, MI 49512, USA",
                    }
                ],
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    monkeypatch.setattr(google_places.requests, "get", fake_get)

    with flask_app.app_context():
        payload = google_places.nearby_place_candidates(
            42.900846,
            -85.531056,
            accuracy_m=8,
            hint="current dock",
        )

    assert post_calls[0]["locationRestriction"]["circle"]["radius"] <= 60
    assert payload["places"] == []
    assert payload["fallback_address"] == "1100 Current Dock Dr, Industrial City, MI 49512"
    assert get_calls[0]["result_type"] == "premise|subpremise|street_address"


def test_precise_gps_keeps_close_google_place(monkeypatch, flask_app):
    def fake_post(url, *, headers, json, timeout):
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "close-customer-dock",
                        "displayName": {"text": "Current Dock Manufacturing"},
                        "shortFormattedAddress": "1100 Current Dock Dr, Industrial City",
                        "location": {"latitude": 42.900936, "longitude": -85.531056},
                        "types": ["manufacturer", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    def fake_get(url, *, params, timeout):
        raise AssertionError("fallback geocode should not be needed for a close place")

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    monkeypatch.setattr(google_places.requests, "get", fake_get)

    with flask_app.app_context():
        payload = google_places.nearby_place_candidates(
            42.900846,
            -85.531056,
            accuracy_m=8,
            hint="current dock",
        )

    assert payload["places"][0]["name"] == "Current Dock Manufacturing"
    assert payload["places"][0]["distance_m"] < 20
    assert payload["fallback_address"] == ""
