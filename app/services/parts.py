from datetime import datetime
import re

from app.extensions import db
from app.models import PartAlias, PartLocationHistory, PartMaster, PartScanEvent, PreTrip
from app.services.flow_events import FlowEventService
from app.services.load_state import destination_from_load
from app.services.plant_addresses import plant_label

SCAN_CONTEXTS = {
    "arrival_scan",
    "departure_scan",
    "pickup_scan",
    "drop_scan",
    "manual_entry",
    "exception_scan",
}

PART_TOKEN_RE = re.compile(r"[A-Z]*\d[A-Z0-9]*")


def normalize_part_value(value):
    raw = (value or "").strip().upper()
    if not raw:
        return ""
    candidates = []
    for token in PART_TOKEN_RE.findall(raw):
        cleaned = token
        for prefix in ("PART", "LOAD", "SKU", "SKID"):
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 1:
                cleaned = cleaned[len(prefix):]
        if any(ch.isdigit() for ch in cleaned):
            candidates.append(cleaned)
    if candidates:
        return min(candidates, key=len)[:120]
    return re.sub(r"[^A-Z0-9]", "", raw)[:120]


def _scan_context(value):
    context = (value or "").strip()
    return context if context in SCAN_CONTEXTS else "manual_entry"


def _latest_pretrip(driver_id, route_date):
    if not driver_id:
        return None
    query = PreTrip.query.filter_by(user_id=driver_id)
    if route_date:
        same_day = query.filter_by(pretrip_date=route_date).order_by(PreTrip.created_at.desc()).first()
        if same_day:
            return same_day
    return query.order_by(PreTrip.created_at.desc()).first()


def _resolve_part(raw_value, normalized, barcode_format=None):
    now = datetime.utcnow()
    alias = PartAlias.query.filter_by(normalized_value=normalized).first()
    if alias:
        alias.last_seen_at = now
        if not alias.raw_scan_value or alias.raw_scan_value == alias.normalized_value or raw_value != normalized:
            alias.raw_scan_value = raw_value
        if alias.raw_barcode_value == alias.normalized_value and raw_value != normalized:
            alias.raw_barcode_value = raw_value
        if barcode_format and not alias.symbology:
            alias.symbology = barcode_format
        if barcode_format and not alias.label_format:
            alias.label_format = barcode_format
        part = alias.part
        part.last_seen_at = now
        part.seen_count = (part.seen_count or 0) + 1
        return part, alias, False

    part = PartMaster.query.filter_by(canonical_part_number=normalized).first()
    created = False
    if not part:
        part = PartMaster(
            canonical_part_number=normalized,
            description="Pending manager confirmation",
            status="pending",
            active=True,
            first_seen_at=now,
            last_seen_at=now,
            seen_count=1,
        )
        db.session.add(part)
        db.session.flush()
        created = True
    else:
        part.last_seen_at = now
        part.seen_count = (part.seen_count or 0) + 1

    alias = PartAlias(
        part_id=part.id,
        raw_scan_value=raw_value,
        raw_barcode_value=raw_value,
        normalized_value=normalized,
        label_format=barcode_format,
        symbology=barcode_format,
        label_source="driver_scan",
        first_seen_at=now,
        last_seen_at=now,
    )
    db.session.add(alias)
    return part, alias, created


def resolve_or_create_part(raw_value, barcode_format=None):
    raw = (raw_value or "").strip()
    normalized = normalize_part_value(raw)
    if not raw or not normalized:
        return None, ""
    part, _alias, _created = _resolve_part(raw, normalized, barcode_format)
    return part, normalized


def _expected_tokens(log, route):
    values = {getattr(log, "part_number", None)}
    for key in (
        "arrive_desc",
        "arrive_secondary_desc",
        "arrive_cargo_desc",
        "depart_desc",
        "depart_secondary_desc",
        "depart_cargo_desc",
        "after_arrival_primary",
        "after_arrival_secondary",
        "after_arrival_cargo",
    ):
        values.add((route or {}).get(key))
    tokens = {normalize_part_value(value) for value in values if value}
    return {token for token in tokens if token}


