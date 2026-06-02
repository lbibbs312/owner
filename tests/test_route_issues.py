"""Unit tests for the centralized issue-derivation layer.

These lock in the spec: no generic RISK, every issue has an explicit reason,
and an issue pill is never green.
"""
from app.services.route_issues import (
    ISSUE_CATALOG,
    board_badge,
    derive_issues,
    issue,
    primary_issue,
)


def test_known_flags_map_to_explicit_reason_codes():
    assert derive_issues(["Needs review"])[0]["code"] == "unconfirmed_drop"
    assert derive_issues(["Needs review"])[0]["label"] == "UNCONFIRMED DROP"
    assert derive_issues(["Missing proof"])[0]["label"] == "MISSING PROOF"
    assert derive_issues(["Mismatch"])[0]["label"] == "DESTINATION MISMATCH"
    assert derive_issues(["Shortage"])[0]["label"] == "COUNT SHORT"
    assert derive_issues(["Hold"])[0]["label"] == "HOLD"
    assert derive_issues([], has_damage=True)[0]["label"] == "DAMAGE"


def test_no_catalog_entry_is_a_generic_risk_label():
    for label, *_ in ISSUE_CATALOG.values():
        assert label != "RISK"
        assert label != "VERIFY ROUTE"
        assert label != "REVIEW ISSUE"


def test_state_only_flags_are_not_issues():
    # Normal route states must never create a red/amber issue pill.
    assert derive_issues(["No pickup"]) == []
    assert derive_issues(["Fuel", "Meeting"]) == []


def test_open_wait_becomes_specific_departure_issue():
    assert derive_issues([], departed=False, wait_minutes=45)[0]["code"] == "needs_departure"
    assert derive_issues([], departed=False, needs_departure=True)[0]["label"] == "NEEDS DEPARTURE"
    assert derive_issues([], departed=False, wait_minutes=5) == []
    assert derive_issues([], departed=True, wait_minutes=120) == []


def test_every_issue_has_reason_action_and_unresolved_state():
    for code in ISSUE_CATALOG:
        obj = issue(code)
        assert obj["reason"], code
        assert obj["action"], code
        assert obj["severity"] in ("ok", "info", "attention", "risk"), code
        assert obj["resolved"] is False, code


def test_badge_is_never_green_for_an_issue():
    risk = board_badge(derive_issues(["Missing proof"]), ok_label="RECORDED", ok_pill_tone="recorded")
    assert risk["severity"] == "risk"
    assert risk["pill_tone"] == "risk"          # red, not the green ok tone
    assert risk["label"] == "MISSING PROOF"      # explicit reason, never "RISK"

    attention = board_badge(derive_issues(["Hold"]), ok_label="RECORDED")
    assert attention["pill_tone"] == "attention"  # amber
    assert attention["short"] == "HOLD"

    clean = board_badge([], ok_label="RECORDED", ok_pill_tone="recorded")
    assert clean["severity"] == "ok"
    assert clean["pill_tone"] == "recorded"

    loaded = board_badge([], ok_label="LOADED", ok_pill_tone="open", ok_severity="info")
    assert loaded["severity"] == "info"
    assert loaded["label"] == "LOADED"


def test_primary_issue_picks_worst_severity():
    issues = derive_issues(["Hold", "Missing proof"])  # attention + risk
    assert primary_issue(issues)["severity"] == "risk"
