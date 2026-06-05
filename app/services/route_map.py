"""Route-map view models derived from real MoveDefense records.

This module builds a display contract for the driver and manager dashboards.
It does not create GPS points, telemetry, synthetic stops, or new locations.
Every node, lane, stop, and move comes from DriverLog, MoveRequest,
PlantTransfer, DamageReport, and existing route/cargo/next-action helpers.
"""
from datetime import date as date_cls, datetime, timedelta
import re

from flask import has_request_context, url_for
from sqlalchemy import or_
import pytz
from werkzeug.routing import BuildError

from app.models import DamageReport, DriverLog, MoveRequest, PartScanEvent, PlantTransfer, User
from app.services.cargo_state import cargo_state_for_log, cargo_state_for_request
from app.services.driver_wait import wait_minutes_for_log
from app.services.floor_operations import (
    ACTIVE_STATUSES,
    next_action_for_request,
    route_next_action,
)
from app.services.load_state import (
    destination_from_load,
    is_empty_load,
    is_service_stop,
    load_display,
    route_problem_reason,
    secondary_not_dropped,
    secondary_not_dropped_reason,
    service_stop_label,
)
from app.services.plant_addresses import PLANT_LABELS, plant_label
from app.services.route_context import build_route_context
from app.services.route_issues import board_badge, derive_issues
from app.models.case import ExceptionEvent


SAFE_EMPTY = "No current data"
NOT_TRACKED = "Not tracked yet"
UNKNOWN_PICKUP_SOURCE_LABEL = "Pickup source unknown"
UNKNOWN_DESTINATION_LABEL = "Destination needs confirmation"
DOCUMENT_MISSING = "Document not attached"
DETROIT_TZ = pytz.timezone("America/Detroit")
RISK_FLAGS = {
    "Damage",
    "Delay",
    "Hold",
    "Mismatch",
    "Missing proof",
    "Needs review",
    "Shortage",
}


def _clean(value):
    return str(value or "").strip()


def _target_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return date_cls.today()
    return date_cls.today()


def _day_bounds(target):
    local_start = DETROIT_TZ.localize(datetime.combine(target, datetime.min.time()))
    utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
    return utc_start, utc_start + timedelta(days=1)


def _safe_url(endpoint, **values):
    if not has_request_context():
        return None
    try:
        return url_for(endpoint, **values)
    except (BuildError, RuntimeError):
        return None


def _date_param(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date_cls):
        return value.isoformat()
    return str(value) if value else None


def _stop_audit_url(log, *, role="driver"):
    log_id = getattr(log, "id", None)
    if not log_id:
        return None
    endpoint = "manager.driver_logs" if role == "manager" else "driver.driver_logs"
    values = {"_anchor": f"route-stop-{log_id}"}
    date_param = _date_param(getattr(log, "date", None))
    if date_param:
        values["date"] = date_param
    if role == "manager" and getattr(log, "driver_id", None):
        values["driver_id"] = log.driver_id
    return _safe_url(endpoint, **values)


def _location_label(value):
    text = _clean(value)
    if not text:
        return None
    return plant_label(text) or text


def _location_key(value):
    text = _location_label(value) or "unspecified"
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unspecified"


def _short_code(value):
    text = _clean(value)
    if not text:
        return ""
    if text in PLANT_LABELS:
        return text
    for code, label in PLANT_LABELS.items():
        if label.lower() == text.lower():
            return code
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return text[:4].upper()
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(word[0] for word in words[:4]).upper()


def _status_label(status):
    status = _clean(status).replace("_", " ").strip()
    return status.title() if status else SAFE_EMPTY


def _board_badge_display(label, *, pill_tone="recorded", row_tone="completed", severity="ok"):
    label = _clean(label).upper() or "RECORDED"
    return {
        "label": label,
        "short": label,
        "pill_tone": pill_tone,
        "row_tone": row_tone,
        "severity": severity,
    }


def _first_issue_code(issues):
    for item in issues or []:
        code = item.get("code")
        if code:
            return code
    return ""


def _qa_hold_label(flags, notes=""):
    if "Hold" not in (flags or ()):
        return ""
    text = _clean(notes).lower()
    if "qa" in text or "quality" in text:
        return "HOLD · QA"
    return "HOLD"


def _stop_board_badge(log, *, movement, issues=(), evidence=None, flags=(), notes="", departed=False):
    """Display-only badge for the Home Live Flow Board.

    The ledger badge stays source/issue centric. This badge uses the same
    source facts but chooses operational labels that read like a live board.
    """
    evidence = evidence or {}
    issue_code = _first_issue_code(issues)
    issue_badge = board_badge(
        issues,
        ok_label=movement["label"],
        ok_pill_tone=movement["pill_tone"],
        ok_row_tone=movement["row_tone"],
        ok_severity=movement["severity"],
    )

    if issue_code and issue_code != "needs_departure":
        if issue_code == "hold":
            hold_label = _qa_hold_label(flags, notes) or issue_badge["short"]
            return _board_badge_display(hold_label, pill_tone="attention", row_tone="hot", severity="attention")
        return issue_badge

    if is_service_stop(log):
        if getattr(log, "maintenance", False):
            label = "DEFECT" if _clean(getattr(log, "downtime_reason", "")) else "TRUCK OK"
            tone = "risk" if label == "DEFECT" else "recorded"
            row_tone = "blocked" if label == "DEFECT" else "completed"
            severity = "risk" if label == "DEFECT" else "ok"
            return _board_badge_display(label, pill_tone=tone, row_tone=row_tone, severity=severity)
        if getattr(log, "fuel", False):
            return _board_badge_display("RECORDED", pill_tone="recorded")
        return _board_badge_display("RECORDED", pill_tone="recorded")

    if not departed:
        return _board_badge_display("OPEN", pill_tone="open", row_tone="active", severity="info")

    code = movement["code"]
    valid_scan_count = int(evidence.get("valid_scan_count") or 0)
    transfer_count = int(evidence.get("transfer_count") or 0)

    if code == "route_start":
        return _board_badge_display("STARTED", pill_tone="open", row_tone="completed", severity="info")
    if code == "no_pickup":
        return _board_badge_display("LEFT EMPTY", pill_tone="recorded")
    if code == "empty_return":
        return _board_badge_display("CLOSED", pill_tone="recorded")
    if code == "loaded":
        return _board_badge_display("IN TRANSIT", pill_tone="open", row_tone="completed", severity="info")
    if code == "in_transit":
        return _board_badge_display("IN TRANSIT", pill_tone="open", row_tone="completed", severity="info")
    if code == "dropped":
        return _board_badge_display("DELIVERED", pill_tone="delivery", row_tone="delivery", severity="ok")
    if valid_scan_count:
        return _board_badge_display("SCANNED", pill_tone="recorded", row_tone="completed", severity="ok")
    if transfer_count:
        return _board_badge_display("SHEET ATTACHED", pill_tone="recorded", row_tone="completed", severity="ok")
    return _board_badge_display("CLOSED", pill_tone="recorded", row_tone="completed", severity="ok")


def _move_board_badge(req, *, cargo=None, has_issue=False, has_damage=False):
    status = _clean(getattr(req, "status", "")).lower().replace("-", "_") or "open"
    cargo = cargo or {}
    cargo_state = cargo.get("state")
    note_text = " ".join(
        _clean(getattr(req, attr, ""))
        for attr in ("blocked_reason", "closed_reason", "notes", "parse_warnings")
    )

    if has_damage or cargo_state == "damaged":
        return _board_badge_display("DAMAGE", pill_tone="risk", row_tone="blocked", severity="risk")
    if has_issue or status in {"blocked", "needs_review"}:
        label = _qa_hold_label(("Hold",), note_text) or "HOLD"
        return _board_badge_display(label, pill_tone="attention", row_tone="hot", severity="attention")
    if status == "completed":
        if getattr(req, "linked_document_id", None) or getattr(req, "linked_plant_transfer_id", None):
            return _board_badge_display("DELIVERED", pill_tone="delivery", row_tone="delivery", severity="ok")
        return _board_badge_display("RECORDED", pill_tone="recorded", row_tone="completed", severity="ok")
    if cargo_state == "delivered":
        return _board_badge_display("DELIVERED", pill_tone="delivery", row_tone="delivery", severity="ok")
    if cargo_state in {"loaded", "onboard"}:
        linked_log = getattr(req, "linked_driver_log", None)
        if linked_log is not None and getattr(linked_log, "depart_time", None):
            return _board_badge_display("IN TRANSIT", pill_tone="open", row_tone="completed", severity="info")
        return _board_badge_display("LOADED", pill_tone="open", row_tone="active", severity="info")
    if status in {"open", "acknowledged", "assigned"}:
        return _board_badge_display("STAGED", pill_tone="open", row_tone="active", severity="info")
    return _board_badge_display("RECORDED", pill_tone="recorded", row_tone="completed", severity="ok")


def _move_board_code(req):
    request_type = _clean(getattr(req, "request_type", "")).lower()
    if "transfer" in request_type or getattr(req, "linked_plant_transfer_id", None):
        return "XFER"
    return "LOAD"


def _move_board_detail(req, *, origin, destination):
    detail_bits = []
    cargo = _clean(getattr(req, "cargo_text", ""))
    part = _clean(getattr(req, "part_number", ""))
    quantity = _quantity_text(req)
    if cargo:
        detail_bits.append(cargo)
    if part and part not in detail_bits:
        detail_bits.append(part)
    if quantity:
        detail_bits.append(quantity)
    suffix = f" · {' · '.join(detail_bits)}" if detail_bits else ""
    return f"{origin} → {destination}{suffix}"


def _line_count_label(count):
    return f"{count} line{'s' if count != 1 else ''}"


def _transfer_board_detail(transfer):
    origin = _location_label(transfer.ship_from) or NOT_TRACKED
    destination = _location_label(transfer.ship_to) or NOT_TRACKED
    lines = list(getattr(transfer, "lines", []) or [])
    skids = [value for value in (_clean(getattr(line, "skids", "")) for line in lines) if value]
    quantities = [value for value in (_clean(getattr(line, "quantity", "")) for line in lines) if value]
    parts = [value for value in (_clean(getattr(line, "part_number", "")) for line in lines) if value]
    detail_bits = []
    if skids:
        detail_bits.append(f"{', '.join(dict.fromkeys(skids))} LP")
    if quantities:
        detail_bits.append(f"{', '.join(dict.fromkeys(quantities))} pcs")
    if parts and not detail_bits:
        detail_bits.append(", ".join(dict.fromkeys(parts[:2])))
    if lines:
        detail_bits.append(_line_count_label(len(lines)))
    suffix = f" · {' · '.join(detail_bits)}" if detail_bits else ""
    return f"{origin} → {destination}{suffix}"


