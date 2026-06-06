from __future__ import annotations

from datetime import datetime
import os
from uuid import uuid4

import pytz
from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AccidentIncidentReport, AccidentWitness, ProofMediaFile
from app.services.file_integrity import sha256_file
from app.services.packet_classification import PacketClassification


YES_VALUES = {"yes", "y", "true", "1", "on"}
ACCIDENT_MEDIA_CATEGORIES = (
    "scene_wide",
    "company_vehicle_front",
    "company_vehicle_rear",
    "company_vehicle_left",
    "company_vehicle_right",
    "damage_closeup",
    "plate_or_unit_number",
    "other_vehicle",
    "property_damage",
    "cargo_damage",
    "police_report",
    "insurance_document",
    "fuel_receipt",
    "odometer_photo",
    "other",
)
ACCIDENT_TRIGGER_FIELDS = (
    "crash",
    "hit",
    "anyone_hurt",
    "injury_reported",
    "tow_away_needed",
    "tow_away",
    "police_called_quick",
    "police_called",
    "other_vehicle_involved_quick",
    "other_vehicle_involved",
    "property_damage_quick",
    "property_damage",
    "claim_expected",
)


def _truthy(value):
    return str(value or "").strip().lower() in YES_VALUES


def _clean(value, default=None):
    value = (value or "").strip()
    return value or default


def _parse_datetime(value):
    value = _clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                return parsed
            return parsed
        except ValueError:
            continue
    return None


def accident_form_required(packet_type=None, answers=None):
    answers = answers or {}
    if packet_type == PacketClassification.ACCIDENT_INCIDENT.value:
        return True
    for field in ACCIDENT_TRIGGER_FIELDS:
        if _truthy(answers.get(field)):
            return True
    return False


def _packet_upload_path():
    upload_root = current_app.config.get("PACKET_UPLOAD_FOLDER", "uploads/packet_media")
    upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))
    os.makedirs(upload_path, exist_ok=True)
    return upload_path


def save_packet_media(uploaded_file, *, packet_type, owner_type, owner_id, category, uploaded_by, related=None, note=None):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        return None
    category = category if category in ACCIDENT_MEDIA_CATEGORIES else "other"
    original = secure_filename(uploaded_file.filename) or "packet-file"
    _, ext = os.path.splitext(original)
    filename = f"{packet_type}-{owner_type}-{owner_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex}{ext or '.bin'}"
    stored_path = os.path.join(_packet_upload_path(), filename)
    uploaded_file.save(stored_path)
    related = related or {}
    media = ProofMediaFile(
        packet_type=packet_type,
        owner_type=owner_type,
        owner_id=owner_id,
        category=category,
        filename=filename,
        original_filename=original,
        content_type=getattr(uploaded_file, "mimetype", None) or getattr(uploaded_file, "content_type", None),
        sha256_hash=sha256_file(stored_path),
        uploaded_by_id=getattr(uploaded_by, "id", None),
        related_truck=related.get("truck"),
        related_trailer=related.get("trailer"),
        related_route_id=related.get("route_id"),
        related_stop_id=related.get("stop_id"),
        manager_note=note,
    )
    db.session.add(media)
    return media


