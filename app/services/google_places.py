"""Google Maps place lookup for driver GPS capture."""
from __future__ import annotations

import math
import re

import requests
from flask import current_app


NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Place Details field masks, layered so review/AI fields are only requested when
# the matching feature flag is on (they cost more and need extra API enablement).
DESTINATION_DETAILS_FIELDS = (
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "types",
    "primaryType",
    "businessStatus",
    "googleMapsUri",
    "regularOpeningHours",
    "currentOpeningHours",
    "parkingOptions",
    "fuelOptions",
)
DESTINATION_DETAILS_REVIEW_FIELDS = ("reviews", "reviewSummary")
DESTINATION_DETAILS_GENERATIVE_FIELDS = ("generativeSummary",)
MIN_AUTOCOMPLETE_QUERY_LENGTH = 2
AUTOCOMPLETE_BIAS_RADIUS_M = 50000
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
NEARBY_FUEL_RADIUS_M = 8000

BUSINESS_TYPES = {
    "accounting",
    "airport",
    "car_repair",
    "car_wash",
    "convenience_store",
    "corporate_office",
    "establishment",
    "gas_station",
    "hardware_store",
    "industrial",
    "local_government_office",
    "manufacturer",
    "moving_company",
    "parking",
    "point_of_interest",
    "post_office",
    "premise",
    "storage",
    "store",
    "warehouse",
}
LOW_VALUE_TYPES = {
    "administrative_area_level_1",
    "administrative_area_level_2",
    "atm",
    "bus_station",
    "country",
    "finance",
    "intersection",
    "locality",
    "neighborhood",
    "political",
    "postal_code",
    "route",
    "street_address",
    "sublocality",
    "sublocality_level_1",
    "transit_station",
}
DESTINATION_GEOGRAPHY_TYPES = {
    "administrative_area_level_1",
    "administrative_area_level_2",
    "country",
    "locality",
    "neighborhood",
    "political",
    "postal_code",
    "sublocality",
    "sublocality_level_1",
}
PREMISE_GEOCODE_TYPES = {"premise", "subpremise", "street_address"}
DEFAULT_PLACE_RADIUS_M = 20
CUSTOMER_PLACE_RADIUS_M = 6
MAX_PLACE_RADIUS_M = 30
FUEL_PLACE_RADIUS_M = 5000
FUEL_MIN_SUGGESTIONS = 5
FUEL_PLACE_TYPES = ("gas_station",)
MIN_DESTINATION_QUERY_LENGTH = 4


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


def _is_fuel_hint(value):
    text = (value or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    return bool(tokens & {"fuel", "gas", "gasoline", "diesel"}) or "truck stop" in text


def _candidate_radius_m(accuracy_m, *, fuel_lookup=False):
    accuracy = _float_or_none(accuracy_m)
    if accuracy is None or accuracy <= 0:
        radius = DEFAULT_PLACE_RADIUS_M
    elif accuracy <= 8:
        radius = 8
    elif accuracy <= 15:
        radius = 12
    elif accuracy <= 30:
        radius = 20
    else:
        radius = MAX_PLACE_RADIUS_M
    if fuel_lookup:
        return max(radius, FUEL_PLACE_RADIUS_M)
    return radius


def _trusted_place_distance_m(accuracy_m):
    return CUSTOMER_PLACE_RADIUS_M


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


def _has_street_number(address):
    return bool(re.search(r"\b\d{1,6}\s+\S+", _clean(address)))


def _destination_place(result):
    name = _place_name(result)
    address = _format_address(result.get("formattedAddress") or result.get("shortFormattedAddress"))
    if not address:
        return None
    types = set(result.get("types") or [])
    has_street = _has_street_number(address) or "street_address" in types or "premise" in types
    is_business = bool(types & BUSINESS_TYPES)
    if types & DESTINATION_GEOGRAPHY_TYPES and not has_street and not is_business:
        return None
    if not is_business and not has_street:
        return None
    if _name_looks_like_address(name, address):
        name = ""
    return {
        "place_id": result.get("id") or result.get("place_id") or "",
        "name": name,
        "address": address,
        "source": "google",
    }


def _address_candidates(lat, lng, key, *, limit=5):
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
        return []
    candidates = []
    seen = set()
    for result in payload.get("results") or []:
        types = set(result.get("types") or [])
        if types & PREMISE_GEOCODE_TYPES:
            address = _format_address(result.get("formatted_address"))
            key = address.lower()
            if address and key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "address": address,
                        "source": "google_geocode",
                        "types": sorted(types),
                    }
                )
        if len(candidates) >= limit:
            break
    return candidates


