"""Collect uploaded route paperwork and render it as a high-quality PDF appendix.

This powers spec item #9 of the document workflow: every photo or file a driver
attaches to a route (BOL, transfer sheet, route sheet, proof/damage photo, truck or
driver document) is gathered, labelled with what it is attached to, and embedded in
the printable route packet at full resolution so it can be reviewed or printed later.
No AI/OCR is involved -- the appendix simply preserves the captured images.
"""
import os

import pytz
from flask import current_app

DETROIT_TZ = pytz.timezone("America/Detroit")


def _upload_dir():
    upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
    return os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root))


def _photo_path(photo):
    if not photo or not photo.filename:
        return None
    path = os.path.join(_upload_dir(), photo.filename)
    return path if os.path.isfile(path) else None


def _uploaded_label(uploaded_at):
    if not uploaded_at:
        return "Upload time not recorded"
    stamp = uploaded_at
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    local_stamp = stamp.astimezone(DETROIT_TZ)
    return local_stamp.strftime("%Y-%m-%d %I:%M%p %Z").replace(" 0", " ").lower()


def _review_label(review_status):
    status = (review_status or "review_optional").strip().lower()
    if status in ("review_optional", "optional", ""):
        return "Review optional"
    if status in ("review_needed", "needs_review", "needs review", "review needed"):
        return "Review needed"
    if status in ("reviewed", "verified", "approved"):
        return "Reviewed"
    return status.replace("_", " ").title()


def _owner_label(photo, log_index_by_id, plant_by_log_id):
    owner_type = (photo.owner_type or "").strip().lower()
    owner_id = (photo.owner_id or "").strip()
    if owner_type in ("", "stop"):
        index = log_index_by_id.get(photo.driver_log_id)
        plant = plant_by_log_id.get(photo.driver_log_id)
        if index:
            return f"Stop {index}" + (f" · {plant}" if plant else "")
        return f"Stop · {plant}" if plant else "Stop"
    if owner_type == "truck":
        return f"Truck {owner_id}" if owner_id else "Truck"
    if owner_type == "driver":
        return "Driver record"
    if owner_type == "route":
        return "Route packet"
    if owner_type == "load":
        return f"Load {owner_id}" if owner_id else "Load"
    if owner_type == "transfer":
        return f"Transfer sheet {owner_id}" if owner_id else "Transfer sheet"
    if owner_type == "issue":
        return f"Issue {owner_id}" if owner_id else "Issue"
    return owner_type.title() + (f" {owner_id}" if owner_id else "") if owner_type else "Route"


def collect_route_documents(logs, *, plant_label=None):
    """Return one entry per uploaded document across the route's logs.

    Each entry holds the resolved file path (or None when the file is missing), the
    human document-type label, what it is attached to, who uploaded it and when, the
    review status, and any optional note.
    """
    logs = list(logs or [])
    log_index_by_id = {}
    plant_by_log_id = {}
    for index, log in enumerate(logs, start=1):
        log_index_by_id[log.id] = index
        plant_by_log_id[log.id] = plant_label(log.plant_name) if plant_label else log.plant_name

    entries = []
    for log in logs:
        driver_name = log.driver.display_name if getattr(log, "driver", None) else "Driver"
        for photo in log.photos:
            uploader = photo.uploaded_by.display_name if getattr(photo, "uploaded_by", None) else driver_name
            entries.append(
                {
                    "photo": photo,
                    "path": _photo_path(photo),
                    "doc_label": photo.document_type_label,
                    "owner_label": _owner_label(photo, log_index_by_id, plant_by_log_id),
                    "uploaded_by": uploader,
                    "uploaded_label": _uploaded_label(photo.uploaded_at),
                    "review_label": _review_label(getattr(photo, "review_status", None)),
                    "note": (photo.note or "").strip(),
                    "file_available": bool(_photo_path(photo)),
                }
            )
    return entries


def render_document_appendix(pdf, entries, *, start_new_page, title="Route Documents"):
    """Render the collected documents onto ``pdf`` at high quality.

    ``start_new_page()`` must add a fresh page (with its header drawn) and return the
    starting y-coordinate. It is called for the first documents page and whenever the
    current page runs out of room. Returns the final y-coordinate (or None when there
    are no documents to render).
    """
    if not entries:
        return None

    y = start_new_page()
    pdf.text(36, y, f"{title} (uploaded paperwork)", size=11, bold=True)
    y -= 14
    y = pdf.multiline_text(
        36,
        y,
        "Full-resolution copies of every document attached to this route, retained so the "
        "paperwork can be reviewed or printed later. Fields are not auto-extracted.",
        width_chars=104,
        size=8,
        leading=10,
        max_lines=2,
    )
    y -= 12

    for entry in entries:
        if y < 380:
            y = start_new_page()
        pdf.text(36, y, f"{entry['doc_label']} — {entry['owner_label']}", size=10, bold=True)
        y -= 13
        y = pdf.multiline_text(
            36,
            y,
            f"Uploaded by {entry['uploaded_by']} · {entry['uploaded_label']} · {entry['review_label']}",
            width_chars=104,
            size=7,
            leading=9,
            max_lines=2,
        )
        if entry["note"]:
            y = pdf.multiline_text(36, y, f"Note: {entry['note']}", width_chars=104, size=7, leading=9, max_lines=2)
        y -= 4
        image_top = y
        drawn_height = pdf.image_file_fit(entry["path"], 36, image_top, 380, 300) if entry["path"] else 0.0
        if not drawn_height:
            pdf.rect(36, image_top - 96, 380, 96)
            pdf.multiline_text(
                42,
                image_top - 42,
                "Document image is missing from upload storage. Open the record in MoveDefense to review the original.",
                width_chars=62,
                size=8,
                leading=10,
                max_lines=3,
                bold=True,
            )
            drawn_height = 96
        y = image_top - drawn_height - 20
    return y