def _transfer_board_item(transfer):
    badge = _board_badge_display("SHEET ATTACHED", pill_tone="recorded", row_tone="completed", severity="ok")
    origin = _location_label(transfer.ship_from) or NOT_TRACKED
    destination = _location_label(transfer.ship_to) or NOT_TRACKED
    return {
        "key": f"transfer-{transfer.id}",
        "kind": "transfer",
        "code": "XFER",
        "title": transfer.transfer_number or f"Transfer {transfer.id}",
        "text": _transfer_board_detail(transfer),
        "meta": f"{origin} to {destination}",
        "board_badge": badge,
        "view_url": _safe_url("driver.view_plant_transfer", transfer_id=transfer.id),
    }


def _truck_board_item(route_pretrip, *, pending_posttrip=False):
    if not route_pretrip:
        return None
    has_defect = bool(_clean(getattr(route_pretrip, "damage_report", "")))
    if not has_defect:
        return None
    badge = _board_badge_display("DEFECT", pill_tone="risk", row_tone="blocked", severity="risk")
    text = "Pretrip defect noted"
    truck = _clean(getattr(route_pretrip, "truck_number", ""))
    trailer = _clean(getattr(route_pretrip, "trailer_number", ""))
    if truck:
        text = f"{text} · truck {truck}"
    if trailer:
        text = f"{text} · trailer {trailer}"
    return {
        "key": f"truck-{route_pretrip.id}",
        "kind": "truck",
        "code": "TRUCK",
        "title": "Vehicle inspection",
        "text": text,
        "meta": _clean(getattr(route_pretrip, "damage_report", "")) or "Inspection record on file",
        "board_badge": badge,
        "view_url": None,
    }


def _norm_key(value):
    return re.sub(r"[^a-z0-9]+", "_", _clean(value).lower()).strip("_") or "unspecified"


def _board_cargo_label(value):
    text = _clean(value)
    if not text or text == NOT_TRACKED:
        return "--"
    return load_display(text)


def _compact_cargo_label(value):
    text = _board_cargo_label(value)
    if text in {"--", NOT_TRACKED}:
        return "--"
    if is_empty_load(text):
        return "Empty"
    return "Parts"


def _cargo_destination_label(value):
    destination = destination_from_load(value)
    if not destination:
        return ""
    return plant_label(destination) or ""


def _with_route_pair(summary, *, pickup="", deliver=""):
    pickup = _clean(pickup)
    deliver = _clean(deliver)
    if pickup:
        summary["pickup"] = pickup
    if deliver:
        summary["deliver"] = deliver
    return summary


def _board_flow_summary(
    log,
    label,
    arrived_with,
    departed_with,
    route_pretrip=None,
    pickup_label=None,
    delivery_label=None,
    *,
    sequence=None,
    is_empty_return=False,
    wait_minutes=None,
    dropped_loads=(),
):
    """Compact display copy for the live board.

    Keep detailed cargo names in the underlying route model, but collapse
    plant-specific load labels in the narrow mobile board so rows read like
    actions instead of cargo arithmetic.
    """
    if is_service_stop(log):
        return {"mode": "plain", "text": _service_board_detail(log, label, route_pretrip=route_pretrip)}

    arrived = _compact_cargo_label(arrived_with)
    closed = bool(getattr(log, "depart_time", None))
    departed = _compact_cargo_label(departed_with) if closed else "--"
    no_pickup = bool(getattr(log, "no_pickup", False))
    pickup_label = _clean(pickup_label)
    delivery_label = _clean(delivery_label)
    arrived_destination = _cargo_destination_label(arrived_with)
    departed_destination = _cargo_destination_label(departed_with) if closed else ""

    wait_suffix = f" · wait {int(wait_minutes)}m" if wait_minutes else ""
    if arrived == "Empty" and not closed and sequence == 1:
        return {"mode": "plain", "text": f"{label} · route start · arrived empty{wait_suffix} · needs departure"}
    if closed and no_pickup and arrived == "Empty" and departed == "Empty":
        if sequence == 1:
            return {"mode": "plain", "text": f"{label} · route start · arrived empty"}
        if is_empty_return:
            return {"mode": "plain", "text": f"{label} · empty return"}
        return {"mode": "plain", "text": f"{label} · left empty"}
    if not closed:
        cargo_text = f" · arrived with {arrived}" if arrived != "Empty" else ""
        return {"mode": "plain", "text": f"{label}{cargo_text}{wait_suffix} · needs departure"}
    if arrived == "Empty" and departed != "Empty":
        return _with_route_pair(
            {"mode": "action", "plant": label, "action": "Picked up", "cargo": departed},
            pickup=label,
            deliver=delivery_label or departed_destination or UNKNOWN_DESTINATION_LABEL,
        )
    if arrived != "Empty" and departed == "Empty":
        return _with_route_pair(
            {"mode": "action", "plant": label, "action": "Dropped", "cargo": arrived},
            pickup=pickup_label or UNKNOWN_PICKUP_SOURCE_LABEL,
            deliver=delivery_label or label,
        )
    if dropped_loads:
        load_count = len([item for item in dropped_loads if not is_empty_load(item)])
        cargo_label = "1 load of Parts" if load_count == 1 else f"{load_count} loads of Parts"
        return _with_route_pair(
            {"mode": "action", "plant": label, "action": "Dropped", "cargo": cargo_label},
            pickup=pickup_label or UNKNOWN_PICKUP_SOURCE_LABEL,
            deliver=delivery_label or label,
        )
    if arrived == departed and arrived != "Empty":
        return _with_route_pair(
            {"mode": "action", "plant": label, "action": "Carrying", "cargo": arrived},
            pickup=pickup_label or UNKNOWN_PICKUP_SOURCE_LABEL,
            deliver=delivery_label or departed_destination or arrived_destination or UNKNOWN_DESTINATION_LABEL,
        )
    return _with_route_pair(
        {"mode": "change", "plant": label, "from": arrived, "to": departed},
        pickup=pickup_label or (label if departed != "Empty" else UNKNOWN_PICKUP_SOURCE_LABEL),
        deliver=delivery_label or departed_destination or arrived_destination or UNKNOWN_DESTINATION_LABEL,
    )


def _service_board_code(log):
    if getattr(log, "fuel", False):
        return "FUEL"
    plant_text = f"{getattr(log, 'plant_name', '')} {plant_label(getattr(log, 'plant_name', ''))}".lower()
    if "ryder" in plant_text:
        return "RYDR"
    if getattr(log, "maintenance", False):
        return "MTN"
    if getattr(log, "meeting", False):
        return "MTG"
    return "SRVC"


def _board_stop_code(log, sequence):
    if is_service_stop(log):
        return _service_board_code(log)
    return f"Stop {sequence or '?'}"


def _service_board_detail(log, label, route_pretrip=None):
    if getattr(log, "fuel", False) and getattr(log, "fuel_mileage", None) is not None:
        start_mileage = getattr(route_pretrip, "start_mileage", None)
        if start_mileage is not None:
            delta = log.fuel_mileage - start_mileage
            if delta < 0:
                return f"{log.fuel_mileage:,} mi recorded"
            return f"+{delta:,} mi from pre-trip"
        return f"{log.fuel_mileage:,} mi recorded"
    return f"{label} · {service_stop_label(log).lower()}"


def _board_stop_detail(
    log,
    label,
    arrived_with,
    departed_with,
    wait_label="",
    route_pretrip=None,
    *,
    sequence=None,
    is_empty_return=False,
):
    if is_service_stop(log):
        return _service_board_detail(log, label, route_pretrip=route_pretrip)

    arrived = _board_cargo_label(arrived_with)
    closed = bool(getattr(log, "depart_time", None))
    departed = _board_cargo_label(departed_with) if closed else "--"
    no_pickup = bool(getattr(log, "no_pickup", False))
    if arrived == "Empty" and not closed and sequence == 1:
        return f"{label} · route start · arrived empty"
    if closed and no_pickup and arrived == "Empty" and departed == "Empty":
        if sequence == 1:
            return f"{label} · route start · arrived empty"
        if is_empty_return:
            return f"{label} · empty return"
        return f"{label} · left empty"

    return f"{label} · {arrived} → {departed}"


