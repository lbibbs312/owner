"""TruckerPlaceSummaryService turns whatever official place data exists into
short driver notes, prefers our own saved notes, and never invents notes."""
from app.services.trucker_place_summary import NOTE_KEYS, TruckerPlaceSummaryService


def test_known_place_notes_beat_google_derived_notes():
    service = TruckerPlaceSummaryService(enable_reviews=True, enable_generative=True)
    result = service.build(
        {
            "place_name": "Receiver Warehouse",
            "known_place_notes": {"dock_note": "Use door 3, ring the bell"},
            "reviews": [{"text": "The docks here are really tight and hard to back into."}],
        }
    )
    assert result["dock_note"] == "Use door 3, ring the bell"
    assert result["source"] == "known_place_notes"
    assert result["confidence"] >= 90


def test_reviews_with_tight_docks_populate_dock_and_backing():
    service = TruckerPlaceSummaryService(enable_reviews=True)
    result = service.build(
        {
            "place_name": "Tight Dock LLC",
            "reviews": [{"text": "Heads up: the docks are tight and it is a blindside back."}],
        }
    )
    assert result["dock_note"] is not None
    assert result["backing_note"] is not None
    assert "tight" in result["dock_note"].lower() or "tight" in result["backing_note"].lower()
    assert result["source"] == "google_reviews"


def test_reviews_with_overnight_parking_populate_parking_note():
    service = TruckerPlaceSummaryService(enable_reviews=True)
    result = service.build(
        {
            "place_name": "Founders Brewing Warehouse",
            "reviews": [{"text": "They let trucks do overnight parking in the back lot."}],
        }
    )
    assert result["overnight_parking_note"] is not None
    assert result["parking_note"] is not None
    assert "overnight" in result["parking_note"].lower()


def test_no_trucker_data_returns_no_notes():
    service = TruckerPlaceSummaryService(enable_reviews=True, enable_generative=True)
    result = service.build({"place_name": "Empty Co", "types": ["warehouse"]})
    for key in NOTE_KEYS:
        assert result[key] is None
    assert result["source"] == "none"
    assert result["confidence"] == 0


def test_no_hallucinated_notes_when_text_has_no_trucker_info():
    service = TruckerPlaceSummaryService(enable_reviews=True, enable_generative=True)
    result = service.build(
        {
            "place_name": "Corner Cafe",
            "reviews": [{"text": "Great coffee, friendly staff, and a clean dining room."}],
            "generativeSummary": {"overview": {"text": "A cozy spot loved by locals."}},
        }
    )
    for key in NOTE_KEYS:
        assert result[key] is None
    assert result["source"] == "none"


def test_place_details_parking_and_hours_become_notes():
    service = TruckerPlaceSummaryService()
    result = service.build(
        {
            "place_name": "Distribution Center",
            "parkingOptions": {"freeParkingLot": True},
            "currentOpeningHours": {"openNow": True},
        }
    )
    assert result["parking_note"] == "Free parking lot on site"
    assert result["hours_note"] == "Open now"
    assert result["source"] == "google_place_details"


def test_review_summary_only_used_when_review_flag_enabled():
    payload = {
        "place_name": "Gated Yard",
        "reviewSummary": {"text": {"text": "Stop at the guard shack to check in before backing."}},
    }
    off = TruckerPlaceSummaryService(enable_reviews=False).build(payload)
    assert off["entrance_note"] is None
    assert off["source"] == "none"

    on = TruckerPlaceSummaryService(enable_reviews=True).build(payload)
    assert on["entrance_note"] is not None
    assert "guard shack" in on["entrance_note"].lower()
