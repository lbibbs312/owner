import pytest

from app.services.move_request_parser import parse_move_request_text


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        (
            "PMT has 10 skids for the DC please",
            {
                "request_type": "move",
                "origin_location_text": "PMT",
                "destination_location_text": "DC",
                "quantity_value": 10,
                "quantity_unit": "skids",
                "quantity_text": "10 skids",
                "priority": "normal",
            },
        ),
        (
            "Trim 52DC has pack for RW please",
            {
                "request_type": "move",
                "origin_location_text": "Trim 52DC",
                "destination_location_text": "RW",
                "cargo_text": "pack",
                "quantity_text": "pack",
                "priority": "normal",
            },
        ),
        (
            "Tonight at 7pm RW to Kraft North HOT 1 skid P3503",
            {
                "request_type": "move",
                "due_time_text": "tonight at 7pm",
                "origin_location_text": "RW",
                "destination_location_text": "Kraft North",
                "priority": "hot",
                "quantity_value": 1,
                "quantity_unit": "skid",
                "quantity_text": "1 skid",
                "part_number": "P3503",
            },
        ),
        (
            "Caleb can't find a trailer",
            {
                "request_type": "blocker",
                "blocked_reason": "cannot find trailer",
                "notes": "cannot find trailer",
            },
        ),
        (
            "ST4 AC doesn't work",
            {
                "request_type": "equipment_issue",
                "equipment_text": "ST4",
                "notes": "AC does not work",
            },
        ),
    ],
)
def test_parse_move_request_text_examples(raw_text, expected):
    result = parse_move_request_text(raw_text)

    assert set(result) == {"suggestions", "confidence", "warnings", "unparsed_text"}
    assert result["confidence"] in {"medium", "high"}
    for field, value in expected.items():
        assert result["suggestions"][field] == value