def _stop_movement_state(
    log,
    *,
    label,
    arrived_with,
    departed_with,
    dropped_loads=(),
    added_loads=(),
    departed=False,
    sequence=None,
    is_empty_return=False,
    route_pretrip=None,
):
    """Return the source-derived semantic state for one route stop.

    This intentionally separates "route start", "no pickup", and "empty
    return". Empty return is not a synonym for arriving empty; it requires
    an empty return to the route origin after a completed delivery.
    """
    if is_service_stop(log):
        if getattr(log, "fuel", False):
            label_text = "FUELED"
            tone = "recorded"
            severity = "ok"
        else:
            label_text = "RECORDED"
            tone = "recorded"
            severity = "ok"
        detail = _service_board_detail(log, label, route_pretrip=route_pretrip)
        return {
            "code": "service",
            "label": label_text,
            "pill_tone": tone,
            "row_tone": "completed",
            "severity": severity,
            "summary": detail,
            "ledger_title": f"{label} · {service_stop_label(log)}",
            "ledger_meta": detail,
        }

    arrived = _board_cargo_label(arrived_with)
    departed_label = _board_cargo_label(departed_with) if departed else "--"
    no_pickup = bool(getattr(log, "no_pickup", False))
    arrived_empty = is_empty_load(arrived_with)
    departed_empty = is_empty_load(departed_with) if departed else False

    if not departed:
        if sequence == 1 and arrived_empty:
            return {
                "code": "route_start_open",
                "label": "OPEN",
                "pill_tone": "open",
                "row_tone": "active",
                "severity": "info",
                "summary": f"{label} · Route start · Arrived empty",
                "ledger_title": f"{label} · Route start",
                "ledger_meta": "Arrived empty · Needs departure",
            }
        return {
            "code": "open",
            "label": "OPEN",
            "pill_tone": "open",
            "row_tone": "active",
            "severity": "info",
            "summary": f"{label} · Arrived {arrived.lower() if arrived == 'Empty' else arrived}",
            "ledger_title": f"{label} · Open stop",
            "ledger_meta": f"Arrived {arrived.lower() if arrived == 'Empty' else arrived} · Needs departure",
        }

    if dropped_loads:
        return {
            "code": "dropped",
            "label": "DROPPED",
            "pill_tone": "delivery",
            "row_tone": "completed",
            "severity": "ok",
            "summary": f"{label} · Dropped {', '.join(dropped_loads)}",
            "ledger_title": f"{label} · Dropped cargo",
            "ledger_meta": f"Arrived {arrived} · Departed {departed_label if not no_pickup else 'no pickup'}",
        }
    if added_loads:
        return {
            "code": "loaded",
            "label": "LOADED",
            "pill_tone": "open",
            "row_tone": "completed",
            "severity": "info",
            "summary": f"{label} · Loaded {', '.join(added_loads)}",
            "ledger_title": f"{label} · Loaded cargo",
            "ledger_meta": f"Arrived empty · Departed {departed_label}",
        }
    if arrived_empty and departed_empty:
        if sequence == 1:
            return {
                "code": "route_start",
                "label": "ROUTE START",
                "pill_tone": "open",
                "row_tone": "completed",
                "severity": "info",
                "summary": f"{label} · Route start · Arrived empty",
                "ledger_title": f"{label} · Route start",
                "ledger_meta": "Arrived empty · Departed no pickup",
            }
        if is_empty_return:
            return {
                "code": "empty_return",
                "label": "EMPTY RETURN",
                "pill_tone": "empty",
                "row_tone": "completed",
                "severity": "ok",
                "summary": f"{label} · Empty return",
                "ledger_title": f"{label} · Empty return",
                "ledger_meta": "Arrived empty · Departed no pickup",
            }
        return {
            "code": "no_pickup",
            "label": "LEFT EMPTY",
            "pill_tone": "empty",
            "row_tone": "completed",
            "severity": "ok",
            "summary": f"{label} · Left empty",
            "ledger_title": f"{label} · No load picked up",
            "ledger_meta": "Arrived empty · Departed with no load picked up",
        }
    if not arrived_empty and departed_label == arrived:
        return {
            "code": "in_transit",
            "label": "IN TRANSIT",
            "pill_tone": "open",
            "row_tone": "completed",
            "severity": "info",
            "summary": f"{label} · Carrying {arrived}",
            "ledger_title": f"{label} · Cargo in transit",
            "ledger_meta": f"Arrived {arrived} · Departed {departed_label}",
        }
    return {
        "code": "recorded",
        "label": "RECORDED",
        "pill_tone": "recorded",
        "row_tone": "completed",
        "severity": "ok",
        "summary": f"{label} · {arrived} → {departed_label}",
        "ledger_title": f"{label} · Recorded",
        "ledger_meta": f"Arrived {arrived} · Departed {departed_label}",
    }


def _date_label(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d %I:%M%p").replace(" 0", " ").lower()
    return _clean(value)


def _driver_name(driver_id=None, driver=None):
    if driver is None and driver_id:
        driver = User.query.get(driver_id)
    if driver is None:
        return NOT_TRACKED
    return getattr(driver, "display_name", None) or getattr(driver, "username", None) or NOT_TRACKED


def _quantity_text(req):
    return _clean(getattr(req, "quantity_display", "")) or _clean(getattr(req, "quantity_text", ""))


def _request_equipment(req):
    return _clean(getattr(req, "equipment_display", "")) or NOT_TRACKED


def _linked_stop_id(req):
    return getattr(req, "linked_driver_log_id", None)


def _damage_log_ids(log_ids):
    log_ids = [log_id for log_id in log_ids if log_id]
    if not log_ids:
        return set()
    reports = DamageReport.query.filter(
        DamageReport.status != "closed",
        DamageReport.driver_log_id.in_(log_ids),
    ).all()
    return {report.driver_log_id for report in reports}


def _open_issue_request_ids(requests):
    ids = set()
    for req in requests:
        status = (req.status or "").lower()
        if status in {"blocked", "needs_review"} or _clean(req.blocked_reason):
            ids.add(req.id)
    return ids


def _request_matches_date(req, target):
    linked_log = getattr(req, "linked_driver_log", None)
    if linked_log is not None and getattr(linked_log, "date", None) == target:
        return True
    for attr in ("due_at", "requested_at", "created_at", "updated_at"):
        value = getattr(req, attr, None)
        if not value:
            continue
        value_date = value.date() if isinstance(value, datetime) else value
        if value_date == target:
            return True
    return False


def _requests_for_view(*, driver_id=None, target=None, selected_move_request_id=None):
    target = target or date_cls.today()
    start, end = _day_bounds(target)
    requests = [
        req for req in MoveRequest.query.filter(MoveRequest.status.in_(ACTIVE_STATUSES)).all()
        if _request_matches_date(req, target)
    ]
    completed_today = MoveRequest.query.filter(
        MoveRequest.status == "completed",
        MoveRequest.updated_at >= start,
        MoveRequest.updated_at < end,
    ).all()
    request_by_id = {req.id: req for req in requests + completed_today}
    if selected_move_request_id and selected_move_request_id not in request_by_id:
        selected = MoveRequest.query.get(selected_move_request_id)
        if selected:
            request_by_id[selected.id] = selected

    rows = list(request_by_id.values())
    if driver_id:
        filtered = []
        for req in rows:
            linked_log = getattr(req, "linked_driver_log", None)
            if req.assigned_driver_id == driver_id or (
                linked_log is not None and linked_log.driver_id == driver_id
            ):
                filtered.append(req)
        rows = filtered

    rows.sort(
        key=lambda req: (
            getattr(req, "due_at", None) is None,
            getattr(req, "due_at", None) or datetime.max,
            getattr(req, "requested_at", None) or datetime.min,
        )
    )
    return rows


def _transfers_for_view(*, driver_id=None, target=None):
    target = target or date_cls.today()
    query = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date == target,
    )
    if driver_id:
        query = query.filter_by(user_id=driver_id)
    return query.order_by(PlantTransfer.created_at.desc()).all()


def _plant_alias_keys(value):
    if not _clean(value):
        return set()
    keys = {_norm_key(value)}
    code = _plant_code(value)
    if code:
        keys.add(_norm_key(code))
        keys.add(_norm_key(plant_label(code) or code))
    label = _location_label(value)
    if label:
        keys.add(_norm_key(label))
    return {key for key in keys if key}


def _location_key_set(*values):
    keys = set()
    for value in values:
        keys.update(_plant_alias_keys(value))
    return {key for key in keys if key}


def _route_origin_keys(route_rows):
    for row in route_rows or []:
        log = row.get("log")
        if not log or is_service_stop(log):
            continue
        keys = _location_key_set(row.get("plant"), getattr(log, "plant_name", None))
        if keys:
            return keys
    return set()


def _matches_location_keys(keys, *values):
    return bool(keys and keys & _location_key_set(*values))


def _transfer_line_text_keys(transfer):
    keys = set()
    for line in getattr(transfer, "lines", []) or []:
        for value in (getattr(line, "part_number", None), getattr(line, "remarks", None)):
            if not _clean(value):
                continue
            key = _norm_key(value)
            if key:
                keys.add(key)
    return keys


def _transfer_proves_stop(transfer, log, *, label, dropped_loads, pickup_label="", linked_move=None):
    if linked_move is not None and getattr(linked_move, "linked_plant_transfer_id", None) == getattr(transfer, "id", None):
        return True
    if transfer.user_id != log.driver_id or transfer.transfer_date != log.date:
        return False
    if not dropped_loads:
        return False
    destination_keys = _plant_alias_keys(label) | _plant_alias_keys(log.plant_name)
    if _norm_key(transfer.ship_to) not in destination_keys and not (_plant_alias_keys(transfer.ship_to) & destination_keys):
        return False
    origin_keys = _plant_alias_keys(pickup_label)
    if origin_keys and (_plant_alias_keys(transfer.ship_from) & origin_keys):
        return True
    line_keys = _transfer_line_text_keys(transfer)
    log_part = _norm_key(getattr(log, "part_number", None)) if _clean(getattr(log, "part_number", None)) else ""
    if log_part and log_part in line_keys:
        return True
    dropped_keys = {_norm_key(load) for load in dropped_loads if _norm_key(load)}
    return bool(line_keys and dropped_keys and line_keys & dropped_keys)


def _move_view_model(req, *, damaged_log_ids=frozenset(), issue_request_ids=frozenset(), role="driver"):
    log = getattr(req, "linked_driver_log", None)
    has_damage = bool(req.linked_driver_log_id and req.linked_driver_log_id in damaged_log_ids)
    cargo = cargo_state_for_request(req, log=log, has_open_damage=has_damage)
    has_issue = req.id in issue_request_ids or has_damage
    next_action = next_action_for_request(req, has_open_issue=has_issue, cargo=cargo)
    status = (req.status or "open").lower()
    priority = (req.priority or "normal").lower()
    origin = _location_label(req.origin_location_text) or NOT_TRACKED
    destination = _location_label(req.destination_location_text) or NOT_TRACKED
    board_status_badge = _move_board_badge(req, cargo=cargo, has_issue=has_issue, has_damage=has_damage)
    edit_url = _safe_url("manager.edit_move_request", request_id=req.id)
    return {
        "move_request_id": req.id,
        "request_number": req.display_number,
        "request_type": _clean(req.request_type) or "move",
        "board_code": _move_board_code(req),
        "board_detail": _move_board_detail(req, origin=origin, destination=destination),
        "board_badge": board_status_badge,
        "raw_text": _clean(req.raw_text) or SAFE_EMPTY,
        "source": _clean(req.source) or NOT_TRACKED,
        "requested_by": _clean(req.requested_by) or NOT_TRACKED,
        "requested_at": _date_label(req.requested_at),
        "origin_location_text": origin,
        "destination_location_text": destination,
        "cargo_text": _clean(req.cargo_text) or SAFE_EMPTY,
        "part_number": _clean(req.part_number),
        "quantity_text": _quantity_text(req),
        "due_at": req.due_at,
        "due_time_text": _clean(req.due_time_text) or _date_label(req.due_at),
        "priority": priority,
        "priority_label": priority.title(),
        "status": status,
        "status_label": _status_label(status),
        "assigned_driver": _clean(req.assigned_display) or "Unassigned",
        "equipment": _request_equipment(req),
        "linked_stop_id": _linked_stop_id(req),
        "linked_route_id": _clean(req.linked_route_id),
        "linked_plant_transfer_id": req.linked_plant_transfer_id,
        "linked_document_id": req.linked_document_id,
        "document_summary": f"Document #{req.linked_document_id}" if req.linked_document_id else DOCUMENT_MISSING,
        "transfer_summary": (
            f"Plant Transfer {req.linked_plant_transfer.transfer_number or req.linked_plant_transfer_id}"
            if req.linked_plant_transfer_id and req.linked_plant_transfer
            else "No linked plant transfer"
        ),
        "cargo_status": cargo["label"],
        "has_damage": has_damage,
        "has_issue": has_issue,
        "next_action": next_action,
        "view_url": edit_url if role == "manager" else None,
        "actions": _move_actions(req, role=role, edit_url=edit_url),
    }


