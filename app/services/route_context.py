"""Canonical route context for driver, manager, dispatch, and report surfaces."""

from dataclasses import dataclass
from datetime import date, datetime
import re

import pytz
from sqlalchemy import or_

from app.extensions import db
from app.models import ActivityEvent, DamageReport, DriverLog, DriverLogPhoto, LoadIntent, PartScanEvent, PlantTimeSample, PreTrip, ShiftRecord, User
from app.services.cargo_state import cargo_state_for_log
from app.services.cargo_reconciliation_service import reconcile_cargo
from app.services.driver_wait import wait_label_for_log
from app.services.load_state import build_driver_log_route_context, current_load_after_logs, route_problem_reason, stop_role_details, truck_issue_reason
from app.services.next_load_prediction import build_next_load_prediction
from app.services.plant_addresses import plant_label
from app.services.plant_time import route_stop_forecasts
from app.services.scan_scope_service import route_scope_id, route_stop_ids
from app.services.stop_summary import build_stop_summary

DETROIT_TZ = pytz.timezone("America/Detroit")
ROUTE_ID_RE = re.compile(r"driver:(?P<driver_id>\d+):date:(?P<route_date>\d{4}-\d{2}-\d{2})(?::truck:(?P<truck_id>[^:]+))?(?::shift:(?P<shift_id>\d+))?")


def _driver_log_sort_key(log):
    return (log.date or date.min, log.arrive_time or "", log.created_at or datetime.min, log.id or 0)


def _active_logs_query():
    return DriverLog.query.filter(DriverLog.deleted_at.is_(None))


def _parse_route_id(route_id):
    if not route_id:
        return {}
    match = ROUTE_ID_RE.fullmatch(str(route_id))
    if not match:
        return {}
    data = match.groupdict()
    result = {"driver_id": int(data["driver_id"]), "route_date": datetime.strptime(data["route_date"], "%Y-%m-%d").date()}
    if data.get("truck_id"):
        result["truck_id"] = data["truck_id"]
    if data.get("shift_id"):
        result["shift_id"] = int(data["shift_id"])
    return result


def _shift_route_date(shift):
    if not shift:
        return None
    if shift.pretrip and shift.pretrip.pretrip_date:
        return shift.pretrip.pretrip_date
    if not shift.start_time:
        return None
    stamp = shift.start_time
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    return stamp.astimezone(DETROIT_TZ).date()


def _route_finalized(driver_id, route_date):
    return ActivityEvent.query.filter_by(
        user_id=driver_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(route_date))).first() is not None


def route_end_arrival_log(logs, *, route_finalized=False):
    """Return the arrival-only route terminus when a finalized route ends there."""
    if not route_finalized or not logs:
        return None
    last_log = logs[-1]
    if getattr(last_log, "depart_time", None):
        return None
    return last_log


def unresolved_departure_logs(logs, *, route_finalized=False):
    """Open stops that still need correction because the route moved past them."""
    if not logs:
        return []
    route_end_log = route_end_arrival_log(logs, route_finalized=route_finalized)
    unresolved = []
    for index, log in enumerate(logs):
        if getattr(log, "depart_time", None):
            continue
        later_stop_exists = index < len(logs) - 1
        if later_stop_exists:
            unresolved.append(log)
            continue
        if route_finalized and (not route_end_log or route_end_log.id != log.id):
            unresolved.append(log)
    return unresolved


def _signature_shift(driver_id, route_date):
    by_pretrip = (
        ShiftRecord.query.join(PreTrip, ShiftRecord.pretrip_id == PreTrip.id)
        .filter(ShiftRecord.user_id == driver_id, PreTrip.pretrip_date == route_date, ShiftRecord.driver_signature.isnot(None))
        .order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc())
        .first()
    )
    if by_pretrip:
        return by_pretrip
    for shift in ShiftRecord.query.filter(ShiftRecord.user_id == driver_id, ShiftRecord.driver_signature.isnot(None)).order_by(ShiftRecord.signature_timestamp.desc(), ShiftRecord.start_time.desc()).limit(50):
        if _shift_route_date(shift) == route_date:
            return shift
    return None


