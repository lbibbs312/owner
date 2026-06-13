"""Deterministic labels for official printed records."""
from datetime import date, datetime
import re

import pytz


LOCAL_TZ = pytz.timezone("America/Detroit")


def _date_token(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    return re.sub(r"\D", "", text)[:8] or "NO-DATE"


def _slug(value, fallback="NA", limit=10):
    text = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").upper())
    return (text or fallback)[:limit]


def _record_token(value):
    if value is None or value == "":
        return "000"
    try:
        return f"{int(value):03d}"
    except (TypeError, ValueError):
        return _slug(value, limit=12)


def generated_at_label(now=None):
    now = now or datetime.utcnow()
    if now.tzinfo is None:
        now = pytz.utc.localize(now)
    local_now = now.astimezone(LOCAL_TZ)
    return f"{local_now.strftime('%Y-%m-%d')} {local_now.strftime('%I:%M%p').lower().lstrip('0')} {local_now.strftime('%Z')}"


def pretrip_document_number(pretrip):
    return f"DVIR-{_date_token(pretrip.pretrip_date)}-{_slug(pretrip.truck_number, 'TRUCK')}-{_record_token(pretrip.id)}"


def route_document_number(route_date, driver=None, truck=None, route_id=None):
    driver_token = _slug(getattr(driver, "employee_id", None) or getattr(driver, "username", None) or getattr(driver, "id", None), "DRV")
    return f"ROUTE-{_date_token(route_date)}-{driver_token}-{_slug(truck, 'TRUCK')}-{_record_token(route_id)}"


def manager_review_document_number(route_date, driver=None, truck=None, route_id=None):
    driver_token = _slug(getattr(driver, "employee_id", None) or getattr(driver, "username", None) or getattr(driver, "id", None), "DRV")
    return f"MGR-REVIEW-{_date_token(route_date)}-{driver_token}-{_slug(truck, 'TRUCK')}-{_record_token(route_id)}"


def eod_document_number(route_date, driver=None, route_id=None):
    driver_token = _slug(getattr(driver, "employee_id", None) or getattr(driver, "username", None) or getattr(driver, "id", None), "DRV")
    return f"EOD-{_date_token(route_date)}-{driver_token}-{_record_token(route_id)}"


def transfer_document_number(transfer):
    transfer_id = transfer.transfer_number or transfer.id
    return f"PLANT-TRANSFER-{_date_token(transfer.transfer_date)}-{_record_token(transfer_id)}"


def evidence_document_number(report):
    return f"PROOF-REPORT-{_record_token(report.id)}"


def move_request_number(move_request):
    created = getattr(move_request, "requested_at", None) or getattr(move_request, "created_at", None)
    return f"MOVE-REQ-{_date_token(created)}-{_record_token(getattr(move_request, 'id', None))}"


def document_meta(title, document_no, *, generated_at=None, page="1 of 1", revision=None):
    return {
        "title": title,
        "document_no": document_no,
        "generated_at": generated_at or generated_at_label(),
        "page": page,
        "revision": revision,
    }
