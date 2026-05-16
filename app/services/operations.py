from collections import defaultdict
from datetime import date, datetime, timedelta

from app.models import DamageReport, DriverLog, OperationalFollowUp, PlantTransfer, PreTrip, Task
from app.services.load_state import route_problem_reason, truck_issue_reason


def _blank(value):
    return not str(value or "").strip()


def week_bounds(anchor=None):
    anchor = anchor or date.today()
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=7)
    return start, end


def _driver_label(user):
    return user.display_name if user else "Unassigned"


def build_exception_items(anchor=None, dock_delay_minutes=30):
    today = anchor or date.today()
    week_start, week_end = week_bounds(today)
    items = []

    transfers = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date >= week_start,
        PlantTransfer.transfer_date < week_end,
    ).all()
    for transfer in transfers:
        label = f"Transfer {transfer.transfer_number or transfer.id}: {transfer.ship_from} to {transfer.ship_to}"
        if _blank(transfer.trailer_number):
            items.append({"severity": "high", "category": "Missing trailer", "label": label, "detail": "Trailer number is blank.", "target_type": "plant_transfer", "target_id": transfer.id})
        if _blank(transfer.transfer_time):
            items.append({"severity": "medium", "category": "Missing time", "label": label, "detail": "Transfer time is blank.", "target_type": "plant_transfer", "target_id": transfer.id})
        if _blank(transfer.driver_name):
            items.append({"severity": "medium", "category": "Missing driver", "label": label, "detail": "Driver name is blank.", "target_type": "plant_transfer", "target_id": transfer.id})
        if _blank(transfer.driver_initials):
            items.append({"severity": "medium", "category": "No driver initials", "label": label, "detail": "Driver initials are blank.", "target_type": "plant_transfer", "target_id": transfer.id})

    logs = DriverLog.query.filter(
        DriverLog.deleted_at.is_(None),
        DriverLog.date >= week_start,
        DriverLog.date < week_end,
    ).all()
    pretrips = PreTrip.query.filter(
        PreTrip.deleted_at.is_(None),
        PreTrip.pretrip_date >= week_start,
        PreTrip.pretrip_date < week_end,
    ).all()
    pretrip_keys = {(pretrip.user_id, pretrip.pretrip_date) for pretrip in pretrips}
    for log in logs:
        label = f"{_driver_label(log.driver)} at {log.plant_name} on {log.date}"
        if _blank(log.arrive_time) or _blank(log.depart_time):
            items.append({"severity": "medium", "category": "Missing time", "label": label, "detail": "Arrival or departure time is missing.", "target_type": "driver_log", "target_id": log.id})
        if (log.driver_id, log.date) not in pretrip_keys:
            items.append({"severity": "high", "category": "No pre-trip", "label": label, "detail": "Driver log exists without a same-day DVIR/pre-trip.", "target_type": "driver_log", "target_id": log.id})
        truck_issue = truck_issue_reason(log)
        route_problem = route_problem_reason(log)
        if log.maintenance or truck_issue:
            items.append({"severity": "high", "category": "Truck issue", "label": label, "detail": truck_issue or "Maintenance marked on driver log.", "target_type": "driver_log", "target_id": log.id})
        if route_problem:
            items.append({"severity": "medium", "category": "Route issue", "label": label, "detail": route_problem, "target_type": "driver_log", "target_id": log.id})
        if log.dock_wait_minutes is not None and log.dock_wait_minutes >= dock_delay_minutes:
            items.append({"severity": "high", "category": "Delayed dock time", "label": label, "detail": f"Dock wait recorded at {log.dock_wait_minutes} minutes.", "target_type": "driver_log", "target_id": log.id})

    open_hot_tasks = Task.query.filter(Task.is_hot.is_(True), Task.status.in_(["pending", "in-progress"])).all()
    for task in open_hot_tasks:
        items.append({"severity": "high", "category": "Open hot move", "label": task.title, "detail": task.details or "Hot move is still open.", "target_type": "task", "target_id": task.id})

    damage_reports = DamageReport.query.filter(DamageReport.status != "closed").order_by(DamageReport.created_at.desc()).all()
    for report in damage_reports:
        items.append({"severity": "high", "category": "Damage flag", "label": f"{report.plant_name} damage report #{report.id}", "detail": report.description, "target_type": "damage_report", "target_id": report.id})

    open_followups = OperationalFollowUp.query.filter_by(status="open").order_by(OperationalFollowUp.created_at.desc()).all()
    for followup in open_followups:
        items.append({"severity": "fixed", "category": "Manager follow-up", "label": followup.plant_name or "Operations follow-up", "detail": f"{followup.kind.replace('_', ' ').title()}: {followup.details}", "target_type": "followup", "target_id": followup.id})

    severity_order = {"high": 0, "medium": 1, "fixed": 2, "low": 3}
    return sorted(items, key=lambda item: (severity_order.get(item["severity"], 9), item["category"], item["label"]))


