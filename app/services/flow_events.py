"""Append-only production flow ledger and projection helpers.

The ledger is authoritative. Current status fields and snapshot rows are
derived projections that can be rebuilt from ``FlowEvent`` rows.
"""
from datetime import date as date_cls, datetime

from sqlalchemy import and_

from app.extensions import db
from app.models import (
    ContainerItem,
    ContainerTreeSnapshot,
    EntityCurrentState,
    ExceptionEvent,
    FlowContainer,
    FlowEvent,
    FlowManifest,
    FlowNodeSnapshot,
)


TENANT_DEFAULT = "lacksdrivers"

EVENT_STATUS = {
    "WIP_STARTED": "wip",
    "WIP_COMPLETED": "wip_completed",
    "STAGED": "staged",
    "ASSIGNED_TO_TRAILER": "loaded",
    "LOADED_TO_CONTAINER": "loaded",
    "REMOVED_FROM_CONTAINER": "removed",
    "MANIFEST_CREATED": "manifest_draft",
    "MANIFEST_ATTACHED": "manifested",
    "DEPARTED_ORIGIN": "in_transit",
    "IN_TRANSIT": "in_transit",
    "ARRIVED_DESTINATION": "arrived",
    "SCAN_RECORDED": "scanned",
    "UNLOADED": "unloaded",
    "RECEIVED": "received",
    "RECONCILED": "reconciled",
    "QA_HOLD_PLACED": "qa_hold",
    "QA_HOLD_RELEASED": "released",
    "SCRAP_MARKED": "scrap",
    "LAB_SAMPLE_ROUTED": "lab_sample",
    "DAMAGE_REPORTED": "damage",
    "FORKLIFT_ISSUE_REPORTED": "forklift_issue",
    "DELAY_REPORTED": "delay",
    "MISMATCH_DETECTED": "mismatch",
    "MISMATCH_RESOLVED": "resolved",
    "PROOF_ATTACHED": "proof_attached",
    "MANAGER_APPROVED": "approved",
    "MANAGER_REJECTED": "rejected",
}

EXCEPTION_STATUSES = {"qa_hold", "scrap", "damage", "forklift_issue", "delay", "mismatch", "rejected"}
BLOCKING_EVENT_TYPES = {"MISMATCH_DETECTED", "QA_HOLD_PLACED", "SCRAP_MARKED", "DAMAGE_REPORTED", "FORKLIFT_ISSUE_REPORTED", "DELAY_REPORTED"}


def _as_entity_id(value):
    return str(value) if value is not None else None


def _event_status(event):
    payload_status = (event.payload_json or {}).get("current_status")
    return payload_status or EVENT_STATUS.get(event.event_type, event.event_type.lower())


def _event_node(event):
    if event.event_type in {"DEPARTED_ORIGIN", "IN_TRANSIT"}:
        return event.destination_node_id or event.origin_node_id
    if event.event_type in {"ARRIVED_DESTINATION", "UNLOADED", "RECEIVED", "RECONCILED"}:
        return event.destination_node_id or event.origin_node_id
    return event.destination_node_id or event.origin_node_id


def _root_container_id(container):
    current = container
    seen = set()
    while current and current.parent_container_id and current.parent_container_id not in seen:
        seen.add(current.id)
        current = current.parent_container
    return current.id if current else container.id


def _container_quantity(container):
    return sum(float(item.quantity or 0) for item in getattr(container, "items", []) or [])