def _fallback_address(lat, lng, key):
    candidates = _address_candidates(lat, lng, key, limit=1)
    return candidates[0]["address"] if candidates else ""


def _address_signature(value):
    value = _format_address(value).lower()
    value = re.sub(r"\b(usa|united states)\b", "", value)
    value = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _addresses_match(left, right):
    left_sig = _address_signature(left)
    right_sig = _address_signature(right)
    if not left_sig or not right_sig:
        return False
    return left_sig == right_sig or left_sig in right_sig or right_sig in left_sig


def _place_dedupe_key(place):
    place_id = _clean(place.get("place_id") or place.get("id")).lower()
    if place_id:
        return f"id:{place_id}"
    return "nameaddr:%s|%s" % (
        _clean(place.get("name")).lower(),
        _clean(place.get("address")).lower(),
    )


def _businesses_at_addresses(addresses, key, *, limit=5, fuel_lookup=False):
    matches = []
    seen = set()
    for item in addresses[:5]:
        address = item.get("address") if isinstance(item, dict) else item
        address = _format_address(address)
        if not address:
            continue
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
                        "places.location",
                        "places.types",
                        "places.primaryType",
                    ]
                ),
            },
            json={
                "textQuery": address,
                "maxResultCount": limit,
            },
            timeout=6,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            continue
        for result in payload.get("places") or []:
            if fuel_lookup and "gas_station" not in set(result.get("types") or []):
                continue
            place = _destination_place(result)
            if not place or not place.get("name"):
                continue
            if not _addresses_match(address, place.get("address")):
                continue
            key_value = _place_dedupe_key(place)
            if key_value in seen:
                continue
            seen.add(key_value)
            place.update(
                {
                    "source": "google_address",
                    "trusted": True,
                    "address_match": True,
                    "match_reason": "same_address",
                }
            )
            matches.append(place)
            if len(matches) >= limit:
                return matches
    return matches


def nearby_place_candidates(lat, lng, *, accuracy_m=None, limit=8, hint="", radius_m=None):
    """Return likely business/place candidates near a raw browser GPS point."""
    key = _api_key()
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Google Maps API key is not configured.",
            "places": [],
            "address_candidates": [],
            "fallback_address": "",
        }

    fuel_lookup = _is_fuel_hint(hint)
    radius = float(radius_m) if radius_m else _candidate_radius_m(accuracy_m, fuel_lookup=fuel_lookup)
    result_limit = max(1, min(int(limit), 20))
    if fuel_lookup:
        result_limit = max(result_limit, FUEL_MIN_SUGGESTIONS)
    request_payload = {
        "maxResultCount": result_limit,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
    }
    if fuel_lookup:
        request_payload["includedTypes"] = list(FUEL_PLACE_TYPES)
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
        json=request_payload,
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
            "address_candidates": [],
            "fallback_address": "",
        }

    trusted_distance = _trusted_place_distance_m(accuracy_m)
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
        dedupe_key = _place_dedupe_key({"place_id": place_id, "name": name, "address": address})
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "place_id": place_id,
                "name": name,
                "address": address,
                "distance_m": int(round(distance)),
                "trusted": distance <= trusted_distance,
                "lat": point[0],
                "lng": point[1],
                "source": "google",
            }
        )

    address_candidates = []
    fallback = ""
    try:
        address_candidates = _address_candidates(lat, lng, key)
        fallback = address_candidates[0]["address"] if address_candidates else ""
    except requests.RequestException:
        address_candidates = []
        try:
            fallback = _fallback_address(lat, lng, key)
        except requests.RequestException:
            fallback = ""
    address_place_matches = []
    if address_candidates:
        try:
            address_place_matches = _businesses_at_addresses(
                address_candidates,
                key,
                fuel_lookup=fuel_lookup,
            )
        except requests.RequestException:
            address_place_matches = []
    for place in address_place_matches:
        dedupe_key = _place_dedupe_key(place)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(place)

    tokens = _hint_tokens(hint)
    if fuel_lookup:
        candidates.sort(
            key=lambda item: (
                0 if item.get("address_match") else 1,
                item.get("distance_m", 0),
                -_hint_score(item, tokens),
                item["name"].lower(),
            )
        )
    else:
        candidates.sort(
            key=lambda item: (
                0 if item.get("address_match") else 1,
                -_hint_score(item, tokens),
                item.get("distance_m", 0),
                item["name"].lower(),
            )
        )
    return {
        "ok": True,
        "places": candidates[:result_limit],
        "address_candidates": address_candidates,
        "fallback_address": fallback,
        "radius_m": radius,
    }


