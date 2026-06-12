"""Google Maps place lookup for driver GPS capture."""
from __future__ import annotations

import math
import re

import requests
from flask import current_app


NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

BUSINESS_TYPES = {
    "accounting",
    "airport",
    "car_repair",
    "car_wash",
    "convenience_store",
    "establishment",
    "gas_station",
    "hardware_store",
    "local_government_office",
    "moving_company",
    "parking",
    "point_of_interest",
    "post_office",
    "premise",
    "storage",
    "store",
}
LOW_VALUE_TYPES = {
    "atm",
    "bus_station",
    "finance",
    "intersection",
    "locality",
    "political",
    "route",
    "street_address",
    "transit_station",
}
PREMISE_GEOCODE_TYPES = {"premise", "subpremise", "street_address"}
DEFAULT_PLACE_RADIUS_M = 90
MIN_PLACE_RADIUS_M = 45
MAX_PLACE_RADIUS_M = 260


def _clean(value):
    return " ".join((value or "").strip().split())


def _api_key():
    return _clean(current_app.config.get("GOOGLE_MAPS_API_KEY"))


def _distance_m(lat1, lng1, lat2, lng2):
    radius = 6371000
    to_rad = math.pi / 180
    d_lat = (lat2 - lat1) * to_rad
    d_lng = (lng2 - lng1) * to_rad
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1 * to_rad)
        * math.cos(lat2 * to_rad)
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_radius_m(accuracy_m):
    accuracy = _float_or_none(accuracy_m)
    if accuracy is None or accuracy <= 0:
        return DEFAULT_PLACE_RADIUS_M
    if accuracy <= 15:
        return max(MIN_PLACE_RADIUS_M, int(round(accuracy * 3 + 30)))
    if accuracy <= 50:
        return min(MAX_PLACE_RADIUS_M, int(round(accuracy * 2 + 50)))
    return min(MAX_PLACE_RADIUS_M, int(round(accuracy * 2 + 80)))


def _place_point(result):
    location = result.get("location") or (result.get("geometry") or {}).get("location") or {}
    lat = _float_or_none(location.get("latitude", location.get("lat")))
    lng = _float_or_none(location.get("longitude", location.get("lng")))
    if lat is None or lng is None:
        return None
    return lat, lng


def _place_name(result):
    display_name = result.get("displayName") or {}
    if isinstance(display_name, dict):
        return _clean(display_name.get("text"))
    return _clean(result.get("name"))


def _is_useful_place(result):
    name = _place_name(result)
    if not name:
        return False
    lowered = name.lower()
    if lowered in {"atm", "bus stop", "parking"}:
        return False
    types = set(result.get("types") or [])
    if types and types <= LOW_VALUE_TYPES:
        return False
    return bool(types & BUSINESS_TYPES) or bool(result.get("id") or result.get("place_id"))


def _format_address(value):
    address = _clean(value)
    if address.endswith(", USA"):
        address = address[:-5]
    return address


def _hint_tokens(value):
    ignored = {"east", "west", "north", "south", "stop", "dock", "the"}
    return [
        token
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) >= 4 and token not in ignored
    ][:6]


def _hint_score(candidate, tokens):
    if not tokens:
        return 0
    haystack = f"{candidate.get('name', '')} {candidate.get('address', '')}".lower()
    return sum(1 for token in tokens if token in haystack)


def _name_looks_like_address(name, address):
    name = _clean(name).lower()
    address = _clean(address).lower()
    if not name:
        return True
    if address and name == address:
        return True
    return bool(re.match(r"^\d+\s+\w+", name))


def _fallback_address(lat, lng, key):
    response = requests.get(
        GEOCODE_URL,
        params={
            "key": key,
            "latlng": f"{lat:.6f},{lng:.6f}",
            "result_type": "premise|subpremise|street_address",
        },
        timeout=6,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        return ""
    for result in payload.get("results") or []:
        types = set(result.get("types") or [])
        if types & PREMISE_GEOCODE_TYPES:
            return _format_address(result.get("formatted_address"))
    return ""


def nearby_place_candidates(lat, lng, *, accuracy_m=None, limit=8, hint=""):
    """Return likely business/place candidates near a raw browser GPS point."""
    key = _api_key()
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Google Maps API key is not configured.",
            "places": [],
            "fallback_address": "",
        }

    radius = _candidate_radius_m(accuracy_m)
    response = requests.post(
        NEARBY_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.formattedAddress",
                    "places.shortFormattedAddress",
                    "places.location",
                    "places.types",
                    "places.primaryType",
                ]
            ),
        },
        json={
            "maxResultCount": max(1, min(int(limit), 20)),
            "rankPreference": "DISTANCE",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius,
                }
            },
        },
        timeout=6,
    )
    payload = response.json()
    if response.status_code >= 400 or payload.get("error"):
        error = payload.get("error") or {}
        return {
            "ok": False,
            "error": error.get("status") or f"http_{response.status_code}",
            "message": error.get("message") or "Google Places did not return nearby places.",
            "places": [],
            "fallback_address": "",
        }

    candidates = []
    seen = set()
    for result in payload.get("places") or []:
        if not _is_useful_place(result):
            continue
        point = _place_point(result)
        if point is None:
            continue
        distance = _distance_m(lat, lng, point[0], point[1])
        if distance > radius:
            continue
        place_id = result.get("id") or result.get("place_id") or ""
        name = _place_name(result)
        address = _format_address(result.get("shortFormattedAddress") or result.get("formattedAddress"))
        if not name:
            continue
        dedupe_key = (name.lower(), address.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "place_id": place_id,
                "name": name,
                "address": address,
                "distance_m": int(round(distance)),
                "lat": point[0],
                "lng": point[1],
                "source": "google",
            }
        )

    tokens = _hint_tokens(hint)
    candidates.sort(key=lambda item: (-_hint_score(item, tokens), item["distance_m"], item["name"].lower()))
    fallback = ""
    if not candidates:
        try:
            fallback = _fallback_address(lat, lng, key)
        except requests.RequestException:
            fallback = ""
    return {
        "ok": True,
        "places": candidates[:limit],
        "fallback_address": fallback,
        "radius_m": radius,
    }


def lookup_destination_place(query):
    """Look up a typed destination address/name and return a likely place label."""
    key = _api_key()
    query = _clean(query)[:255]
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Google Maps API key is not configured.",
            "place": None,
        }
    if len(query) < 6:
        return {"ok": False, "error": "short_query", "place": None}

    response = requests.post(
        TEXT_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.formattedAddress",
                    "places.shortFormattedAddress",
                    "places.types",
                    "places.primaryType",
                ]
            ),
        },
        json={"textQuery": query, "maxResultCount": 3},
        timeout=6,
    )
    payload = response.json()
    if response.status_code >= 400 or payload.get("error"):
        error = payload.get("error") or {}
        return {
            "ok": False,
            "error": error.get("status") or f"http_{response.status_code}",
            "message": error.get("message") or "Google Places did not return a destination match.",
            "place": None,
        }

    for result in payload.get("places") or []:
        name = _place_name(result)
        address = _format_address(result.get("formattedAddress") or result.get("shortFormattedAddress"))
        if not name and not address:
            continue
        if _name_looks_like_address(name, address):
            name = ""
        return {
            "ok": True,
            "place": {
                "place_id": result.get("id") or "",
                "name": name,
                "address": address,
                "source": "google",
            },
        }
    return {"ok": True, "place": None}