def create_accident_report_from_form(form, files, *, user, damage_report=None, driver_log=None):
    now = datetime.utcnow()
    driver = getattr(damage_report, "reported_by", None) or getattr(driver_log, "driver", None) or user
    report = AccidentIncidentReport(
        damage_report_id=getattr(damage_report, "id", None),
        driver_log_id=getattr(driver_log, "id", None),
        stop_id=getattr(driver_log, "id", None),
        driver_id=getattr(driver, "id", None),
        created_by_id=user.id,
        updated_by_id=user.id,
        incident_date_time=_parse_datetime(form.get("incident_date_time")),
        reported_date_time=_parse_datetime(form.get("reported_date_time")) or now,
        truck=_clean(form.get("truck")) or getattr(damage_report, "truck_number", None) or None,
        trailer=_clean(form.get("trailer")) or getattr(damage_report, "trailer_number", None) or None,
        route_id=_clean(form.get("route_id")),
        plant_or_location=_clean(form.get("plant_or_location")) or getattr(damage_report, "plant_name", None) or getattr(driver_log, "plant_name", None),
        exact_location_text=_clean(form.get("exact_location_text")),
        gps_latitude=_float_or_none(form.get("gps_latitude")),
        gps_longitude=_float_or_none(form.get("gps_longitude")),
        public_road_private_property_yard_dock=_clean(form.get("public_road_private_property_yard_dock")),
        city=_clean(form.get("city")),
        state=_clean(form.get("state")),
        nearest_city_or_town=_clean(form.get("nearest_city_or_town")),
        weather=_clean(form.get("weather")),
        lighting=_clean(form.get("lighting")),
        surface_condition=_clean(form.get("surface_condition")),
        anyone_hurt=_clean(form.get("anyone_hurt"), "unknown"),
        other_vehicle_involved_quick=_clean(form.get("other_vehicle_involved_quick"), "unknown"),
        property_damage_quick=_clean(form.get("property_damage_quick"), "unknown"),
        police_called_quick=_clean(form.get("police_called_quick"), "unknown"),
        tow_away_needed=_clean(form.get("tow_away_needed"), "unknown"),
        vehicle_safe_to_operate_quick=_clean(form.get("vehicle_safe_to_operate_quick"), "needs_review"),
        manager_notified_quick=_clean(form.get("manager_notified_quick"), "no"),
        hit_object=_truthy(form.get("hit_object")),
        hit_by_third_party=_truthy(form.get("hit_by_third_party")),
        backing_incident=_truthy(form.get("backing_incident")),
        dock_or_yard_incident=_truthy(form.get("dock_or_yard_incident")),
        cargo_damage=_truthy(form.get("cargo_damage")),
        vehicle_damage=_truthy(form.get("vehicle_damage")),
        property_damage=_truthy(form.get("property_damage")),
        injury_reported=_truthy(form.get("injury_reported")),
        tow_away=_truthy(form.get("tow_away")),
        police_called=_clean(form.get("police_called"), "unknown"),
        other_vehicle_involved=_truthy(form.get("other_vehicle_involved")),
        claim_expected=_truthy(form.get("claim_expected")),
        other_incident_type=_truthy(form.get("other_incident_type")),
        driver_statement=_clean(form.get("driver_statement")),
        facts_only_acknowledgement=_truthy(form.get("facts_only_acknowledgement")),
        company_vehicle_damage_description=_clean(form.get("company_vehicle_damage_description")),
        other_vehicle_damage_description=_clean(form.get("other_vehicle_damage_description")),
        property_damage_description=_clean(form.get("property_damage_description")),
        cargo_damage_description=_clean(form.get("cargo_damage_description")),
        visible_damage_location=_clean(form.get("visible_damage_location")),
        vehicle_safe_to_operate=_clean(form.get("vehicle_safe_to_operate"), "needs_review"),
        repair_needed=_clean(form.get("repair_needed"), "needs_review"),
        vehicle_removed_from_service=_clean(form.get("vehicle_removed_from_service"), "needs_review"),
        other_driver_name=_clean(form.get("other_driver_name")),
        other_driver_phone=_clean(form.get("other_driver_phone")),
        other_driver_license_number=_clean(form.get("other_driver_license_number")),
        other_vehicle_make_model=_clean(form.get("other_vehicle_make_model")),
        other_vehicle_plate=_clean(form.get("other_vehicle_plate")),
        other_insurance_company=_clean(form.get("other_insurance_company")),
        other_policy_or_claim_number=_clean(form.get("other_policy_or_claim_number")),
        other_party_notes=_clean(form.get("other_party_notes")),
        police_agency=_clean(form.get("police_agency")),
        police_report_number=_clean(form.get("police_report_number")),
        citation_issued=_clean(form.get("citation_issued"), "unknown"),
        citation_to_company_driver=_clean(form.get("citation_to_company_driver"), "unknown"),
        claim_opened=_clean(form.get("claim_opened"), "no"),
        claim_number=_clean(form.get("claim_number")),
        insurance_company=_clean(form.get("insurance_company")),
        insurance_contact=_clean(form.get("insurance_contact")),
        insurer_notified_at=_parse_datetime(form.get("insurer_notified_at")),
        claim_notes=_clean(form.get("claim_notes")),
        public_road_in_commerce=_clean(form.get("public_road_in_commerce"), "unknown"),
        fatality=_clean(form.get("fatality"), "unknown"),
        number_of_injuries=_int_or_none(form.get("number_of_injuries")),
        number_of_fatalities=_int_or_none(form.get("number_of_fatalities")),
        medical_treatment_away_from_scene=_clean(form.get("medical_treatment_away_from_scene"), "unknown"),
        disabling_damage_tow_away=_clean(form.get("disabling_damage_tow_away"), "unknown"),
        hazmat_released_other_than_fuel=_clean(form.get("hazmat_released_other_than_fuel"), "unknown"),
        required_reports_attached=_clean(form.get("required_reports_attached"), "unknown"),
        loading_or_unloading_only=_clean(form.get("loading_or_unloading_only"), "unknown"),
        boarding_or_alighting_only=_clean(form.get("boarding_or_alighting_only"), "unknown"),
        dot_review_status=_clean(form.get("dot_review_status"), "not_indicated"),
        dot_review_note=_clean(form.get("dot_review_note")),
        driver_performing_safety_sensitive_function=_clean(form.get("driver_performing_safety_sensitive_function"), "unknown"),
        loss_of_human_life=_clean(form.get("loss_of_human_life"), "unknown"),
        moving_violation_citation=_clean(form.get("moving_violation_citation"), "unknown"),
        citation_time=_parse_datetime(form.get("citation_time")),
        bodily_injury_treatment_away_from_scene=_clean(form.get("bodily_injury_treatment_away_from_scene"), "unknown"),
        tow_away_disabling_damage=_clean(form.get("tow_away_disabling_damage"), "unknown"),
        alcohol_test_review=_clean(form.get("alcohol_test_review"), "not_indicated"),
        alcohol_test_time=_parse_datetime(form.get("alcohol_test_time")),
        alcohol_delay_reason=_clean(form.get("alcohol_delay_reason")),
        controlled_substance_test_review=_clean(form.get("controlled_substance_test_review"), "not_indicated"),
        controlled_substance_test_time=_parse_datetime(form.get("controlled_substance_test_time")),
        controlled_substance_delay_reason=_clean(form.get("controlled_substance_delay_reason")),
        manager_notified=_clean(form.get("manager_notified"), "no"),
        manager_notified_at=_parse_datetime(form.get("manager_notified_at")),
        dispatcher_notified=_clean(form.get("dispatcher_notified"), "no"),
        dispatcher_notified_at=_parse_datetime(form.get("dispatcher_notified_at")),
        replacement_vehicle_needed=_clean(form.get("replacement_vehicle_needed"), "no"),
        driver_relieved_from_route=_clean(form.get("driver_relieved_from_route"), "no"),
        photos_required_complete=_clean(form.get("photos_required_complete"), "no"),
        follow_up_notes=_clean(form.get("follow_up_notes")),
        manager_review_status=_clean(form.get("manager_review_status"), "open"),
        claim_review_status=_clean(form.get("claim_review_status"), "not_indicated"),
        close_status=_clean(form.get("close_status"), "Needs more information"),
        manager_note=_clean(form.get("manager_note")),
        driver_signature=_clean(form.get("driver_signature")),
        manager_signature=_clean(form.get("manager_signature")),
        created_at=now,
        updated_at=now,
    )
    db.session.add(report)
    db.session.flush()
    _add_witness_rows(report, form)
    related = {
        "truck": report.truck,
        "trailer": report.trailer,
        "route_id": report.route_id,
        "stop_id": report.stop_id,
    }
    for uploaded_file in files.getlist("photos"):
        save_packet_media(
            uploaded_file,
            packet_type="accident_incident",
            owner_type="accident_incident_report",
            owner_id=report.id,
            category=_clean(form.get("photo_category"), "other"),
            uploaded_by=user,
            related=related,
        )
    return report


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _add_witness_rows(report, form):
    names = form.getlist("witness_name")
    phones = form.getlist("witness_phone")
    summaries = form.getlist("witness_statement_summary")
    max_rows = max(len(names), len(phones), len(summaries), 0)
    for index in range(max_rows):
        name = _clean(names[index] if index < len(names) else None)
        phone = _clean(phones[index] if index < len(phones) else None)
        summary = _clean(summaries[index] if index < len(summaries) else None)
        if name or phone or summary:
            db.session.add(
                AccidentWitness(
                    accident_id=report.id,
                    witness_name=name,
                    witness_phone=phone,
                    witness_statement_summary=summary,
                )
            )


