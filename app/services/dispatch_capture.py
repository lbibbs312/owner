import json
import re
from datetime import date as date_cls, datetime

from app.extensions import db
from app.models import ActivityEvent, DamageReport, DispatchCapture, ExceptionEvent, MoveRequest
from app.services.activity import record_activity
from app.services.audit import record_audit_event
from app.services.document_numbers import move_request_number
from app.services.flow_events import FlowEventService
from app.services.move_request_parser import parse_move_request_text


CAPTURE_STATUSES_OPEN = ("captured", "needs_triage")

CAPTURE_TYPE_LABELS = {
    "hot_move": "Hot Move",
    "empty_pack": "Empty Pack",
    "quality_hold": "Quality Hold",
    "delay_no_parts": "Delay / No Parts",
    "damage": "Damage",
    "trailer_request": "Trailer Request",
    "maintenance": "Maintenance",
    "general_note": "General Note",
}

CONVERSION_LABELS = {
    "move_request": "MoveRequest",
    "empty_pack_return": "EmptyPackReturn",
    "quality_hold": "QualityHold",
    "damage_issue": "DamageIssue",
    "delay_report": "DelayReport",
    "maintenance_issue": "MaintenanceIssue",
}

PLANT_ALIASES = {
    "rw": "Raleigh West",
    "raleigh west": "Raleigh West",
    "front end": "Raleigh West",
    "intake": "Raleigh West",
    "kp": "Kraft Plater",
    "kraft": "Kraft Plater",
    "kraft plant": "Kraft Plater",
    "kraft plater": "Kraft Plater",
    "pw": "Paint West",
    "paint west": "Paint West",
    "plastic west": "Paint West",
    "coating": "Paint West",
    "pc": "Paint Central",
    "paint central": "Paint Central",
    "52l": "52nd Street DC",
    "52dc": "52nd Street DC",
    "52nd": "52nd Street DC",
    "52nd street": "52nd Street DC",
    "52nd street dc": "52nd Street DC",
    "trim": "Trim DC",
    "trim dc": "Trim DC",
    "re": "Raleigh East",
    "raleigh east": "Raleigh East",
    "oem": "Raleigh East",
    "oem dock": "Raleigh East",
    "helios": "Helios",
    "quality": "Quality Hold",
    "quality hold": "Quality Hold",
    "qa": "Quality Hold",
}

PART_RE = re.compile(r"\b[A-Z]{1,5}\d[A-Z0-9-]{2,}\b", re.IGNORECASE)
QUANTITY_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:skids?|pallets?|racks?|packs?|boxes?|trailers?|pcs?|pieces?)\b", re.IGNORECASE)
TRAILER_RE = re.compile(r"\b(?:trailer|trlr|tr)\s*#?\s*([A-Z0-9-]{2,})\b", re.IGNORECASE)
PERSON_RE = re.compile(r"\b(?:both of you|all of you|[A-Z][a-z]+ [A-Z][a-z]+)\b")


def _clean(value):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or None


def _json_dump(values):
    clean_values = [str(value).strip() for value in (values or []) if str(value or "").strip()]
    return json.dumps(clean_values)