class FlowProjectionService:
    @staticmethod
    def get_current_state(entity_type, entity_id, *, tenant_id=TENANT_DEFAULT):
        return EntityCurrentState.query.filter_by(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=_as_entity_id(entity_id),
        ).first()

    @staticmethod
    def apply_event(event, *, commit=False):
        status = _event_status(event)
        node_id = _event_node(event)
        FlowProjectionService._upsert_entity_state(event, status=status, node_id=node_id)
        FlowProjectionService._apply_materialized_models(event, status=status, node_id=node_id)
        FlowProjectionService._update_node_snapshot(event, status=status, node_id=node_id)
        if commit:
            db.session.commit()

    @staticmethod
    def rebuild_for_entity(entity_type, entity_id, *, tenant_id=TENANT_DEFAULT, commit=False):
        entity_id = _as_entity_id(entity_id)
        EntityCurrentState.query.filter_by(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        ).delete()
        events = (
            FlowEvent.query.filter_by(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id)
            .order_by(FlowEvent.occurred_at.asc(), FlowEvent.id.asc())
            .all()
        )
        for event in events:
            FlowProjectionService.apply_event(event, commit=False)
        if commit:
            db.session.commit()
        return FlowProjectionService.get_current_state(entity_type, entity_id, tenant_id=tenant_id)

    @staticmethod
    def rebuild_for_day(target_date, *, tenant_id=TENANT_DEFAULT, commit=False):
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
        FlowNodeSnapshot.query.filter_by(tenant_id=tenant_id, snapshot_date=target_date).delete()
        events = (
            FlowEvent.query.filter(
                FlowEvent.tenant_id == tenant_id,
                FlowEvent.occurred_at >= start,
                FlowEvent.occurred_at <= end,
            )
            .order_by(FlowEvent.occurred_at.asc(), FlowEvent.id.asc())
            .all()
        )
        for event in events:
            FlowProjectionService._update_node_snapshot(event, status=_event_status(event), node_id=_event_node(event))
        if commit:
            db.session.commit()
        return FlowNodeSnapshot.query.filter_by(tenant_id=tenant_id, snapshot_date=target_date).all()

    @staticmethod
    def _upsert_entity_state(event, *, status, node_id):
        entity_id = _as_entity_id(event.entity_id)
        if not entity_id:
            return None
        state = FlowProjectionService.get_current_state(event.entity_type, entity_id, tenant_id=event.tenant_id)
        if state is None:
            state = EntityCurrentState(
                tenant_id=event.tenant_id,
                entity_type=event.entity_type,
                entity_id=entity_id,
            )
            db.session.add(state)
        state.current_status = status
        state.current_node_id = node_id or state.current_node_id
        state.parent_container_id = event.container_id or state.parent_container_id
        state.active_manifest_id = event.manifest_id or state.active_manifest_id
        state.active_route_id = event.route_id or state.active_route_id
        state.last_event_id = event.id
        state.last_event_at = event.occurred_at
        return state

    @staticmethod
    def _apply_materialized_models(event, *, status, node_id):
        if event.manifest_id:
            manifest = FlowManifest.query.get(event.manifest_id)
            if manifest:
                manifest.current_status = status if event.entity_type == "manifest" else manifest.current_status
                manifest.route_id = event.route_id or manifest.route_id
                manifest.vehicle_id = event.vehicle_id or manifest.vehicle_id
                manifest.trailer_id = event.trailer_id or manifest.trailer_id
                manifest.origin_node_id = event.origin_node_id or manifest.origin_node_id
                manifest.destination_node_id = event.destination_node_id or manifest.destination_node_id

        if event.container_id:
            container = FlowContainer.query.get(event.container_id)
            if container:
                container.current_status = status
                container.current_node_id = node_id or container.current_node_id
                payload_parent = (event.payload_json or {}).get("parent_container_id")
                if payload_parent is not None:
                    container.parent_container_id = payload_parent
                FlowProjectionService._upsert_container_snapshot(event, container, status=status, node_id=node_id)

        if event.item_id:
            item = ContainerItem.query.get(event.item_id)
            if item and event.container_id and item.container_id != event.container_id:
                item.container_id = event.container_id

    @staticmethod
    def _upsert_container_snapshot(event, container, *, status, node_id):
        snapshot = ContainerTreeSnapshot.query.filter_by(
            tenant_id=event.tenant_id,
            container_id=container.id,
        ).first()
        if snapshot is None:
            snapshot = ContainerTreeSnapshot(
                tenant_id=event.tenant_id,
                container_id=container.id,
                root_container_id=_root_container_id(container),
            )
            db.session.add(snapshot)
        snapshot.parent_container_id = container.parent_container_id
        snapshot.root_container_id = _root_container_id(container)
        snapshot.current_node_id = node_id or container.current_node_id
        snapshot.current_status = status
        snapshot.current_quantity = _container_quantity(container)
        snapshot.active_manifest_id = event.manifest_id or snapshot.active_manifest_id
        snapshot.last_event_id = event.id

    @staticmethod
    def _update_node_snapshot(event, *, status, node_id):
        if not node_id:
            return None
        snapshot_date = event.occurred_at.date() if isinstance(event.occurred_at, datetime) else date_cls.today()
        snapshot = FlowNodeSnapshot.query.filter_by(
            tenant_id=event.tenant_id,
            node_id=node_id,
            snapshot_date=snapshot_date,
        ).first()
        if snapshot is None:
            snapshot = FlowNodeSnapshot(
                tenant_id=event.tenant_id,
                node_id=node_id,
                snapshot_date=snapshot_date,
                wip_count=0,
                staged_count=0,
                loaded_count=0,
                in_transit_count=0,
                received_count=0,
                blocked_count=0,
                proof_needed_count=0,
                exception_count=0,
            )
            db.session.add(snapshot)
        def bump(name):
            setattr(snapshot, name, (getattr(snapshot, name) or 0) + 1)
        if status == "wip":
            bump("wip_count")
        elif status == "staged":
            bump("staged_count")
        elif status in {"loaded", "manifested"}:
            bump("loaded_count")
        elif status == "in_transit":
            bump("in_transit_count")
        elif status in {"received", "reconciled"}:
            bump("received_count")
        elif status in EXCEPTION_STATUSES:
            bump("exception_count")
            bump("blocked_count")
        if event.event_type in {"LOADED_TO_CONTAINER", "ASSIGNED_TO_TRAILER"} and not event.manifest_id:
            bump("proof_needed_count")
        snapshot.last_event_id = event.id
        return snapshot


