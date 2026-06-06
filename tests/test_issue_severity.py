"""Tests for the display-layer issue severity/category normalization helper.

These lock in the product rules: Critical is reserved for genuinely critical
situations, and routine short waits / blank fields never escalate to Critical.
"""
from app.services.issue_severity import (
    CATEGORIES,
    LEVELS,
    classify_issue,
    classify_wait,
    severity_level,
)
from app.services.driver_wait import dock_time_review_label


def _level(**kwargs):
    return classify_issue(**kwargs)["level"]


# --- Critical is reserved for genuinely critical situations -----------------

def test_damage_is_critical_safety_issue():
    result = classify_issue(category="Damage flag", severity="high")
    assert result["level"] == "critical"
    assert result["level_label"] == "Critical"
    assert result["category"] == "safety"
    assert result["category_label"] == "Safety Issue"


def test_wrong_delivery_is_critical_cargo_issue():
    result = classify_issue(category="Wrong delivery")
    assert result["level"] == "critical"
    assert result["category"] == "cargo"


def test_stranded_equipment_is_critical():
    assert classify_issue(category="Stranded equipment")["level"] == "critical"
    assert classify_issue(category="Stranded equipment")["category"] == "equipment"


def test_route_blocking_failure_is_critical():
    assert classify_issue(category="Route-blocking failure")["level"] == "critical"


# --- Routine waits never render as Critical ---------------------------------

def test_one_minute_wait_is_not_critical():
    result = classify_wait(1)
    assert result["category"] == "delay"
    assert result["level"] == "info"
    assert result["level"] != "critical"


def test_nineteen_minute_wait_is_not_critical_without_threshold():
    assert classify_wait(19)["level"] == "info"
    assert classify_wait(19, threshold=30)["level"] == "info"
    assert classify_wait(19)["level"] != "critical"


def test_wait_escalates_only_at_two_hour_review_threshold():
    assert classify_wait(19, threshold=15)["level"] == "info"
    assert classify_wait(45)["level"] == "info"
    assert classify_wait(119)["level"] == "info"
    assert classify_wait(120)["level"] == "action"
    assert classify_wait(180)["level"] == "high"
    # even a very long wait stays below the old Critical display level
    assert classify_wait(600)["level"] == "high"
    assert classify_wait(600)["level"] != "critical"


def test_dock_time_display_language_uses_review_thresholds():
    assert dock_time_review_label(57) == "Dock time: 57 min"
    assert dock_time_review_label(120) == "Long wait — needs review"
    assert dock_time_review_label(180) == "Extended wait — manager review required"


def test_classify_wait_handles_none_and_garbage():
    assert classify_wait(None) is None
    assert classify_wait("abc") is None


# --- Workflow / data-check rules --------------------------------------------

def test_missing_departure_is_action_needed_not_critical():
    result = classify_issue(category="Missing Departure", severity="medium")
    assert result["level"] == "action"
    assert result["level_label"] == "Action Needed"
    assert result["category"] == "workflow"
    assert result["level"] != "critical"


def test_suspicious_timing_is_data_check_and_low_urgency():
    result = classify_issue(
        category="Suspicious timing", label="only 1 minute between stops"
    )
    assert result["category"] == "data_check"
    assert result["level"] in {"info", "watch"}
    assert result["level"] != "critical"


def test_routine_categories_cannot_escalate_to_high_or_critical():
    # Even if an upstream severity claims "high", routine categories are capped.
    assert _level(category="Missing time", severity="high") == "action"
    assert _level(category="Delayed dock time", severity="high") in {"watch", "action"}
    assert _level(category="Missing trailer", severity="high") == "action"


# --- Equipment / request ----------------------------------------------------

def test_ordinary_truck_issue_is_high_not_critical():
    result = classify_issue(category="Truck issue", severity="high")
    assert result["level"] == "high"
    assert result["category"] == "equipment"
    assert result["level"] != "critical"


def test_open_hot_move_is_high_request():
    result = classify_issue(category="Open hot move")
    assert result["level"] == "high"
    assert result["category"] == "request"


# --- Severity fallback for unknown categories -------------------------------

def test_unknown_category_falls_back_to_severity():
    assert _level(category="Totally unknown", severity="high") == "high"
    assert _level(category="Totally unknown", severity="low") == "info"
    assert _level(category="Totally unknown", severity="followup") == "watch"
    assert _level(category=None, severity="medium") == "action"


def test_severity_level_helper_maps_raw_strings():
    assert severity_level("high") == "high"
    assert severity_level("medium") == "action"
    assert severity_level("followup") == "watch"
    assert severity_level("low") == "info"
    assert severity_level(None) == "info"
    assert severity_level("nonsense") == "info"


# --- Shape / integrity ------------------------------------------------------

def test_classification_shape_is_stable():
    result = classify_issue(category="Truck issue", severity="high")
    assert set(result) == {
        "level",
        "level_label",
        "level_rank",
        "level_class",
        "category",
        "category_label",
    }
    assert result["level"] in LEVELS
    assert result["category"] in CATEGORIES
    assert result["level_class"].startswith("issue-badge ")