def _json_load(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _find_plants(text):
    haystack = f" {text.lower()} "
    matches = []
    for alias, label in sorted(PLANT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, haystack):
            if label not in matches:
                matches.append(label)
    return matches


def _infer_type(text, requested_type):
    selected = (requested_type or "").strip().lower()
    if selected in CAPTURE_TYPE_LABELS:
        return selected
    lower = text.lower()
    if "hot" in lower or "asap" in lower or "urgent" in lower:
        return "hot_move"
    if "empty pack" in lower or "empties" in lower:
        return "empty_pack"
    if "quality" in lower or "qa" in lower or "hold" in lower or "containment" in lower:
        return "quality_hold"
    if "no part" in lower or "delay" in lower or "full" in lower or "shutdown" in lower or "blocked" in lower:
        return "delay_no_parts"
    if "damage" in lower or "damaged" in lower:
        return "damage"
    if "trailer" in lower:
        return "trailer_request"
    if "maintenance" in lower or "broken" in lower or "not working" in lower:
        return "maintenance"
    return "general_note"


def _priority_for(text, capture_type, parser_priority):
    lower = text.lower()
    if capture_type == "hot_move":
        return "hot"
    if parser_priority and parser_priority != "normal":
        return parser_priority
    if capture_type in {"quality_hold", "damage", "maintenance"}:
        return "high"
    if any(token in lower for token in ("shutdown", "asap", "urgent", "blocked", "really full", "no parts")):
        return "high"
    return "normal"


def _missing_fields(capture_type, from_node, to_node, part_numbers, trailer_ids, quantities):
    required = {
        "hot_move": ("from plant", "to plant", "part/load"),
        "empty_pack": ("from plant", "to plant", "pack quantity"),
        "quality_hold": ("plant", "part/load"),
        "delay_no_parts": ("plant", "owner/action"),
        "damage": ("plant", "trailer/load"),
        "trailer_request": ("plant", "trailer/load"),
        "maintenance": ("truck/equipment", "owner/action"),
        "general_note": (),
    }.get(capture_type, ())
    missing = []
    for field in required:
        if field == "from plant" and not from_node:
            missing.append(field)
        elif field == "to plant" and not to_node:
            missing.append(field)
        elif field == "plant" and not (from_node or to_node):
            missing.append(field)
        elif field in {"part/load", "trailer/load"} and not (part_numbers or trailer_ids):
            missing.append(field)
        elif field == "pack quantity" and not quantities:
            missing.append(field)
        elif field == "truck/equipment" and not trailer_ids:
            missing.append(field)
        elif field == "owner/action":
            missing.append(field)
    return missing


def _capture_snapshot(capture):
    return {
        "id": capture.id,
        "tenant_id": capture.tenant_id,
        "raw_text": capture.raw_text,
        "source": capture.source,
        "captured_by": capture.captured_by,
        "captured_at": capture.captured_at,
        "guessed_type": capture.guessed_type,
        "priority": capture.priority,
        "confidence": capture.confidence,
        "extracted_from_node": capture.extracted_from_node,
        "extracted_to_node": capture.extracted_to_node,
        "extracted_part_numbers": _json_load(capture.extracted_part_numbers),
        "extracted_trailer_ids": _json_load(capture.extracted_trailer_ids),
        "extracted_quantities": _json_load(capture.extracted_quantities),
        "extracted_people": _json_load(capture.extracted_people),
        "missing_fields": _json_load(capture.missing_fields_json),
        "status": capture.status,
        "converted_entity_type": capture.converted_entity_type,
        "converted_entity_id": capture.converted_entity_id,
    }


def build_capture_fields(raw_text, requested_type=None):
    text = _clean(raw_text) or ""
    parse_result = parse_move_request_text(text)
    suggestions = parse_result.get("suggestions") or {}
    capture_type = _infer_type(text, requested_type)
    plants = _find_plants(text)
    from_node = _clean(suggestions.get("origin_location_text")) or (plants[0] if plants else None)
    to_node = _clean(suggestions.get("destination_location_text")) or (plants[1] if len(plants) > 1 else None)
    part_numbers = sorted({match.group(0).upper() for match in PART_RE.finditer(text)})
    if suggestions.get("part_number"):
        part_numbers.append(str(suggestions["part_number"]).upper())
        part_numbers = sorted(set(part_numbers))
    trailer_ids = sorted({match.group(1).upper() for match in TRAILER_RE.finditer(text)})
    quantities = sorted({match.group(0) for match in QUANTITY_RE.finditer(text)})
    if suggestions.get("quantity_text"):
        quantities.append(str(suggestions["quantity_text"]))
        quantities = sorted(set(quantities))
    people = sorted({match.group(0) for match in PERSON_RE.finditer(raw_text or "")})
    priority = _priority_for(text, capture_type, suggestions.get("priority"))
    missing = _missing_fields(capture_type, from_node, to_node, part_numbers, trailer_ids, quantities)
    confidence = parse_result.get("confidence") or ("medium" if plants or requested_type else "low")
    return {
        "raw_text": text,
        "guessed_type": capture_type,
        "priority": priority,
        "confidence": confidence,
        "extracted_from_node": from_node,
        "extracted_to_node": to_node,
        "extracted_part_numbers": part_numbers,
        "extracted_trailer_ids": trailer_ids,
        "extracted_quantities": quantities,
        "extracted_people": people,
        "missing_fields": missing,
        "status": "needs_triage" if missing else "captured",
        "parse_result": parse_result,
    }


def create_dispatch_capture(*, raw_text, capture_type=None, source="manager_dashboard", user=None, tenant_id="lacksdrivers", commit=True):
    fields = build_capture_fields(raw_text, requested_type=capture_type)
    capture = DispatchCapture(
        tenant_id=tenant_id,
        raw_text=fields["raw_text"],
        source=source or "manager_dashboard",
        captured_by=getattr(user, "id", None),
        captured_at=datetime.utcnow(),
        guessed_type=fields["guessed_type"],
        priority=fields["priority"],
        confidence=fields["confidence"],
        extracted_from_node=fields["extracted_from_node"],
        extracted_to_node=fields["extracted_to_node"],
        extracted_part_numbers=_json_dump(fields["extracted_part_numbers"]),
        extracted_trailer_ids=_json_dump(fields["extracted_trailer_ids"]),
        extracted_quantities=_json_dump(fields["extracted_quantities"]),
        extracted_people=_json_dump(fields["extracted_people"]),
        missing_fields_json=_json_dump(fields["missing_fields"]),
        status=fields["status"],
    )
    db.session.add(capture)
    db.session.flush()
    record_audit_event(
        user_id=getattr(user, "id", None),
        target_type="dispatch_capture",
        target_id=capture.id,
        action="captured",
        reason=f"Captured raw dispatch text: {capture.raw_text}",
        before_values={},
        after_values=_capture_snapshot(capture),
        commit=False,
    )
    record_activity(
        user_id=getattr(user, "id", None),
        category="dispatch_capture",
        action="captured",
        title="Dispatch capture saved",
        details=capture.raw_text,
        target_type="dispatch_capture",
        target_id=capture.id,
        commit=False,
    )
    if commit:
        db.session.commit()
    return capture


def open_dispatch_captures(limit=25):
    captures = (
        DispatchCapture.query.filter(DispatchCapture.status.in_(CAPTURE_STATUSES_OPEN))
        .order_by(DispatchCapture.captured_at.desc(), DispatchCapture.id.desc())
        .limit(limit)
        .all()
    )
    return [capture_row(capture) for capture in captures]


def capture_row(capture):
    snapshot = _capture_snapshot(capture)
    snapshot.update({
        "display_number": capture.display_number,
        "type_label": CAPTURE_TYPE_LABELS.get(capture.guessed_type, "General Note"),
        "priority_label": (capture.priority or "normal").replace("_", " ").title(),
        "status_label": (capture.status or "captured").replace("_", " ").title(),
        "captured_by_label": capture.captured_by_user.display_name if capture.captured_by_user else "Unknown",
    })
    return snapshot


def _move_request_from_capture(capture, *, request_type, user):
    part_numbers = _json_load(capture.extracted_part_numbers)
    quantities = _json_load(capture.extracted_quantities)
    cargo_text = "Empty pack return" if request_type == "empty_pack" else None
    move_request = MoveRequest(
        source="dispatch_capture",
        raw_text=capture.raw_text,
        requested_by=capture.captured_by_user.display_name if capture.captured_by_user else None,
        requested_at=capture.captured_at or datetime.utcnow(),
        request_type=request_type,
        priority=capture.priority or "normal",
        origin_location_text=capture.extracted_from_node,
        destination_location_text=capture.extracted_to_node,
        cargo_text=cargo_text or capture.raw_text,
        part_number=part_numbers[0] if part_numbers else None,
        quantity_text=quantities[0] if quantities else None,
        notes=f"Converted from {capture.display_number}. Raw capture preserved in audit.",
        status="open",
        parsed_confidence=capture.confidence,
        parse_warnings="; ".join(_json_load(capture.missing_fields_json)) or None,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.session.add(move_request)
    db.session.flush()
    move_request.request_number = move_request_number(move_request)
    FlowEventService.append_event(
        event_type="WIP_STARTED",
        entity_type="move_request",
        entity_id=move_request.id,
        actor_user_id=user.id,
        actor_role=user.role,
        origin_node_id=move_request.origin_location_text,
        destination_node_id=move_request.destination_location_text,
        source="dispatch_capture",
        payload_json={
            "dispatch_capture_id": capture.id,
            "raw_capture": capture.raw_text,
            "request_number": move_request.request_number,
            "priority": move_request.priority,
        },
        notes=f"Converted {capture.display_number} into {move_request.display_number}.",
        commit=False,
    )
    record_activity(
        user_id=user.id,
        category="move_request",
        action="created_from_capture",
        title="Move request created from dispatch capture",
        details=f"{capture.display_number}: {capture.raw_text}",
        target_type="move_request",
        target_id=move_request.id,
        commit=False,
    )
    return move_request


def convert_dispatch_capture(capture, *, entity_type, user, commit=True):
    entity_type = (entity_type or "move_request").strip().lower()
    before_values = _capture_snapshot(capture)
    converted = None

    if entity_type in {"move_request", "hot_move"}:
        converted = _move_request_from_capture(capture, request_type="move", user=user)
    elif entity_type == "empty_pack_return":
        converted = _move_request_from_capture(capture, request_type="empty_pack", user=user)
    elif entity_type == "trailer_request":
        converted = _move_request_from_capture(capture, request_type="trailer_request", user=user)
    elif entity_type == "damage_issue":
        converted = DamageReport(
            reported_by_id=user.id,
            plant_name=capture.extracted_from_node or capture.extracted_to_node or "Other",
            description=capture.raw_text,
            stage="before",
            status="open",
        )
        db.session.add(converted)
        db.session.flush()
    else:
        event_type = {
            "quality_hold": "quality_hold",
            "delay_report": "delay_no_parts",
            "maintenance_issue": "maintenance",
        }.get(entity_type, capture.guessed_type or "general_note")
        converted = ExceptionEvent(
            event_type=event_type,
            severity="high" if capture.priority in {"hot", "high", "safety"} else "medium",
            plant_name=capture.extracted_from_node or capture.extracted_to_node,
            event_date=date_cls.today(),
            target_type="dispatch_capture",
            target_id=capture.id,
            summary=CAPTURE_TYPE_LABELS.get(capture.guessed_type, "Dispatch capture"),
            details=capture.raw_text,
        )
        db.session.add(converted)
        db.session.flush()

    capture.status = "converted"
    capture.converted_entity_type = CONVERSION_LABELS.get(entity_type, "MoveRequest")
    capture.converted_entity_id = converted.id

    record_audit_event(
        user_id=user.id,
        target_type="dispatch_capture",
        target_id=capture.id,
        action="converted",
        reason=f"Converted {capture.display_number} to {capture.converted_entity_type}; raw text preserved: {capture.raw_text}",
        before_values=before_values,
        after_values=_capture_snapshot(capture),
        commit=False,
    )
    record_activity(
        user_id=user.id,
        category="dispatch_capture",
        action="converted",
        title="Dispatch capture converted",
        details=f"{capture.display_number} -> {capture.converted_entity_type} #{capture.converted_entity_id}: {capture.raw_text}",
        target_type="dispatch_capture",
        target_id=capture.id,
        commit=False,
    )
    if commit:
        db.session.commit()
    return converted


def dismiss_dispatch_capture(capture, *, user, commit=True):
    before_values = _capture_snapshot(capture)
    capture.status = "dismissed"
    record_audit_event(
        user_id=user.id,
        target_type="dispatch_capture",
        target_id=capture.id,
        action="dismissed",
        reason=f"Dismissed raw dispatch capture: {capture.raw_text}",
        before_values=before_values,
        after_values=_capture_snapshot(capture),
        commit=False,
    )
    if commit:
        db.session.commit()
    return capture