class FlowMismatchService:
    @staticmethod
    def evaluate_after_event(event):
        if event.event_type == "MISMATCH_DETECTED":
            return []
        findings = []
        findings.extend(FlowMismatchService._loaded_without_manifest(event))
        findings.extend(FlowMismatchService._unexpected_scan(event))
        findings.extend(FlowMismatchService._quantity_mismatch(event))
        return findings

    @staticmethod
    def _loaded_without_manifest(event):
        if event.event_type not in {"LOADED_TO_CONTAINER", "ASSIGNED_TO_TRAILER"}:
            return []
        if event.manifest_id:
            return []
        payload = event.payload_json or {}
        if payload.get("manager_override_event_id"):
            return []
        return [{
            "event_type": "MISMATCH_DETECTED",
            "severity": "high",
            "exception_code": "MANIFEST_MISSING",
            "summary": "Loaded cargo missing manifest",
            "details": "Cargo was loaded or assigned to a trailer without an attached manifest or intersite shipper.",
            "block_audit_approval": True,
        }]

    @staticmethod
    def _quantity_mismatch(event):
        if event.event_type not in {"SCAN_RECORDED", "RECONCILED"} or not event.manifest_id:
            return []
        payload = event.payload_json or {}
        expected = payload.get("quantity_expected")
        scanned = payload.get("quantity_scanned")
        if expected is None or scanned is None:
            return []
        try:
            mismatch = float(expected) != float(scanned)
        except (TypeError, ValueError):
            mismatch = str(expected) != str(scanned)
        if not mismatch:
            return []
        return [{
            "event_type": "MISMATCH_DETECTED",
            "severity": "high",
            "exception_code": "QUANTITY_MISMATCH",
            "summary": "Manifest quantity mismatch",
            "details": f"Expected {expected}; scanned {scanned}.",
            "block_audit_approval": True,
        }]

    @staticmethod
    def _unexpected_scan(event):
        if event.event_type != "SCAN_RECORDED":
            return []
        payload = event.payload_json or {}
        validation_status = (payload.get("validation_status") or "").lower()
        if validation_status not in {"unexpected", "needs_review", "pending_part"}:
            return []
        return [{
            "event_type": "MISMATCH_DETECTED",
            "severity": "high" if validation_status == "unexpected" else "medium",
            "exception_code": "UNEXPECTED_SCAN" if validation_status == "unexpected" else "SCAN_NEEDS_REVIEW",
            "summary": "Scanned cargo needs review",
            "details": payload.get("validation_message") or "Cargo scan did not match the expected route, manifest, or location.",
            "block_audit_approval": validation_status == "unexpected",
        }]


