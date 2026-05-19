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
    assert "2 of 2 stops are completed" in narrative["status_summary"]
    assert narrative["summary_sentence"] == (
        "Lamar completed 2 of 2 stops. "
        "The route has departure/load-out recorded for every stop. "
        "No delay or damage events were reported today."
    )
    assert narrative["exception_summary"] == "No delay or damage events were reported today."
    assert narrative["narrative_lines"][1] == {
        "label": "Current activity",
        "text": "No open stops are visible; the route was completed.",
    }
    assert narrative["action_items"] == []
    assert narrative["needs_review_items"] == []
    assert narrative["critical_exception_items"] == []
    assert narrative["has_damage_reports"] is False
    assert narrative["has_delay_events"] is False
