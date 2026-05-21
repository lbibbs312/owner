from datetime import date, datetime
from types import SimpleNamespace

from app.services.load_state import (
    build_driver_log_route_context,
    cargo_delta_for_stop,
    classify_stop_role,
    normalize_cargo_value,
    normalized_cargo_items,
)
from app.services.plant_time import plant_time_sample_eligibility, stop_time_sample


def _log(id, plant_name, load_size, depart_load_size=None, *, arrive_time="08:00", depart_time="08:20", secondary_load=None, no_pickup=False):
    return SimpleNamespace(
        id=id,
        driver_id=1,
        date=date(2026, 5, 20),
        plant_name=plant_name,
        load_size=load_size,
        depart_load_size=depart_load_size,
        secondary_load=secondary_load,
        arrive_time=arrive_time,
        depart_time=depart_time,
        no_pickup=no_pickup,
        hot_parts=False,
        maintenance=False,
        fuel=False,
        meeting=False,
        downtime_reason="",
        created_at=datetime(2026, 5, 20, 8, id),
    )


def test_cargo_normalization_treats_empty_aliases_as_empty():
    assert normalize_cargo_value(None) == "Empty"
    assert normalize_cargo_value(" no load ") == "Empty"
    assert normalize_cargo_value("N/A") == "Empty"
    assert normalized_cargo_items("No Pickup", "Raleigh East Load") == ("Raleigh East Load",)


def test_helios_raleigh_east_ppl_stop_roles_and_deltas():
    logs = [
        _log(1, "Helios", "Empty", "Raleigh East Load", arrive_time="08:00", depart_time="08:15", secondary_load="PPL Load"),
        _log(2, "RE", "Raleigh East Load", "PPL Load", arrive_time="08:30", depart_time="08:45"),
        _log(3, "PPL", "PPL Load", "Empty", arrive_time="09:00", depart_time="09:10", no_pickup=True),
    ]
    routes = build_driver_log_route_context(logs)

    helios_delta = cargo_delta_for_stop(logs[0], routes[1])
    assert classify_stop_role(logs[0], routes[1]) == "pickup_origin"
    assert set(helios_delta["picked_up"]) == {"Raleigh East Load", "PPL Load"}

    raleigh_delta = cargo_delta_for_stop(logs[1], routes[2])
    assert classify_stop_role(logs[1], routes[2]) == "multi_stop_drop"
    assert raleigh_delta["delivered"] == ("Raleigh East Load",)
    assert raleigh_delta["picked_up"] == ()

    ppl_delta = cargo_delta_for_stop(logs[2], routes[3])
    assert classify_stop_role(logs[2], routes[3]) == "drop_only"
    assert ppl_delta["delivered"] == ("PPL Load",)


def test_mixed_transfer_stop_is_training_eligible():
    log = _log(1, "RE", "Raleigh East Load", "PPL Load", arrive_time="10:00", depart_time="10:24")
    route = build_driver_log_route_context([log])[1]

    eligibility = plant_time_sample_eligibility(log, route=route)
    sample = stop_time_sample(log)

    assert eligibility["included"] is True
    assert eligibility["training_eligible"] is True
    assert eligibility["stop_role"] == "mixed_transfer"
    assert eligibility["action_type"] == "mixed"
    assert sample["included"] is True
    assert sample["action_type"] == "mixed"


def test_current_open_stop_is_not_training_eligible():
    log = _log(1, "PC", "Empty", None, arrive_time="11:00", depart_time=None)

    eligibility = plant_time_sample_eligibility(log)
    sample = stop_time_sample(log)

    assert eligibility["included"] is False
    assert eligibility["training_eligible"] is False
    assert eligibility["stop_role"] == "current_open"
    assert eligibility["excluded_reason"] == "Departure missing"
    assert sample["included"] is False
    assert sample["training_eligible"] is False