def _route_pretrips(driver_id, route_date, *, truck_id=None, shift_id=None):
    if shift_id:
        shift = ShiftRecord.query.get(shift_id)
        if shift and shift.pretrip:
            return [shift.pretrip]
    query = PreTrip.query.filter(PreTrip.user_id == driver_id, PreTrip.pretrip_date == route_date, PreTrip.deleted_at.is_(None))
    if truck_id:
        query = query.filter(db.func.lower(db.func.trim(PreTrip.truck_number)) == str(truck_id).strip().lower())
    return query.order_by(PreTrip.created_at.asc(), PreTrip.id.asc()).all()


def _route_shift_id(driver_id, route_date, *, truck_id=None, pretrips=None, shift_id=None):
    if shift_id:
        return shift_id
    query = ShiftRecord.query.filter(ShiftRecord.user_id == driver_id)
    if pretrips:
        pretrip_ids = [item.id for item in pretrips if getattr(item, "id", None)]
        if pretrip_ids:
            query = query.filter(ShiftRecord.pretrip_id.in_(pretrip_ids))
    shifts = query.order_by(ShiftRecord.start_time.asc(), ShiftRecord.id.asc()).all()
    matching = []
    for shift in shifts:
        if _shift_route_date(shift) != route_date:
            continue
        shift_truck = getattr(getattr(shift, "pretrip", None), "truck_number", None)
        if truck_id and shift_truck and str(shift_truck).strip().lower() != str(truck_id).strip().lower():
            continue
        matching.append(shift)
    return matching[0].id if len(matching) == 1 else None


def _canonical_route_id(route_id, logs, driver_id, route_date, *, truck_id=None, shift_id=None):
    if not driver_id or not route_date:
        return route_id or "unknown"
    parsed = _parse_route_id(route_id)
    broad_route_id = bool(route_id and parsed and not parsed.get("truck_id") and not parsed.get("shift_id"))
    if route_id and not broad_route_id:
        return route_id
    if not truck_id and logs:
        truck_id = getattr(logs[0], "truck_number", None)
    value = route_scope_id(logs) or f"driver:{driver_id}:date:{route_date.isoformat() if hasattr(route_date, 'isoformat') else route_date}"
    if truck_id:
        value = f"{value}:truck:{str(truck_id).strip()}"
    if shift_id:
        value = f"{value}:shift:{shift_id}"
    return value


def _resolve_scope(route_id=None, session_id=None, shift_id=None, stop_id=None, driver_log_id=None, driver_id=None, route_date=None, truck_id=None):
    resolved = _parse_route_id(route_id)
    if resolved:
        return {**resolved, "scope_source": "route_id"}

    shift_key = shift_id or session_id
    if shift_key:
        shift = ShiftRecord.query.get(shift_key)
        if shift:
            route_date = _shift_route_date(shift) or route_date
            truck_id = truck_id or getattr(getattr(shift, "pretrip", None), "truck_number", None)
            return {"driver_id": shift.user_id, "route_date": route_date, "truck_id": truck_id, "shift_id": shift.id, "scope_source": "shift"}

    stop_key = stop_id or driver_log_id
    if stop_key:
        log = DriverLog.query.get(stop_key)
        if log:
            return {"driver_id": log.driver_id, "route_date": log.date, "truck_id": truck_id, "selected_log_id": log.id, "scope_source": "stop"}

    return {"driver_id": driver_id, "route_date": route_date, "truck_id": truck_id, "scope_source": "fallback"}


def _delay_reason_required(log, timing):
    if not log or not timing or getattr(log, "downtime_reason", None):
        return False
    delay = timing.get("delay_minutes") or 0
    expected = timing.get("estimate_minutes") or 0
    if getattr(log, "hot_parts", False) and delay > 0:
        return True
    if delay >= 15:
        return True
    return bool(expected and delay >= 10 and delay >= expected * 0.5)


def _route_cta(label, action, style="primary"):
    return {"label": label, "action": action, "style": style}