def _validation_for_scan(log, route, part, normalized, context):
    expected_tokens = _expected_tokens(log, route)
    plant_code = getattr(log, "plant_name", None)
    destination = destination_from_load(getattr(log, "load_size", None))
    part_destination = getattr(part, "default_destination_plant_id", None)

    if getattr(part, "status", "") == "pending":
        return "pending_part", "Unknown part saved as a pending record for manager confirmation."
    if part_destination and plant_code and part_destination == plant_code and context == "drop_scan":
        return "valid", f"Part is expected to drop at {plant_label(plant_code)}."
    if normalized in expected_tokens:
        return "valid", "Scanned cargo matches this stop's recorded load context."
    if context == "drop_scan" and destination and destination != plant_code:
        return "unexpected", f"Cargo appears assigned to {plant_label(destination)}, not {plant_label(plant_code)}."
    if context in {"arrival_scan", "departure_scan", "pickup_scan", "manual_entry"}:
        return "recorded", "Scan recorded for this stop."
    return "needs_review", "Scan recorded; dispatcher should verify this part against the move."


def record_part_scan(*, log, route=None, raw_value, scan_context, barcode_format=None, device_id=None, gps_lat=None, gps_lng=None, created_offline=False, move_id=None):
    raw = (raw_value or "").strip()
    normalized = normalize_part_value(raw)
    if not raw or not normalized:
        raise ValueError("A barcode or part value is required.")

    context = _scan_context(scan_context)
    part, _alias, _created = _resolve_part(raw, normalized, barcode_format)
    pretrip = _latest_pretrip(getattr(log, "driver_id", None), getattr(log, "date", None))
    validation_status, validation_message = _validation_for_scan(log, route or {}, part, normalized, context)

    event = PartScanEvent(
        raw_value=raw,
        normalized_value=normalized,
        barcode_format=barcode_format,
        part_id=part.id,
        move_id=move_id,
        route_id=f"driver:{getattr(log, 'driver_id', None)}:date:{getattr(log, 'date', '')}" if getattr(log, "driver_id", None) and getattr(log, "date", None) else None,
        stop_id=getattr(log, "id", None),
        driver_log_id=getattr(log, "id", None),
        driver_id=getattr(log, "driver_id", None),
        truck_id=getattr(pretrip, "truck_number", None),
        trailer_id=getattr(pretrip, "trailer_number", None),
        plant_id=getattr(log, "plant_name", None),
        scan_context=context,
        device_id=device_id,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        validation_status=validation_status,
        validation_message=validation_message,
        created_offline=bool(created_offline),
        synced_at=None if created_offline else datetime.utcnow(),
    )
    db.session.add(event)
    db.session.flush()

    location = PartLocationHistory(
        part_id=part.id,
        plant_id=getattr(log, "plant_name", None),
        stop_id=getattr(log, "id", None),
        move_id=move_id,
        status=context.replace("_scan", ""),
        timestamp=event.timestamp,
        source_scan_event_id=event.id,
    )
    db.session.add(location)
    FlowEventService.append_event(
        event_type="SCAN_RECORDED",
        entity_type="part",
        entity_id=part.id,
        route_id=event.route_id,
        stop_id=getattr(log, "id", None),
        vehicle_id=getattr(pretrip, "truck_number", None),
        trailer_id=getattr(pretrip, "trailer_number", None),
        actor_user_id=getattr(log, "driver_id", None),
        actor_role="driver",
        origin_node_id=getattr(log, "plant_name", None),
        destination_node_id=destination_from_load(getattr(log, "depart_load_size", None)) or getattr(log, "plant_name", None),
        occurred_at=event.timestamp,
        device_id=device_id,
        source="scanner",
        payload_json={
            "part_scan_event_id": event.id,
            "raw_value": raw,
            "normalized_value": normalized,
            "scan_context": context,
            "validation_status": validation_status,
            "validation_message": validation_message,
            "created_offline": bool(created_offline),
        },
        commit=False,
    )
    return event


def scan_event_payload(event):
    return {
        "id": event.id,
        "raw_value": event.raw_value,
        "normalized_value": event.normalized_value,
        "barcode_format": event.barcode_format,
        "scan_context": event.scan_context,
        "validation_status": event.validation_status,
        "validation_message": event.validation_message,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "part": event.part.canonical_part_number if event.part else None,
        "part_status": event.part.status if event.part else None,
    }
