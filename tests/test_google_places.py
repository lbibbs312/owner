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
        post_calls.append((url, json))
        if url == google_places.TEXT_SEARCH_URL:
            return FakeResponse(
                {
                    "places": [
                        {
                            "id": "current-dock-address",
                            "displayName": {"text": "Current Dock Manufacturing"},
                            "formattedAddress": "1100 Current Dock Dr, Industrial City, MI 49512, USA",
                            "location": {"latitude": 42.900936, "longitude": -85.531056},
                            "types": ["manufacturer", "point_of_interest", "establishment"],
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "far-supplier",
                        "displayName": {"text": "Far Supplier Warehouse"},
                        "shortFormattedAddress": "900 Far Dock Rd, Industrial City",
                        "location": {"latitude": 42.901278, "longitude": -85.531056},
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
                    },
                    {
                        "types": ["premise"],
                        "formatted_address": "1102 Current Dock Dr, Industrial City, MI 49512, USA",
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
            accuracy_m=13,
            hint="current dock",
        )

    assert post_calls[0][1]["locationRestriction"]["circle"]["radius"] == 12
    assert post_calls[1][0] == google_places.TEXT_SEARCH_URL
    assert post_calls[1][1]["textQuery"] == "1100 Current Dock Dr, Industrial City, MI 49512"
    assert payload["places"][0]["name"] == "Current Dock Manufacturing"
    assert payload["places"][0]["trusted"] is True
    assert payload["places"][0]["address_match"] is True
    assert "Far Supplier Warehouse" not in [place["name"] for place in payload["places"]]
    assert payload["fallback_address"] == "1100 Current Dock Dr, Industrial City, MI 49512"
    assert [item["address"] for item in payload["address_candidates"]] == [
        "1100 Current Dock Dr, Industrial City, MI 49512",
        "1102 Current Dock Dr, Industrial City, MI 49512",
    ]
    assert get_calls[0]["result_type"] == "premise|subpremise|street_address"


def test_gps_address_lookup_can_return_five_business_suggestions(monkeypatch, flask_app):
    post_calls = []

    def fake_post(url, *, headers, json, timeout):
        post_calls.append((url, json))
        if url != google_places.TEXT_SEARCH_URL:
            return FakeResponse({"places": []})
        street_number = json["textQuery"].split()[0]
        return FakeResponse(
            {
                "places": [
                    {
                        "id": f"business-{street_number}",
                        "displayName": {"text": f"Business {street_number}"},
                        "formattedAddress": f"{street_number} Test Dock Dr, Industrial City, MI 49512, USA",
                        "types": ["warehouse", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    def fake_get(url, *, params, timeout):
        return FakeResponse(
            {
                "status": "OK",
                "results": [
                    {
                        "types": ["premise"],
                        "formatted_address": f"{number} Test Dock Dr, Industrial City, MI 49512, USA",
                    }
                    for number in ("1100", "1102", "1104", "1106", "1108")
                ],
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    monkeypatch.setattr(google_places.requests, "get", fake_get)

    with flask_app.app_context():
        payload = google_places.nearby_place_candidates(
            42.900846,
            -85.531056,
            accuracy_m=5,
            hint="dock",
        )

    assert post_calls[0][0] == google_places.NEARBY_URL
    assert [call[1]["textQuery"] for call in post_calls[1:]] == [
        "1100 Test Dock Dr, Industrial City, MI 49512",
        "1102 Test Dock Dr, Industrial City, MI 49512",
        "1104 Test Dock Dr, Industrial City, MI 49512",
        "1106 Test Dock Dr, Industrial City, MI 49512",
        "1108 Test Dock Dr, Industrial City, MI 49512",
    ]
    assert [place["name"] for place in payload["places"]] == [
        "Business 1100",
        "Business 1102",
        "Business 1104",
        "Business 1106",
        "Business 1108",
    ]
    assert all(place["source"] == "google_address" for place in payload["places"])
    assert payload["radius_m"] == 8


def test_fuel_hint_requests_at_least_five_nearby_gas_stations(monkeypatch, flask_app):
    post_calls = []

    def fake_post(url, *, headers, json, timeout):
        post_calls.append((url, json))
        if url == google_places.TEXT_SEARCH_URL:
            return FakeResponse({"places": []})
        return FakeResponse(
            {
                "places": [
                    {
                        "id": f"fuel-{index}",
                        "displayName": {"text": f"Fuel Station {index}"},
                        "shortFormattedAddress": f"{1000 + index} Fuel Rd, Industrial City",
                        "location": {
                            "latitude": 42.900846 + (index * 0.001),
                            "longitude": -85.531056,
                        },
                        "types": ["gas_station", "point_of_interest", "establishment"],
                    }
                    for index in range(1, 6)
                ]
            }
        )

    def fake_get(url, *, params, timeout):
        return FakeResponse({"status": "OK", "results": []})

    monkeypatch.setattr(google_places.requests, "post", fake_post)
    monkeypatch.setattr(google_places.requests, "get", fake_get)

    with flask_app.app_context():
        payload = google_places.nearby_place_candidates(
            42.900846,
            -85.531056,
            accuracy_m=8,
            limit=3,
            hint="fuel station truck stop",
        )

    nearby_request = post_calls[0][1]
    assert nearby_request["includedTypes"] == ["gas_station"]
    assert nearby_request["maxResultCount"] == 5
    assert nearby_request["locationRestriction"]["circle"]["radius"] == google_places.FUEL_PLACE_RADIUS_M
    assert len(payload["places"]) == 5
    assert [place["name"] for place in payload["places"]] == [
        "Fuel Station 1",
        "Fuel Station 2",
        "Fuel Station 3",
        "Fuel Station 4",
        "Fuel Station 5",
    ]
    assert payload["radius_m"] == google_places.FUEL_PLACE_RADIUS_M


def test_precise_gps_keeps_close_google_place(monkeypatch, flask_app):
    def fake_post(url, *, headers, json, timeout):
        if url == google_places.TEXT_SEARCH_URL:
            return FakeResponse({"places": []})
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "close-customer-dock",
                        "displayName": {"text": "Current Dock Manufacturing"},
                        "shortFormattedAddress": "1100 Current Dock Dr, Industrial City",
                        "location": {"latitude": 42.900891, "longitude": -85.531056},
                        "types": ["manufacturer", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    def fake_get(url, *, params, timeout):
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

    close_match = next(place for place in payload["places"] if place["name"] == "Current Dock Manufacturing")
    assert close_match["distance_m"] <= 6
    assert close_match["trusted"] is True
    assert payload["fallback_address"] == "1100 Current Dock Dr, Industrial City, MI 49512"
    assert payload["address_candidates"][0]["address"] == "1100 Current Dock Dr, Industrial City, MI 49512"


def test_destination_lookup_returns_business_name_and_address(monkeypatch, flask_app):
    post_calls = []

    def fake_post(url, *, headers, json, timeout):
        post_calls.append((url, json))
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "destination-locality",
                        "displayName": {"text": "Raleigh"},
                        "formattedAddress": "Raleigh, NC, USA",
                        "types": ["locality", "political"],
                    },
                    {
                        "id": "destination-customer",
                        "displayName": {"text": "Receiver Warehouse"},
                        "formattedAddress": "1100 Receiver Ave, Industrial City, MI 49512, USA",
                        "types": ["warehouse", "point_of_interest", "establishment"],
                    },
                    {
                        "id": "destination-annex",
                        "displayName": {"text": "Receiver Annex"},
                        "formattedAddress": "1110 Receiver Ave, Industrial City, MI 49512, USA",
                        "types": ["warehouse", "point_of_interest", "establishment"],
                    }
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)

    with flask_app.app_context():
        payload = google_places.lookup_destination_place("1100 Receiver Ave Industrial City")

    assert post_calls[0][0] == google_places.TEXT_SEARCH_URL
    assert post_calls[0][1]["textQuery"] == "1100 Receiver Ave Industrial City"
    assert post_calls[0][1]["maxResultCount"] == 5
    assert payload["ok"] is True
    assert payload["place"]["name"] == "Receiver Warehouse"
    assert payload["place"]["address"] == "1100 Receiver Ave, Industrial City, MI 49512"
    assert [place["name"] for place in payload["places"]] == ["Receiver Warehouse", "Receiver Annex"]
    assert "Raleigh" not in [place["name"] for place in payload["places"]]
    assert payload["places"][1]["address"] == "1110 Receiver Ave, Industrial City, MI 49512"


def test_destination_lookup_sends_location_bias_and_near_context(monkeypatch, flask_app):
    post_calls = []

    def fake_post(url, *, headers, json, timeout):
        post_calls.append((url, json))
        return FakeResponse(
            {
                "places": [
                    {
                        "id": "destination-local",
                        "displayName": {"text": "4365 52nd St SE"},
                        "formattedAddress": "4365 52nd St SE, Grand Rapids, MI 49512, USA",
                        "types": ["street_address"],
                    },
                    {
                        "id": "destination-other",
                        "displayName": {"text": "4365 Canal Ave SW"},
                        "formattedAddress": "4365 Canal Ave SW, Grandville, MI 49418, USA",
                        "types": ["street_address"],
                    },
                ]
            }
        )

    monkeypatch.setattr(google_places.requests, "post", fake_post)

    with flask_app.app_context():
        payload = google_places.lookup_destination_place(
            "4365 52nd St SE",
            bias_lat=42.8706,
            bias_lng=-85.5359,
            near="4365 52nd St SE, Grand Rapids, MI 49512",
        )

    assert post_calls[0][0] == google_places.TEXT_SEARCH_URL
    assert post_calls[0][1]["textQuery"] == "4365 52nd St SE near 4365 52nd St SE, Grand Rapids, MI 49512"
    assert post_calls[0][1]["locationBias"] == {
        "circle": {
            "center": {"latitude": 42.8706, "longitude": -85.5359},
            "radius": 50000,
        }
    }
    assert payload["ok"] is True
    assert payload["places"][0]["address"] == "4365 52nd St SE, Grand Rapids, MI 49512"
    assert len(payload["places"]) == 2