def _move_actions(req, *, role, edit_url=None):
    if role != "manager":
        return []
    actions = []
    status = (req.status or "open").lower()
    if status in {"open", "assigned"}:
        actions.append({
            "label": "Acknowledge",
            "url": _safe_url("manager.acknowledge_move_request", request_id=req.id),
            "method": "post",
        })
    actions.append({"label": "Assign driver", "url": edit_url, "method": "get"})
    actions.append({"label": "Start/link route", "url": edit_url, "method": "get"})
    if status != "blocked":
        actions.append({
            "label": "Mark blocked",
            "url": _safe_url("manager.mark_move_request_blocked", request_id=req.id),
            "method": "post",
        })
    if status != "completed":
        actions.append({
            "label": "Mark completed",
            "url": _safe_url("manager.mark_move_request_completed", request_id=req.id),
            "method": "post",
        })
    actions.append({"label": "Attach document", "url": edit_url, "method": "get"})
    actions.append({"label": "View audit/proof", "url": edit_url, "method": "get"})
    return actions


def _stop_actions(log, *, linked_move=None, role="driver"):
    actions = []
    view_endpoint = "manager.view_driver_log" if role == "manager" else "driver.view_driver_log"
    edit_endpoint = "driver.edit_driver_log"
    actions.append({
        "label": "Open stop",
        "url": _stop_audit_url(log, role=role) or _safe_url(view_endpoint, log_id=log.id),
        "method": "get",
    })
    if role == "driver":
        if not log.depart_time:
            actions.append({"label": "Record departure", "url": _safe_url("driver.depart_driver_log", log_id=log.id), "method": "get"})
            actions.append({"label": "Confirm cargo", "url": _safe_url("driver.pickup_driver_log", log_id=log.id), "method": "get"})
        actions.append({"label": "Add damage", "url": _safe_url("driver.new_damage_report"), "method": "get"})
        actions.append({"label": "Attach document", "url": _safe_url("driver.new_plant_transfer"), "method": "get"})
    if linked_move and role == "manager":
        actions.append({
            "label": "View linked move request",
            "url": _safe_url("manager.edit_move_request", request_id=linked_move.id),
            "method": "get",
        })
    return actions


def _stop_status(row, log, *, current_stop_id=None, has_issue=False, has_damage=False, linked_move=None, issue_severity="ok"):
    if linked_move is not None and (linked_move.status or "").lower() == "blocked":
        return "blocked"
    if has_damage or (has_issue and issue_severity == "risk"):
        return "needs_review"
    if current_stop_id and log.id == current_stop_id:
        return "active"
    if has_issue and issue_severity == "attention":
        return "active"
    if log.depart_time:
        return "completed"
    return "future"


def _stop_next_action(log, *, status, cargo, linked_move=None, issues=()):
    issue_list = list(issues or ())
    if issue_list:
        return issue_list[0].get("action") or "Open issue details"
    if status == "blocked":
        return "Resolve blocker"
    if status == "needs_review":
        return "Open issue details"
    if linked_move is not None:
        has_issue = (linked_move.status or "").lower() in {"blocked", "needs_review"}
        return next_action_for_request(linked_move, has_open_issue=has_issue)
    if not log.depart_time:
        if cargo["state"] == "unknown":
            return "Confirm cargo"
        return "Record departure"
    return "No action needed"


def _plant_code(name):
    """Resolve a plant name/label to its canonical plant code, or None."""
    n = _norm_key(name)
    if not n:
        return None
    for code, lbl in PLANT_LABELS.items():
        if _norm_key(code) == n or _norm_key(lbl) == n:
            return code
    return None