def build_delay_report(anchor=None, dock_delay_minutes=30):
    today = anchor or date.today()
    week_start, week_end = week_bounds(today)
    logs = DriverLog.query.filter(
        DriverLog.deleted_at.is_(None),
        DriverLog.date >= week_start,
        DriverLog.date < week_end,
        DriverLog.dock_wait_minutes.isnot(None),
    ).all()
    delayed_logs = [log for log in logs if (log.dock_wait_minutes or 0) >= dock_delay_minutes]
    by_plant = defaultdict(list)
    for log in logs:
        by_plant[log.plant_name].append(log.dock_wait_minutes or 0)
    plant_averages = [
        {"plant": plant, "average_wait": round(sum(values) / len(values), 1), "records": len(values)}
        for plant, values in sorted(by_plant.items())
    ]
    return {"week_start": week_start, "week_end": week_end - timedelta(days=1), "delayed_logs": delayed_logs, "plant_averages": plant_averages, "threshold": dock_delay_minutes}


def build_weekly_savings(anchor=None, dock_delay_minutes=30):
    today = anchor or date.today()
    week_start, week_end = week_bounds(today)
    transfers = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date >= week_start,
        PlantTransfer.transfer_date < week_end,
    ).all()
    complete_transfers = [
        transfer for transfer in transfers
        if not any([_blank(transfer.trailer_number), _blank(transfer.driver_name), _blank(transfer.transfer_time), _blank(transfer.driver_initials)])
    ]
    incomplete_transfers = len(transfers) - len(complete_transfers)
    completion_rate = round((len(complete_transfers) / len(transfers)) * 100, 1) if transfers else 100.0

    pretrips = PreTrip.query.filter(
        PreTrip.deleted_at.is_(None),
        PreTrip.pretrip_date >= week_start,
        PreTrip.pretrip_date < week_end,
    ).count()
    hot_moves = Task.query.filter(
        Task.is_hot.is_(True),
        Task.created_at >= datetime.combine(week_start, datetime.min.time()),
        Task.created_at < datetime.combine(week_end, datetime.min.time()),
    ).all()
    hot_moves_full_timestamps = [task for task in hot_moves if task.status == "completed" and task.accepted_at and task.completed_at]

    delay_report = build_delay_report(today, dock_delay_minutes)
    damage_reports = DamageReport.query.filter(
        DamageReport.created_at >= datetime.combine(week_start, datetime.min.time()),
        DamageReport.created_at < datetime.combine(week_end, datetime.min.time()),
    ).all()
    damage_reports_with_photos = [report for report in damage_reports if report.photos]

    followups = OperationalFollowUp.query.filter(
        OperationalFollowUp.created_at >= datetime.combine(week_start, datetime.min.time()),
        OperationalFollowUp.created_at < datetime.combine(week_end, datetime.min.time()),
    ).all()
    wrong_location_events = [f for f in followups if f.kind in {"wrong_location", "unclear_dispatch"}]
    gage_tracking_followups = [f for f in followups if f.kind == "gage_tracking"]

    missing_paperwork_prevented = incomplete_transfers + len([item for item in build_exception_items(today, dock_delay_minutes) if item["category"] in {"Missing trailer", "Missing time", "No driver initials", "No pre-trip"}])
    completed_moves = len([task for task in hot_moves if task.status == "completed"]) + len(complete_transfers)
    supervisor_minutes_saved = (completed_moves * 2) + (missing_paperwork_prevented * 5) + (len(delay_report["delayed_logs"]) * 10) + (len(damage_reports_with_photos) * 15)

    return {
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "transfer_completion_rate": completion_rate,
        "complete_transfer_count": len(complete_transfers),
        "total_transfer_count": len(transfers),
        "incomplete_transfer_count": incomplete_transfers,
        "same_day_pretrip_count": pretrips,
        "hot_moves_completed_with_timestamps": len(hot_moves_full_timestamps),
        "hot_move_count": len(hot_moves),
        "plant_averages": delay_report["plant_averages"],
        "delayed_dock_count": len(delay_report["delayed_logs"]),
        "damage_reports_with_photos": len(damage_reports_with_photos),
        "damage_report_count": len(damage_reports),
        "wrong_location_or_unclear_dispatch_count": len(wrong_location_events),
        "gage_tracking_followup_count": len(gage_tracking_followups),
        "completed_moves": completed_moves,
        "missing_paperwork_prevented": missing_paperwork_prevented,
        "supervisor_minutes_saved": supervisor_minutes_saved,
    }