def build_route_cta_context(
    route_context,
    driver_log=None,
    production_flow_context=None,
    *,
    proof_missing=False,
    has_active_shift=False,
    route_is_active=False,
    route_date=None,
    today_local_date=None,
    has_last_route=False,
    selected_date_forced=False,
    pending_posttrip=False,
):
    """Return the single route CTA decision used by driver/mobile surfaces."""
    rows = getattr(route_context, "rows", None) or []
    current_stop = getattr(route_context, "current_stop", None) or driver_log
    route_status = getattr(route_context, "route_status", None)
    route_finalized = bool(getattr(route_context, "route_finalized", False) or route_status == "finalized")
    all_departed = bool(getattr(route_context, "all_departed", False))
    posttrip_complete = getattr(route_context, "posttrip_status", None) == "complete"
    has_route_history = bool(rows)
    is_today = bool(route_date and today_local_date and route_date == today_local_date)

    allowed_actions = []
    display_mode = "active_route"
    next_action = "No action needed"
    primary = None
    secondary = None
    route_message = ""
    proof_message = "Documents current"

    show_finalize = False
    show_attach = False
    show_print = has_route_history
    show_start_shift = False
    show_posttrip = bool(pending_posttrip)

    if route_finalized and pending_posttrip:
        display_mode = "completed_route"
        next_action = "PostTrip Due"
        primary = _route_cta("PostTrip Due", "posttrip")
        secondary = _route_cta("Print Route", "print_route", "ghost") if has_route_history else None
        route_message = "Route is closed. Complete PostTrip mileage."
        proof_message = "Document proof is missing." if proof_missing else proof_message
        show_attach = bool(proof_missing)
        allowed_actions = ["posttrip", "print_route", "view_route"]
        if proof_missing:
            allowed_actions.append("attach_document")
    elif route_finalized and route_is_active:
        display_mode = "active_route"
        next_action = "Continue route"
        primary = _route_cta("Add Stop", "add_stop")
        secondary = _route_cta("Attach Document", "attach_document", "ghost") if proof_missing else _route_cta("Print Route", "print_route", "ghost")
        route_message = "Shift is still active. Continue the route or attach proof."
        proof_message = "Document proof is missing." if proof_missing else proof_message
        show_attach = bool(proof_missing)
        allowed_actions = ["add_stop", "attach_document", "print_route", "view_route", "route_history"]
    elif route_finalized and not proof_missing:
        display_mode = "finalized_route"
        next_action = "No action needed"
        primary = _route_cta("Print Route", "print_route")
        secondary = _route_cta("Route History", "route_history", "ghost")
        route_message = "Route is finalized."
        allowed_actions = ["print_route", "route_history", "view_route"]
    elif route_finalized and proof_missing:
        display_mode = "proof_needed"
        next_action = "Attach document"
        primary = _route_cta("Attach Document", "attach_document")
        secondary = _route_cta("Print Route", "print_route", "ghost")
        route_message = "Route is finalized."
        proof_message = "Document proof is missing."
        show_attach = True
        allowed_actions = ["attach_document", "print_route", "view_route", "route_history"]
    elif current_stop is not None and not getattr(current_stop, "depart_time", None):
        display_mode = "active_stop"
        if cargo_state_for_log(current_stop)["state"] == "unknown":
            next_action = "Confirm cargo"
            primary = _route_cta("Confirm Cargo", "confirm_cargo")
            allowed_actions = ["confirm_cargo"]
        else:
            next_action = "Record departure"
            primary = _route_cta("Record Departure", "record_departure")
            allowed_actions = ["record_departure", "add_damage", "add_note"]
        secondary = _route_cta("Add Damage", "add_damage", "ghost")
        route_message = "Current stop is open."
    elif all_departed and has_route_history and not route_finalized:
        if is_today and not selected_date_forced:
            display_mode = "completed_route"
            secondary = _route_cta("Print Draft", "print_route", "ghost")
            if pending_posttrip:
                next_action = "PostTrip Due"
                primary = _route_cta("PostTrip Due", "posttrip")
                allowed_actions = ["posttrip", "print_route", "view_route"]
                route_message = "All recorded stops are closed. Complete PostTrip before finalizing."
            elif posttrip_complete:
                next_action = "Finalize route"
                primary = _route_cta("Finalize Route", "finalize_route")
                show_finalize = True
                allowed_actions = ["finalize_route", "print_route", "view_route"]
                route_message = "All recorded stops and PostTrip are complete."
            else:
                next_action = "PostTrip required"
                primary = _route_cta("Print Draft", "print_route")
                allowed_actions = ["print_route", "view_route"]
                route_message = "All recorded stops are closed. PostTrip is required before finalizing."
        else:
            display_mode = "read_only_history" if selected_date_forced else "last_route"
            next_action = "Start new shift or View last route"
            primary = _route_cta("Start New Shift", "start_shift")
            secondary = _route_cta("Print Last Route", "print_route", "ghost")
            show_start_shift = True
            allowed_actions = ["start_shift", "view_route", "print_route", "route_history"]
            route_message = "Showing a completed route."
    elif has_route_history or has_last_route:
        display_mode = "active_route" if route_is_active else ("read_only_history" if selected_date_forced else "last_route")
        next_action = "Start new shift or View last route" if not route_is_active else "Complete route"
        primary = _route_cta("Start New Shift", "start_shift") if not route_is_active else _route_cta("Add Stop", "add_stop")
        secondary = _route_cta("View Last Route", "view_route", "ghost")
        show_start_shift = not route_is_active
        allowed_actions = ["start_shift", "view_route", "print_route", "route_history"] if not route_is_active else ["add_stop", "view_route"]
        route_message = "Showing route history." if not route_is_active else "Route is active."
    else:
        display_mode = "no_active_shift" if not has_active_shift else "active_route"
        next_action = "Start shift"
        primary = _route_cta("Start Shift", "start_shift")
        secondary = _route_cta("View Last Route", "route_history", "ghost")
        show_start_shift = True
        show_print = False
        allowed_actions = ["start_shift", "route_history"]
        route_message = "No active route for this date."

    if proof_missing and not route_finalized and next_action not in {"Confirm cargo", "Record departure", "Finalize route"}:
        display_mode = "proof_needed"
        next_action = "Attach document"
        primary = _route_cta("Attach Document", "attach_document")
        secondary = _route_cta("Print Route", "print_route", "ghost") if has_route_history else secondary
        show_attach = True
        proof_message = "Document proof is missing."
        if "attach_document" not in allowed_actions:
            allowed_actions.insert(0, "attach_document")

    return {
        "route_display_mode": display_mode,
        "next_action": next_action,
        "primary_cta": primary,
        "secondary_cta": secondary,
        "allowed_actions": allowed_actions,
        "route_state_message": route_message,
        "proof_state_message": proof_message,
        "show_finalize_button": show_finalize,
        "show_attach_document_button": show_attach,
        "show_print_button": show_print,
        "show_start_shift_button": show_start_shift,
        "show_posttrip_button": show_posttrip,
        "route_finalized": route_finalized,
        "proof_missing": bool(proof_missing),
        "has_route_history": has_route_history,
    }