def _build_stops(route_context, *, role="driver", move_requests=None, route_pretrip=None):
    move_requests = move_requests or []
    linked_by_log = {req.linked_driver_log_id: req for req in move_requests if req.linked_driver_log_id}
    log_ids = [row["log"].id for row in getattr(route_context, "rows", []) if row.get("log")]
    damaged_log_ids = _damage_log_ids(log_ids)
    scan_events_by_log = {}
    proof_transfers = []
    if log_ids:
        _review_req = {e.stop_id for e in ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_requested",
            ExceptionEvent.stop_id.in_(log_ids),
        ).all()}
        _review_done = {e.stop_id for e in ExceptionEvent.query.filter(
            ExceptionEvent.event_type == "manager_review_resolved",
            ExceptionEvent.stop_id.in_(log_ids),
        ).all()}
        review_requested_ids = _review_req - _review_done
        scan_events = PartScanEvent.query.filter(
            or_(PartScanEvent.stop_id.in_(log_ids), PartScanEvent.driver_log_id.in_(log_ids))
        ).all()
        for event in scan_events:
            for event_log_id in {event.stop_id, event.driver_log_id}:
                if event_log_id:
                    scan_events_by_log.setdefault(event_log_id, []).append(event)
    else:
        review_requested_ids = set()
        _review_done = set()
    driver_ids = sorted({row["log"].driver_id for row in getattr(route_context, "rows", []) if row.get("log")})
    route_dates = sorted({row["log"].date for row in getattr(route_context, "rows", []) if row.get("log") and row["log"].date})
    if driver_ids and route_dates:
        proof_transfers = PlantTransfer.query.filter(
            PlantTransfer.deleted_at.is_(None),
            PlantTransfer.user_id.in_(driver_ids),
            PlantTransfer.transfer_date.in_(route_dates),
        ).all()
    true_exception_by_stop = {}
    issue_stop_ids = set()
    for item in (getattr(route_context, "true_exceptions", None) or []) + (getattr(route_context, "review_items", None) or []):
        if item.get("stop_id"):
            issue_stop_ids.add(item["stop_id"])
            true_exception_by_stop.setdefault(item["stop_id"], []).append(item)

    route_rows = list(getattr(route_context, "rows", []) or [])
    stops = []
    route_origin_keys = _route_origin_keys(route_rows)
    prior_drop_seen = False
    pending_pickup_by_cargo = {}
    current_stop_id = getattr(getattr(route_context, "current_stop", None), "id", None)
    future_removed_by_log_id = {}
    future_removed_keys = set()
    for future_row in reversed(route_rows):
        future_log = future_row.get("log")
        if future_log:
            future_removed_by_log_id[getattr(future_log, "id", None)] = set(future_removed_keys)
        for removed in future_row.get("cargo_removed") or ():
            if not is_empty_load(removed):
                future_removed_keys.add(_norm_key(load_display(removed)))

    for row in route_rows:
        log = row.get("log")
        if not log:
            continue
        label = row.get("plant") or _location_label(log.plant_name) or SAFE_EMPTY
        linked_move = linked_by_log.get(log.id)
        cargo = cargo_state_for_log(log, has_open_damage=log.id in damaged_log_ids)
        route = row.get("route") or {}
        flags = _detail_flags(log, row, route)
        has_damage = log.id in damaged_log_ids
        wait_minutes = wait_minutes_for_log(log, now=None) if not log.depart_time else (log.dock_wait_minutes or 0)
        sequence = row.get("index") or len(stops) + 1
        arrived_with = row.get("cargo_in") or log.load_size or NOT_TRACKED
        departed_with = row.get("cargo_out") or log.depart_load_size or NOT_TRACKED
        wait_label = f"{wait_minutes} min" if wait_minutes is not None else NOT_TRACKED
        departed = bool(log.depart_time)
        # --- Real drop / proof / destination evidence (not flag relabeling) ---
        dropped_loads = [load_display(it) for it in (row.get("cargo_removed") or ()) if not is_empty_load(it)]
        added_loads = [load_display(it) for it in (row.get("cargo_added") or ()) if not is_empty_load(it)]
        is_empty_return = bool(prior_drop_seen and _matches_location_keys(route_origin_keys, label, log.plant_name))
        drop_pickup_label = ""
        for dropped in dropped_loads:
            drop_pickup_label = pending_pickup_by_cargo.get(_norm_key(dropped)) or ""
            if drop_pickup_label:
                break
        movement = _stop_movement_state(
            log,
            label=label,
            arrived_with=arrived_with,
            departed_with=departed_with,
            dropped_loads=dropped_loads,
            added_loads=added_loads,
            departed=departed,
            sequence=sequence,
            is_empty_return=is_empty_return,
            route_pretrip=route_pretrip,
        )
        scan_events_for_stop = scan_events_by_log.get(log.id, [])
        review_scan_statuses = {"unexpected", "missing", "missed_drop", "needs_review", "pending_part"}
        valid_scan_count = len([
            event for event in scan_events_for_stop
            if (event.validation_status or "recorded").lower() not in review_scan_statuses
        ])
        short_scan_count = len([
            event for event in scan_events_for_stop
            if (event.validation_status or "").lower() in {"missing", "missed_drop"}
            or "short" in _clean(event.validation_message).lower()
        ])
        transfer_matches = [
            transfer for transfer in proof_transfers
            if _transfer_proves_stop(
                transfer,
                log,
                label=label,
                dropped_loads=dropped_loads,
                pickup_label=drop_pickup_label,
                linked_move=linked_move,
            )
        ]
        proof_count = (
            len(getattr(log, "photos", []) or [])
            + valid_scan_count
            + len(transfer_matches)
            + (1 if getattr(linked_move, "linked_document_id", None) else 0)
            + (1 if getattr(linked_move, "linked_plant_transfer_id", None) else 0)
        )
        driver_confirmed_drop = bool(route.get("unloaded_on_arrival") or route.get("secondary_dropped_on_arrival"))
        proof_present = bool(proof_count or driver_confirmed_drop)
        stop_code = _plant_code(log.plant_name) or _plant_code(label)
        expected_dests = []
        dest_mismatch = False
        for dropped in dropped_loads:
            dest = destination_from_load(dropped)
            if dest:
                expected_dests.append(plant_label(dest))
                if stop_code and dest != stop_code:
                    dest_mismatch = True
        drop_unconfirmed = bool(
            route.get("unload_blocked")
            or route.get("secondary_drop_blocked")
            or secondary_not_dropped(log)
        )
        # Classify an already-flagged drop by real evidence (item 3 of the spec).
        mismatch = bool(dropped_loads) and dest_mismatch
        missing_proof = bool(dropped_loads) and drop_unconfirmed and not proof_present and not mismatch
        unconfirmed_only = drop_unconfirmed and not mismatch and not missing_proof
        drop_reason = _clean(
            route.get("unload_reason")
            or route.get("secondary_drop_reason")
            or secondary_not_dropped_reason(log)
            or route_problem_reason(log)
        )
        stop_evidence = {
            "arrived_with": arrived_with,
            "departed_with": departed_with,
            "dropped": dropped_loads,
            "load": ", ".join(dict.fromkeys(dropped_loads)) or None,
            "picked_up": added_loads,
            "expected_destination": ", ".join(dict.fromkeys(expected_dests)) or None,
            "actual_stop": label,
            "action_needed": "Confirm destination or send to manager review" if mismatch else None,
            "proof": "Attached" if proof_present else "None on file",
            "proof_count": proof_count,
            "scan_count": len(scan_events_for_stop),
            "valid_scan_count": valid_scan_count,
            "transfer_count": len(transfer_matches),
            "driver_confirmation": "Drop confirmed" if driver_confirmed_drop else "No drop confirmation",
            "reason": drop_reason or None,
        }
        stop_issues = derive_issues(
            flags,
            has_damage=has_damage,
            departed=departed,
            wait_minutes=wait_minutes,
            unconfirmed_drop=unconfirmed_only,
            destination_mismatch=mismatch,
            missing_proof=missing_proof,
            needs_departure=not departed and log.id == current_stop_id,
            review_requested=log.id in review_requested_ids,
            evidence=stop_evidence,
            extra_codes=("count_short",) if short_scan_count else (),
        )
        missing_departure_items = [
            item for item in true_exception_by_stop.get(log.id, [])
            if _clean(item.get("label")).lower() == "missing departure"
        ]
        if missing_departure_items and log.id != current_stop_id:
            detail = _clean(missing_departure_items[0].get("detail"))
            stop_issues.insert(0, {
                "code": "missing_departure_sequence",
                "label": "MISSING DEPARTURE",
                "severity": "risk",
                "reason": detail or "This stop is still open even though a later stop exists.",
                "action": "Record departure or send to manager review",
                "evidence": dict(stop_evidence, route_context_exception=detail or None),
                "resolved": False,
            })
        is_review_closed = log.id in _review_done
        if is_review_closed:
            stop_issues = []
        has_issue = bool(stop_issues)
        active_damage_blocker = has_damage and not is_review_closed
        issue_severity = "risk" if any(item.get("severity") == "risk" for item in stop_issues) else ("attention" if stop_issues else "ok")
        status = _stop_status(
            row,
            log,
            current_stop_id=current_stop_id,
            has_issue=has_issue,
            has_damage=active_damage_blocker,
            linked_move=linked_move,
            issue_severity=issue_severity,
        )
        stop_badge = board_badge(
            stop_issues,
            ok_label=movement["label"],
            ok_pill_tone=movement["pill_tone"],
            ok_row_tone=movement["row_tone"],
            ok_severity=movement["severity"],
        )
        board_status_badge = _stop_board_badge(
            log,
            movement=movement,
            issues=stop_issues,
            evidence=stop_evidence,
            flags=flags,
            notes=f"{row.get('note') or ''} {getattr(log, 'downtime_reason', '') or ''}",
            departed=departed,
        )
        added_load_keys = {
            _norm_key(load_display(load))
            for load in added_loads
            if not is_empty_load(load)
        }
        if (
            movement["code"] == "loaded"
            and added_load_keys
            and added_load_keys.issubset(future_removed_by_log_id.get(log.id, set()))
        ):
            board_status_badge = _board_badge_display("DELIVERED", pill_tone="delivery", row_tone="delivery", severity="ok")
        stops.append({
            "stop_id": log.id,
            "sequence": sequence,
            "plant_name": label,
            "short_code": _short_code(log.plant_name or label),
            "board_code": _board_stop_code(log, sequence),
            "board_detail": _board_stop_detail(
                log,
                label,
                arrived_with,
                departed_with,
                wait_label=wait_label,
                route_pretrip=route_pretrip,
                sequence=sequence,
                is_empty_return=is_empty_return,
            ),
            "board_flow": _board_flow_summary(
                log,
                label,
                arrived_with,
                departed_with,
                route_pretrip=route_pretrip,
                sequence=sequence,
                is_empty_return=is_empty_return,
                wait_minutes=wait_minutes,
                pickup_label=drop_pickup_label,
                delivery_label=label if dropped_loads else "",
                dropped_loads=dropped_loads,
            ),
            "movement_code": movement["code"],
            "movement_label": movement["label"],
            "movement_summary": movement["summary"],
            "ledger_title": movement["ledger_title"],
            "ledger_meta": movement["ledger_meta"],
            "status": status,
            "status_label": _status_label(status),
            "arrival_at": log.arrive_time or "",
            "departure_at": log.depart_time or "",
            "wait_minutes": wait_minutes,
            "wait_label": wait_label,
            "arrived_with": arrived_with,
            "departed_with": departed_with,
            "requires_unload_check": bool(route.get("arrived_at_primary_destination") and not is_service_stop(log)),
            "requires_secondary_drop_check": bool(route.get("arrived_at_secondary_destination") and not is_service_stop(log)),
            "no_pickup": bool(getattr(log, "no_pickup", False)),
            "cargo_status": cargo["label"],
            "linked_move_request_id": getattr(linked_move, "id", None),
            "linked_move_request_number": getattr(linked_move, "display_number", None),
            "linked_plant_transfer_id": getattr(linked_move, "linked_plant_transfer_id", None),
            "linked_document_id": getattr(linked_move, "linked_document_id", None),
            "document_summary": (
                f"Document #{linked_move.linked_document_id}"
                if linked_move is not None and linked_move.linked_document_id
                else DOCUMENT_MISSING
            ),
            "has_damage": has_damage,
            "has_issue": has_issue,
            "flags": flags,
            "issues": stop_issues,
            "evidence": stop_evidence,
            "badge": stop_badge,
            "board_badge": board_status_badge,
            "notes": row.get("note") or "",
            "next_action": _stop_next_action(log, status=status, cargo=cargo, linked_move=linked_move, issues=stop_issues),
            "view_url": _stop_audit_url(log, role=role)
            or _safe_url("manager.view_driver_log" if role == "manager" else "driver.view_driver_log", log_id=log.id),
            "actions": _stop_actions(log, linked_move=linked_move, role=role),
        })
        for added in added_loads:
            pending_pickup_by_cargo[_norm_key(added)] = label
        if dropped_loads:
            prior_drop_seen = True
    return stops


def _detail_flags(log, row, route):
    text = " ".join(
        _clean(value)
        for value in (
            getattr(log, "downtime_reason", ""),
            row.get("note"),
            " ".join(route.get("warnings") or []),
        )
    ).lower()
    flags = []
    if getattr(log, "hot_parts", False):
        flags.append("Hot")
    if getattr(log, "no_pickup", False):
        flags.append("No pickup")
    if "hold" in text or "held" in text or "blocked" in text:
        flags.append("Hold")
    if "damage" in text or "damaged" in text:
        flags.append("Damage")
    if "missing proof" in text or "missing document" in text or "proof missing" in text:
        flags.append("Missing proof")
    if "mismatch" in text or "wrong plant" in text or "wrong trailer" in text or "wrong load" in text:
        flags.append("Mismatch")
    if "shortage" in text or "short " in f"{text} " or "shorted" in text:
        flags.append("Shortage")
    if "delay" in text or "delayed" in text or "late" in text:
        flags.append("Delay")
    if "scrap" in text:
        flags.append("Scrap")
    if route.get("unload_blocked") or route.get("secondary_drop_blocked"):
        flags.append("Needs review")
    if getattr(log, "maintenance", False):
        flags.append("Maintenance")
    if getattr(log, "fuel", False):
        flags.append("Fuel")
    if getattr(log, "meeting", False):
        flags.append("Meeting")
    return tuple(dict.fromkeys(flags))


def _part_labels(log, *extra_parts):
    labels = []
    part = _clean(getattr(log, "part_number", ""))
    if part:
        labels.append(f"HOT {part}" if getattr(log, "hot_parts", False) else part)
    elif getattr(log, "hot_parts", False):
        labels.append("Hot part")
    for item in extra_parts:
        text = _clean(item)
        if text and text not in labels:
            labels.append(text)
    return labels


def _delivery_destination(load_label, fallback_plant):
    destination = destination_from_load(load_label)
    if destination:
        return plant_label(destination), destination
    return UNKNOWN_DESTINATION_LABEL, "destination-needs-confirmation"


def _load_count_label(count):
    return f"{count} load{'s' if count != 1 else ''}"


def _stop_count_label(count):
    return f"{count} stop{'s' if count != 1 else ''}"


def _new_narrative_group(kind, *, title, route_line, board_detail=None, origin_label=None, destination_label=None):
    return {
        "key": _norm_key(f"{kind}:{title}:{origin_label}:{destination_label}"),
        "kind": kind,
        "tone": "empty" if kind == "empty" else ("delivery" if kind == "delivery" else "pickup"),
        "title": title,
        "route_line": route_line,
        "board_detail": board_detail or route_line,
        "origin_label": origin_label,
        "destination_label": destination_label,
        "count": 0,
        "load_count_label": "",
        "stop_count_label": "",
        "parts": [],
        "flags": [],
        "details": [],
        "latest_departure_at": "",
    }


