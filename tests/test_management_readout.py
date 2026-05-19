from types import SimpleNamespace

from app.services.management_readout import build_management_narrative


def test_management_narrative_reports_completed_route_without_exceptions():
    first = SimpleNamespace(
        id=1,
        driver=SimpleNamespace(display_name="Lamar Bibbs"),
        depart_time="08:00",
        plant_name="KP",
        maintenance=False,
        fuel=False,
        meeting=False,
    )
    second = SimpleNamespace(
        id=2,
        driver=first.driver,
        depart_time="09:00",
        plant_name="PE",
        maintenance=False,
        fuel=False,
        meeting=False,
    )

    narrative = build_management_narrative(
        {
            "log": second,
            "day_logs": [first, second],
            "log_routes": {1: {"plant": "Kraft Plant"}, 2: {"plant": "Paint East"}},
            "delay_logs": [],
            "damage_reports": [],
            "truck_context": {"truck_id": "st4"},
        }
    )

    assert narrative["route_status"] == "Completed"
    assert "The route was completed" in narrative["status_summary"]
    assert narrative["exception_summary"] == (
        "No delay events were reported. No damage reports were filed. "
        "No maintenance, fuel, or meeting flags were recorded."
    )
    assert narrative["narrative_lines"][1] == {
        "label": "Open stop",
        "text": "No open stops are visible; the route was completed.",
    }
    assert narrative["action_items"] == ["No immediate management action is flagged from this log."]
