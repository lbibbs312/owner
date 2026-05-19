from datetime import datetime
import os
import re
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    ActivityEvent,
    DriverLog,
    HotMove,
    HotPartAlert,
    HotPartEvent,
    HotPartPhoto,
    OperationalFollowUp,
    PartRouteProfile,
    PreTrip,
)
from app.services.parts import resolve_or_create_part
from app.services.plant_addresses import PLANT_LABELS, plant_label


EXCEPTION_EVENT_TYPES = {"cant_find_part", "wrong_part", "delay_reported"}
PROOF_EVENT_TYPES = {"label_scanned", "photo_added"}
COMPLETED_EVENT_TYPES = {"dropped_off"}


def _now():
    return datetime.utcnow()


def _task_status(task):
    if getattr(task, "status", None) == "completed":
        return "completed"
    if getattr(task, "status", None) == "in-progress":
        return "in_progress"
    if getattr(task, "accepted_at", None):
        return "accepted"
    return "assigned"


def _plant_code(value):
    wanted = (value or "").strip().lower()
    if not wanted:
        return ""
    for code, label in PLANT_LABELS.items():
        if wanted in {code.lower(), label.lower()}:
            return code
    return (value or "").strip()


def task_route_codes(task):
    title = (getattr(task, "title", None) or "").strip()
    match = re.match(r"^(.+?)\s+to\s+(.+)$", title, flags=re.IGNORECASE)
    if not match:
        return "", ""
    return _plant_code(match.group(1)), _plant_code(match.group(2))


def _latest_pretrip(driver_id, route_date=None):
    if not driver_id:
        return None
    query = PreTrip.query.filter(PreTrip.user_id == driver_id, PreTrip.deleted_at.is_(None))
    if route_date:
        same_day = query.filter(PreTrip.pretrip_date == route_date).order_by(PreTrip.created_at.desc()).first()
        if same_day:
            return same_day
    return query.order_by(PreTrip.pretrip_date.desc(), PreTrip.created_at.desc()).first()


def truck_id_for_driver(driver_id, route_date=None):
    pretrip = _latest_pretrip(driver_id, route_date)
    return getattr(pretrip, "truck_number", None)


def _part_for_task(task):
    part_number = (getattr(task, "part_number", None) or "").strip()
    if not part_number:
        return None, ""
    return resolve_or_create_part(part_number)


def _part_label_from(hot_move=None, task=None, raw_part_number=None):
    alert = getattr(hot_move, "alert", None)
    part = getattr(alert, "part", None) if alert else None
    return (
        getattr(part, "canonical_part_number", None)
        or getattr(alert, "raw_part_number", None)
        or raw_part_number
        or getattr(task, "part_number", None)
        or "Unlisted hot part"
    )


def _apply_task_state(hot_move, task):
    status = _task_status(task)
    if status == "completed":
        hot_move.status = "completed"
        hot_move.completed_at = hot_move.completed_at or getattr(task, "completed_at", None) or _now()
    elif hot_move.status in {"assigned", "accepted", "in_progress"}:
        hot_move.status = status
    if getattr(task, "accepted_at", None) and not hot_move.accepted_at:
        hot_move.accepted_at = task.accepted_at
    if getattr(task, "completed_at", None) and not hot_move.completed_at:
        hot_move.completed_at = task.completed_at


def ensure_hot_move_for_task(task, *, driver_id=None, truck_id=None, created_by_id=None, source="dispatch", create_event=True):
    if not task or not getattr(task, "is_hot", False):
        return None

    hot_move = HotMove.query.filter_by(move_id=task.id).order_by(HotMove.id.asc()).first()
    part, _normalized = _part_for_task(task)
    driver_id = driver_id or getattr(task, "assigned_to", None)
    if not truck_id:
        truck_id = truck_id_for_driver(driver_id)

    if hot_move is None:
        alert = HotPartAlert(
            part_id=getattr(part, "id", None),
            raw_part_number=(getattr(task, "part_number", None) or None),
            priority="hot",
            source=source,
            status="assigned" if driver_id else "active",
            created_by=created_by_id,
            created_at=_now(),
        )
        db.session.add(alert)
        db.session.flush()
        hot_move = HotMove(
            hot_part_alert_id=alert.id,
            move_id=task.id,
            driver_id=driver_id,
            truck_id=truck_id,
            status=_task_status(task),
            accepted_at=getattr(task, "accepted_at", None),
            completed_at=getattr(task, "completed_at", None),
        )
        db.session.add(hot_move)
        db.session.flush()
        if create_event:
            event = HotPartEvent(
                hot_move_id=hot_move.id,
                part_id=getattr(part, "id", None),
                event_type="alert_created",
                driver_id=driver_id,
                truck_id=truck_id,
                timestamp=_now(),
                created_offline=False,
                synced_at=_now(),
            )
            db.session.add(event)
    else:
        if driver_id and not hot_move.driver_id:
            hot_move.driver_id = driver_id
        if truck_id and not hot_move.truck_id:
            hot_move.truck_id = truck_id
        if hot_move.alert and part and not hot_move.alert.part_id:
            hot_move.alert.part_id = part.id
        if hot_move.alert and getattr(task, "part_number", None) and not hot_move.alert.raw_part_number:
            hot_move.alert.raw_part_number = task.part_number
        _apply_task_state(hot_move, task)

    return hot_move