def _photo_review_rows(logs):
    ids = route_stop_ids(logs)
    if not ids:
        return [], []
    photos = DriverLogPhoto.query.filter(DriverLogPhoto.driver_log_id.in_(ids)).all()
    blockers = []
    rows = []
    for photo in photos:
        row = {
            "photo_id": photo.id,
            "stop_id": photo.driver_log_id,
            "label": photo.original_filename or photo.filename,
            "file_available": bool(photo.file_available),
            "note": photo.note or "",
        }
        rows.append(row)
        if not row["file_available"]:
            blockers.append({"label": "Photo proof render failure", "detail": "Photo record exists but file failed to render. Review in system before approval.", "stop_id": photo.driver_log_id})
    return rows, blockers


@dataclass
class RouteStateSnapshot:
    route_id: str
    driver_id: int | None
    truck_id: str | None
    route_date: object
    route_status: str
    current_stop: object | None
    current_stop_status: str
    current_activity_label: str
    previous_cargo_cycle_status: str
    current_cargo: dict
    next_load_intent_status: str
    next_load_destination: str
    next_load_basis: str
    next_required_driver_action: str
    timing_status: str
    delay_reason_required: bool
    mileage_status: str
    posttrip_status: str
    signature_status: str
    approval_status: str
    approval_unavailable_reasons: list
    true_exceptions: list
    review_items: list
    report_summary_sentence: str
    rows: list
    route_state: dict
    next_load_prediction: dict | None
    log_routes: dict
    stop_timing: dict
    scope_source: str
    all_departed: bool
    route_finalized: bool
    photo_reviews: list

    def to_dict(self):
        def row_dict(row):
            log = row.get("log")
            return {k: v for k, v in row.items() if k not in {"log", "route", "timing"}} | {
                "log_id": getattr(log, "id", None),
                "driver_id": getattr(log, "driver_id", None),
                "date": str(getattr(log, "date", "")) if getattr(log, "date", None) else None,
            }
        current = self.current_stop
        return {
            "route_id": self.route_id,
            "driver_id": self.driver_id,
            "truck_id": self.truck_id,
            "route_date": str(self.route_date) if self.route_date else None,
            "route_status": self.route_status,
            "current_stop_id": getattr(current, "id", None),
            "current_stop": self.current_stop_plant,
            "current_stop_status": self.current_stop_status,
            "current_activity_label": self.current_activity_label,
            "previous_cargo_cycle_status": self.previous_cargo_cycle_status,
            "current_cargo": self.current_cargo,
            "next_load_intent_status": self.next_load_intent_status,
            "next_load_destination": self.next_load_destination,
            "next_load_basis": self.next_load_basis,
            "next_required_driver_action": self.next_required_driver_action,
            "timing_status": self.timing_status,
            "delay_reason_required": self.delay_reason_required,
            "mileage_status": self.mileage_status,
            "posttrip_status": self.posttrip_status,
            "signature_status": self.signature_status,
            "approval_status": self.approval_status,
            "approval_unavailable_reasons": self.approval_unavailable_reasons,
            "true_exceptions": self.true_exceptions,
            "review_items": self.review_items,
            "report_summary_sentence": self.report_summary_sentence,
            "rows": [row_dict(row) for row in self.rows],
            "next_load_prediction": self.next_load_prediction,
            "scope_source": self.scope_source,
            "all_departed": self.all_departed,
            "route_finalized": self.route_finalized,
            "photo_reviews": self.photo_reviews,
        }

    @property
    def current_stop_plant(self):
        if not self.current_stop:
            return None
        row = next((item for item in self.rows if item.get("log") is self.current_stop or item.get("log_id") == self.current_stop.id), None)
        return (row or {}).get("plant") or plant_label(getattr(self.current_stop, "plant_name", None))


