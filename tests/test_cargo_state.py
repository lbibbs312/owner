"""Tests for cargo-state normalization (derived from existing fields only)."""
from types import SimpleNamespace

from app.services.cargo_state import (
    STATE_LABELS,
    cargo_state_for_log,
    cargo_state_for_request,
    cargo_state_label,
    normalize_cargo_state,
)
from app.services.load_state import destination_from_load, load_display
from app.services.plant_addresses import UNKNOWN_LOAD_LABEL, UNKNOWN_PLANT_LABEL, plant_label


def _log(**kw):
    base = dict(id=1, load_size="", depart_time="", depart_load_size="", no_pickup=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _req(**kw):
    base = dict(status="open", linked_document_id=None, linked_plant_transfer_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_normalize_known_states_pass_through():
    for state in ("loaded", "onboard", "delivered", "held", "assigned", "requested"):
        assert normalize_cargo_state(state)["state"] == state


def test_normalize_empty_and_blank():
    assert normalize_cargo_state("")["state"] == "unknown"
    assert normalize_cargo_state(None)["state"] == "unknown"
    assert normalize_cargo_state("no pickup")["state"] == "empty"
    assert normalize_cargo_state("none")["state"] == "empty"


def test_normalize_keyword_buckets():
    assert normalize_cargo_state("trailer damaged on arrival")["state"] == "damaged"
    assert normalize_cargo_state("partial load")["state"] == "short"
    assert normalize_cargo_state("returned to origin")["state"] == "returned"
    assert normalize_cargo_state("delivered to dock 4")["state"] == "delivered"
    assert normalize_cargo_state("Plastic West Load")["state"] == "onboard"


def test_log_empty_when_no_pickup_or_empty_load():
    assert cargo_state_for_log(_log(no_pickup=True))["state"] == "empty"
    assert cargo_state_for_log(_log(load_size="empty"))["state"] == "empty"


def test_log_onboard_when_arrived_loaded_and_not_departed():
    assert cargo_state_for_log(_log(load_size="Plastic West Load"))["state"] == "onboard"


def test_log_delivered_when_departed_empty():
    log = _log(load_size="Plastic West Load", depart_time="2026-05-28 15:00:00", depart_load_size="empty")
    assert cargo_state_for_log(log)["state"] == "delivered"


def test_log_still_onboard_when_departed_with_load():
    log = _log(load_size="Plastic West Load", depart_time="2026-05-28 15:00:00", depart_load_size="Paint Central Load")
    assert cargo_state_for_log(log)["state"] == "onboard"


def test_open_damage_signal_overrides_everything():
    assert cargo_state_for_log(_log(load_size="empty"), has_open_damage=True)["state"] == "damaged"
    assert cargo_state_for_request(_req(status="open"), has_open_damage=True)["state"] == "damaged"


def test_request_status_fallback_without_log():
    assert cargo_state_for_request(_req(status="open"))["state"] == "requested"
    assert cargo_state_for_request(_req(status="assigned"))["state"] == "assigned"
    assert cargo_state_for_request(_req(status="completed", linked_document_id=5))["state"] == "delivered"


def test_request_completed_without_document_needs_document():
    assert cargo_state_for_request(_req(status="completed"))["state"] == "pending_document"


def test_request_prefers_linked_log_truth():
    req = _req(status="in_progress", linked_document_id=1)
    log = _log(load_size="Plastic West Load", depart_time="2026-05-28 15:00:00", depart_load_size="empty")
    assert cargo_state_for_request(req, log=log)["state"] == "delivered"


def test_label_lookup():
    assert cargo_state_label("pending_document") == "Document Needed"
    assert cargo_state_label("nonsense") == STATE_LABELS["unknown"]


def test_ambiguous_paint_east_tokens_need_confirmation():
    assert plant_label("PE") == UNKNOWN_PLANT_LABEL
    assert plant_label("Paint East") == UNKNOWN_PLANT_LABEL
    assert destination_from_load("PE Load") is None
    assert load_display("PE Load") == UNKNOWN_LOAD_LABEL
    assert load_display("Paint East Load") == UNKNOWN_LOAD_LABEL
