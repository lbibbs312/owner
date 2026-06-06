"""Manager case grouping for repeated plant and truck issues."""

from collections import defaultdict
from datetime import date, timedelta

from app.models import ActivityEvent, DriverLog, PreTrip
from app.services.load_state import truck_issue_reason
from app.services.plant_addresses import plant_label
from app.services.plant_time import forecast_for_stop


def _minutes_label(minutes):
    if minutes is None:
        return "+0m"
    return f"+{int(round(minutes))}m"


def _truck_key(value):
    return (value or "").strip()


def _pretrip_truck_map(start_date, end_date):
    pretrips = (
        PreTrip.query
        .filter(PreTrip.deleted_at.is_(None), PreTrip.pretrip_date >= start_date, PreTrip.pretrip_date < end_date)
        .order_by(PreTrip.created_at.desc(), PreTrip.id.desc())
        .all()
    )
    trucks = {}
    for pretrip in pretrips:
        key = (pretrip.user_id, pretrip.pretrip_date)
        if key not in trucks and _truck_key(pretrip.truck_number):
            trucks[key] = _truck_key(pretrip.truck_number)
    return trucks


def build_exception_events(logs, *, anchor=None):
    anchor = anchor or date.today()
    events = []
    for log in logs:
        forecast = forecast_for_stop(log) if not getattr(log, "depart_time", None) else None
        delay_minutes = 0
        if forecast and forecast.get("delay_minutes") is not None:
            delay_minutes = max(0, forecast.get("delay_minutes") or 0)
        elif log.dock_wait_minutes:
            delay_minutes = max(0, log.dock_wait_minutes or 0)
        if delay_minutes > 0 or (forecast and forecast.get("severity") in {"warning", "high"}):
            plant = plant_label(log.plant_name)
            events.append({
                "event_type": "plant_delay",
                "severity": "high" if delay_minutes >= 45 else "medium",
                "stop_id": log.id,
                "driver_log_id": log.id,
                "driver_id": log.driver_id,
                "plant_name": plant,
                "event_date": log.date,
                "delay_minutes": delay_minutes,
                "summary": f"{plant} stop is running {_minutes_label(delay_minutes)} over expected.",
            })
        issue = truck_issue_reason(log) or ("Maintenance marked on driver log." if log.maintenance else "")
        if issue:
            events.append({
                "event_type": "truck_issue",
                "severity": "high",
                "stop_id": log.id,
                "driver_log_id": log.id,
                "driver_id": log.driver_id,
                "plant_name": plant_label(log.plant_name),
                "event_date": log.date,
                "summary": issue,
            })
    return events


def build_followup_cases(*, anchor=None):
    anchor = anchor or date.today()
    week_start = anchor - timedelta(days=anchor.weekday())
    week_end = week_start + timedelta(days=7)
    logs = (
        DriverLog.query
        .filter(DriverLog.deleted_at.is_(None), DriverLog.date >= week_start, DriverLog.date < week_end)
        .order_by(DriverLog.date.asc(), DriverLog.arrive_time.asc(), DriverLog.id.asc())
        .all()
    )
    truck_map = _pretrip_truck_map(week_start, week_end)
    plant_groups = defaultdict(list)
    truck_groups = defaultdict(list)
    for event in build_exception_events(logs, anchor=anchor):
        if event["event_type"] == "plant_delay" and event.get("event_date") == anchor:
            plant_groups[event["plant_name"]].append(event)
        elif event["event_type"] == "truck_issue":
            truck = _truck_key(truck_map.get((event.get("driver_id"), event.get("event_date"))))
            if truck:
                event["truck_id"] = truck
                truck_groups[truck].append(event)

    ryder_events = (
        ActivityEvent.query
        .filter(ActivityEvent.category == "ryder", ActivityEvent.created_at >= week_start)
        .order_by(ActivityEvent.created_at.desc())
        .all()
    )
    for item in ryder_events:
        details = item.details or ""
        parts = dict(
            part.split(":", 1) for part in [p.strip() for p in details.split(";")] if ":" in part
        )
        truck = _truck_key(parts.get("Truck"))
        if truck:
            truck_groups[truck].append({
                "event_type": "truck_issue",
                "severity": "high",
                "truck_id": truck,
                "event_date": item.created_at.date(),
                "summary": parts.get("Issue") or item.title or "Ryder service follow-up",
                "target_type": item.target_type,
                "target_id": item.target_id,
                "last_seen": "Ryder Rentals" if "ryder" in details.lower() or "ryder" in (item.title or "").lower() else "Route records",
            })

    cases = []
    for plant, events in sorted(plant_groups.items()):
        if len(events) < 2:
            continue
        delays = [event.get("delay_minutes") or 0 for event in events]
        avg_delay = sum(delays) / len(delays) if delays else 0
        worst = max(delays) if delays else 0
        cases.append({
            "case_type": "plant_delay",
            "title": f"{plant} delay pattern today",
            "summary": f"{plant} has {len(events)} delayed stops today. Average delay: {_minutes_label(avg_delay)}.",
            "metrics": [
                f"{len(events)} delayed stops",
                f"average {_minutes_label(avg_delay)} over baseline",
                f"worst stop {_minutes_label(worst)}",
            ],
            "plant": plant,
            "owner": "Unassigned",
            "status": "Open",
            "events": events,
        })

    for truck, events in sorted(truck_groups.items()):
        if len(events) < 2:
            continue
        last_seen = next((event.get("last_seen") for event in events if event.get("last_seen")), None) or (events[-1].get("plant_name") or "Route history")
        cases.append({
            "case_type": "truck_issue",
            "title": f"Truck {truck} maintenance pattern",
            "summary": f"Truck {truck} has {len(events)} related maintenance reports this week.",
            "metrics": [
                f"{len(events)} related reports this week",
                f"last seen at {last_seen}",
                "Ryder follow-up pending" if any("ryder" in (event.get("summary") or "").lower() for event in events) else "Manager follow-up pending",
            ],
            "truck": truck,
            "owner": "Unassigned",
            "status": "Open",
            "events": events,
        })
    return cases


def same_plant_intelligence(log, stop_forecast, logs):
    if not log or not stop_forecast or not stop_forecast.get("delay_minutes"):
        return []
    plant = plant_label(log.plant_name)
    delay = stop_forecast.get("delay_minutes") or 0
    lines = [f"{plant} is running {_minutes_label(delay)} over expected for this stop."]
    today_delays = []
    for item in logs or []:
        if plant_label(item.plant_name) != plant:
            continue
        forecast = forecast_for_stop(item)
        if forecast.get("delay_minutes"):
            today_delays.append(forecast.get("delay_minutes") or 0)
    if len(today_delays) >= 2:
        avg_delay = sum(today_delays) / len(today_delays)
        lines.append(f"{plant} has {len(today_delays)} delayed stops today. Average delay: {_minutes_label(avg_delay)}.")
    return lines


def same_vehicle_intelligence(truck_id, cases):
    truck_id = _truck_key(truck_id)
    if not truck_id:
        return []
    return [case["summary"] for case in cases or [] if case.get("case_type") == "truck_issue" and _truck_key(case.get("truck")) == truck_id]