def _event_part_id(hot_move, raw_scan_value=None, barcode_format=None):
    if raw_scan_value:
        part, _normalized = resolve_or_create_part(raw_scan_value, barcode_format)
        if part and hot_move.alert and not hot_move.alert.part_id:
            hot_move.alert.part_id = part.id
        return getattr(part, "id", None), _normalized
    alert_part = getattr(getattr(hot_move, "alert", None), "part", None)
    return getattr(alert_part, "id", None), None


def _event_sentence(event_type):
    return {
        "label_scanned": "Hot part label scanned",
        "photo_added": "Hot part photo added",
        "picked_up": "Hot part picked up",
        "dropped_off": "Hot part dropped off",
        "cant_find_part": "Driver cannot find hot part",
        "wrong_part": "Driver reported wrong part",
        "delay_reported": "Driver reported hot part delay",
        "driver_accepted": "Driver accepted hot part move",
    }.get(event_type, event_type.replace("_", " ").title())


def _route_exception(hot_move, event_type, driver_id, plant_id):
    if event_type not in EXCEPTION_EVENT_TYPES or not driver_id:
        return
    part_label = _part_label_from(hot_move)
    details = f"{_event_sentence(event_type)} for {part_label}. Dispatch review is required."
    followup = OperationalFollowUp(
        created_by_id=driver_id,
        kind="hot_part_exception",
        plant_name=plant_id,
        details=details,
        status="open",
    )
    db.session.add(followup)
    db.session.add(
        ActivityEvent(
            user_id=driver_id,
            category="exception",
            action=event_type,
            title="Hot part exception reported",
            details=details,
            target_type="hot_move",
            target_id=hot_move.id,
        )
    )


def _update_route_profile(hot_move, event_type):
    part = getattr(getattr(hot_move, "alert", None), "part", None)
    task = getattr(hot_move, "move", None)
    if not part or not task:
        return
    origin, destination = task_route_codes(task)
    if not origin and not destination:
        return

    profile = PartRouteProfile.query.filter_by(
        part_id=part.id,
        origin_plant_id=origin or None,
        destination_plant_id=destination or None,
    ).first()
    if profile is None:
        profile = PartRouteProfile(
            part_id=part.id,
            origin_plant_id=origin or None,
            destination_plant_id=destination or None,
            route_label=f"{plant_label(origin)} to {plant_label(destination)}" if origin or destination else None,
            times_completed=0,
            times_exception=0,
            confidence_score=0.0,
            status="pending",
            last_seen_at=_now(),
        )
        db.session.add(profile)

    if event_type in COMPLETED_EVENT_TYPES:
        profile.times_completed = (profile.times_completed or 0) + 1
    elif event_type in EXCEPTION_EVENT_TYPES:
        profile.times_exception = (profile.times_exception or 0) + 1

    completed = profile.times_completed or 0
    if profile.status != "confirmed":
        profile.status = "suggested" if completed >= 1 else "pending"
    if completed >= 5:
        profile.confidence_score = max(profile.confidence_score or 0.0, 0.9)
    elif completed >= 3:
        profile.confidence_score = max(profile.confidence_score or 0.0, 0.65)
    elif completed >= 1:
        profile.confidence_score = max(profile.confidence_score or 0.0, 0.3)
    profile.last_seen_at = _now()


