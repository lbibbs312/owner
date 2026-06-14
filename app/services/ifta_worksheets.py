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


def _format_number(value):
    if value is None:
        return None
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _format_unit(value, unit, *, commas=False):
    number = _format_number(value)
    if number is None:
        return None
    if commas:
        try:
            parsed = float(value)
            number = f"{parsed:,.0f}" if parsed.is_integer() else f"{parsed:,.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            pass
    return f"{number} {unit}"


def _format_money(value):
    if value is None:
        return None
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _label_date(value):
    return value.isoformat() if value else None


def _join_parts(*values, separator=" "):
    parts = [str(value).strip() for value in values if str(value or "").strip()]
    return separator.join(parts) or None


def _city_state(city, state):
    return _join_parts(city, state, separator=", ")


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
    trip_driver_supplied = any(
        getattr(trip, field) is not None
        for field in (
            "origin_city",
            "origin_state",
            "destination_city",
            "destination_state",
            "route_traveled",
            "total_trip_distance",
            "jurisdiction",
            "jurisdiction_distance",
            "taxable_distance",
            "nontaxable_distance",
            "toll_distance",
            "loaded_empty_deadhead",
            "beginning_odometer",
            "ending_odometer",
            "notes",
        )
    )
    if trip_driver_supplied:
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


def _trip_has_route_facts(row):
    return bool(
        _clean(row.origin_city)
        or _clean(row.origin_state)
        or _clean(row.destination_city)
        or _clean(row.destination_state)
        or _clean(row.route_traveled)
        or row.total_trip_distance is not None
    )


def _trip_has_jurisdiction_miles(row):
    return bool(_clean(row.jurisdiction) and row.jurisdiction_distance is not None and row.jurisdiction_distance > 0)


def _fuel_has_facts(fuel):
    return bool(
        fuel.purchase_date
        or _clean(fuel.seller_name)
        or _clean(fuel.seller_address)
        or _clean(fuel.city)
        or _clean(fuel.state_or_province)
        or fuel.gallons_or_liters is not None
        or _clean(fuel.fuel_type)
        or fuel.total_sale_amount is not None
        or fuel.price_per_gallon_or_liter is not None
        or _clean(fuel.vehicle_unit_number)
        or _clean(fuel.purchaser_name)
        or ifta_receipt_available(fuel)
    )


def _fuel_review_label(fuel):
    label = _join_parts(_label_date(fuel.purchase_date), fuel.city or fuel.seller_name or fuel.seller_address)
    if label:
        return f"{label} fuel record"
    if fuel.id:
        return f"fuel record #{fuel.id}"
    return "fuel record"


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
    total_sale_amount = 0.0

    for row in worksheet.trip_rows:
        if _trip_has_jurisdiction_miles(row):
            jurisdiction = row.jurisdiction
            miles = row.jurisdiction_distance
            miles_by_jurisdiction[jurisdiction] = miles_by_jurisdiction.get(jurisdiction, 0) + miles
            taxable_by_jurisdiction[jurisdiction] = taxable_by_jurisdiction.get(jurisdiction, 0) + (row.taxable_distance or 0)
            nontaxable_by_jurisdiction[jurisdiction] = nontaxable_by_jurisdiction.get(jurisdiction, 0) + (row.nontaxable_distance or 0)
        total_distance += row.total_trip_distance or 0
        if _trip_has_route_facts(row) and (row.beginning_odometer is None or row.ending_odometer is None):
            missing_odometer_rows.append(row)
        if _trip_has_route_facts(row) and not _trip_has_jurisdiction_miles(row):
            missing_jurisdiction_distance_rows.append(row)

    for row in worksheet.fuel_records:
        gallons = row.gallons_or_liters or 0
        if row.state_or_province and gallons > 0:
            jurisdiction = row.state_or_province
            fuel_by_jurisdiction[jurisdiction] = fuel_by_jurisdiction.get(jurisdiction, 0) + gallons
        if row.fuel_type and gallons > 0:
            fuel_type = row.fuel_type
            fuel_by_type[fuel_type] = fuel_by_type.get(fuel_type, 0) + gallons
        total_fuel += gallons
        total_sale_amount += row.total_sale_amount or 0
        if not ifta_receipt_available(row):
            missing_receipt_rows.append(row)

    return {
        "total_distance": total_distance,
        "total_fuel": total_fuel,
        "total_sale_amount": total_sale_amount,
        "total_miles_by_jurisdiction": miles_by_jurisdiction,
        "taxable_miles_by_jurisdiction": taxable_by_jurisdiction,
        "nontaxable_miles_by_jurisdiction": nontaxable_by_jurisdiction,
        "total_fuel_purchased_by_jurisdiction": fuel_by_jurisdiction,
        "total_gallons_liters_by_fuel_type": fuel_by_type,
        "average_mpg_estimate": round(total_distance / total_fuel, 2) if total_distance and total_fuel else None,
        "missing_odometer_rows": missing_odometer_rows,
        "missing_receipt_rows": missing_receipt_rows,
        "missing_jurisdiction_distance_rows": missing_jurisdiction_distance_rows,
    }


