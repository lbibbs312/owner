"""Tests for the canonical stop-summary line builder.

These tests pin the printed Stop Details cell of the Driver Route Audit
Sheet to a single canonical shape, replacing the older freeform prose that
echoed adjacent table columns and framed every stop as a pickup attempt.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.services.stop_summary import (
    CURRENT_OPEN,
    COMBINED,
    DELIVERY,
    DELIVERY_RETAINED,
    NO_PICKUP,
    PICKUP,
    SERVICE,
    SHIFT_END,
    SHIFT_START,
    build_stop_summary,
    classify_stop_purpose,
    deviation_reason,
)


def _log(*, plant_name="KP", depart_time="16:33", no_pickup=False):
    return SimpleNamespace(
        id=1,
        plant_name=plant_name,
        depart_time=depart_time,
        no_pickup=no_pickup,
        hot_parts=False,
        maintenance=False,
        fuel=False,
        meeting=False,
        date=date(2026, 5, 27),
        arrive_time="16:05",
        downtime_reason="",
        created_at=datetime(2026, 5, 27, 16, 5),
    )


def _route(**overrides):
    base = {
        "plant": "Kraft Plant",
        "stop_role": "drop_only",
        "cargo_added": (),
        "cargo_removed": (),
        "cargo_retained": (),
        "deviation": False,
        "primary_destination": None,
        "service_stop": False,
        "service_stop_label": "",
        "unload_blocked": False,
        "unload_reason": "",
        "secondary_drop_blocked": False,
        "secondary_drop_reason": "",
    }
    base.update(overrides)
    return base


def _summary_lines(**kwargs):
    return build_stop_summary(**kwargs)["summary_lines"]


# ---------------------------------------------------------------------------
# Purpose classification
# ---------------------------------------------------------------------------


def test_shift_start_when_first_stop_has_no_cargo_events():
    log = _log(plant_name="RW")
    route = _route(plant="Raleigh West", stop_role="no_pickup")
    purpose = classify_stop_purpose(
        route, log, is_first=True, is_last=False, route_finalized=False
    )
    assert purpose == SHIFT_START


def test_shift_end_when_last_stop_has_no_cargo_events_and_finalized():
    log = _log()
    route = _route(plant="Kraft Plant", stop_role="final_stop")
    purpose = classify_stop_purpose(
        route, log, is_first=False, is_last=True, route_finalized=True
    )
    assert purpose == SHIFT_END


def test_shift_end_when_last_stop_no_pickup_and_departed():
    log = _log()
    route = _route(plant="Kraft Plant", stop_role="no_pickup")
    purpose = classify_stop_purpose(
        route, log, is_first=False, is_last=True, route_finalized=False
    )
    assert purpose == SHIFT_END


def test_current_open_overrides_other_purposes():
    log = _log(depart_time=None)
    route = _route(plant="Kraft Plant", stop_role="current_open")
    purpose = classify_stop_purpose(
        route, log, is_first=False, is_last=True, route_finalized=False, current_open=True
    )
    assert purpose == CURRENT_OPEN


def test_delivery_purpose_preserved_at_final_stop():
    """A delivery that happens to be the last stop is a delivery, not a shift-end."""
    log = _log()
    route = _route(
        plant="Raleigh East",
        stop_role="drop_only",
        cargo_removed=("Raleigh East Load",),
    )
    purpose = classify_stop_purpose(
        route, log, is_first=False, is_last=True, route_finalized=False
    )
    assert purpose == DELIVERY


def test_service_stop_is_typed_regardless_of_position():
    log = _log(plant_name="Ryder Rentals")
    route = _route(
        plant="Ryder Rentals",
        stop_role="service_stop",
        service_stop=True,
        service_stop_label="Ryder service stop",
    )
    purpose = classify_stop_purpose(
        route, log, is_first=False, is_last=True, route_finalized=False
    )
    assert purpose == SERVICE


# ---------------------------------------------------------------------------
# Canonical shape
# ---------------------------------------------------------------------------


def test_first_line_is_always_plant_colon_purpose_label():
    log = _log()
    route = _route(
        plant="Kraft Plant",
        stop_role="mixed_transfer",
        cargo_added=("Raleigh East Load",),
        cargo_removed=("52nd Street L Load",),
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert lines[0] == "Kraft Plant: Pickup and delivery."


def test_delivery_event_is_named_explicitly():
    """The headline regression: drops appear as first-class events, not
    inferred from manifest deltas. Previously a delivery at Raleigh East
    rendered as 'No pickup recorded; departed empty'."""
    log = _log(plant_name="RE")
    route = _route(
        plant="Raleigh East",
        stop_role="drop_only",
        cargo_removed=("Raleigh East Load",),
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert lines[0] == "Raleigh East: Delivery."
    assert "Delivered Raleigh East Load." in lines


def test_pickup_event_is_named_explicitly():
    log = _log(plant_name="KP")
    route = _route(
        plant="Kraft Plant",
        stop_role="pickup_origin",
        cargo_added=("Raleigh East Load", "52nd Street L Load"),
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert lines[0] == "Kraft Plant: Pickup."
    assert "Loaded Raleigh East Load." in lines
    assert "Loaded 52nd Street L Load." in lines


def test_multi_stop_drop_announces_continuation():
    log = _log(plant_name="RE")
    route = _route(
        plant="Raleigh East",
        stop_role="multi_stop_drop",
        cargo_removed=("Raleigh East Load",),
        cargo_retained=("PPL Load",),
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert "Delivered Raleigh East Load." in lines
    assert "Continuing with PPL Load." in lines


def test_no_pickup_stop_says_departed_empty():
    log = _log(plant_name="RW", no_pickup=True)
    route = _route(
        plant="Raleigh West",
        stop_role="no_pickup",
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert lines[0] == "Raleigh West: Stop (no pickup, departed empty)."
    assert "Departed empty." in lines


def test_shift_end_does_not_duplicate_departed_empty():
    """Shift end already implies the truck rolled empty -- don't echo it."""
    log = _log()
    route = _route(plant="Kraft Plant", stop_role="no_pickup")
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=True, route_finalized=True
    )
    assert lines[0] == "Kraft Plant: Shift end."
    assert "Departed empty." not in lines


