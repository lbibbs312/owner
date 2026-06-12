from __future__ import annotations

from datetime import datetime
import mimetypes
import os
import re
from uuid import uuid4

import pytz
from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import IftaFuelRecord, IftaTripDistanceRow, IftaWorksheet
from app.services.file_integrity import sha256_file


IFTA_REVIEW_STATUSES = ("Draft", "Needs Review", "Ready for Tax Preparer", "Closed")
IMAGE_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _clean(value, default=None):
    value = (value or "").strip()
    return value or default


def _parse_date(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _float_or_none(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        # Drivers type things like "$163.80", "63.5 gal", or "1,234" — keep
        # the number instead of silently storing NULL.
        match = re.search(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", value)
        if not match:
            return None
        value = match.group(0).replace(",", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _ifta_upload_path():
    upload_root = current_app.config.get("IFTA_UPLOAD_FOLDER", "uploads/ifta_receipts")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    os.makedirs(upload_path, exist_ok=True)
    return upload_path


def save_ifta_receipt(uploaded_file, worksheet_id):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        return None, None, None, None
    original = secure_filename(uploaded_file.filename) or "fuel-receipt"
    _, ext = os.path.splitext(original)
    filename = f"ifta-receipt-{worksheet_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext or '.bin'}"
    stored_path = os.path.join(_ifta_upload_path(), filename)
    uploaded_file.save(stored_path)
    with open(stored_path, "rb") as stored:
        data = stored.read()
    mimetype = getattr(uploaded_file, "mimetype", None) or mimetypes.guess_type(filename)[0]
    return filename, sha256_file(stored_path), data, mimetype


def ifta_receipt_path(filename):
    if not filename:
        return None
    path = os.path.join(_ifta_upload_path(), filename)
    return path if os.path.isfile(path) else None


def ifta_receipt_available(fuel):
    # The upload folder is wiped on redeploy unless it sits on the persistent
    # disk — the database copy is the durable source.
    if fuel is None:
        return False
    if getattr(fuel, "receipt_data", None):
        return True
    return bool(ifta_receipt_path(fuel.receipt_photo))


def create_ifta_worksheet_from_form(form, files, *, user, report_context=None):
    now = datetime.utcnow()
    context = report_context or {}
    worksheet = IftaWorksheet(
        reporting_period_quarter=_clean(form.get("reporting_period_quarter")) or context.get("reporting_period_quarter"),
        reporting_year=_int_or_none(form.get("reporting_year") or context.get("reporting_year")),
        driver_id=user.id if getattr(user, "role", None) == "driver" else _int_or_none(form.get("driver_id")),
        truck=_clean(form.get("truck")) or context.get("truck"),
        trailer=_clean(form.get("trailer")) or context.get("trailer"),
        vin_or_vehicle_unit_number=_clean(form.get("vin_or_vehicle_unit_number")) or context.get("vehicle_unit_number"),
        fleet_number=_clean(form.get("fleet_number")),
        base_jurisdiction=_clean(form.get("base_jurisdiction")),
        carrier_name=_clean(form.get("carrier_name")),
        ifta_license_number=_clean(form.get("ifta_license_number")),
        review_status=_clean(form.get("review_status"), "Draft"),
        created_by_id=user.id,
        updated_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(worksheet)
    db.session.flush()
    trip = IftaTripDistanceRow(
        worksheet_id=worksheet.id,
        trip_start_date=_parse_date(form.get("trip_start_date") or context.get("trip_start_date")),
        trip_end_date=_parse_date(form.get("trip_end_date") or context.get("trip_end_date")),
        origin_city=_clean(form.get("origin_city")),
        origin_state=_clean(form.get("origin_state")),
        destination_city=_clean(form.get("destination_city")),
        destination_state=_clean(form.get("destination_state")),
        route_traveled=_clean(form.get("route_traveled")),
        beginning_odometer=_float_or_none(form.get("beginning_odometer") or context.get("start_mileage")),
        ending_odometer=_float_or_none(form.get("ending_odometer") or context.get("current_mileage")),
        total_trip_distance=_float_or_none(form.get("total_trip_distance") or context.get("total_route_miles")),
        jurisdiction=_clean(form.get("jurisdiction")),
        jurisdiction_distance=_float_or_none(form.get("jurisdiction_distance")),
        taxable_distance=_float_or_none(form.get("taxable_distance")),
        nontaxable_distance=_float_or_none(form.get("nontaxable_distance")),
        toll_distance=_float_or_none(form.get("toll_distance")),
        loaded_empty_deadhead=_clean(form.get("loaded_empty_deadhead")),
        notes=_clean(form.get("trip_notes")),
    )
    if any(getattr(trip, field) is not None for field in ("trip_start_date", "origin_city", "destination_city", "total_trip_distance", "jurisdiction")):
        db.session.add(trip)
    receipt_filename, receipt_hash, receipt_data, receipt_mimetype = save_ifta_receipt(files.get("receipt_photo"), worksheet.id)
    fuel_driver_supplied = bool(
        receipt_filename
        or _clean(form.get("purchase_date"))
        or _clean(form.get("seller_name"))
        or _clean(form.get("seller_address"))
        or _clean(form.get("fuel_city"))
        or _clean(form.get("state_or_province"))
        or _clean(form.get("gallons_or_liters"))
        or _clean(form.get("fuel_type"))
        or _clean(form.get("ending_odometer"))
        or _clean(form.get("tax_paid"))
    )
    fuel = IftaFuelRecord(
        worksheet_id=worksheet.id,
        purchase_date=_parse_date(form.get("purchase_date") or context.get("route_date_value")),
        seller_name=_clean(form.get("seller_name")) or context.get("fuel_seller_name"),
        seller_address=_clean(form.get("seller_address")) or context.get("fuel_seller_address"),
        city=_clean(form.get("fuel_city")) or context.get("fuel_city"),
        state_or_province=_clean(form.get("state_or_province")) or context.get("fuel_state"),
        gallons_or_liters=_float_or_none(form.get("gallons_or_liters")),
        fuel_type=_clean(form.get("fuel_type")),
        price_per_gallon_or_liter=_float_or_none(form.get("price_per_gallon_or_liter")),
        total_sale_amount=_float_or_none(form.get("total_sale_amount")),
        vehicle_unit_number=_clean(form.get("vehicle_unit_number")) or context.get("vehicle_unit_number") or worksheet.vin_or_vehicle_unit_number,
        purchaser_name=_clean(form.get("purchaser_name")) or context.get("purchaser_name"),
        receipt_photo=receipt_filename,
        receipt_hash=receipt_hash,
        receipt_data=receipt_data,
        receipt_mimetype=receipt_mimetype,
        tax_paid=_clean(form.get("tax_paid")),
        bulk_fuel=str(form.get("bulk_fuel") or "").lower() in {"1", "yes", "true", "on"},
    )
    if fuel_driver_supplied:
        db.session.add(fuel)
    return worksheet


def worksheet_summaries(worksheet):
    miles_by_jurisdiction = {}
    taxable_by_jurisdiction = {}
    nontaxable_by_jurisdiction = {}
    fuel_by_jurisdiction = {}
    fuel_by_type = {}
    missing_odometer_rows = []
    missing_receipt_rows = []
    missing_jurisdiction_distance_rows = []
    total_distance = 0.0
    total_fuel = 0.0

    for row in worksheet.trip_rows:
        jurisdiction = row.jurisdiction or "Not recorded"
        miles = row.jurisdiction_distance or row.total_trip_distance or 0
        miles_by_jurisdiction[jurisdiction] = miles_by_jurisdiction.get(jurisdiction, 0) + miles
        taxable_by_jurisdiction[jurisdiction] = taxable_by_jurisdiction.get(jurisdiction, 0) + (row.taxable_distance or 0)
        nontaxable_by_jurisdiction[jurisdiction] = nontaxable_by_jurisdiction.get(jurisdiction, 0) + (row.nontaxable_distance or 0)
        total_distance += row.total_trip_distance or miles or 0
        if row.beginning_odometer is None or row.ending_odometer is None:
            missing_odometer_rows.append(row)
        if row.jurisdiction_distance is None:
            missing_jurisdiction_distance_rows.append(row)

    for row in worksheet.fuel_records:
        jurisdiction = row.state_or_province or "Not recorded"
        fuel_type = row.fuel_type or "Not recorded"
        gallons = row.gallons_or_liters or 0
        fuel_by_jurisdiction[jurisdiction] = fuel_by_jurisdiction.get(jurisdiction, 0) + gallons
        fuel_by_type[fuel_type] = fuel_by_type.get(fuel_type, 0) + gallons
        total_fuel += gallons
        if not ifta_receipt_available(row):
            missing_receipt_rows.append(row)

    return {
        "total_miles_by_jurisdiction": miles_by_jurisdiction,
        "taxable_miles_by_jurisdiction": taxable_by_jurisdiction,
        "nontaxable_miles_by_jurisdiction": nontaxable_by_jurisdiction,
        "total_fuel_purchased_by_jurisdiction": fuel_by_jurisdiction,
        "total_gallons_liters_by_fuel_type": fuel_by_type,
        "average_mpg_estimate": round(total_distance / total_fuel, 2) if total_fuel else None,
        "missing_odometer_rows": missing_odometer_rows,
        "missing_receipt_rows": missing_receipt_rows,
        "missing_jurisdiction_distance_rows": missing_jurisdiction_distance_rows,
    }


def ifta_open_items(worksheet):
    summaries = worksheet_summaries(worksheet)
    items = []
    if summaries["missing_odometer_rows"]:
        items.append("Missing odometer rows")
    if summaries["missing_receipt_rows"]:
        items.append("Missing receipt rows")
    if summaries["missing_jurisdiction_distance_rows"]:
        items.append("Missing jurisdiction distance rows")
    if worksheet.review_status in {"Draft", "Needs Review"}:
        items.append("IFTA Review")
    if not worksheet.manager_signature and worksheet.review_status == "Closed":
        items.append("Manager signature not captured")
    return items


def ifta_packet_status(worksheet):
    if ifta_open_items(worksheet):
        return "Needs Review"
    if worksheet.review_status in {"Ready for Tax Preparer", "Closed"}:
        return worksheet.review_status
    return "Needs Review"


def ifta_fuel_rows(worksheet):
    rows = []
    for index, fuel in enumerate(worksheet.fuel_records, 1):
        receipt_available = ifta_receipt_available(fuel)
        receipt_ext = os.path.splitext(fuel.receipt_photo or "")[1].lower()
        receipt_is_image = receipt_available and (
            receipt_ext in IMAGE_RECEIPT_EXTENSIONS
            or (getattr(fuel, "receipt_mimetype", None) or "").startswith("image/")
        )
        rows.append(
            {
                "number": index,
                "fuel": fuel,
                "receipt_available": receipt_available,
                "receipt_is_image": receipt_is_image,
                "receipt_status": "Available" if receipt_available else "Photo not available in upload storage",
                "receipt_hash": fuel.receipt_hash or "Not recorded",
                "receipt_photo": fuel.receipt_photo or "Not recorded",
            }
        )
    return rows


def build_ifta_packet(worksheet, *, generated_by):
    generated_at = datetime.utcnow()
    return {
        "worksheet": worksheet,
        "document_number": f"IFTA-{worksheet.id:06d}",
        "packet_type": "IFTA Support Worksheet",
        "packet_title": "IFTA Support Worksheet",
        "generated_by": generated_by.display_name,
        "generated_at": _label_dt(generated_at),
        "current_status": ifta_packet_status(worksheet),
        "open_items": ifta_open_items(worksheet),
        "summaries": worksheet_summaries(worksheet),
        "fuel_rows": ifta_fuel_rows(worksheet),
    }


def _label_dt(value):
    if not value:
        return "Not recorded"
    if value.tzinfo is None:
        value = pytz.utc.localize(value).astimezone(pytz.timezone("America/Detroit"))
    return value.strftime("%Y-%m-%d %I:%M%p %Z").replace(" 0", " ").lower()
