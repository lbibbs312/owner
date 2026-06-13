"""Filter a driver's recent places down to the ones that actually match the
current context — the resolved GPS/address, or what the driver is typing.

The Start Shift Location page used to dump *every* recent stop into a list,
so a driver standing at 1916 Jefferson Ave would see places 15+ miles away
(52nd Logistics, Kraft Plater, Plastic Plate Inc...). That is confusing and
dangerous. Never surface unfiltered recents in the driver UI: always run them
through :func:`filter_contextual_recents` so a recent only appears when the
driver's address, GPS point, or typed text actually matches it.
"""
from __future__ import annotations

import math
import re

# Default "this is the same place" radius for GPS matching. Tight on purpose:
# a recent stop only counts as relevant if the driver is essentially on top of
# it, not merely in the same part of town.
DEFAULT_RADIUS_M = 250.0


def _clean(value):
    return " ".join((value or "").strip().split())


def _normalize_address(value):
    """Lowercase, drop ZIP and country, collapse punctuation so two ways of
    writing the same street compare equal."""
    value = _clean(value).lower()
    value = re.sub(r"\b(usa|united states)\b", "", value)
    value = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _addresses_match(left, right):
    left_n = _normalize_address(left)
    right_n = _normalize_address(right)
    if not left_n or not right_n:
        return False
    return left_n == right_n or left_n in right_n or right_n in left_n


def _float_or_none(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _distance_m(lat1, lng1, lat2, lng2):
    radius = 6371000.0
    to_rad = math.pi / 180.0
    d_lat = (lat2 - lat1) * to_rad
    d_lng = (lng2 - lng1) * to_rad
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _recent_lat_lng(recent):
    lat = _float_or_none(recent.get("lat", recent.get("latitude")))
    lng = _float_or_none(recent.get("lng", recent.get("longitude")))
    return lat, lng


def _typed_tokens(typed_input):
    return [
        token
        for token in re.findall(r"[a-z0-9]+", _clean(typed_input).lower())
        if len(token) >= 2
    ]


def _typed_haystack(recent):
    """Every field typed text may match: place/business name, alias, street
    number + street name + city (all live inside the address), and the
    normalized address."""
    parts = []
    for key in ("name", "label", "business_name", "alias", "place_name", "city", "street", "address"):
        value = recent.get(key)
        if value:
            parts.append(str(value))
    haystack = " ".join(parts).lower()
    return _clean(haystack + " " + _normalize_address(recent.get("address")))


def _typed_matches(recent, tokens):
    if not tokens:
        return False
    haystack = _typed_haystack(recent)
    if not haystack:
        return False
    return all(token in haystack for token in tokens)


def filter_contextual_recents(
    recent_places,
    *,
    current_address=None,
    current_lat=None,
    current_lng=None,
    typed_input=None,
    radius_m=DEFAULT_RADIUS_M,
):
    """Return only the recents relevant to the current context.

    - ``typed_input`` present: recents whose name/alias/street/city/address
      contain *every* typed token (e.g. "plas" -> Plastic Plate Inc).
    - otherwise, ``current_address``/GPS present: recents whose normalized
      address matches, or whose saved lat/lng is within ``radius_m`` of the
      current GPS point.
    - nothing relevant (empty input, no GPS, no address): ``[]``.
    """
    recents = list(recent_places or [])
    typed = _clean(typed_input)
    lat = _float_or_none(current_lat)
    lng = _float_or_none(current_lng)
    address = _clean(current_address)
    radius = _float_or_none(radius_m)
    if radius is None or radius <= 0:
        radius = DEFAULT_RADIUS_M

    # The driver is actively typing -> text search wins over location.
    if typed:
        tokens = _typed_tokens(typed)
        return [recent for recent in recents if _typed_matches(recent, tokens)]

    have_point = lat is not None and lng is not None
    if not address and not have_point:
        # No typed input, no address, no GPS -> show nothing.
        return []

    matches = []
    for recent in recents:
        if address and _addresses_match(address, recent.get("address")):
            matches.append(recent)
            continue
        if have_point:
            r_lat, r_lng = _recent_lat_lng(recent)
            if r_lat is not None and r_lng is not None and _distance_m(lat, lng, r_lat, r_lng) <= radius:
                matches.append(recent)
    return matches