def _apply_event_state(hot_move, event_type, timestamp):
    if event_type == "driver_accepted":
        hot_move.status = "in_progress"
        hot_move.accepted_at = hot_move.accepted_at or timestamp
        if hot_move.alert:
            hot_move.alert.status = "assigned"
    elif event_type == "picked_up":
        hot_move.status = "picked_up"
        hot_move.picked_up_at = hot_move.picked_up_at or timestamp
        if hot_move.alert:
            hot_move.alert.status = "picked_up"
    elif event_type == "dropped_off":
        hot_move.status = "dropped"
        hot_move.dropped_at = hot_move.dropped_at or timestamp
        if hot_move.alert:
            hot_move.alert.status = "dropped"
    elif event_type in EXCEPTION_EVENT_TYPES:
        hot_move.status = "exception"
        if hot_move.alert:
            hot_move.alert.status = "assigned"
    elif event_type == "cleared" and hot_move.alert:
        hot_move.alert.status = "cleared"
        hot_move.alert.cleared_at = timestamp


def record_hot_part_event(
    hot_move,
    event_type,
    *,
    driver_id=None,
    truck_id=None,
    stop_id=None,
    plant_id=None,
    raw_scan_value=None,
    barcode_format=None,
    photo_id=None,
    created_offline=False,
):
    if not hot_move:
        raise ValueError("A hot move is required.")
    event_type = (event_type or "").strip()
    if event_type == "label_scanned" and not (raw_scan_value or "").strip():
        raise ValueError("Scan the part label before saving proof.")

    timestamp = _now()
    part_id, normalized = _event_part_id(hot_move, raw_scan_value, barcode_format)
    driver_id = driver_id or hot_move.driver_id
    truck_id = truck_id or hot_move.truck_id or truck_id_for_driver(driver_id)

    event = HotPartEvent(
        hot_move_id=hot_move.id,
        part_id=part_id or getattr(getattr(hot_move, "alert", None), "part_id", None),
        event_type=event_type,
        raw_scan_value=(raw_scan_value or None),
        normalized_scan_value=normalized,
        photo_id=photo_id,
        driver_id=driver_id,
        truck_id=truck_id,
        stop_id=stop_id,
        plant_id=plant_id,
        timestamp=timestamp,
        created_offline=bool(created_offline),
        synced_at=None if created_offline else timestamp,
    )
    db.session.add(event)
    _apply_event_state(hot_move, event_type, timestamp)
    _route_exception(hot_move, event_type, driver_id, plant_id)
    _update_route_profile(hot_move, event_type)
    return event


def save_hot_part_photo(hot_move, uploaded_file, *, uploaded_by_id=None, stop_id=None, plant_id=None):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("Take or choose a photo before saving proof.")
    upload_root = current_app.config.get("HOT_PART_UPLOAD_FOLDER", "uploads/hot_part_photos")
    os.makedirs(upload_root, exist_ok=True)
    original = secure_filename(uploaded_file.filename) or "hot-part-photo"
    name, ext = os.path.splitext(original)
    filename = f"hot-part-{hot_move.id}-{_now().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext or '.jpg'}"
    uploaded_file.save(os.path.join(upload_root, filename))

    photo = HotPartPhoto(
        filename=filename,
        original_filename=original,
        content_type=getattr(uploaded_file, "mimetype", None),
        uploaded_by_id=uploaded_by_id,
        uploaded_at=_now(),
    )
    db.session.add(photo)
    db.session.flush()
    event = record_hot_part_event(
        hot_move,
        "photo_added",
        driver_id=uploaded_by_id,
        stop_id=stop_id,
        plant_id=plant_id,
        photo_id=photo.id,
    )
    return photo, event


def _status_label(status):
    return (status or "assigned").replace("_", " ").title()


def _event_types(events):
    return {event.event_type for event in events}


def _exception_text(events):
    for event in reversed(events):
        if event.event_type == "cant_find_part":
            return "Can't Find Part"
        if event.event_type == "wrong_part":
            return "Wrong Part"
        if event.event_type == "delay_reported":
            return "Delay Reported"
    return ""


