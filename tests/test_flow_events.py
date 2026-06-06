from datetime import datetime

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


def test_flow_event_appends_projection_and_rebuilds(app):
    from app.extensions import db
    from app.models import EntityCurrentState, FlowEvent
    from app.services.flow_events import FlowEventService, FlowProjectionService

    event = FlowEventService.append_event(
        event_type="STAGED",
        entity_type="move_request",
        entity_id=42,
        origin_node_id="KP",
        destination_node_id="52L",
        source="admin",
        payload_json={"legacy_status_projection": "assigned"},
        commit=True,
    )

    state = EntityCurrentState.query.filter_by(entity_type="move_request", entity_id="42").one()
    assert event.id
    assert state.current_status == "staged"
    assert state.current_node_id == "52L"
    assert state.last_event_id == event.id

    db.session.delete(state)
    db.session.commit()
    rebuilt = FlowProjectionService.rebuild_for_entity("move_request", 42, commit=True)

    assert rebuilt.current_status == "staged"
    assert rebuilt.last_event_id == FlowEvent.query.one().id


def test_offline_event_id_is_idempotent(app):
    from app.models import FlowEvent
    from app.services.flow_events import FlowEventService

    first = FlowEventService.append_event(
        event_type="SCAN_RECORDED",
        entity_type="part",
        entity_id=7,
        device_id="driver-phone-1",
        offline_event_id="offline-123",
        source="mobile",
        commit=True,
    )
    second = FlowEventService.append_event(
        event_type="SCAN_RECORDED",
        entity_type="part",
        entity_id=7,
        device_id="driver-phone-1",
        offline_event_id="offline-123",
        source="mobile",
        commit=True,
    )

    assert second.id == first.id
    assert FlowEvent.query.count() == 1


def test_nested_container_projection_tracks_root_and_quantity(app):
    from app.extensions import db
    from app.models import ContainerItem, ContainerTreeSnapshot, ContainerType, FlowContainer, FlowManifest
    from app.services.flow_events import FlowEventService

    trailer_type = ContainerType(name="Trailer", code="trailer")
    rack_type = ContainerType(name="Rack", code="rack")
    db.session.add_all([trailer_type, rack_type])
    db.session.flush()
    trailer = FlowContainer(container_type_id=trailer_type.id, identifier="225")
    rack = FlowContainer(container_type_id=rack_type.id, identifier="R-001", parent_container=trailer)
    db.session.add_all([trailer, rack])
    db.session.flush()
    item = ContainerItem(container_id=rack.id, part_sku="SKU-1", serial_number="S1", lot_id="L1", quantity=12)
    manifest = FlowManifest(manifest_number="10355338", origin_node_id="Staging", destination_node_id="Trailer 225")
    db.session.add_all([item, manifest])
    db.session.flush()

    FlowEventService.append_event(
        event_type="LOADED_TO_CONTAINER",
        entity_type="container",
        entity_id=rack.id,
        container_id=rack.id,
        item_id=item.id,
        manifest_id=manifest.id,
        origin_node_id="Staging",
        destination_node_id="Trailer 225",
        source="scanner",
        payload_json={"parent_container_id": trailer.id},
        commit=True,
    )

    snapshot = ContainerTreeSnapshot.query.filter_by(container_id=rack.id).one()
    assert snapshot.root_container_id == trailer.id
    assert snapshot.parent_container_id == trailer.id
    assert snapshot.current_status == "loaded"
    assert snapshot.current_quantity == 12


def test_loaded_without_manifest_creates_structured_mismatch(app):
    from app.models import ExceptionEvent, FlowEvent
    from app.services.flow_events import FlowEventService

    FlowEventService.append_event(
        event_type="LOADED_TO_CONTAINER",
        entity_type="container",
        entity_id=99,
        trailer_id="225",
        origin_node_id="Staging",
        destination_node_id="Load Build",
        source="scanner",
        commit=True,
    )

    mismatch = FlowEvent.query.filter_by(event_type="MISMATCH_DETECTED").one()
    exception = ExceptionEvent.query.one()
    assert mismatch.payload_json["exception_code"] == "MANIFEST_MISSING"
    assert mismatch.payload_json["block_audit_approval"] is True
    assert exception.event_type == "MANIFEST_MISSING"


def test_flow_map_dashboard_exposes_lane_first_contract(app):
    from app.extensions import db
    from app.models import MoveRequest, User

    user = User(username="flowboss", email="flowboss@example.com", role="management")
    user.set_password("password1")
    db.session.add(user)
    db.session.flush()
    db.session.add(MoveRequest(
        raw_text="Move racks from KP to 52L",
        created_by_id=user.id,
        status="open",
        origin_location_text="KP",
        destination_location_text="52L",
        requested_at=datetime.utcnow(),
    ))
    db.session.commit()

    client = app.test_client()
    client.post("/login", data={"login_name": "flowboss", "password": "password1"})
    resp = client.get("/manager/dashboard")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Manager Workspace" in body
    assert 'data-component="FlowMapDashboard"' not in body
    assert "WIP / Production" not in body
    assert "Manifested" not in body
    assert 'aria-label="View Production Flow facility map"' not in body
