from datetime import date, timedelta

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
        items.append({"severity": "followup", "category": "Manager follow-up", "label": followup.plant_name or "Operations follow-up", "detail": f"{followup.kind.replace('_', ' ').title()}: {followup.details}", "target_type": "followup", "target_id": followup.id})

    severity_order = {"high": 0, "medium": 1, "followup": 2, "low": 3}
    return sorted(items, key=lambda item: (severity_order.get(item["severity"], 9), item["category"], item["label"]))
