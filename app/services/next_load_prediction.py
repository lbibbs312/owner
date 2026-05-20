"""Next-load intent prediction without promoting guesses to actual cargo."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

import pytz

from app.models import DriverLog, HotMove, PartScanEvent, PlantPredictionRule, Task
from app.services.load_state import destination_from_load, destination_load_value
from app.services.plant_addresses import PLANT_LABELS, plant_label
from app.services.plant_time import forecast_for_stop

CONFIRMED = "confirmed"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
UNKNOWN = "unknown"

DISPATCH_TASK = "dispatch_task"
MANIFEST_SCAN = "manifest_scan"
ROUTE_PLAN = "route_plan"
PLANT_RULE = "plant_rule"
HISTORICAL_PATTERN = "historical_pattern"
UNKNOWN_SOURCE = "unknown"

SHIPPER_SCAN_CONTEXTS = {"shipper", "shipper_scan", "manifest", "manifest_scan", "shipping_document", "bol", "paperwork"}


def _clean(value):
    return (value or "").strip()


def _norm(value):
    return _clean(value).lower()


def _plant_code(value):
    wanted = _norm(value)
    if not wanted:
        return ""
    for code, label in PLANT_LABELS.items():
        if wanted in {code.lower(), label.lower()}:
            return code
    return _clean(value)


def _task_route_codes(task):
    title = _clean(getattr(task, "title", ""))
    lowered = title.lower()
    marker = " to "
    split_at = lowered.find(marker)
    if split_at < 0:
        return "", ""
    return _plant_code(title[:split_at]), _plant_code(title[split_at + len(marker):])


def _source_label(source):
    return {
        DISPATCH_TASK: "dispatch task",
        MANIFEST_SCAN: "manifest scan",
        ROUTE_PLAN: "route plan",
        PLANT_RULE: "plant rule",
        HISTORICAL_PATTERN: "historical pattern",
        UNKNOWN_SOURCE: "unknown",
    }.get(source, source.replace("_", " "))


def _confidence_label(confidence):
    return {
        CONFIRMED: "Confirmed",
        HIGH: "High",
        MEDIUM: "Medium",
        LOW: "Low",
        UNKNOWN: "Unknown",
    }.get(confidence, _clean(confidence).title())


def _current_stop_plant(current_stop):
    return _plant_code(getattr(current_stop, "plant_name", None)) if current_stop else ""


@dataclass
class NextLoadPrediction:
    predicted_pickup_plant_id: str = ""
    predicted_destination_plant_id: str = ""
    predicted_load_label: str = "Unknown"
    predicted_ready_at: object = None
    estimated_remaining_minutes: int | None = None
    confidence: str = UNKNOWN
    source: str = UNKNOWN_SOURCE
    reason_text: str = "No dispatch task, manifest scan, plant rule, or strong history is available."
    required_driver_action: str = "Scan shipper barcode or select destination before departure."
    can_promote_to_actual_cargo: bool = False
    expires_at: object = None
    current_stop_elapsed_minutes: int | None = None
    plant_average_label: str = "No baseline"
    elapsed_label: str = "--"
    ready_at_label: str = ""
    status: str = "Awaiting confirmation"
    severity: str = "muted"
    delay_minutes: int | None = None
    delay_reason_required: bool = False
    delay_reason_text: str = ""

    @property
    def is_known(self):
        return bool(self.predicted_destination_plant_id and self.source != UNKNOWN_SOURCE)

    @property
    def source_label(self):
        return _source_label(self.source)

    @property
    def confidence_label(self):
        return _confidence_label(self.confidence)

    @property
    def title(self):
        if self.source == MANIFEST_SCAN and self.is_known:
            return "Next Load Confirmed"
        if self.confidence == CONFIRMED and self.is_known:
            return "Next Load Confirmed"
        return "Next Load Estimate" if self.is_known else "Next Load Unknown"

    @property
    def display_destination(self):
        return plant_label(self.predicted_destination_plant_id) if self.predicted_destination_plant_id else "Unknown"

    @property
    def display_pickup(self):
        return plant_label(self.predicted_pickup_plant_id) if self.predicted_pickup_plant_id else "Current stop"

    def to_dict(self):
        return {
            "predicted_pickup_plant_id": self.predicted_pickup_plant_id,
            "predicted_destination_plant_id": self.predicted_destination_plant_id,
            "predicted_load_label": self.predicted_load_label,
            "predicted_ready_at": self.predicted_ready_at,
            "estimated_remaining_minutes": self.estimated_remaining_minutes,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "source": self.source,
            "source_label": self.source_label,
            "reason_text": self.reason_text,
            "required_driver_action": self.required_driver_action,
            "can_promote_to_actual_cargo": self.can_promote_to_actual_cargo,
            "expires_at": self.expires_at,
            "current_stop_elapsed_minutes": self.current_stop_elapsed_minutes,
            "plant_average_label": self.plant_average_label,
            "elapsed_label": self.elapsed_label,
            "ready_at_label": self.ready_at_label,
            "status": self.status,
            "severity": self.severity,
            "delay_minutes": self.delay_minutes,
            "delay_reason_required": self.delay_reason_required,
            "delay_reason_text": self.delay_reason_text,
            "is_known": self.is_known,
            "title": self.title,
            "display_destination": self.display_destination,
            "display_pickup": self.display_pickup,
        }


def _with_timing(prediction, current_stop, timing_forecast=None, now=None):
    forecast = timing_forecast
    if forecast is None and current_stop is not None:
        forecast = forecast_for_stop(current_stop, now=now)
    if not forecast:
        return prediction
    prediction.predicted_ready_at = forecast.get("ready_at")
    prediction.ready_at_label = forecast.get("ready_at_label") or ""
    prediction.estimated_remaining_minutes = forecast.get("remaining_minutes")
    prediction.current_stop_elapsed_minutes = forecast.get("elapsed_minutes")
    prediction.elapsed_label = forecast.get("elapsed_label") or "--"
    prediction.plant_average_label = forecast.get("today_average_label") if forecast.get("today_average") is not None else forecast.get("estimate_label")
    prediction.status = forecast.get("status") or prediction.status
    prediction.severity = forecast.get("severity") or prediction.severity
    prediction.delay_minutes = forecast.get("delay_minutes")
    open_stop = current_stop is not None and not getattr(current_stop, "depart_time", None)
    missing_reason = not _clean(getattr(current_stop, "downtime_reason", "")) if current_stop is not None else False
    prediction.delay_reason_required = bool(open_stop and missing_reason and prediction.severity in {"warning", "high"})
    if prediction.delay_reason_required:
        delay = prediction.delay_minutes or 0
        prediction.delay_reason_text = f"Driver delay reason required: current stop is {delay}m over plant average."
    return prediction


def _make_prediction(*, pickup, destination, confidence, source, reason_text, required_driver_action, can_promote, current_stop, timing_forecast, now):
    prediction = NextLoadPrediction(
        predicted_pickup_plant_id=pickup or "",
        predicted_destination_plant_id=destination or "",
        predicted_load_label=destination_load_value(destination) if destination else "Unknown",
        confidence=confidence,
        source=source,
        reason_text=reason_text,
        required_driver_action=required_driver_action,
        can_promote_to_actual_cargo=can_promote,
        expires_at=(now + timedelta(hours=4)) if now else None,
    )
    return _with_timing(prediction, current_stop, timing_forecast, now)


def _active_task_for_driver(driver_id):
    if not driver_id:
        return None
    return (
        Task.query.filter(
            Task.status.in_(["pending", "in-progress"]),
            (Task.assigned_to == driver_id) | (Task.accepted_by_id == driver_id),
        )
        .order_by(Task.status == "pending", Task.created_at.desc(), Task.id.desc())
        .first()
    )


def _active_hot_move_for_driver(driver_id):
    if not driver_id:
        return None
    return (
        HotMove.query.filter(
            HotMove.driver_id == driver_id,
            HotMove.status.in_(["assigned", "accepted", "picked_up"]),
        )
        .order_by(HotMove.accepted_at.desc().nullslast(), HotMove.id.desc())
        .first()
    )


def _prediction_from_task(task, pickup, current_stop, timing_forecast, now):
    if not task:
        return None
    origin, destination = _task_route_codes(task)
    if not destination:
        return None
    if pickup and origin and pickup != origin:
        return None
    source = DISPATCH_TASK
    reason = f"Task #{task.id} assigns {plant_label(origin) if origin else 'current stop'} to {plant_label(destination)}."
    return _make_prediction(
        pickup=origin or pickup,
        destination=destination,
        confidence=CONFIRMED,
        source=source,
        reason_text=reason,
        required_driver_action="Confirm loaded and record departure before this becomes actual cargo.",
        can_promote=True,
        current_stop=current_stop,
        timing_forecast=timing_forecast,
        now=now,
    )


def _ship_to_from_text(value):
    text = _clean(value)
    if not text:
        return ""
    for pattern in (r"ship\s*to\s*[:=]\s*([A-Za-z0-9 _-]+)", r"to\s*[:=]\s*([A-Za-z0-9 _-]+)"):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).strip().split(";")[0].split(",")[0]
            code = _plant_code(raw)
            if code:
                return code
    return ""


def _prediction_from_manifest_scan(event, pickup, current_stop, timing_forecast, now):
    if not event:
        return None
    destination = ""
    if getattr(event, "part", None) is not None:
        destination = _plant_code(getattr(event.part, "default_destination_plant_id", None))
    destination = destination or _ship_to_from_text(getattr(event, "validation_message", None)) or _ship_to_from_text(getattr(event, "raw_value", None))
    if not destination:
        return None
    return _make_prediction(
        pickup=_plant_code(getattr(event, "plant_id", None)) or pickup,
        destination=destination,
        confidence=HIGH,
        source=MANIFEST_SCAN,
        reason_text=f"Shipper/manifest scan #{event.id} identifies destination {plant_label(destination)}.",
        required_driver_action="Confirm loaded and record departure before promoting manifest cargo to actual route cargo.",
        can_promote=True,
        current_stop=current_stop,
        timing_forecast=timing_forecast,
        now=now,
    )


def _manifest_scan_for_stop(current_stop):
    if not current_stop or not getattr(current_stop, "id", None):
        return None
    return (
        PartScanEvent.query.filter(PartScanEvent.stop_id == current_stop.id)
        .filter(PartScanEvent.scan_context.in_(SHIPPER_SCAN_CONTEXTS))
        .order_by(PartScanEvent.timestamp.desc(), PartScanEvent.id.desc())
        .first()
    )


def _prediction_from_rule(pickup, current_stop, timing_forecast, now):
    if not pickup:
        return None
    rule = (
        PlantPredictionRule.query.filter_by(plant_id=pickup, active=True)
        .order_by(PlantPredictionRule.id.asc())
        .first()
    )
    if not rule:
        return None
    destination = _plant_code(rule.predicted_destination_plant_id)
    return _make_prediction(
        pickup=pickup,
        destination=destination,
        confidence=_norm(rule.confidence) or MEDIUM,
        source=PLANT_RULE,
        reason_text=f"Active plant rule for {plant_label(pickup)} predicts {plant_label(destination)}.",
        required_driver_action="Scan shipper barcode or confirm loaded before departure.",
        can_promote=False,
        current_stop=current_stop,
        timing_forecast=timing_forecast,
        now=now,
    )


def _historical_destination(pickup, route_date, current_stop=None, history_days=30):
    if not pickup or not route_date:
        return "", 0, 0.0
    start = route_date - timedelta(days=history_days)
    query = DriverLog.query.filter(
        DriverLog.deleted_at.is_(None),
        DriverLog.plant_name.in_([pickup, plant_label(pickup)]),
        DriverLog.date >= start,
        DriverLog.date <= route_date,
        DriverLog.depart_time.isnot(None),
        DriverLog.depart_load_size.isnot(None),
    )
    if current_stop is not None and getattr(current_stop, "id", None):
        query = query.filter(DriverLog.id != current_stop.id)
    counts = Counter()
    for log in query.all():
        destination = destination_from_load(log.depart_load_size)
        if destination:
            counts[destination] += 1
    if not counts:
        return "", 0, 0.0
    destination, count = counts.most_common(1)[0]
    total = sum(counts.values())
    return destination, count, count / total if total else 0.0


def _prediction_from_history(pickup, route_date, current_stop, timing_forecast, now):
    destination, count, ratio = _historical_destination(pickup, route_date, current_stop=current_stop)
    if not destination:
        return None
    confidence = MEDIUM if count >= 3 and ratio >= 0.6 else LOW
    percent = int(round(ratio * 100))
    return _make_prediction(
        pickup=pickup,
        destination=destination,
        confidence=confidence,
        source=HISTORICAL_PATTERN,
        reason_text=f"{plant_label(pickup)} history points to {plant_label(destination)} on {percent}% of recent completed load-outs ({count} sample{'s' if count != 1 else ''}).",
        required_driver_action="Scan shipper barcode or confirm loaded before departure.",
        can_promote=False,
        current_stop=current_stop,
        timing_forecast=timing_forecast,
        now=now,
    )


def build_next_load_prediction(
    *,
    current_route=None,
    current_stop=None,
    driver_id=None,
    truck_id=None,
    current_cargo_state=None,
    active_dispatch_task=None,
    active_hot_move=None,
    scanned_manifest_or_shipper=None,
    plant_rules=None,
    recent_route_history=None,
    plant_timing_history=None,
    current_stop_elapsed_time=None,
    route_date=None,
    timing_forecast=None,
    now=None,
):
    """Return the best next-load intent without changing actual cargo fields.

    Source priority is dispatch/hot move, manifest/shipper scan, plant rule,
    historical pattern, then unknown. Human-readable load labels are display only;
    the prediction keeps pickup and destination plant IDs structured.
    """
    now = now or datetime.now(pytz.timezone("America/Detroit"))
    driver_id = driver_id or getattr(current_stop, "driver_id", None)
    route_date = route_date or getattr(current_stop, "date", None)
    pickup = _current_stop_plant(current_stop)

    hot_move = active_hot_move or _active_hot_move_for_driver(driver_id)
    task = active_dispatch_task or (getattr(hot_move, "move", None) if hot_move else None) or _active_task_for_driver(driver_id)
    prediction = _prediction_from_task(task, pickup, current_stop, timing_forecast, now)
    if prediction:
        return prediction

    manifest_event = scanned_manifest_or_shipper or _manifest_scan_for_stop(current_stop)
    prediction = _prediction_from_manifest_scan(manifest_event, pickup, current_stop, timing_forecast, now)
    if prediction:
        return prediction

    prediction = _prediction_from_rule(pickup, current_stop, timing_forecast, now)
    if prediction:
        return prediction

    prediction = _prediction_from_history(pickup, route_date, current_stop, timing_forecast, now)
    if prediction:
        return prediction

    unknown = NextLoadPrediction(
        predicted_pickup_plant_id=pickup,
        predicted_load_label="Unknown",
        confidence=UNKNOWN,
        source=UNKNOWN_SOURCE,
        reason_text="No dispatch task, manifest scan, plant rule, or strong historical pattern is available.",
        required_driver_action="Scan shipper barcode or select destination before departure.",
        can_promote_to_actual_cargo=False,
        expires_at=(now + timedelta(hours=2)) if now else None,
    )
    return _with_timing(unknown, current_stop, timing_forecast, now)