class FlowEventService:
    @staticmethod
    def append_event(
        *,
        event_type,
        entity_type,
        entity_id,
        tenant_id=TENANT_DEFAULT,
        route_id=None,
        stop_id=None,
        manifest_id=None,
        vehicle_id=None,
        trailer_id=None,
        container_id=None,
        item_id=None,
        actor_user_id=None,
        actor_role=None,
        origin_node_id=None,
        destination_node_id=None,
        occurred_at=None,
        device_id=None,
        offline_event_id=None,
        correlation_id=None,
        source="system",
        payload_json=None,
        notes=None,
        photo_id=None,
        document_id=None,
        apply_projection=True,
        run_rules=True,
        commit=False,
    ):
        if offline_event_id and device_id:
            existing = FlowEvent.query.filter(
                and_(
                    FlowEvent.tenant_id == tenant_id,
                    FlowEvent.device_id == device_id,
                    FlowEvent.offline_event_id == offline_event_id,
                )
            ).first()
            if existing:
                return existing

        event = FlowEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=_as_entity_id(entity_id),
            route_id=route_id,
            stop_id=stop_id,
            manifest_id=manifest_id,
            vehicle_id=vehicle_id,
            trailer_id=trailer_id,
            container_id=container_id,
            item_id=item_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            occurred_at=occurred_at or datetime.utcnow(),
            device_id=device_id,
            offline_event_id=offline_event_id,
            correlation_id=correlation_id,
            source=source,
            payload_json=payload_json or {},
            notes=notes,
            photo_id=photo_id,
            document_id=document_id,
        )
        db.session.add(event)
        db.session.flush()

        if apply_projection:
            FlowProjectionService.apply_event(event, commit=False)

        if run_rules:
            for finding in FlowMismatchService.evaluate_after_event(event):
                FlowEventService._append_mismatch_event(event, finding)

        if commit:
            db.session.commit()
        return event

    @staticmethod
    def _append_mismatch_event(source_event, finding):
        payload = {
            "rule_name": finding["summary"],
            "exception_code": finding["exception_code"],
            "source_event_id": source_event.id,
            "block_audit_approval": bool(finding.get("block_audit_approval")),
            "show_on_flow_map": True,
        }
        mismatch = FlowEventService.append_event(
            tenant_id=source_event.tenant_id,
            event_type="MISMATCH_DETECTED",
            entity_type=source_event.entity_type,
            entity_id=source_event.entity_id,
            route_id=source_event.route_id,
            stop_id=source_event.stop_id,
            manifest_id=source_event.manifest_id,
            vehicle_id=source_event.vehicle_id,
            trailer_id=source_event.trailer_id,
            container_id=source_event.container_id,
            item_id=source_event.item_id,
            actor_user_id=source_event.actor_user_id,
            actor_role=source_event.actor_role,
            origin_node_id=source_event.origin_node_id,
            destination_node_id=source_event.destination_node_id,
            occurred_at=source_event.occurred_at,
            device_id=source_event.device_id,
            correlation_id=source_event.correlation_id,
            source="system",
            payload_json=payload,
            notes=finding.get("details"),
            apply_projection=True,
            run_rules=False,
            commit=False,
        )
        db.session.add(ExceptionEvent(
            event_type=finding["exception_code"],
            severity=finding.get("severity") or "medium",
            route_id=source_event.route_id,
            stop_id=source_event.stop_id,
            driver_log_id=source_event.stop_id,
            plant_name=source_event.destination_node_id or source_event.origin_node_id,
            event_date=source_event.occurred_at.date() if source_event.occurred_at else None,
            target_type=source_event.entity_type,
            target_id=int(source_event.entity_id) if str(source_event.entity_id).isdigit() else None,
            summary=finding["summary"],
            details=finding.get("details"),
        ))
        return mismatch