def _add_narrative_detail(groups, key, group, detail):
    if key not in groups:
        groups[key] = group
    target = groups[key]
    target["count"] += 1
    target["load_count_label"] = _load_count_label(target["count"])
    target["stop_count_label"] = _stop_count_label(len(target["details"]) + 1)
    target["latest_departure_at"] = detail.get("departure_at") or target["latest_departure_at"]
    for part in detail.get("parts") or []:
        if part not in target["parts"]:
            target["parts"].append(part)
    for flag in detail.get("flags") or []:
        if flag not in target["flags"]:
            target["flags"].append(flag)
        if flag in RISK_FLAGS:
            target["tone"] = "blocked"
        elif flag == "Hot" and target.get("tone") != "blocked":
            target["tone"] = "hot"
    target["details"].append(detail)


def _base_stop_detail(log, row, route, *, cargo_label, pickup=None, is_empty_return=False):
    flags = list(_detail_flags(log, row, route))
    parts = _part_labels(log, *((pickup or {}).get("parts") or ()))
    wait_minutes = wait_minutes_for_log(log, now=None) if not getattr(log, "depart_time", None) else (getattr(log, "dock_wait_minutes", None) or 0)
    wait_label = f"Wait {wait_minutes} min" if wait_minutes else ""
    pickup_label = ""
    if pickup:
        pickup_label = f"Picked up at {pickup['plant_label']}"
        if pickup.get("departure_at"):
            pickup_label = f"{pickup_label} before stop {row.get('index')}"
        for flag in pickup.get("flags") or []:
            if flag not in flags:
                flags.append(flag)
    return {
        "stop_id": getattr(log, "id", None),
        "sequence": row.get("index"),
        "board_code": _board_stop_code(log, row.get("index")),
        "board_detail": _board_stop_detail(
            log,
            row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
            row.get("cargo_in") or route.get("arrive_cargo_desc") or load_display(getattr(log, "load_size", "")),
            row.get("cargo_out") or route.get("depart_cargo_desc") or load_display(getattr(log, "depart_load_size", "")),
            wait_label=wait_label.replace("Wait ", "", 1) if wait_label else "",
            sequence=row.get("index"),
            is_empty_return=is_empty_return,
        ),
        "board_flow": _board_flow_summary(
            log,
            row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
            row.get("cargo_in") or route.get("arrive_cargo_desc") or load_display(getattr(log, "load_size", "")),
            row.get("cargo_out") or route.get("depart_cargo_desc") or load_display(getattr(log, "depart_load_size", "")),
            pickup_label=(pickup or {}).get("plant_label"),
            sequence=row.get("index"),
            is_empty_return=is_empty_return,
            wait_minutes=wait_minutes,
        ),
        "plant": row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
        "arrival_at": getattr(log, "arrive_time", ""),
        "departure_at": getattr(log, "depart_time", ""),
        "cargo_label": cargo_label,
        "arrived_with": row.get("cargo_in") or route.get("arrive_cargo_desc") or load_display(getattr(log, "load_size", "")),
        "departed_with": row.get("cargo_out") or route.get("depart_cargo_desc") or load_display(getattr(log, "depart_load_size", "")),
        "no_pickup": bool(getattr(log, "no_pickup", False)),
        "parts": parts,
        "flags": tuple(dict.fromkeys(flags)),
        "wait_label": wait_label,
        "note": row.get("note") or "",
        "pickup_label": pickup_label,
        "view_url": _stop_audit_url(log)
        or _safe_url("driver.view_driver_log", log_id=getattr(log, "id", None)),
    }


def _pickup_info(log, row, route, cargo_label):
    return {
        "plant_label": row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY,
        "stop_id": getattr(log, "id", None),
        "sequence": row.get("index"),
        "departure_at": getattr(log, "depart_time", ""),
        "parts": _part_labels(log),
        "flags": _detail_flags(log, row, route),
        "cargo_label": cargo_label,
    }


def _build_delivery_narratives(route_context):
    """Aggregate completed route work into readable delivery and empty-load cards."""
    groups = {}
    pending_by_cargo = {}
    pending_by_destination = {}
    route_rows = list(getattr(route_context, "rows", []) or [])
    route_origin_keys = _route_origin_keys(route_rows)
    prior_drop_seen = False

    for row in route_rows:
        log = row.get("log")
        route = row.get("route") or {}
        if not log or not getattr(log, "depart_time", None):
            continue

        plant_label_text = row.get("plant") or plant_label(getattr(log, "plant_name", None)) or SAFE_EMPTY
        removed = [load_display(item) for item in row.get("cargo_removed") or () if not is_empty_load(item)]
        added = [load_display(item) for item in row.get("cargo_added") or () if not is_empty_load(item)]
        is_empty_return = bool(
            prior_drop_seen
            and _matches_location_keys(route_origin_keys, plant_label_text, getattr(log, "plant_name", None))
        )

        for cargo_label in removed:
            cargo_key = _norm_key(cargo_label)
            destination_label, destination_key = _delivery_destination(cargo_label, plant_label_text)
            pickup = pending_by_cargo.pop(cargo_key, None)
            if pickup and pending_by_destination.get(destination_key) is pickup:
                pending_by_destination.pop(destination_key, None)
            if pickup is None:
                pickup = pending_by_destination.pop(destination_key, None)
            origin_label = (pickup or {}).get("plant_label") or UNKNOWN_PICKUP_SOURCE_LABEL
            key = _norm_key(f"delivery:{origin_label}:{destination_label}")
            group = _new_narrative_group(
                "delivery",
                title=f"{destination_label} delivery from {origin_label}",
                route_line=f"{cargo_label} delivered from {origin_label} to {destination_label}",
                board_detail=f"{origin_label} → {destination_label} · {cargo_label}",
                origin_label=origin_label,
                destination_label=destination_label,
            )
            detail = _base_stop_detail(log, row, route, cargo_label=cargo_label, pickup=pickup)
            _add_narrative_detail(groups, key, group, detail)

        arrived_empty = is_empty_load(row.get("cargo_in")) or is_empty_load(route.get("arrive_cargo_desc")) or is_empty_load(getattr(log, "load_size", None))
        departed_empty = is_empty_load(row.get("cargo_out")) or is_empty_load(route.get("depart_cargo_desc")) or is_empty_load(getattr(log, "depart_load_size", None))
        if not removed and not added and arrived_empty and departed_empty and is_empty_return:
            key = _norm_key(f"empty:{plant_label_text}")
            group = _new_narrative_group(
                "empty",
                title=f"{plant_label_text} empty load",
                route_line=f"Arrived empty and departed empty at {plant_label_text}",
                board_detail=f"{plant_label_text} · empty return",
                destination_label=plant_label_text,
            )
            detail = _base_stop_detail(log, row, route, cargo_label="Empty load", is_empty_return=True)
            _add_narrative_detail(groups, key, group, detail)

        for cargo_label in added:
            destination_label, destination_key = _delivery_destination(cargo_label, plant_label_text)
            info = _pickup_info(log, row, route, cargo_label)
            pending_by_cargo[_norm_key(cargo_label)] = info
            pending_by_destination[destination_key] = info

        if removed:
            prior_drop_seen = True

    for group in groups.values():
        narrative_issues = [
            issue
            for issue in derive_issues(group.get("flags") or ())
            if issue.get("code") != "needs_departure"
        ]
        group["issues"] = narrative_issues
        group["badge"] = board_badge(
            narrative_issues,
            ok_label="EMPTY RETURN" if group.get("kind") == "empty" else "RECORDED",
            ok_pill_tone="empty" if group.get("kind") == "empty" else "recorded",
            ok_row_tone="empty" if group.get("kind") == "empty" else ("delivery" if group.get("kind") == "delivery" else "completed"),
        )
        group["board_badge"] = board_badge(
            narrative_issues,
            ok_label="CLOSED" if group.get("kind") == "empty" else "DELIVERED",
            ok_pill_tone="recorded" if group.get("kind") == "empty" else "delivery",
            ok_row_tone="completed" if group.get("kind") == "empty" else ("delivery" if group.get("kind") == "delivery" else "completed"),
        )

    return sorted(
        groups.values(),
        key=lambda item: (
            item.get("count") or 0,
            item.get("kind") == "delivery",
            item.get("latest_departure_at") or "",
        ),
        reverse=True,
    )


def _move_board_item(move):
    badge = move.get("board_badge") or _board_badge_display("RECORDED")
    return {
        "key": f"move-{move.get('move_request_id')}",
        "kind": "move",
        "code": move.get("board_code") or "LOAD",
        "title": move.get("request_number") or "Move request",
        "text": move.get("board_detail") or move.get("raw_text") or SAFE_EMPTY,
        "meta": move.get("raw_text") or move.get("next_action") or "",
        "board_badge": badge,
        "view_url": move.get("view_url"),
    }


def _ops_board_items(moves, transfers, *, route_pretrip=None, pending_posttrip=False):
    items = []
    linked_transfer_ids = {move.get("linked_plant_transfer_id") for move in moves if move.get("linked_plant_transfer_id")}
    for move in moves:
        items.append(_move_board_item(move))
    for transfer in transfers:
        if transfer.id in linked_transfer_ids:
            continue
        items.append(_transfer_board_item(transfer))
    truck_item = _truck_board_item(route_pretrip, pending_posttrip=pending_posttrip)
    if truck_item:
        items.append(truck_item)
    return items


def _plant_seed(plants, label, *, role="driver"):
    label = _location_label(label)
    if not label:
        return None
    key = _location_key(label)
    if key not in plants:
        plants[key] = {
            "plant_key": key,
            "label": label,
            "short_code": _short_code(label),
            "active_stop_count": 0,
            "open_request_count": 0,
            "blocked_count": 0,
            "waiting_count": 0,
            "completed_today_count": 0,
            "related_move_request_ids": [],
            "related_stop_ids": [],
            "related_plant_transfer_ids": [],
            "worst_status": "none",
            "move_queue_url": _safe_url("manager.move_requests", location=label) if role == "manager" else None,
            "active_moves_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes") if role == "manager" else None,
            "timing_url": _safe_url("manager.manager_dashboard", plant=label, focus="routes") if role == "manager" else None,
        }
    return plants[key]