def ifta_open_items(worksheet):
    summaries = worksheet_summaries(worksheet)
    items = []
    if not _clean(worksheet.base_jurisdiction):
        items.append("Add base jurisdiction.")
    if not _clean(worksheet.carrier_name):
        items.append("Add carrier name.")
    if not _clean(worksheet.ifta_license_number):
        items.append("Add IFTA license number, if applicable.")
    for fuel in worksheet.fuel_records:
        if not _fuel_has_facts(fuel):
            continue
        label = _fuel_review_label(fuel)
        if fuel.gallons_or_liters is None:
            items.append(f"Add gallons for {label}.")
        if not ifta_receipt_available(fuel):
            items.append(f"Attach receipt photo for {label}.")
    if not worksheet.trip_rows or not any(_trip_has_jurisdiction_miles(row) for row in worksheet.trip_rows):
        items.append("Add jurisdiction mileage before using this worksheet for IFTA review.")
    if not worksheet.trip_rows or not any(_trip_has_route_facts(row) for row in worksheet.trip_rows):
        items.append("Add trip origin/destination or route miles.")
    elif summaries["missing_jurisdiction_distance_rows"]:
        items.append("Add jurisdiction mileage for recorded trip rows.")
    if summaries["missing_odometer_rows"]:
        items.append("Add beginning and ending odometer for recorded trip rows.")
    if not worksheet.manager_signature and worksheet.review_status == "Closed":
        items.append("Add manager signature before closing this worksheet.")
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
        if not _fuel_has_facts(fuel):
            continue
        receipt_available = ifta_receipt_available(fuel)
        receipt_ext = os.path.splitext(fuel.receipt_photo or "")[1].lower()
        receipt_is_image = receipt_available and (
            receipt_ext in IMAGE_RECEIPT_EXTENSIONS
            or (getattr(fuel, "receipt_mimetype", None) or "").startswith("image/")
        )
        location = _city_state(fuel.city, fuel.state_or_province)
        facts = [
            ("Date", _label_date(fuel.purchase_date)),
            ("Seller", fuel.seller_name),
            ("Address", fuel.seller_address),
            ("Location", location),
            ("Gallons or liters", _format_number(fuel.gallons_or_liters)),
            ("Fuel type", fuel.fuel_type),
            ("Tax paid", fuel.tax_paid),
            ("Total sale", f"${fuel.total_sale_amount:.2f}" if fuel.total_sale_amount is not None else None),
            ("Vehicle unit", fuel.vehicle_unit_number),
            ("Purchaser", fuel.purchaser_name),
        ]
        receipt_status = "Attached" if receipt_available else "Missing"
        rows.append(
            {
                "number": index,
                "fuel": fuel,
                "label": fuel.seller_name or location or fuel.fuel_type or f"Fuel record #{index}",
                "date": _label_date(fuel.purchase_date),
                "seller": fuel.seller_name,
                "address": fuel.seller_address,
                "location": location,
                "volume": _format_unit(fuel.gallons_or_liters, "gal/L"),
                "fuel_type": fuel.fuel_type,
                "amount": _format_money(fuel.total_sale_amount),
                "vehicle_unit": fuel.vehicle_unit_number,
                "purchaser": fuel.purchaser_name,
                "receipt_status": receipt_status,
                "facts": [(label, value) for label, value in facts if value not in (None, "")],
                "receipt_available": receipt_available,
                "receipt_is_image": receipt_is_image,
                "receipt_hash": fuel.receipt_hash,
                "receipt_photo": fuel.receipt_photo,
            }
        )
    return rows