def accident_media(report):
    return (
        ProofMediaFile.query.filter_by(
            packet_type="accident_incident",
            owner_type="accident_incident_report",
            owner_id=report.id,
        )
        .order_by(ProofMediaFile.uploaded_at.asc(), ProofMediaFile.id.asc())
        .all()
    )


def accident_media_path(media):
    upload_path = os.path.join(_packet_upload_path(), media.filename)
    return upload_path if os.path.isfile(upload_path) else None


def dot_review_label(report):
    facts_need_review = any(
        value == "yes"
        for value in (
            report.public_road_in_commerce,
            report.fatality,
            report.medical_treatment_away_from_scene,
            report.disabling_damage_tow_away,
            report.hazmat_released_other_than_fuel,
        )
    )
    if report.dot_review_status == "reviewed":
        return "DOT review completed"
    return "DOT review needed" if facts_need_review else "DOT review not indicated from entered facts."


def testing_review_may_be_needed(report):
    return any(
        value == "yes"
        for value in (
            report.loss_of_human_life,
            report.moving_violation_citation,
            report.bodily_injury_treatment_away_from_scene,
            report.tow_away_disabling_damage,
        )
    ) or report.alcohol_test_review in {"needs_review", "ordered", "completed", "not_completed"} or report.controlled_substance_test_review in {"needs_review", "ordered", "completed", "not_completed"}