def lookup_destination_place(query, *, bias_lat=None, bias_lng=None, near=""):
    """Look up a typed destination address/name and return likely place labels."""
    key = _api_key()
    query = _clean(query)[:255]
    near = _clean(near)[:255]
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Google Maps API key is not configured.",
            "place": None,
            "places": [],
        }
    if len(query) < MIN_DESTINATION_QUERY_LENGTH:
        return {"ok": False, "error": "short_query", "place": None, "places": []}
    search_query = query
    if near and near.lower() not in query.lower():
        search_query = f"{query} near {near}"
    lat = _float_or_none(bias_lat)
    lng = _float_or_none(bias_lng)
    request_payload = {"textQuery": search_query, "maxResultCount": 5}
    if lat is not None and lng is not None:
        request_payload["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 50000,
            }
        }

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
        json=request_payload,
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
            "places": [],
        }

    places = []
    seen = set()
    for result in payload.get("places") or []:
        place = _destination_place(result)
        if not place:
            continue
        dedupe_key = (place["name"].lower(), place["address"].lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        places.append(place)
    return {"ok": True, "place": places[0] if places else None, "places": places[:5]}


def _normalize_place_id(value):
    value = _clean(value)
    if value.startswith("places/"):
        return value[len("places/"):]
    return value


def autocomplete_destination(text, *, lat=None, lng=None, session_token="", limit=6):
    """Google Places Autocomplete (New): live destination predictions.

    Biases toward the driver's current location when GPS is known and passes a
    session token so the follow-up Place Details call is billed as one session.
    Returns compact suggestions only — no ratings, photos, or summaries.
    """
    key = _api_key()
    text = _clean(text)[:255]
    session_token = _clean(session_token)
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Google Maps API key is not configured.",
            "suggestions": [],
            "session_token": session_token,
        }
    if len(text) < MIN_AUTOCOMPLETE_QUERY_LENGTH:
        return {"ok": False, "error": "short_query", "suggestions": [], "session_token": session_token}

    payload = {"input": text}
    if session_token:
        payload["sessionToken"] = session_token
    bias_lat = _float_or_none(lat)
    bias_lng = _float_or_none(lng)
    if bias_lat is not None and bias_lng is not None:
        payload["locationRestriction"] = {
            "circle": {
                "center": {"latitude": bias_lat, "longitude": bias_lng},
                "radius": AUTOCOMPLETE_BIAS_RADIUS_M,
            }
        }
        # ``origin`` makes Google return distanceMeters per prediction.
        payload["origin"] = {"latitude": bias_lat, "longitude": bias_lng}

    response = requests.post(
        AUTOCOMPLETE_URL,
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
        json=payload,
        timeout=6,
    )
    data = response.json()
    if response.status_code >= 400 or data.get("error"):
        error = data.get("error") or {}
        return {
            "ok": False,
            "error": error.get("status") or f"http_{response.status_code}",
            "message": error.get("message") or "Google Places did not return suggestions.",
            "suggestions": [],
            "session_token": session_token,
        }

    suggestions = []
    for item in data.get("suggestions") or []:
        prediction = item.get("placePrediction") or {}
        place_id = _normalize_place_id(prediction.get("placeId") or prediction.get("place"))
        structured = prediction.get("structuredFormat") or {}
        main_text = _clean((structured.get("mainText") or {}).get("text"))
        secondary_text = _clean((structured.get("secondaryText") or {}).get("text"))
        full_text = _clean((prediction.get("text") or {}).get("text"))
        if not main_text:
            main_text = full_text
        if not place_id or not main_text:
            continue
        distance = prediction.get("distanceMeters")
        suggestions.append(
            {
                "place_id": place_id,
                "main_text": main_text,
                "secondary_text": secondary_text,
                "formatted_address": full_text,
                "distance_meters": int(distance) if isinstance(distance, (int, float)) else None,
                "source": "google_places",
            }
        )
        if len(suggestions) >= limit:
            break
    return {"ok": True, "suggestions": suggestions, "session_token": session_token}


