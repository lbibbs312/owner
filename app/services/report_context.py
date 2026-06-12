"""Driver report context and prefill support."""

from __future__ import annotations

from datetime import date, datetime

import pytz

from app.models import DriverLog, PreTrip, ShiftRecord
from app.services.driver_wait import wait_label_for_log
from app.services.plant_addresses import PLANT_ADDRESSES, plant_label
from app.services.route_context import build_route_context


DETROIT_TZ = pytz.timezone("America/Detroit")


def _local_now(now=None):
    stamp = now or datetime.utcnow()
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    return stamp.astimezone(DETROIT_TZ)


def _date_value(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _quarter_for(value):
    if not value:
        return None
    return f"Q{((value.month - 1) // 3) + 1}"


def _latest_route_pretrip(driver_id, route_date, *, truck_id=None):
    if not driver_id or not route_date:
        return None
    query = PreTrip.query.filter(
        PreTrip.user_id == driver_id,
        PreTrip.pretrip_date == route_date,
        PreTrip.deleted_at.is_(None),
    )
    if truck_id:
        query = query.filter(PreTrip.truck_number == str(truck_id))
    return query.order_by(PreTrip.created_at.desc(), PreTrip.id.desc()).first()


def _route_shift(driver_id, route_date, pretrip=None):
    if not driver_id or not route_date:
        return None
    query = ShiftRecord.query.filter(ShiftRecord.user_id == driver_id)
    if pretrip:
        query = query.filter(ShiftRecord.pretrip_id == pretrip.id)
    for shift in query.order_by(ShiftRecord.start_time.desc(), ShiftRecord.id.desc()).limit(20):
        shift_pretrip = getattr(shift, "pretrip", None)
        if shift_pretrip and shift_pretrip.pretrip_date == route_date:
            return shift
    return None


def _selected_stop(route_context, selected_log_id=None):
    if selected_log_id:
        for row in route_context.rows:
            log = row.get("log")
            if getattr(log, "id", None) == selected_log_id:
                return log, row
    current = route_context.current_stop
    if current:
        row = next(
            (item for item in route_context.rows if getattr(item.get("log"), "id", None) == current.id),
            {},
        )
        return current, row
    if route_context.rows:
        row = route_context.rows[-1]
        return row.get("log"), row
    return None, {}


def _mileage_context(logs, pretrip):
    posttrip = getattr(pretrip, "posttrip", None)
    fuel_logs = [log for log in logs if getattr(log, "fuel", False) and getattr(log, "fuel_mileage", None) is not None]
    last_fuel_mileage = fuel_logs[-1].fuel_mileage if fuel_logs else None
    start_mileage = getattr(pretrip, "start_mileage", None)
    end_mileage = getattr(posttrip, "end_mileage", None)
    return {
        "start_mileage": start_mileage,
        "last_fuel_mileage": last_fuel_mileage,
        "end_mileage": end_mileage,
        "current_mileage": last_fuel_mileage or end_mileage or start_mileage,
        "total_route_miles": getattr(posttrip, "miles_driven", None),
    }


def _city_state_from_address(address):
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    if len(parts) < 2:
        return "", ""
    tail = parts[-1]
    if tail.lower() in {"usa", "united states"} and len(parts) >= 3:
        tail = parts[-2]
        city = parts[-3] if len(parts) >= 4 else ""
    else:
        city = parts[-2] if len(parts) >= 3 else ""
    state = tail.split()[0].upper() if tail else ""
    if len(state) != 2:
        state = ""
    return city, state


def build_report_context(
    *,
    user,
    selected_report_type=None,
    route_date=None,
    driver_log_id=None,
    stop_id=None,
    now=None,
):
    """Return known report fields derived from the active driver workflow.

    Blank values stay blank. This helper must not invent "unknown" values for
    fields the driver has not explicitly answered.
    """

    local_now = _local_now(now)
    selected_log_id = driver_log_id or stop_id
    selected_log = DriverLog.query.get(selected_log_id) if selected_log_id else None
    if selected_log and getattr(user, "role", None) != "management" and selected_log.driver_id != user.id:
        selected_log = None
        selected_log_id = None

    report_date = _date_value(route_date) or getattr(selected_log, "date", None) or local_now.date()
    route_context = build_route_context(
        driver_id=getattr(user, "id", None),
        route_date=report_date,
        driver_log_id=getattr(selected_log, "id", None),
        now=local_now,
    )
    stop, stop_row = _selected_stop(route_context, getattr(selected_log, "id", None))
    logs = [row["log"] for row in route_context.rows if row.get("log")]
    pretrip = _latest_route_pretrip(
        getattr(user, "id", None),
        report_date,
        truck_id=getattr(route_context, "truck_id", None),
    )
    if not pretrip:
        pretrip = _latest_route_pretrip(getattr(user, "id", None), report_date)
    shift = _route_shift(getattr(user, "id", None), report_date, pretrip=pretrip)
    mileage = _mileage_context(logs, pretrip)

    truck = getattr(route_context, "truck_id", None) or getattr(pretrip, "truck_number", None)
    trailer = getattr(pretrip, "trailer_number", None)
    plant_code = getattr(stop, "plant_name", None)
    plant_name = plant_label(plant_code) if plant_code else None
    address = getattr(stop, "location_address", None) or (PLANT_ADDRESSES.get(plant_code) if plant_code else None)
    active_wait = wait_label_for_log(stop) if stop and not getattr(stop, "depart_time", None) else None
    fuel_seller_name = plant_name if selected_report_type == "fuel_odo_ifta" and getattr(stop, "fuel", False) else ""
    fuel_seller_address = address if fuel_seller_name else ""
    fuel_city, fuel_state = _city_state_from_address(fuel_seller_address)

    return {
        "selected_report_type": selected_report_type,
        "driver_id": getattr(user, "id", None),
        "driver_name": getattr(user, "display_name", None),
        "truck": truck,
        "trailer": trailer,
        "route_id": getattr(route_context, "route_id", None),
        "route_date": report_date,
        "route_date_value": report_date.isoformat() if report_date else "",
        "shift": getattr(pretrip, "shift", None) or getattr(shift, "id", None),
        "shift_id": getattr(shift, "id", None),
        "stop_id": getattr(stop, "id", None),
        "stop_label": plant_name,
        "stop_code": plant_code,
        "stop_status": (stop_row or {}).get("status"),
        "plant_or_location": plant_name,
        "exact_location_text": address,
        "city": "",
        "state": "",
        "fuel_seller_name": fuel_seller_name,
        "fuel_seller_address": fuel_seller_address,
        "fuel_city": fuel_city,
        "fuel_state": fuel_state,
        "incident_datetime_value": local_now.strftime("%Y-%m-%dT%H:%M"),
        "reported_datetime_value": local_now.strftime("%Y-%m-%dT%H:%M"),
        "reporting_period_quarter": _quarter_for(report_date),
        "reporting_year": report_date.year if report_date else None,
        "trip_start_date": report_date.isoformat() if report_date else "",
        "trip_end_date": report_date.isoformat() if report_date else "",
        "purchaser_name": getattr(user, "display_name", None),
        "vehicle_unit_number": truck,
        "active_wait_label": active_wait,
        "route_status": getattr(route_context, "route_status", None),
        "pretrip_id": getattr(pretrip, "id", None),
        "posttrip_id": getattr(getattr(pretrip, "posttrip", None), "id", None),
        **mileage,
    }