def build_hot_part_narrative(hot_move=None, *, task=None, raw_part_number=None, events=None):
    events = list(events if events is not None else (getattr(hot_move, "events", []) if hot_move else []))
    types = _event_types(events)
    part_label = _part_label_from(hot_move, task, raw_part_number)

    if "cant_find_part" in types:
        return "The driver marked Can't Find Part. Dispatch review is required."
    if "wrong_part" in types:
        return "The driver marked Wrong Part. Dispatch review is required."
    if "delay_reported" in types:
        return f"The driver reported a delay for hot part {part_label}. Dispatch review is required."

    has_scan = "label_scanned" in types
    has_photo = "photo_added" in types
    picked = "picked_up" in types
    dropped = "dropped_off" in types
    accepted = "driver_accepted" in types or getattr(hot_move, "accepted_at", None)

    if not has_scan and not has_photo:
        if dropped:
            return f"Hot part {part_label} was marked dropped off, but no scan or photo proof was recorded."
        if picked:
            return f"Hot part {part_label} was marked picked up, but no scan or photo proof was recorded."
        return f"Hot part {part_label} was assigned, but no scan or photo proof was recorded."

    intro = f"Hot part {part_label} was assigned"
    if accepted:
        intro += " and accepted by the driver"
    intro += "."

    proof = "The driver scanned the part label" if has_scan else "The driver photographed the label"
    if dropped:
        return f"{intro} {proof} and marked it dropped off."
    if picked:
        return f"{intro} {proof} and marked it picked up. Drop-off has not been recorded yet."
    return f"{intro} {proof}. Pickup and drop-off have not both been recorded yet."


def build_hot_part_proof(hot_move=None, *, task=None, raw_part_number=None, events=None):
    events = sorted(
        list(events if events is not None else (getattr(hot_move, "events", []) if hot_move else [])),
        key=lambda event: (event.timestamp or datetime.min, event.id or 0),
    )
    types = _event_types(events)
    part_label = _part_label_from(hot_move, task, raw_part_number)
    scan_events = [event for event in events if event.event_type == "label_scanned"]
    photo_events = [event for event in events if event.event_type == "photo_added"]
    last_event = events[-1] if events else None
    has_proof = bool(scan_events or photo_events)

    if scan_events and "picked_up" in types:
        proof_sentence = f"Driver scanned hot part {part_label} and marked it picked up."
    elif scan_events and "dropped_off" in types:
        proof_sentence = f"Driver scanned hot part {part_label} and marked it dropped off."
    elif photo_events and "dropped_off" in types:
        proof_sentence = "Driver photographed the label and marked the hot part dropped off."
    elif photo_events and "picked_up" in types:
        proof_sentence = "Driver photographed the label and marked the hot part picked up."
    elif has_proof:
        proof_sentence = f"Proof was recorded for hot part {part_label}."
    else:
        proof_sentence = "No hot-part scan proof was recorded for this route."

    status_value = getattr(hot_move, "status", None)
    if not status_value and task:
        status_value = _task_status(task)

    return {
        "hot_move": hot_move,
        "hot_part_number": part_label,
        "current_status": _status_label(status_value),
        "has_scan_proof": bool(scan_events),
        "has_photo_proof": bool(photo_events),
        "has_any_proof": has_proof,
        "proof_sentence": proof_sentence,
        "narrative": build_hot_part_narrative(hot_move, task=task, raw_part_number=raw_part_number, events=events),
        "open_exception": _exception_text(events),
        "last_event_timestamp": getattr(last_event, "timestamp", None),
        "events": events,
        "photo_events": photo_events,
        "scan_events": scan_events,
    }


def build_route_hot_part_proof(day_logs=None, related_task=None):
    day_logs = list(day_logs or [])
    if related_task and getattr(related_task, "is_hot", False):
        hot_move = HotMove.query.filter_by(move_id=related_task.id).order_by(HotMove.id.asc()).first()
        if hot_move:
            return build_hot_part_proof(hot_move, task=related_task)
        return build_hot_part_proof(task=related_task)

    stop_ids = [log.id for log in day_logs if getattr(log, "id", None)]
    if stop_ids:
        event = (
            HotPartEvent.query
            .filter(HotPartEvent.stop_id.in_(stop_ids))
            .order_by(HotPartEvent.timestamp.desc(), HotPartEvent.id.desc())
            .first()
        )
        if event:
            return build_hot_part_proof(event.hot_move)

    hot_log = next((log for log in day_logs if getattr(log, "hot_parts", False) or getattr(log, "part_number", None)), None)
    if hot_log and getattr(hot_log, "hot_parts", False):
        return build_hot_part_proof(raw_part_number=getattr(hot_log, "part_number", None))
    return None


def hot_part_event_payload(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "label": _event_sentence(event.event_type),
        "raw_scan_value": event.raw_scan_value,
        "normalized_scan_value": event.normalized_scan_value,
        "photo_id": event.photo_id,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    }