def destination_place_details(place_id, *, session_token="", include_reviews=False, include_generative=False):
    """Google Place Details (New) for a chosen destination.

    Requests minimal fields first; review/AI fields only when their flags ask
    for them. Returns a normalized ``place`` plus the ``raw`` payload so the
    trucker-summary service can mine official fields without the raw Google
    candidate list ever being persisted.
    """
    key = _api_key()
    place_id = _normalize_place_id(place_id)
    session_token = _clean(session_token)
    if not key:
        return {"ok": False, "error": "not_configured", "place": None, "raw": {}}
    if not place_id:
        return {"ok": False, "error": "missing_place_id", "place": None, "raw": {}}

    fields = list(DESTINATION_DETAILS_FIELDS)
    if include_reviews:
        fields += list(DESTINATION_DETAILS_REVIEW_FIELDS)
    if include_generative:
        fields += list(DESTINATION_DETAILS_GENERATIVE_FIELDS)
    params = {}
    if session_token:
        params["sessionToken"] = session_token

    def _fetch(field_list):
        resp = requests.get(
            PLACE_DETAILS_URL + place_id,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": ",".join(field_list)},
            params=params or None,
            timeout=6,
        )
        return resp, resp.json()

    response, data = _fetch(fields)
    if (response.status_code >= 400 or data.get("error")) and len(fields) > len(DESTINATION_DETAILS_FIELDS):
        # Review / generative-summary fields are not enabled for every key or
        # region. Don't let that break destination selection — retry with the
        # minimal field set so the driver still gets the place + base notes.
        response, data = _fetch(list(DESTINATION_DETAILS_FIELDS))
    if response.status_code >= 400 or data.get("error"):
        error = data.get("error") or {}
        return {
            "ok": False,
            "error": error.get("status") or f"http_{response.status_code}",
            "message": error.get("message") or "Google Places did not return place details.",
            "place": None,
            "raw": {},
        }

    point = _place_point(data)
    place = {
        "place_id": data.get("id") or place_id,
        "name": _place_name(data),
        "address": _format_address(data.get("formattedAddress")),
        "lat": point[0] if point else None,
        "lng": point[1] if point else None,
        "types": list(data.get("types") or []),
        "primary_type": _clean(data.get("primaryType")),
        "business_status": _clean(data.get("businessStatus")),
        "google_maps_uri": _clean(data.get("googleMapsUri")),
        "source": "google_places",
    }
    return {"ok": True, "place": place, "raw": data}


