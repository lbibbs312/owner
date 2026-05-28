"""Tests for the floor-operations snapshot service."""
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _user(username="mgr", role="management"):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=f"{username}@example.com", role=role)
    user.set_password("password1")
    db.session.add(user)
    db.session.commit()
    return user


def _move_request(creator_id, **kw):
    from app.extensions import db
    from app.models import MoveRequest

    base = dict(raw_text="move parts", created_by_id=creator_id, status="open", priority="normal")
    base.update(kw)
    req = MoveRequest(**base)
    db.session.add(req)
    db.session.commit()
    return req


FLOOR_CARD_KEYS = [
    "ready_to_move", "loading_now", "unloading_now", "blocked_or_no_parts",
    "on_road", "completed_recently", "waiting_over_limit", "hot_or_urgent",
]


def test_empty_database_returns_safe_state(app):
    from app.services.floor_operations import build_floor_operations_snapshot

    snap = build_floor_operations_snapshot()
    assert snap["queue_summary"] == {
        "open_requests": 0, "hot_requests": 0, "unassigned_requests": 0,
        "blocked_requests": 0, "due_soon_requests": 0,
    }
    assert snap["map_nodes"] == []
    assert snap["map_edges"] == []
    assert snap["active_moves"] == []
    assert snap["needs_attention"] == []
    assert snap["latest_requests"] == []
    assert [c["key"] for c in snap["floor_cards"]] == FLOOR_CARD_KEYS
    assert all(card["count"] == 0 for card in snap["floor_cards"])


def test_queue_summary_counts(app):
    from app.services.floor_operations import build_floor_operations_snapshot

    user = _user()
    _move_request(user.id, priority="hot", origin_location_text="Raleigh East",
                  destination_location_text="Plastic West", cargo_text="HDPE")
    _move_request(user.id, status="blocked", blocked_reason="no parts",
                  origin_location_text="A", destination_location_text="B")
    _move_request(user.id, status="assigned", assigned_driver_id=user.id,
                  due_at=datetime.utcnow() + timedelta(minutes=30),
                  origin_location_text="A", destination_location_text="B")

    summary = build_floor_operations_snapshot()["queue_summary"]
    assert summary["open_requests"] == 3
    assert summary["hot_requests"] == 1
    assert summary["unassigned_requests"] == 2
    assert summary["blocked_requests"] == 1
    assert summary["due_soon_requests"] == 1


def test_map_nodes_and_edges_derived_from_locations(app):
    from app.services.floor_operations import build_floor_operations_snapshot

    user = _user()
    _move_request(user.id, status="assigned", assigned_driver_id=user.id,
                  origin_location_text="Raleigh East", destination_location_text="Plastic West")

    snap = build_floor_operations_snapshot()
    labels = {node["label"] for node in snap["map_nodes"]}
    assert "Raleigh East" in labels
    assert "Plastic West" in labels

    node = snap["map_nodes"][0]
    assert set(node) >= {
        "key", "label", "open_request_count", "active_move_count", "blocked_count",
        "waiting_count", "completed_today_count", "worst_status",
    }

    assert len(snap["map_edges"]) == 1
    edge = snap["map_edges"][0]
    assert set(edge) >= {
        "origin_key", "destination_key", "origin_label", "destination_label",
        "open_count", "active_count", "completed_count", "worst_status",
    }
    assert edge["open_count"] == 1
    assert edge["active_count"] == 1
    assert edge["worst_status"] == "active"


def test_blocked_request_surfaces_in_needs_attention(app):
    from app.services.floor_operations import build_floor_operations_snapshot

    user = _user()
    _move_request(user.id, status="blocked", blocked_reason="line down",
                  origin_location_text="A", destination_location_text="B")
    snap = build_floor_operations_snapshot()
    assert len(snap["needs_attention"]) == 1
    item = snap["needs_attention"][0]
    assert item["target_type"] == "move_request"
    assert item["issue"]["category"] == "workflow"
    assert item["issue"]["level"] in {"action", "high", "critical"}


def test_assigned_move_queue_is_driver_scoped(app):
    from app.services.floor_operations import assigned_move_queue

    user = _user()
    driver = _user("driver1", "driver")
    _move_request(user.id, status="assigned", assigned_driver_id=driver.id,
                  origin_location_text="A", destination_location_text="B")
    _move_request(user.id, status="open")  # unassigned, belongs to nobody

    rows = assigned_move_queue(driver.id)
    assert len(rows) == 1
    assert rows[0]["status"] == "assigned"
    assert rows[0]["status_label"] == "Assigned"
    assert assigned_move_queue(None) == []
    assert assigned_move_queue(999999) == []


def test_floor_card_keys_match_contract(app):
    from app.services.floor_operations import build_floor_operations_snapshot

    assert [c["key"] for c in build_floor_operations_snapshot()["floor_cards"]] == FLOOR_CARD_KEYS


# --- Next action map --------------------------------------------------------

def _mk(creator_id, **kw):
    from app.models import MoveRequest

    base = dict(raw_text="x", created_by_id=creator_id, status="open", priority="normal")
    base.update(kw)
    return MoveRequest(**base)


def test_next_action_map(app):
    from app.services.floor_operations import next_action_for_request

    user = _user()
    na = next_action_for_request
    assert na(_mk(user.id, status="cancelled")) == "No action needed"
    assert na(_mk(user.id, status="completed", linked_document_id=1)) == "No action needed"
    assert na(_mk(user.id, status="open")) == "Assign driver"
    assert na(_mk(user.id, status="acknowledged")) == "Assign driver"
    assert na(_mk(user.id, status="open", assigned_driver_id=user.id)) == "Acknowledge request"
    assert na(_mk(user.id, status="assigned", assigned_driver_id=user.id)) == "Start or link route"
    assert na(_mk(user.id, status="blocked")) == "Review blocker"
    assert na(_mk(user.id, status="needs_review")) == "Review issue"


def test_next_action_decline_signal_wins(app):
    from app.services.floor_operations import next_action_for_request

    user = _user()
    req = _mk(user.id, status="assigned", assigned_driver_id=user.id, notes="driver declined the move")
    assert next_action_for_request(req) == "Reassign declined move"


def test_next_action_in_progress_operational_substate(app):
    from app.services.floor_operations import next_action_for_request

    user = _user()
    # Route linked, cargo known, no current open stop, document missing -> Attach document.
    req = _mk(user.id, status="in_progress", assigned_driver_id=user.id,
              linked_route_id="R-1", cargo_text="HDPE", part_number="P1")
    assert next_action_for_request(req) == "Attach document"
    # Cargo unknown -> Confirm cargo takes priority.
    req2 = _mk(user.id, status="in_progress", assigned_driver_id=user.id, linked_route_id="R-2")
    assert next_action_for_request(req2) == "Confirm cargo"