def build_route_context(*, route_id=None, session_id=None, shift_id=None, stop_id=None, driver_log_id=None, driver_id=None, route_date=None, truck_id=None, selected_log_id=None, now=None):
    scope = _resolve_scope(route_id=route_id, session_id=session_id, shift_id=shift_id, stop_id=stop_id, driver_log_id=driver_log_id, driver_id=driver_id, route_date=route_date, truck_id=truck_id)
    driver_id = scope.get("driver_id")
    route_date = scope.get("route_date")
    truck_id = scope.get("truck_id") or truck_id
    selected_log_id = selected_log_id or scope.get("selected_log_id")
    if isinstance(route_date, str):
        route_date = datetime.strptime(route_date, "%Y-%m-%d").date()

    logs = []
    if driver_id and route_date:
        logs = sorted(_active_logs_query().filter_by(driver_id=driver_id, date=route_date).all(), key=_driver_log_sort_key)
    log_routes = build_driver_log_route_context(logs)
    timing = route_stop_forecasts(logs, now=now)
    route_finalized = bool(driver_id and route_date and _route_finalized(driver_id, route_date))
    all_departed = bool(logs) and all(getattr(log, "depart_time", None) for log in logs)
    open_logs = [log for log in logs if not getattr(log, "depart_time", None)]
    current_open = open_logs[-1] if open_logs and open_logs[-1].id == logs[-1].id and not route_finalized else None
    route_end_log = route_end_arrival_log(logs, route_finalized=route_finalized)
    unresolved_departure_ids = {
        log.id for log in unresolved_departure_logs(logs, route_finalized=route_finalized)
    }

    for index, log in enumerate(logs):
        route = log_routes.get(log.id)
        if route is None:
            continue
        route.update(stop_role_details(log, route))
        route.update(build_stop_summary(
            route, log,
            is_first=(index == 0),
            is_last=(index == len(logs) - 1),
            route_finalized=route_finalized,
            wait_label=wait_label_for_log(log),
            current_open=bool(current_open and current_open.id == log.id),
        ))

    rows = []
    for index, log in enumerate(logs, start=1):
        route = log_routes.get(log.id, {})
        is_current = bool(current_open and current_open.id == log.id)
        later_stop_exists = index < len(logs)
        is_route_end_arrival = bool(route_end_log and route_end_log.id == log.id)
        is_missing_departure = bool(not log.depart_time and (log.id in unresolved_departure_ids or later_stop_exists))
        is_final = bool(route_finalized and index == len(logs) and not is_current and not is_missing_departure)
        role = stop_role_details(log, route, is_current_open=is_current, is_final_stop=is_final)
        timing_row = timing.get(log.id, {})
        if is_current:
            status = "Current"
            status_key = "current"
            note = "Awaiting departure / load intent"
        elif is_missing_departure:
            status = "Missing Departure"
            status_key = "open"
            note = "Missing departure because route finalization was attempted." if route_finalized else "Missing departure because a later stop exists."
        elif is_final:
            status = "Finalized"
            status_key = "finalized"
            note = "Route finalized at final stop." if is_route_end_arrival else "Route finalized"
        else:
            status = "Completed" if log.depart_time else "Open"
            status_key = "complete" if log.depart_time else "open"
            note = route.get("action") or ("Awaiting departure / load intent" if not log.depart_time else "Completed")
        delay_required = bool(is_current and _delay_reason_required(log, timing_row))
        row = {
            "index": index,
            "log": log,
            "log_id": log.id,
            "route": route,
            "status": status,
            "status_key": status_key,
            "plant": route.get("plant") or plant_label(log.plant_name),
            "arrive_time": log.arrive_time,
            "depart_time": log.depart_time,
            "cargo_in": role["arrival_cargo"],
            "cargo_out": role["departure_cargo"] if log.depart_time else (route.get("depart_cargo_desc") or "--"),
            "note": note,
            "stop_role": role["stop_role"],
            "cargo_added": role["cargo_added"],
            "cargo_removed": role["cargo_removed"],
            "cargo_retained": role["cargo_retained"],
            "train_pickup_timing": role["train_pickup_timing"],
            "timing_status": timing_row.get("status") or "Timing status pending",
            "timing_class": timing_row.get("severity") or "muted",
            "ready_estimate_label": timing_row.get("ready_at_label") or "",
            "delay_reason_required": delay_required,
            "timing": timing_row,
        }
        rows.append(row)

    current_cargo = current_load_after_logs(logs)
    cargo_review = reconcile_cargo(logs, log_routes) if logs else {"issues": []}
    previous_cargo_cycle_status = "needs_review" if cargo_review.get("issues") else "complete"
    current_timing = timing.get(current_open.id, {}) if current_open else {}

    prediction = None
    if current_open:
        prediction = build_next_load_prediction(
            current_stop=current_open,
            driver_id=driver_id,
            truck_id=truck_id,
            current_cargo_state=current_cargo,
            route_date=route_date,
            timing_forecast=current_timing,
            now=now,
        ).to_dict()
    next_status = "unknown"
    if prediction and prediction.get("is_known"):
        next_status = "confirmed" if prediction.get("confidence") == "confirmed" or prediction.get("can_promote_to_actual_cargo") else "predicted"
    next_destination = (prediction or {}).get("display_destination") or "Unknown"
    next_basis = (prediction or {}).get("source_label") or "unknown"
    next_action = (prediction or {}).get("required_driver_action") or ""

    pretrips = _route_pretrips(driver_id, route_date, truck_id=truck_id, shift_id=scope.get("shift_id")) if driver_id and route_date else []
    if not truck_id and pretrips:
        truck_id = pretrips[-1].truck_number
    shift_id = _route_shift_id(driver_id, route_date, truck_id=truck_id, pretrips=pretrips, shift_id=scope.get("shift_id")) if driver_id and route_date else None
    route_id_value = _canonical_route_id(route_id, logs, driver_id, route_date, truck_id=truck_id, shift_id=shift_id)
    active_route = bool(current_open or (logs and unresolved_departure_ids)) and not route_finalized
    if route_finalized:
        route_status = "finalized"
    elif active_route:
        route_status = "active"
    elif all_departed:
        route_status = "completed"
    else:
        route_status = "active" if logs else "active"

    posttrip_status = "not due until route close" if route_status == "active" else "pending"
    mileage_status = "pending route close" if route_status == "active" else "not recorded"
    for pretrip in pretrips:
        if pretrip.posttrip:
            posttrip_status = "complete"
            if pretrip.start_mileage and pretrip.posttrip.end_mileage is not None:
                mileage_status = "complete"
            elif route_status != "active":
                mileage_status = "needs correction"
            break

    signature = _signature_shift(driver_id, route_date) if driver_id and route_date else None
    signature_status = "captured" if signature and signature.driver_signature else ("pending route close" if route_status == "active" else "missing")
    photo_reviews, photo_blockers = _photo_review_rows(logs)

    true_exceptions = []
    review_items = []
    for row in rows:
        log = row["log"]
        truck_issue = truck_issue_reason(log)
        route_issue = route_problem_reason(log)
        if row["status"] == "Missing Departure":
            item = {"label": "Missing Departure", "detail": row["note"], "stop_id": log.id}
            true_exceptions.append(item)
            review_items.append(item)
        if row["delay_reason_required"]:
            item = {"label": "Driver delay reason missing", "detail": f"{row['plant']} requires a delay reason before final approval.", "stop_id": log.id}
            true_exceptions.append(item)
            review_items.append(item)
        if truck_issue:
            true_exceptions.append({"label": "Truck issue", "detail": truck_issue, "stop_id": log.id})
        if route_issue:
            true_exceptions.append({"label": "Route issue", "detail": route_issue, "stop_id": log.id})
    for issue in cargo_review.get("issues") or []:
        review_items.append({"label": "Cargo mismatch", "detail": issue})
    review_items.extend(photo_blockers)

    approval_reasons = []
    if route_status == "active":
        approval_reasons.append("Active stop still open")
    if posttrip_status != "complete" and route_status != "active":
        approval_reasons.append("PostTrip mileage pending")
    if signature_status != "captured":
        approval_reasons.append("Driver signature pending route close" if route_status == "active" else "Driver signature missing")
    approval_reasons.extend(item["label"] for item in review_items if item.get("label") not in approval_reasons)
    approval_status = "final approval not available while route active" if route_status == "active" else ("blocked" if approval_reasons else "ready")

    current_label = ""
    if current_open:
        current_label = "Awaiting departure / load intent"
    elif rows:
        current_label = "Route completed" if all_departed else "Route open"
    current_stop_status = "current" if current_open else ("finalized" if route_finalized else ("completed" if all_departed else "open"))
    timing_status = current_timing.get("status") or "Timing status pending"
    delay_required = bool(current_open and _delay_reason_required(current_open, current_timing))

    driver = User.query.get(driver_id) if driver_id else None
    name = (driver.first_name or driver.display_name or driver.username) if driver else "Driver"
    if current_open:
        summary = f"{name} is currently at {plant_label(current_open.plant_name)} awaiting departure/load-out."
        if previous_cargo_cycle_status == "complete":
            if next_status == "unknown":
                summary = f"The previous cargo cycle appears complete. {summary} Next load not confirmed."
            else:
                summary = f"The previous cargo cycle appears complete. {summary}"
    elif all_departed:
        summary = f"{name} has completed {len(logs)} stop event{'s' if len(logs) != 1 else ''}."
    else:
        summary = f"{name} has {len(logs)} recorded stop event{'s' if len(logs) != 1 else ''}."

    legacy_route_status = "Finalized" if route_finalized else ("Active" if current_open or (logs and not all_departed) else ("Completed" if all_departed else "No Route"))
    route_state = {
        "route_status": legacy_route_status,
        "rows": rows,
        "current_activity": {
            "log": current_open,
            "plant": plant_label(current_open.plant_name) if current_open else None,
            "status": "Current Active Stop",
            "detail": "Awaiting load-out/departure" if current_open else current_label,
            "forecast_status": timing_status,
            "forecast_class": current_timing.get("severity") or "muted",
            "timing_status": timing_status,
            "timing_class": current_timing.get("severity") or "muted",
            "pickup_estimate": f"Pickup estimate: ready around {current_timing.get('ready_at_label')}" if current_timing.get("ready_at_label") else "Pickup estimate: timing history pending",
        } if current_open else None,
        "all_departed": all_departed,
    }

    return RouteStateSnapshot(
        route_id=route_id_value,
        driver_id=driver_id,
        truck_id=truck_id,
        route_date=route_date,
        route_status=route_status,
        current_stop=current_open,
        current_stop_status=current_stop_status,
        current_activity_label=current_label,
        previous_cargo_cycle_status=previous_cargo_cycle_status,
        current_cargo=current_cargo,
        next_load_intent_status=next_status,
        next_load_destination=next_destination,
        next_load_basis=next_basis,
        next_required_driver_action=next_action,
        timing_status=timing_status,
        delay_reason_required=delay_required,
        mileage_status=mileage_status,
        posttrip_status=posttrip_status,
        signature_status=signature_status,
        approval_status=approval_status,
        approval_unavailable_reasons=approval_reasons,
        true_exceptions=true_exceptions,
        review_items=review_items,
        report_summary_sentence=summary,
        rows=rows,
        route_state=route_state,
        next_load_prediction=prediction,
        log_routes=log_routes,
        stop_timing=timing,
        scope_source=scope.get("scope_source") or "fallback",
        all_departed=all_departed,
        route_finalized=route_finalized,
        photo_reviews=photo_reviews,
    )