def reverse_geocode(lat, lng):
    """Lat/Lng -> nearest street address via the Geocoding API.

    Used by the one-driver page's "fill address from GPS" control so it never
    depends on the browser Maps JavaScript library loading.
    """
    key = _api_key()
    la, ln = _float_or_none(lat), _float_or_none(lng)
    if not key:
        return {"ok": False, "error": "not_configured", "address": "", "place_id": "", "types": []}
    if la is None or ln is None:
        return {"ok": False, "error": "missing_input", "address": "", "place_id": "", "types": []}
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{la},{ln}", "key": key},
            timeout=6,
        )
        data = resp.json()
    except Exception:
        return {"ok": False, "error": "request_failed", "address": "", "place_id": "", "types": []}
    if data.get("status") != "OK" or not data.get("results"):
        return {"ok": False, "error": data.get("status") or "no_result", "address": "", "place_id": "", "types": []}
    top = data["results"][0]
    return {
        "ok": True,
        "address": _format_address(top.get("formatted_address")),
        "place_id": top.get("place_id") or "",
        "types": list(top.get("types") or []),
    }


def _meters_to_miles_text(meters):
    try:
        meters = float(meters)
    except (TypeError, ValueError):
        return ""
    miles = meters / 1609.344
    if miles < 0.1:
        return f"{int(round(meters))} m"
    if miles < 10:
        return f"{miles:.1f} mi"
    return f"{int(round(miles))} mi"


def _duration_to_text(duration):
    try:
        seconds = int(str(duration).rstrip("s"))
    except (TypeError, ValueError):
        return ""
    minutes = max(1, int(round(seconds / 60)))
    if minutes < 60:
        return f"{minutes} min"
    hours, rem = divmod(minutes, 60)
    return f"{hours} hr {rem} min" if rem else f"{hours} hr"


def route_summary(origin_lat, origin_lng, dest_lat, dest_lng):
    """Drive time / distance from the start location to the destination via the
    Routes API. Returns ``{"ok": False}`` on any problem so callers can omit it."""
    key = _api_key()
    o_lat, o_lng = _float_or_none(origin_lat), _float_or_none(origin_lng)
    d_lat, d_lng = _float_or_none(dest_lat), _float_or_none(dest_lng)
    if not key or None in (o_lat, o_lng, d_lat, d_lng):
        return {"ok": False, "error": "missing_input"}
    body = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lng}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lng}}},
        "travelMode": "DRIVE",
    }
    try:
        response = requests.post(
            ROUTES_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.description",
            },
            json=body,
            timeout=6,
        )
        data = response.json()
    except requests.RequestException:
        return {"ok": False, "error": "request_failed"}
    if response.status_code >= 400 or data.get("error") or not data.get("routes"):
        error = data.get("error") or {}
        return {"ok": False, "error": error.get("status") or f"http_{response.status_code}"}
    route = data["routes"][0]
    description = _clean(route.get("description"))
    return {
        "ok": True,
        "distance_text": _meters_to_miles_text(route.get("distanceMeters")),
        "duration_text": _duration_to_text(route.get("duration")),
        "route_text": f"via {description}" if description else "",
    }


def nearby_truck_services(lat, lng, *, limit=3, radius_m=NEARBY_FUEL_RADIUS_M):
    """Fuel stations near the destination, closest first. Best-effort: returns
    [] on any error. We do not claim diesel/DEF without fuelOptions data."""
    key = _api_key()
    lat, lng = _float_or_none(lat), _float_or_none(lng)
    if not key or lat is None or lng is None:
        return []
    body = {
        "includedTypes": ["gas_station"],
        "maxResultCount": min(max(int(limit), 1), 10),
        "rankPreference": "DISTANCE",
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}},
    }
    try:
        response = requests.post(
            NEARBY_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.location,places.types,places.primaryType",
            },
            json=body,
            timeout=6,
        )
        data = response.json()
    except requests.RequestException:
        return []
    if response.status_code >= 400 or data.get("error"):
        return []
    results = []
    for place in data.get("places") or []:
        name = _place_name(place)
        point = _place_point(place)
        if not name or point is None:
            continue
        results.append(
            {
                "name": name,
                "type": "fuel nearby",
                "distance_text": _meters_to_miles_text(_distance_m(lat, lng, point[0], point[1])),
                "hints": [],
            }
        )
        if len(results) >= limit:
            break
    return results