def ifta_cover_fields(worksheet):
    quarter_year = _join_parts(worksheet.reporting_period_quarter, worksheet.reporting_year)
    fields = [
        ("Driver", worksheet.driver.display_name if worksheet.driver else None),
        ("Truck", worksheet.truck),
        ("Trailer", worksheet.trailer),
        ("VIN and unit", worksheet.vin_or_vehicle_unit_number),
        ("Fleet number", worksheet.fleet_number),
        ("Quarter and year", quarter_year),
    ]
    return [(label, value) for label, value in fields if value not in (None, "")]


def ifta_vehicle_fields(worksheet, summaries):
    fields = [
        ("Base jurisdiction", worksheet.base_jurisdiction),
        ("Carrier name", worksheet.carrier_name),
        ("IFTA license number", worksheet.ifta_license_number),
        ("Average MPG estimate", _format_number(summaries["average_mpg_estimate"])),
    ]
    return [(label, value) for label, value in fields if value not in (None, "")]


def ifta_distance_rows(summaries):
    rows = []
    for jurisdiction, miles in sorted(summaries["total_miles_by_jurisdiction"].items()):
        rows.append(
            {
                "jurisdiction": jurisdiction,
                "total_miles": _format_unit(miles, "mi"),
                "taxable_miles": _format_unit(summaries["taxable_miles_by_jurisdiction"].get(jurisdiction, 0), "mi"),
                "nontaxable_miles": _format_unit(summaries["nontaxable_miles_by_jurisdiction"].get(jurisdiction, 0), "mi"),
            }
        )
    return rows


def ifta_fuel_jurisdiction_rows(summaries):
    rows = []
    for jurisdiction, volume in sorted(summaries["total_fuel_purchased_by_jurisdiction"].items()):
        rows.append(
            {
                "jurisdiction": jurisdiction,
                "volume": _format_unit(volume, "gal/L"),
            }
        )
    return rows


def ifta_trip_rows(worksheet):
    rows = []
    for index, row in enumerate(worksheet.trip_rows, 1):
        if not _trip_has_route_facts(row):
            continue
        dates = _join_parts(_label_date(row.trip_start_date), _label_date(row.trip_end_date), separator=" to ")
        origin = _city_state(row.origin_city, row.origin_state)
        destination = _city_state(row.destination_city, row.destination_state)
        odometer = None
        if row.beginning_odometer is not None or row.ending_odometer is not None:
            odometer = _join_parts(_format_number(row.beginning_odometer), _format_number(row.ending_odometer), separator=" to ")
        jurisdiction = None
        if row.jurisdiction or row.jurisdiction_distance is not None:
            jurisdiction = _join_parts(row.jurisdiction, _format_unit(row.jurisdiction_distance, "mi"), separator=" - ")
        facts = [
            ("Dates", dates),
            ("Origin", origin),
            ("Destination", destination),
            ("Route", row.route_traveled),
            ("Odometer", odometer),
            ("Total distance", _format_unit(row.total_trip_distance, "mi")),
            ("Jurisdiction distance", jurisdiction),
            ("Notes", row.notes),
        ]
        rows.append(
            {
                "number": index,
                "dates": dates,
                "origin": origin,
                "destination": destination,
                "route": row.route_traveled,
                "odometer": odometer,
                "total_distance": _format_unit(row.total_trip_distance, "mi"),
                "jurisdiction": jurisdiction,
                "notes": row.notes,
                "facts": [(label, value) for label, value in facts if value not in (None, "")],
            }
        )
    return rows