def accident_open_items(report, media=None):
    media = list(media if media is not None else accident_media(report))
    items = []
    if not media and report.photos_required_complete != "no":
        items.append("Photo not available")
    for item in media:
        if not accident_media_path(item) and not item.media_not_required_reason:
            items.append("Photo not available")
            break
    if report.manager_review_status != "closed":
        items.append("Manager review open")
    if not report.manager_signature:
        items.append("Manager signature not captured")
    if dot_review_label(report) == "DOT review needed":
        items.append("DOT review needed")
    if report.claim_expected or report.claim_opened == "yes" or report.claim_review_status == "needs_review":
        items.append("Claim review needed")
    if (report.police_called == "yes" or report.police_called_quick == "yes") and not report.police_report_number:
        items.append("Police report number missing")
    if report.other_vehicle_involved or report.other_vehicle_involved_quick == "yes":
        if not (report.other_driver_name and report.other_driver_phone):
            items.append("Other-party information incomplete")
    if not report.driver_statement:
        items.append("Driver statement missing")
    if report.vehicle_safe_to_operate in {None, "", "needs_review"} or report.vehicle_safe_to_operate_quick == "needs_review":
        items.append("Vehicle safe-to-operate review needed")
    return items


def accident_media_rows(report, media=None):
    rows = []
    for index, item in enumerate(list(media if media is not None else accident_media(report)), 1):
        file_available = bool(accident_media_path(item))
        rows.append(
            {
                "number": index,
                "media": item,
                "category": item.category,
                "original_filename": item.original_filename or item.filename,
                "stored_filename": item.filename,
                "uploaded_by": item.uploaded_by.display_name if item.uploaded_by else "MoveDefense",
                "uploaded_at": _label_dt(item.uploaded_at),
                "related_truck": item.related_truck or report.truck or "Not recorded",
                "related_trailer": item.related_trailer or report.trailer or "Not recorded",
                "related_route": item.related_route_id or report.route_id or "Not recorded",
                "related_stop": item.related_stop_id or report.stop_id or "Not recorded",
                "sha256_hash": item.sha256_hash or "Not recorded",
                "file_available": file_available,
                "file_status": "Available" if file_available else "Photo not available in upload storage",
                "manager_note": item.manager_note or "No manager note recorded",
            }
        )
    return rows


def accident_packet_status(report, media=None):
    if accident_open_items(report, media):
        return "Needs Review"
    if report.close_status == "Accepted as complete":
        return "Complete"
    return "Needs Review"


def build_accident_packet(report, *, generated_by):
    generated_at = datetime.utcnow()
    media = accident_media(report)
    media_rows = accident_media_rows(report, media)
    open_items = accident_open_items(report, media)
    return {
        "report": report,
        "document_number": f"ACCIDENT-{report.id:06d}",
        "packet_type": "Accident and Incident Packet",
        "generated_by": generated_by.display_name,
        "generated_at": _label_dt(generated_at),
        "current_status": accident_packet_status(report, media),
        "media": media_rows,
        "open_items": open_items,
        "dot_review_label": dot_review_label(report),
        "testing_review_visible": testing_review_may_be_needed(report),
        "chain": {
            "created_by": report.created_by.display_name if report.created_by else "MoveDefense",
            "created_at": _label_dt(report.created_at),
            "submitted_at": _label_dt(report.submitted_at) if report.submitted_at else "Not submitted",
            "driver_can_edit": "yes" if report.driver_can_edit else "no",
            "route_finalized": "yes" if report.route_finalized else "no",
            "locked_by": report.locked_by.display_name if report.locked_by else "Not locked",
            "locked_at": _label_dt(report.locked_at) if report.locked_at else "Not locked",
            "packet_generated_at": _label_dt(generated_at),
        },
    }


def _label_dt(value):
    if not value:
        return "Not recorded"
    if value.tzinfo is None:
        value = pytz.utc.localize(value).astimezone(pytz.timezone("America/Detroit"))
    return value.strftime("%Y-%m-%d %I:%M%p %Z").replace(" 0", " ").lower()