# ---------------------------------------------------------------------------
# Echo-data removal
# ---------------------------------------------------------------------------


def test_summary_never_echoes_next_stop():
    """The 'First stop after departure: X' line duplicated the next row's
    Route column. It should not appear anywhere in the new summary."""
    log = _log(plant_name="KP")
    route = _route(
        plant="Kraft Plant",
        stop_role="pickup_origin",
        cargo_added=("Raleigh East Load",),
        next_stop="Raleigh East",
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    rendered = " ".join(lines)
    assert "First stop after departure" not in rendered
    assert "Raleigh East" not in rendered or "Loaded Raleigh East Load" in rendered


def test_summary_never_echoes_transit_cargo_state():
    """The 'Departed with X + Y' line duplicated the next row's Transit
    Cargo column. The new summary names cargo via Loaded/Delivered events
    instead of restating the post-departure manifest."""
    log = _log(plant_name="KP")
    route = _route(
        plant="Kraft Plant",
        stop_role="pickup_origin",
        cargo_added=("Raleigh East Load", "52nd Street L Load"),
        depart_cargo_desc="Raleigh East Load + 52nd Street L Load",
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    rendered = " ".join(lines)
    assert "Departed with" not in rendered


# ---------------------------------------------------------------------------
# Deviation
# ---------------------------------------------------------------------------


def test_deviation_reason_anchors_the_chip_when_set():
    route = _route(deviation=True, primary_destination="RE")
    reason = deviation_reason(route)
    assert reason == "Secondary cargo handled while load for Raleigh East still onboard"


def test_no_deviation_reason_when_flag_clear():
    assert deviation_reason(_route(deviation=False)) is None
    assert deviation_reason(None) is None


def test_deviation_reason_is_exposed_alongside_summary():
    """The deviation reason is returned as a separate field so the print
    template can render it next to the badge instead of inlining it into
    the stop summary lines (the badge owns deviation presentation)."""
    log = _log(plant_name="52SL")
    route = _route(
        plant="52nd Street L",
        stop_role="mixed_transfer",
        cargo_added=("Raleigh East Load",),
        cargo_removed=("52nd Street L Load",),
        deviation=True,
        primary_destination="RE",
    )
    result = build_stop_summary(
        route, log, is_first=False, is_last=False, route_finalized=False
    )
    assert result["deviation_reason"] == "Secondary cargo handled while load for Raleigh East still onboard"
    rendered = " ".join(result["summary_lines"])
    assert "Deviation:" not in rendered, "badge owns deviation rendering, not the summary lines"


# ---------------------------------------------------------------------------
# Wait time + exceptions
# ---------------------------------------------------------------------------


def test_wait_time_appears_as_its_own_line():
    log = _log()
    route = _route(plant="Kraft Plant", stop_role="no_pickup")
    lines = _summary_lines(
        route=route,
        log=log,
        is_first=False,
        is_last=True,
        route_finalized=True,
        wait_label="Wait 28 min",
    )
    assert "Wait 28 min." in lines


def test_unload_blocked_is_called_out_with_reason():
    log = _log(plant_name="RE")
    route = _route(
        plant="Raleigh East",
        stop_role="drop_only",
        unload_blocked=True,
        unload_reason="No forklift available",
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert "Unload not completed: No forklift available." in lines


def test_secondary_drop_blocked_is_called_out_with_reason():
    log = _log(plant_name="PPL")
    route = _route(
        plant="PPL",
        stop_role="drop_only",
        secondary_drop_blocked=True,
        secondary_drop_reason="Dock occupied",
    )
    lines = _summary_lines(
        route=route, log=log, is_first=False, is_last=False, route_finalized=False
    )
    assert "Secondary cargo not dropped: Dock occupied." in lines
