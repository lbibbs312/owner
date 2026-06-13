"""Start Shift Location recents must be contextual, never a global dump.

Coordinates here are synthetic test fixtures (not real driver GPS) and are
never printed — only asserted on.
"""
from app.services.contextual_recents import DEFAULT_RADIUS_M, filter_contextual_recents


# Synthetic "current" point used across the radius tests.
HERE_LAT = 42.9000
HERE_LNG = -85.6000
CURRENT_ADDRESS = "1916 Jefferson Ave SE, Grand Rapids, MI 49507"


def _recents():
    return [
        {"name": "Plastic Plate Inc", "address": "5500 Northland Dr NE, Grand Rapids, MI 49525",
         "lat": HERE_LAT + 0.05, "lng": HERE_LNG + 0.05},
        {"name": "52nd Logistics", "address": "4400 52nd St SE, Kentwood, MI 49512",
         "lat": HERE_LAT + 0.04, "lng": HERE_LNG - 0.03},
        {"name": "Kraft Plater", "address": "1200 Front Ave NW, Grand Rapids, MI 49504",
         "lat": HERE_LAT + 0.03, "lng": HERE_LNG + 0.02},
        {"name": "Raleigh East", "address": "3500 Raleigh Dr SE, Grand Rapids, MI 49512",
         "lat": HERE_LAT + 0.06, "lng": HERE_LNG + 0.04},
        {"name": "Paint Central", "address": "900 Paint Rd SW, Wyoming, MI 49519",
         "lat": HERE_LAT - 0.05, "lng": HERE_LNG - 0.04},
    ]


def _names(matches):
    return [match["name"] for match in matches]


def test_empty_input_with_gps_does_not_show_unrelated_recents():
    matches = filter_contextual_recents(
        _recents(), current_address=CURRENT_ADDRESS, current_lat=HERE_LAT, current_lng=HERE_LNG
    )
    assert "52nd Logistics" not in _names(matches)
    assert "Kraft Plater" not in _names(matches)
    assert "Plastic Plate Inc" not in _names(matches)


def test_1916_jefferson_address_hides_far_recents():
    matches = filter_contextual_recents(_recents(), current_address=CURRENT_ADDRESS)
    assert _names(matches) == []


def test_same_normalized_address_shows_matching_recent():
    recents = _recents() + [
        {"name": "Jefferson Dock", "address": "1916 Jefferson Ave SE, Grand Rapids, MI"}
    ]
    matches = filter_contextual_recents(recents, current_address=CURRENT_ADDRESS)
    assert _names(matches) == ["Jefferson Dock"]


def test_recent_within_250m_of_gps_shows():
    recents = _recents() + [
        # ~166 m north of the current point; no address on purpose so only the
        # radius rule can match it.
        {"name": "Jefferson Neighbor", "lat": HERE_LAT + 0.0015, "lng": HERE_LNG}
    ]
    matches = filter_contextual_recents(recents, current_lat=HERE_LAT, current_lng=HERE_LNG)
    assert "Jefferson Neighbor" in _names(matches)
    # The far recents stay out.
    assert "Plastic Plate Inc" not in _names(matches)


def test_recent_outside_radius_is_excluded():
    recents = [{"name": "Far Yard", "lat": HERE_LAT + 0.01, "lng": HERE_LNG}]  # ~1.1 km
    matches = filter_contextual_recents(
        recents, current_lat=HERE_LAT, current_lng=HERE_LNG, radius_m=DEFAULT_RADIUS_M
    )
    assert matches == []


def test_typing_plastic_shows_plastic_plate():
    matches = filter_contextual_recents(_recents(), typed_input="plastic")
    assert _names(matches) == ["Plastic Plate Inc"]


def test_typing_partial_prefix_shows_match():
    matches = filter_contextual_recents(_recents(), typed_input="plas")
    assert _names(matches) == ["Plastic Plate Inc"]


def test_typing_partial_street_name_shows_match():
    matches = filter_contextual_recents(_recents(), typed_input="52nd")
    assert "52nd Logistics" in _names(matches)
    assert "Plastic Plate Inc" not in _names(matches)


def test_typing_overrides_gps_so_other_places_are_searchable():
    # Standing at Jefferson but typing "kraft" should surface Kraft Plater.
    matches = filter_contextual_recents(
        _recents(), current_address=CURRENT_ADDRESS, current_lat=HERE_LAT,
        current_lng=HERE_LNG, typed_input="kraft",
    )
    assert _names(matches) == ["Kraft Plater"]


def test_no_gps_and_empty_input_shows_nothing():
    assert filter_contextual_recents(_recents()) == []
    assert filter_contextual_recents(_recents(), typed_input="") == []
    assert filter_contextual_recents(_recents(), typed_input="   ") == []
