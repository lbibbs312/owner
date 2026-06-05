from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError


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


def _commit_fails(db):
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_flow_event_offline_idempotency_is_unique_only_when_present(app):
    from app.extensions import db
    from app.models import FlowEvent

    db.session.add_all([
        FlowEvent(event_type="SCAN_RECORDED", entity_type="part", entity_id="A", source="mobile"),
        FlowEvent(event_type="SCAN_RECORDED", entity_type="part", entity_id="A", source="mobile"),
    ])
    db.session.commit()

    db.session.add(
        FlowEvent(
            event_type="SCAN_RECORDED",
            entity_type="part",
            entity_id="A",
            source="mobile",
            device_id="driver-phone-1",
            offline_event_id="offline-123",
        )
    )
    db.session.commit()
    db.session.add(
        FlowEvent(
            event_type="SCAN_RECORDED",
            entity_type="part",
            entity_id="A",
            source="mobile",
            device_id="driver-phone-1",
            offline_event_id="offline-123",
        )
    )

    _commit_fails(db)


def test_part_canonical_and_alias_are_unique_per_tenant(app):
    from app.extensions import db
    from app.models import PartAlias, PartMaster

    first = PartMaster(tenant_id="tenant-a", canonical_part_number="L861", status="active")
    db.session.add(first)
    db.session.commit()

    db.session.add(PartMaster(tenant_id="tenant-a", canonical_part_number="L861", status="active"))
    _commit_fails(db)

    second_tenant = PartMaster(tenant_id="tenant-b", canonical_part_number="L861", status="active")
    db.session.add(second_tenant)
    db.session.commit()

    db.session.add(
        PartAlias(
            tenant_id="tenant-a",
            part_id=first.id,
            raw_scan_value="L861",
            raw_barcode_value="L861",
            normalized_value="L861",
        )
    )
    db.session.commit()
    db.session.add(
        PartAlias(
            tenant_id="tenant-a",
            part_id=first.id,
            raw_scan_value="L861",
            raw_barcode_value="L861",
            normalized_value="L861",
        )
    )

    _commit_fails(db)


def test_move_part_rejects_impossible_quantity_math(app):
    from app.extensions import db
    from app.models import MovePart, PartMaster, Task

    task = Task(title="Move L861")
    part = PartMaster(canonical_part_number="L861", status="active")
    db.session.add_all([task, part])
    db.session.commit()

    db.session.add(
        MovePart(
            move_id=task.id,
            part_id=part.id,
            expected_quantity=1,
            picked_quantity=2,
            dropped_quantity=0,
        )
    )

    _commit_fails(db)


def test_plant_transfer_lines_require_unique_nonnegative_cargo_detail(app):
    from app.extensions import db
    from app.models import PlantTransfer, PlantTransferLine, User

    driver = User(username="driver1", email="driver1@example.com", role="driver")
    transfer = PlantTransfer(
        user_id=1,
        transfer_date=date(2026, 6, 5),
        ship_to="52L",
        ship_from="KP",
    )
    db.session.add(driver)
    db.session.flush()
    transfer.user_id = driver.id
    db.session.add(transfer)
    db.session.flush()
    db.session.add(
        PlantTransferLine(
            plant_transfer_id=transfer.id,
            line_number=1,
            side="left",
            part_number="L861",
            quantity="4",
            skids="1",
        )
    )
    db.session.commit()

    db.session.add(
        PlantTransferLine(
            plant_transfer_id=transfer.id,
            line_number=1,
            side="left",
            part_number="L861",
            quantity="1",
        )
    )
    _commit_fails(db)

    db.session.add(
        PlantTransferLine(
            plant_transfer_id=transfer.id,
            line_number=2,
            side="left",
            remarks="driver note only",
        )
    )
    _commit_fails(db)

    db.session.add(
        PlantTransferLine(
            plant_transfer_id=transfer.id,
            line_number=3,
            side="left",
            part_number="L861",
            quantity="-1",
        )
    )
    _commit_fails(db)