def ifta_summary_cards(*, status, open_items, summaries, fuel_rows, receipt_rows, trip_rows, distance_rows):
    cards = [
        ("Review status", status),
        ("Open items", str(len(open_items))),
    ]
    if fuel_rows:
        cards.append(("Fuel records", str(len(fuel_rows))))
        if summaries["total_fuel"] > 0:
            cards.append(("Fuel volume", _format_unit(summaries["total_fuel"], "gal/L")))
        if summaries["total_sale_amount"] > 0:
            cards.append(("Fuel spend", _format_money(summaries["total_sale_amount"])))
        cards.append(("Receipts attached", f"{len(receipt_rows)} of {len(fuel_rows)}"))
    if trip_rows or distance_rows:
        cards.append(("Trip rows", str(len(trip_rows))))
        if summaries["total_distance"] > 0:
            cards.append(("Route miles", _format_unit(summaries["total_distance"], "mi")))
        if distance_rows:
            cards.append(("Jurisdictions", str(len(distance_rows))))
    return [(label, value) for label, value in cards if value not in (None, "")]


def _report_date_range(*rows):
    dates = []
    for row in rows:
        for value in row:
            if value:
                dates.append(value)
    dates = sorted(set(dates))
    if not dates:
        return None
    if len(dates) == 1:
        return _label_date(dates[0])
    return f"{_label_date(dates[0])} to {_label_date(dates[-1])}"


def _receipt_report_label(row):
    extension = os.path.splitext(row.get("receipt_photo") or "")[1].lower().lstrip(".")
    if extension:
        return f"Receipt image ({extension.upper()})" if extension in {"jpg", "jpeg", "png", "gif", "webp"} else f"Receipt file ({extension.upper()})"
    return "Receipt file"


def fuel_mileage_rows(worksheet):
    rows = []
    for index, row in enumerate(worksheet.trip_rows, 1):
        odometer = None
        if row.beginning_odometer is not None and row.ending_odometer is not None:
            odometer = f"{_format_unit(row.beginning_odometer, 'mi', commas=True)} to {_format_unit(row.ending_odometer, 'mi', commas=True)}"
        elif row.ending_odometer is not None:
            odometer = _format_unit(row.ending_odometer, "mi", commas=True)
        elif row.beginning_odometer is not None:
            odometer = _format_unit(row.beginning_odometer, "mi", commas=True)
        trip = _join_parts(_city_state(row.origin_city, row.origin_state), _city_state(row.destination_city, row.destination_state), separator=" to ")
        dates = _join_parts(_label_date(row.trip_start_date), _label_date(row.trip_end_date), separator=" to ")
        distance = _format_unit(row.total_trip_distance, "mi", commas=True)
        if not any((dates, trip, row.route_traveled, odometer, distance, row.notes)):
            continue
        rows.append(
            {
                "number": index,
                "dates": dates,
                "trip": trip,
                "route": row.route_traveled,
                "odometer": odometer,
                "distance": distance,
                "notes": row.notes,
            }
        )
    return rows


def fuel_mileage_summary_cards(summaries, fuel_rows, receipt_rows, mileage_rows):
    cards = [("Fuel records", str(len(fuel_rows)))]
    if summaries["total_fuel"] > 0:
        cards.append(("Fuel volume", _format_unit(summaries["total_fuel"], "gal/L", commas=True)))
    if summaries["total_sale_amount"] > 0:
        cards.append(("Fuel spend", _format_money(summaries["total_sale_amount"])))
    if fuel_rows:
        cards.append(("Receipt proof", f"{len(receipt_rows)} of {len(fuel_rows)} attached"))
    if summaries["total_distance"] > 0:
        cards.append(("Recorded miles", _format_unit(summaries["total_distance"], "mi", commas=True)))
    if mileage_rows:
        cards.append(("Mileage entries", str(len(mileage_rows))))
    return [(label, value) for label, value in cards if value not in (None, "")]