def _lane_seed(lanes, origin, destination, *, role="driver"):
    origin = _location_label(origin)
    destination = _location_label(destination)
    if not origin or not destination:
        return None
    origin_key = _location_key(origin)
    destination_key = _location_key(destination)
    key = (origin_key, destination_key)
    if key not in lanes:
        lanes[key] = {
            "origin_key": origin_key,
            "destination_key": destination_key,
            "origin_label": origin,
            "destination_label": destination,
            "status": "none",
            "open_count": 0,
            "active_count": 0,
            "completed_count": 0,
            "blocked_count": 0,
            "linked_move_request_ids": [],
            "linked_stop_ids": [],
            "linked_plant_transfer_ids": [],
            "view_url": _safe_url("manager.move_requests", origin=origin, destination=destination) if role == "manager" else None,
        }
    return lanes[key]


def _worst_status(*, blocked=0, waiting=0, active=0, open_=0, completed=0):
    if blocked:
        return "blocked"
    if waiting:
        return "waiting"
    if active:
        return "active"
    if open_:
        return "open"
    if completed:
        return "completed"
    return "none"


def _build_plants_and_lanes(stops, moves, transfers, *, role="driver"):
    plants = {}
    lanes = {}

    for stop in stops:
        plant = _plant_seed(plants, stop["plant_name"], role=role)
        if not plant:
            continue
        plant["related_stop_ids"].append(stop["stop_id"])
        if stop["status"] == "completed":
            plant["completed_today_count"] += 1
        elif stop["status"] == "blocked":
            plant["blocked_count"] += 1
            plant["active_stop_count"] += 1
        elif stop["status"] == "needs_review":
            plant["blocked_count"] += 1
            plant["active_stop_count"] += 1
        elif stop["status"] == "active":
            plant["active_stop_count"] += 1
            plant["waiting_count"] += 1

    for prev, nxt in zip(stops, stops[1:]):
        lane = _lane_seed(lanes, prev["plant_name"], nxt["plant_name"], role=role)
        if not lane:
            continue
        lane["linked_stop_ids"].extend([prev["stop_id"], nxt["stop_id"]])
        if nxt["status"] in {"active", "needs_review"}:
            lane["active_count"] += 1
        elif nxt["status"] == "blocked":
            lane["blocked_count"] += 1
        elif nxt["status"] == "completed":
            lane["completed_count"] += 1
        else:
            lane["open_count"] += 1

    for move in moves:
        origin = _plant_seed(plants, move["origin_location_text"], role=role)
        destination = _plant_seed(plants, move["destination_location_text"], role=role)
        for plant in (origin, destination):
            if not plant:
                continue
            plant["related_move_request_ids"].append(move["move_request_id"])
            if move["status"] == "completed":
                plant["completed_today_count"] += 1
            else:
                plant["open_request_count"] += 1
            if move["status"] == "blocked" or move["has_issue"]:
                plant["blocked_count"] += 1
            if move["status"] in {"assigned", "in_progress", "waiting"}:
                plant["active_stop_count"] += 1
            if move["status"] == "waiting":
                plant["waiting_count"] += 1

        lane = _lane_seed(lanes, move["origin_location_text"], move["destination_location_text"], role=role)
        if lane:
            lane["linked_move_request_ids"].append(move["move_request_id"])
            if move["status"] == "completed":
                lane["completed_count"] += 1
            elif move["status"] == "blocked" or move["has_issue"]:
                lane["blocked_count"] += 1
            elif move["status"] in {"assigned", "in_progress", "waiting"}:
                lane["active_count"] += 1
            else:
                lane["open_count"] += 1

    for transfer in transfers:
        origin = _plant_seed(plants, transfer.ship_from, role=role)
        destination = _plant_seed(plants, transfer.ship_to, role=role)
        for plant in (origin, destination):
            if plant:
                plant["related_plant_transfer_ids"].append(transfer.id)
                plant["completed_today_count"] += 1
        lane = _lane_seed(lanes, transfer.ship_from, transfer.ship_to, role=role)
        if lane:
            lane["linked_plant_transfer_ids"].append(transfer.id)
            lane["completed_count"] += 1

    for plant in plants.values():
        plant["related_move_request_ids"] = sorted(set(plant["related_move_request_ids"]))
        plant["related_stop_ids"] = sorted(set(plant["related_stop_ids"]))
        plant["related_plant_transfer_ids"] = sorted(set(plant["related_plant_transfer_ids"]))
        plant["worst_status"] = _worst_status(
            blocked=plant["blocked_count"],
            waiting=plant["waiting_count"],
            active=plant["active_stop_count"],
            open_=plant["open_request_count"],
            completed=plant["completed_today_count"],
        )

    for lane in lanes.values():
        lane["linked_move_request_ids"] = sorted(set(lane["linked_move_request_ids"]))
        lane["linked_stop_ids"] = sorted(set(lane["linked_stop_ids"]))
        lane["linked_plant_transfer_ids"] = sorted(set(lane["linked_plant_transfer_ids"]))
        lane["status"] = _worst_status(
            blocked=lane["blocked_count"],
            active=lane["active_count"],
            open_=lane["open_count"],
            completed=lane["completed_count"],
        )

    return (
        sorted(plants.values(), key=lambda p: (-p["active_stop_count"], -p["open_request_count"], p["label"])),
        sorted(lanes.values(), key=lambda l: (-(l["open_count"] + l["active_count"] + l["completed_count"]), l["origin_label"], l["destination_label"])),
    )


def _route_summary(route_context, *, moves, stops, driver=None):
    current_stop = getattr(route_context, "current_stop", None)
    current_stop_id = getattr(current_stop, "id", None)
    current_location = (
        plant_label(current_stop.plant_name)
        if current_stop is not None
        else (stops[-1]["plant_name"] if stops else SAFE_EMPTY)
    )
    issue_count = len([s for s in stops if s["has_issue"] or s["has_damage"]]) + len([m for m in moves if m["has_issue"] or m["has_damage"]])
    document_needed = len([m for m in moves if not m["linked_document_id"] and not m["linked_plant_transfer_id"]])
    next_action = route_next_action(
        route_context,
        has_high_issue=bool(issue_count),
        missing_document=bool(document_needed and stops),
    )
    return {
        "route_id": getattr(route_context, "route_id", None),
        "driver_name": _driver_name(getattr(route_context, "driver_id", None), driver=driver),
        "truck": getattr(route_context, "truck_id", None) or NOT_TRACKED,
        "equipment": getattr(route_context, "truck_id", None) or NOT_TRACKED,
        "status": getattr(route_context, "route_status", None) or ("active" if stops else "no_route"),
        "current_stop_id": current_stop_id,
        "current_location": current_location,
        "next_action": next_action,
        "issue_summary": f"{issue_count} issue{'s' if issue_count != 1 else ''}" if issue_count else "No open issues",
        "document_summary": f"{document_needed} document needed" if document_needed else "Documents current",
    }


def _dispatch_issue_message(stop, issue):
    label = issue.get("label") or "REVIEW"
    code = issue.get("code") or ""
    evidence = stop.get("evidence") or {}
    affected = ", ".join(evidence.get("dropped") or []) or stop.get("plant_name") or SAFE_EMPTY
    plant = stop.get("plant_name") or SAFE_EMPTY
    if code == "destination_mismatch":
        text = f"{label} · {affected} destination needs review"
    elif code == "count_short":
        valid = evidence.get("valid_scan_count")
        total = evidence.get("scan_count")
        scan_text = f"{valid} valid / {total} scanned" if total is not None and valid is not None else affected
        text = f"{label} · {scan_text}"
    elif code == "damage":
        text = f"{label} · {plant}"
    elif code == "hold":
        text = f"{label} · {plant}"
    elif code == "needs_departure":
        text = f"{label} · {plant}"
    else:
        text = f"{label} · {affected}"
    return {
        "label": label,
        "text": text,
        "severity": issue.get("severity") or "attention",
        "source": "stop",
        "stop_id": stop.get("stop_id"),
        "code": code,
    }


def _dispatch_messages(stops, moves):
    """Build the live dispatch ticker from real issue and dispatch signals."""
    messages = []
    for stop in stops:
        for issue_item in stop.get("issues") or []:
            if issue_item.get("code") == "needs_departure":
                continue
            messages.append(_dispatch_issue_message(stop, issue_item))
        if "Hot" in (stop.get("flags") or ()):
            messages.append({
                "label": "HOT PARTS",
                "text": f"HOT PARTS · {stop.get('plant_name') or SAFE_EMPTY}",
                "severity": "attention",
                "source": "stop",
                "stop_id": stop.get("stop_id"),
                "code": "hot_parts",
            })

    for move in moves:
        lane = f"{move.get('origin_location_text') or SAFE_EMPTY} → {move.get('destination_location_text') or SAFE_EMPTY}"
        priority = (move.get("priority") or "").lower()
        status = (move.get("status") or "").lower()
        if priority in {"hot", "safety"}:
            messages.append({
                "label": "HOT PARTS",
                "text": f"HOT PARTS · {lane}",
                "severity": "attention",
                "source": "move",
                "move_request_id": move.get("move_request_id"),
                "code": "hot_parts",
            })
        if status in {"blocked", "needs_review", "waiting"} or move.get("has_issue"):
            messages.append({
                "label": "HOLD",
                "text": f"HOLD · {lane}",
                "severity": "attention",
                "source": "move",
                "move_request_id": move.get("move_request_id"),
                "code": "hold",
            })

    severity_order = {"risk": 0, "attention": 1, "info": 2, "ok": 3}
    code_order = {
        "missing_proof": 0,
        "destination_mismatch": 1,
        "count_short": 2,
        "damage": 3,
        "unconfirmed_drop": 4,
        "hold": 5,
        "hot_parts": 6,
        "needs_departure": 7,
    }
    unique = []
    seen = set()
    for message in sorted(
        messages,
        key=lambda item: (
            severity_order.get(item.get("severity"), 9),
            code_order.get(item.get("code"), 99),
            item.get("text") or "",
        ),
    ):
        key = message.get("text")
        if key in seen:
            continue
        seen.add(key)
        unique.append(message)
    if not unique:
        return [{"label": "NO ALERTS", "text": "NO ALERTS FROM DISPATCH", "severity": "ok", "source": "none", "code": "none"}]
    return unique


