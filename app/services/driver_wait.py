from datetime import datetime

import pytz
from flask_login import current_user
from sqlalchemy import or_

from app.models import DriverLog
from app.services.plant_addresses import plant_label


DETROIT_TZ = pytz.timezone("America/Detroit")
UTC_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


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


def elapsed_wait_minutes(log, now=None):
    arrival = arrival_local_datetime(log)
    if not arrival:
        return None
    now = now or datetime.now(DETROIT_TZ)
    if now.tzinfo is None:
        now = DETROIT_TZ.localize(now)
    else:
        now = now.astimezone(DETROIT_TZ)
    return max(0, int((now - arrival).total_seconds() // 60))


def wait_minutes_for_log(log, now=None):
    if getattr(log, "dock_wait_minutes", None) is not None:
        return max(0, int(log.dock_wait_minutes or 0))
    if not getattr(log, "depart_time", None):
        return elapsed_wait_minutes(log, now=now)
    return None


def wait_label_for_log(log, now=None):
    minutes = wait_minutes_for_log(log, now=now)
    if minutes is None:
        return ""
    prefix = "Active wait" if not getattr(log, "depart_time", None) and getattr(log, "dock_wait_minutes", None) is None else "Wait"
    return f"{prefix} {minutes} min"


def active_driver_wait_status(driver_id, now=None):
    log = (
        DriverLog.query
        .filter_by(driver_id=driver_id, deleted_at=None)
        .filter(or_(DriverLog.depart_time.is_(None), DriverLog.depart_time == ""))
        .order_by(DriverLog.date.desc(), DriverLog.created_at.desc(), DriverLog.id.desc())
        .first()
    )
    if not log:
        return None
    minutes = elapsed_wait_minutes(log, now=now)
    if minutes is None:
        return None
    arrival = arrival_local_datetime(log)
    return {
        "log": log,
        "log_id": log.id,
        "plant": plant_label(log.plant_name),
        "minutes": minutes,
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
            "wait_label_for_log": wait_label_for_log,
        }