def build_fuel_mileage_report(worksheet, *, generated_by):
    generated_at = datetime.utcnow()
    summaries = worksheet_summaries(worksheet)
    fuel_rows = ifta_fuel_rows(worksheet)
    receipt_rows = [dict(row, receipt_report_label=_receipt_report_label(row)) for row in fuel_rows if row["receipt_available"]]
    mileage_rows = fuel_mileage_rows(worksheet)
    date_range = _report_date_range(
        [row["fuel"].purchase_date for row in fuel_rows],
        [row.trip_start_date for row in worksheet.trip_rows],
        [row.trip_end_date for row in worksheet.trip_rows],
    )
    quarter_year = _join_parts(worksheet.reporting_period_quarter, worksheet.reporting_year)
    vehicle_fields = [
        ("Driver", worksheet.driver.display_name if worksheet.driver else None),
        ("Date range", date_range),
        ("Quarter", quarter_year),
        ("Truck", worksheet.truck),
        ("Trailer", worksheet.trailer),
        ("Vehicle unit", worksheet.vin_or_vehicle_unit_number),
    ]
    return {
        "worksheet": worksheet,
        "document_number": f"FUEL-{worksheet.id:06d}",
        "report_title": "Fuel & Mileage Report",
        "generated_by": generated_by.display_name,
        "generated_at": _label_dt(generated_at),
        "summary_cards": fuel_mileage_summary_cards(summaries, fuel_rows, receipt_rows, mileage_rows),
        "vehicle_fields": [(label, value) for label, value in vehicle_fields if value not in (None, "")],
        "fuel_rows": fuel_rows,
        "receipt_rows": receipt_rows,
        "mileage_rows": mileage_rows,
        "has_receipts": bool(receipt_rows),
        "has_mileage": bool(mileage_rows),
    }


def build_ifta_packet(worksheet, *, generated_by):
    generated_at = datetime.utcnow()
    summaries = worksheet_summaries(worksheet)
    fuel_rows = ifta_fuel_rows(worksheet)
    receipt_rows = [row for row in fuel_rows if row["receipt_available"]]
    distance_rows = ifta_distance_rows(summaries)
    fuel_jurisdiction_rows = ifta_fuel_jurisdiction_rows(summaries)
    trip_rows = ifta_trip_rows(worksheet)
    open_items = ifta_open_items(worksheet)
    current_status = ifta_packet_status(worksheet)
    return {
        "worksheet": worksheet,
        "document_number": f"IFTA-{worksheet.id:06d}",
        "packet_type": "IFTA Support Worksheet",
        "packet_title": "IFTA Support Worksheet",
        "generated_by": generated_by.display_name,
        "generated_at": _label_dt(generated_at),
        "current_status": current_status,
        "open_items": open_items,
        "summary_cards": ifta_summary_cards(
            status=current_status,
            open_items=open_items,
            summaries=summaries,
            fuel_rows=fuel_rows,
            receipt_rows=receipt_rows,
            trip_rows=trip_rows,
            distance_rows=distance_rows,
        ),
        "summaries": summaries,
        "cover_fields": ifta_cover_fields(worksheet),
        "vehicle_fields": ifta_vehicle_fields(worksheet, summaries),
        "distance_rows": distance_rows,
        "fuel_jurisdiction_rows": fuel_jurisdiction_rows,
        "fuel_rows": fuel_rows,
        "receipt_rows": receipt_rows,
        "trip_rows": trip_rows,
        "has_vehicle_summary": bool(ifta_vehicle_fields(worksheet, summaries)),
        "has_distance_summary": bool(distance_rows or fuel_jurisdiction_rows),
        "has_fuel_summary": bool(fuel_rows),
        "has_receipts": bool(receipt_rows),
        "has_trip_detail": bool(trip_rows),
        "raw_log_rows": [],
    }


def _label_dt(value):
    if not value:
        return "Not recorded"
    if value.tzinfo is None:
        value = pytz.utc.localize(value).astimezone(pytz.timezone("America/Detroit"))
    return value.strftime("%Y-%m-%d %I:%M%p %Z").replace(" 0", " ").lower()
