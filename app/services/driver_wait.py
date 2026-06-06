from datetime import datetime

import pytz
from flask_login import current_user
from sqlalchemy import or_

from app.models import ActivityEvent, DriverLog, PreTrip, ShiftRecord
from app.services.plant_addresses import plant_label


DETROIT_TZ = pytz.timezone("America/Detroit")
UTC_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
ACTIVE_WAIT_MAX_SECONDS = 18 * 60 * 60


def arrival_local_datetime(log):
    value = (getattr(log, "arrive_time", None) or "").strip()
    if not value:
        return None
    for fmt in UTC_FORMATS:
        try:
            return pytz.utc.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def elapsed_wait_seconds(log, now=None):
    arrival = arrival_local_datetime(log)
    if not arrival:
        return None
    now = now or datetime.now(DETROIT_TZ)
    if now.tzinfo is None:
        now = DETROIT_TZ.localize(now)
    else:
        now = now.astimezone(DETROIT_TZ)
    return max(0, int((now - arrival).total_seconds()))


def elapsed_wait_minutes(log, now=None):
    seconds = elapsed_wait_seconds(log, now=now)
    if seconds is None:
        return None
    return seconds // 60


def wait_minutes_for_log(log, now=None):
    if getattr(log, "dock_wait_minutes", None) is not None:
        return max(0, int(log.dock_wait_minutes or 0))
    if not getattr(log, "depart_time", None):
        return elapsed_wait_minutes(log, now=now)
    return None


def dock_time_review_label(minutes):
    if minutes is None:
        return ""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    if minutes >= 180:
        return "Extended wait — manager review required"
    if minutes >= 120:
        return "Long wait — needs review"
    return f"Dock time: {minutes} min"


def wait_label_for_log(log, now=None):
    minutes = wait_minutes_for_log(log, now=now)
    if minutes is None:
        return ""
    return dock_time_review_label(minutes)


def _shift_route_date(shift):
    if not shift:
        return None
    if shift.pretrip and shift.pretrip.pretrip_date:
        return shift.pretrip.pretrip_date
    if not shift.start_time:
        return None
    start_time = shift.start_time
    if start_time.tzinfo is None:
        start_time = pytz.utc.localize(start_time)
    return start_time.astimezone(DETROIT_TZ).date()


def _active_route_date_for_driver(driver_id, today_local_date):
    open_shift = (
        ShiftRecord.query.filter_by(user_id=driver_id, end_time=None)
        .order_by(ShiftRecord.start_time.desc())
        .first()
    )
    shift_date = _shift_route_date(open_shift)
    if shift_date:
        return shift_date
    pretrips = (
        PreTrip.query.filter_by(user_id=driver_id, deleted_at=None)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .limit(20)
        .all()
    )
    open_pretrip = next((pretrip for pretrip in pretrips if not pretrip.posttrip), None)
    return open_pretrip.pretrip_date if open_pretrip and open_pretrip.pretrip_date else today_local_date


def _route_finalized(driver_id, route_date):
    if not driver_id or not route_date:
        return False
    return ActivityEvent.query.filter_by(
        user_id=driver_id,
        category="eod",
        action="finalized",
        target_type="end_of_day",
    ).filter(ActivityEvent.details.contains(str(route_date))).first() is not None


def active_driver_wait_status(driver_id, now=None):
    now = now or datetime.now(DETROIT_TZ)
    if now.tzinfo is None:
        now = DETROIT_TZ.localize(now)
    else:
        now = now.astimezone(DETROIT_TZ)
    route_date = _active_route_date_for_driver(driver_id, now.date())
    if _route_finalized(driver_id, route_date):
        return None
    log = (
        DriverLog.query
        .filter_by(driver_id=driver_id, date=route_date, deleted_at=None)
        .filter(or_(DriverLog.depart_time.is_(None), DriverLog.depart_time == ""))
        .order_by(DriverLog.date.desc(), DriverLog.created_at.desc(), DriverLog.id.desc())
        .first()
    )
    if not log:
        return None
    seconds = elapsed_wait_seconds(log, now=now)
    if seconds is None or seconds > ACTIVE_WAIT_MAX_SECONDS:
        return None
    minutes = seconds // 60
    arrival = arrival_local_datetime(log)
    return {
        "log": log,
        "log_id": log.id,
        "plant": plant_label(log.plant_name),
        "minutes": minutes,
        "seconds": seconds,
        "arrival_label": arrival.strftime("%I:%M%p").lower().lstrip("0") if arrival else "",
    }


def register_context_processors(app):
    @app.context_processor
    def inject_driver_wait_status():
        active_wait = None
        if current_user.is_authenticated and getattr(current_user, "role", None) == "driver":
            active_wait = active_driver_wait_status(current_user.id)
        return {
            "active_driver_wait": active_wait,
            "dock_time_review_label": dock_time_review_label,
            "wait_label_for_log": wait_label_for_log,
        }