def _cta_pulse(route_context, stops, *, proof_missing=False, pending_posttrip=False):
    """Return the one primary workflow CTA that should pulse.

    CAMERA pulses ONLY for a genuine proof issue on a stop (missing_proof /
    unconfirmed_drop / damage) -- never as a blanket "departed today without a
    transfer" nudge, and never as a catch-all for unmapped issues. ``proof_missing``
    is accepted for call-site compatibility but no longer forces a camera pulse.
    """
    # Map issue codes to the concrete next action. Codes not listed here
    # (hot, review_requested, audit_risk, route_deviation, ...) do NOT force a
    # CTA pulse -- they fall through to the route-state defaults below.
    issue_action = {
        "missing_proof": "camera",
        "unconfirmed_drop": "camera",
        "damage": "camera",
        "destination_mismatch": "transfer",
        "count_short": "transfer",
        "hold": "transfer",
        "needs_departure": "depart",
        "open_wait": "depart",
    }
    issues_by_severity = sorted(
        (
            (stop, issue_item)
            for stop in stops
            for issue_item in (stop.get("issues") or [])
        ),
        key=lambda item: 0 if item[1].get("severity") == "risk" else 1,
    )
    for stop, issue_item in issues_by_severity:
        key = issue_action.get(issue_item.get("code"))
        if not key:
            continue
        return {
            "key": key,
            "reason": issue_item.get("label") or issue_item.get("reason") or "Issue requires action",
            "severity": issue_item.get("severity") or "attention",
            "issue_code": issue_item.get("code"),
            "stop_id": stop.get("stop_id"),
        }

    current = getattr(route_context, "current_stop", None)
    if current is not None and not getattr(current, "depart_time", None):
        return {"key": "depart", "reason": "Active stop needs departure/load closeout", "severity": "attention", "stop_id": current.id}
    if pending_posttrip:
        return {"key": "posttrip", "reason": "Route is complete; PostTrip is required", "severity": "attention"}

    next_action = _clean(route_next_action(route_context, has_high_issue=False, missing_document=False)).lower()
    route_status = getattr(route_context, "route_status", None)
    if "attach document" in next_action:
        return {"key": "transfer", "reason": "Transfer sheet or document is needed", "severity": "attention"}
    if route_status == "completed" and getattr(route_context, "posttrip_status", None) == "complete":
        return {"key": "finalize", "reason": "Route is ready to finalize", "severity": "attention"}
    if route_status == "active" and getattr(route_context, "rows", None) and current is None and not getattr(route_context, "all_departed", False):
        return {"key": "add_stop", "reason": "Route needs the next stop", "severity": "attention"}
    return {"key": "none", "reason": "No required CTA", "severity": "ok"}


def _empty_states(route, stops, moves, lanes):
    return {
        "no_route": not bool(stops),
        "no_stops": not bool(stops),
        "no_move_requests": not bool(moves),
        "no_lane_data": not bool(lanes),
    }


def build_driver_map_mode_context(route_context, route_map=None, production_flow_context=None, *, route_date=None, today_local_date=None, route_is_active=False):
    """Choose the driver map mode without requiring active driving."""
    route_map = route_map or {}
    production_flow_context = production_flow_context or {}
    stops = route_map.get("stops") or []
    ops_board_items = route_map.get("ops_board_items") or []
    has_route_history = bool(stops)
    has_board_activity = bool(stops or route_map.get("moves") or ops_board_items)
    has_production = bool(
        production_flow_context.get("flow_nodes")
        or production_flow_context.get("flow_lanes")
        or production_flow_context.get("flow_items")
    )
    current_stop = getattr(route_context, "current_stop", None)
    is_today = bool(route_date and today_local_date and route_date == today_local_date)

    if current_stop is not None or (route_is_active and has_board_activity) or (is_today and has_board_activity):
        mode = "live_current_work"
        label = "Active Route Map"
        empty = ""
    elif has_route_history:
        mode = "route_replay"
        label = "Last Route Replay" if not is_today else "Route Replay"
        empty = ""
    elif has_production:
        mode = "production_flow"
        label = "Production Flow"
        empty = ""
    else:
        mode = "no_current_activity"
        label = "Start Day" if is_today else "No Current Activity"
        empty = "No stops logged yet today. Start day by recording the first stop." if is_today else "No route stops logged for this date."

    return {
        "map_mode": mode,
        "map_label": label,
        "map_empty_message": empty,
        "has_route_history": has_route_history,
        "has_production_flow": has_production,
    }


def build_driver_route_map_context(
    driver_log=None,
    driver=None,
    date=None,
    selected_stop_id=None,
    selected_plant=None,
    selected_move_request_id=None,
    route_pretrip=None,
    proof_missing=False,
    pending_posttrip=False,
):
    """Build the driver route-map context from the driver's real work."""
    driver_id = getattr(driver, "id", None) or getattr(driver_log, "driver_id", None)
    target = _target_date(date or getattr(driver_log, "date", None))
    route_context = build_route_context(
        driver_log_id=getattr(driver_log, "id", None),
        driver_id=driver_id,
        route_date=target,
        selected_log_id=selected_stop_id,
    )
    requests = _requests_for_view(
        driver_id=driver_id,
        target=target,
        selected_move_request_id=selected_move_request_id,
    )
    request_log_ids = [req.linked_driver_log_id for req in requests if req.linked_driver_log_id]
    damaged_log_ids = _damage_log_ids(request_log_ids)
    issue_request_ids = _open_issue_request_ids(requests)
    moves = [
        _move_view_model(req, damaged_log_ids=damaged_log_ids, issue_request_ids=issue_request_ids, role="driver")
        for req in requests
    ]
    stops = _build_stops(route_context, role="driver", move_requests=requests, route_pretrip=route_pretrip)
    delivery_narratives = _build_delivery_narratives(route_context)
    transfers = _transfers_for_view(driver_id=driver_id, target=target)
    plants, lanes = _build_plants_and_lanes(stops, moves, transfers, role="driver")
    ops_board_items = _ops_board_items(
        moves,
        transfers,
        route_pretrip=route_pretrip,
        pending_posttrip=pending_posttrip,
    )
    route = _route_summary(route_context, moves=moves, stops=stops, driver=driver)
    dispatch_messages = _dispatch_messages(stops, moves)
    return {
        "map_mode": "live_current_work" if stops or moves or plants or ops_board_items else "no_current_activity",
        "map_label": "Active Route Map" if stops or moves or plants or ops_board_items else "No Current Activity",
        "map_empty_message": "No route stops logged for this date." if not (stops or ops_board_items) else "",
        "route": route,
        "stops": stops,
        "ops_board_items": ops_board_items,
        "delivery_narratives": delivery_narratives,
        "dispatch_messages": dispatch_messages,
        "dispatch_ticker_text": " · ".join(message["text"] for message in dispatch_messages),
        "cta_pulse": _cta_pulse(route_context, stops, proof_missing=proof_missing, pending_posttrip=pending_posttrip),
        "moves": moves,
        "plants": plants,
        "lanes": lanes,
        "selected": {
            "selected_stop_id": selected_stop_id,
            "selected_plant": selected_plant,
            "selected_move_request_id": selected_move_request_id,
        },
        "empty_states": _empty_states(route, stops, moves, lanes),
    }


def build_manager_route_map_context(date=None, selected_plant=None, selected_driver_id=None):
    """Build the manager route-map context across today's real routes/requests."""
    target = _target_date(date)
    log_query = DriverLog.query.filter(DriverLog.deleted_at.is_(None), DriverLog.date == target)
    if selected_driver_id:
        log_query = log_query.filter_by(driver_id=selected_driver_id)
    logs = log_query.order_by(DriverLog.driver_id.asc(), DriverLog.created_at.asc(), DriverLog.id.asc()).all()
    driver_ids = sorted({log.driver_id for log in logs})
    if selected_driver_id and selected_driver_id not in driver_ids:
        driver_ids = [selected_driver_id]

    requests = _requests_for_view(
        driver_id=selected_driver_id,
        target=target,
        selected_move_request_id=None,
    )
    request_log_ids = [req.linked_driver_log_id for req in requests if req.linked_driver_log_id]
    damaged_log_ids = _damage_log_ids(request_log_ids)
    issue_request_ids = _open_issue_request_ids(requests)
    moves = [
        _move_view_model(req, damaged_log_ids=damaged_log_ids, issue_request_ids=issue_request_ids, role="manager")
        for req in requests
    ]

    stops = []
    route_contexts = []
    for driver_id in driver_ids:
        route_context = build_route_context(driver_id=driver_id, route_date=target)
        route_contexts.append(route_context)
        stops.extend(_build_stops(route_context, role="manager", move_requests=requests))

    transfers = _transfers_for_view(driver_id=selected_driver_id, target=target)
    plants, lanes = _build_plants_and_lanes(stops, moves, transfers, role="manager")

    selected_driver = User.query.get(selected_driver_id) if selected_driver_id else None
    primary_context = route_contexts[0] if len(route_contexts) == 1 else None
    if primary_context:
        route = _route_summary(primary_context, moves=moves, stops=stops, driver=selected_driver)
    else:
        active_count = len([stop for stop in stops if stop["status"] in {"active", "needs_review", "blocked"}])
        issue_count = len([s for s in stops if s["has_issue"] or s["has_damage"]]) + len([m for m in moves if m["has_issue"] or m["has_damage"]])
        route = {
            "route_id": None,
            "driver_name": f"{len(driver_ids)} driver{'s' if len(driver_ids) != 1 else ''}" if driver_ids else NOT_TRACKED,
            "truck": NOT_TRACKED,
            "equipment": NOT_TRACKED,
            "status": "active" if active_count or moves else "no_route",
            "current_stop_id": next((stop["stop_id"] for stop in stops if stop["status"] == "active"), None),
            "current_location": next((stop["plant_name"] for stop in stops if stop["status"] == "active"), SAFE_EMPTY),
            "next_action": "Open issue details" if issue_count else ("Assign driver" if moves else "No action needed"),
            "issue_summary": f"{issue_count} issue{'s' if issue_count != 1 else ''}" if issue_count else "No open issues",
            "document_summary": "Documents current",
        }

    return {
        "route": route,
        "stops": stops,
        "moves": moves,
        "plants": plants,
        "lanes": lanes,
        "selected": {
            "selected_stop_id": None,
            "selected_plant": selected_plant,
            "selected_move_request_id": None,
        },
        "empty_states": _empty_states(route, stops, moves, lanes),
    }
