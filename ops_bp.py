"""Blueprint for transfer-tracking, exception/audit dashboards, and damage workflow.

Register this blueprint in ``lacksdrivers.py`` near the existing
``app.register_blueprint(manager_bp)`` call:

    from ops_bp import ops_bp
    app.register_blueprint(ops_bp)

Legacy edit/delete routes on PlantTransfer / DamageReport / DriverLog /
PreTrip should be migrated to call ``record_audit_event`` next; the new
routes below already do.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    url_for, send_from_directory,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models import (
    db,
    AuditEvent,
    DamagePhoto,
    DamageReport,
    PlantTransfer,
    PlantTransferLine,
)
from services_ops import (
    DEFAULT_DOCK_DELAY_MINUTES,
    build_delay_report,
    build_exception_items,
    build_weekly_savings,
    model_snapshot,
    record_audit_event,
    record_activity,
)

ops_bp = Blueprint("ops_bp", __name__)

ALLOWED_PHOTO_EXT = {"png", "jpg", "jpeg", "gif", "webp", "heic"}

TRANSFER_FIELDS = (
    "transfer_number", "transfer_date", "ship_to", "ship_from",
    "trailer_number", "driver_name", "driver_initials",
    "transfer_time", "loaded_by",
)


def _management_only():
    if not current_user.is_authenticated or getattr(current_user, "role", "") != "management":
        flash("Management only!", "danger")
        return redirect(url_for("dashboard"))
    return None


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _parse_date(raw: str) -> date:
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _parse_int(raw):
    try:
        return int(raw) if raw not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _collect_lines(form) -> list[dict]:
    """Pull repeater lines out of the form.

    Expects form keys named ``line_<i>_side``, ``line_<i>_part_number``, etc.
    Empty lines (no part_number AND no quantity AND no remarks) are skipped.
    """
    lines: list[dict] = []
    indices = set()
    for key in form.keys():
        if key.startswith("line_") and "_" in key[5:]:
            try:
                idx = int(key.split("_")[1])
                indices.add(idx)
            except (ValueError, IndexError):
                continue
    for idx in sorted(indices):
        part = (form.get(f"line_{idx}_part_number") or "").strip()
        qty = _parse_int(form.get(f"line_{idx}_quantity"))
        skids = _parse_int(form.get(f"line_{idx}_skids"))
        remarks = (form.get(f"line_{idx}_remarks") or "").strip()
        if not part and qty is None and skids is None and not remarks:
            continue
        side = (form.get(f"line_{idx}_side") or "left").strip().lower()
        if side not in ("left", "right"):
            side = "left"
        is_hot = form.get(f"line_{idx}_is_hot") in ("1", "true", "on", "yes")
        lines.append({
            "line_number": len(lines) + 1,
            "side": side,
            "part_number": part or None,
            "quantity": qty,
            "skids": skids,
            "remarks": remarks or None,
            "is_hot": is_hot,
        })
    return lines


# ---------------------------------------------------------------------------
# Transfer create / edit
# ---------------------------------------------------------------------------

@ops_bp.route("/transfers", methods=["GET"])
@login_required
def list_transfers():
    transfers = (
        PlantTransfer.query
        .filter(PlantTransfer.deleted_at.is_(None))
        .order_by(PlantTransfer.transfer_date.desc(), PlantTransfer.id.desc())
        .limit(200)
        .all()
    )
    return render_template("transfer_list.html", transfers=transfers)


@ops_bp.route("/transfers/new", methods=["GET"])
@login_required
def new_transfer():
    return render_template("transfer_form.html", transfer=None, lines=[])


@ops_bp.route("/transfers", methods=["POST"])
@login_required
def create_transfer():
    form = request.form
    t = PlantTransfer(
        user_id=current_user.id,
        transfer_number=(form.get("transfer_number") or "").strip() or None,
        transfer_date=_parse_date(form.get("transfer_date")),
        ship_to=(form.get("ship_to") or "").strip() or None,
        ship_from=(form.get("ship_from") or "").strip() or None,
        trailer_number=(form.get("trailer_number") or "").strip() or None,
        driver_name=(form.get("driver_name") or "").strip() or None,
        driver_initials=(form.get("driver_initials") or "").strip() or None,
        transfer_time=(form.get("transfer_time") or "").strip() or None,
        loaded_by=(form.get("loaded_by") or "").strip() or None,
    )
    db.session.add(t)
    db.session.flush()  # need t.id

    for line_data in _collect_lines(form):
        db.session.add(PlantTransferLine(plant_transfer_id=t.id, **line_data))

    record_audit_event(
        user_id=current_user.id,
        target_type="plant_transfer",
        target_id=t.id,
        action="create",
        reason="created via ops_bp.create_transfer",
        before_values=None,
        after_values=model_snapshot(t, TRANSFER_FIELDS),
    )
    record_activity(
        user_id=current_user.id,
        category="transfer",
        action="create",
        title=f"Transfer #{t.transfer_number or t.id} created",
        details=f"{t.ship_from or '?'} -> {t.ship_to or '?'}",
        target_type="plant_transfer",
        target_id=t.id,
    )
    db.session.commit()
    flash("Transfer saved.", "success")
    return redirect(url_for("ops_bp.list_transfers"))


@ops_bp.route("/transfers/<int:tid>/edit", methods=["GET"])
@login_required
def edit_transfer(tid: int):
    t = PlantTransfer.query.get_or_404(tid)
    if t.deleted_at is not None:
        abort(404)
    return render_template("transfer_form.html", transfer=t, lines=t.lines)


@ops_bp.route("/transfers/<int:tid>", methods=["POST"])
@login_required
def update_transfer(tid: int):
    t = PlantTransfer.query.get_or_404(tid)
    if t.deleted_at is not None:
        abort(404)

    edit_reason = (request.form.get("edit_reason") or "").strip()
    if not edit_reason:
        flash("Edit reason is required.", "danger")
        return redirect(url_for("ops_bp.edit_transfer", tid=tid))

    before = model_snapshot(t, TRANSFER_FIELDS)
    form = request.form
    t.transfer_number = (form.get("transfer_number") or "").strip() or None
    t.transfer_date = _parse_date(form.get("transfer_date"))
    t.ship_to = (form.get("ship_to") or "").strip() or None
    t.ship_from = (form.get("ship_from") or "").strip() or None
    t.trailer_number = (form.get("trailer_number") or "").strip() or None
    t.driver_name = (form.get("driver_name") or "").strip() or None
    t.driver_initials = (form.get("driver_initials") or "").strip() or None
    t.transfer_time = (form.get("transfer_time") or "").strip() or None
    t.loaded_by = (form.get("loaded_by") or "").strip() or None

    # Replace lines wholesale (simpler, matches single-form-post UX).
    for old in list(t.lines):
        db.session.delete(old)
    db.session.flush()
    for line_data in _collect_lines(form):
        db.session.add(PlantTransferLine(plant_transfer_id=t.id, **line_data))

    after = model_snapshot(t, TRANSFER_FIELDS)
    record_audit_event(
        user_id=current_user.id,
        target_type="plant_transfer",
        target_id=t.id,
        action="update",
        reason=edit_reason,
        before_values=before,
        after_values=after,
    )
    db.session.commit()
    flash("Transfer updated.", "success")
    return redirect(url_for("ops_bp.list_transfers"))


# ---------------------------------------------------------------------------
# Manager dashboards
# ---------------------------------------------------------------------------

@ops_bp.route("/manager/exceptions", methods=["GET"])
@login_required
def manager_exceptions():
    guard = _management_only()
    if guard:
        return guard
    threshold = _parse_int(request.args.get("threshold")) or DEFAULT_DOCK_DELAY_MINUTES
    items = build_exception_items(dock_delay_minutes=threshold)
    grouped: dict[str, list] = {"high": [], "medium": [], "low": []}
    for it in items:
        grouped.setdefault(it.get("severity", "low"), []).append(it)
    return render_template(
        "manager_exceptions.html", grouped=grouped, threshold=threshold,
    )


@ops_bp.route("/manager/review", methods=["GET"])
@login_required
def manager_review():
    guard = _management_only()
    if guard:
        return guard
    metrics = build_weekly_savings()
    return render_template("manager_review.html", metrics=metrics)


@ops_bp.route("/manager/savings", methods=["GET"])
@login_required
def manager_savings():
    guard = _management_only()
    if guard:
        return guard
    metrics = build_weekly_savings()
    return render_template("manager_weekly_savings.html", metrics=metrics)


@ops_bp.route("/manager/delays", methods=["GET"])
@login_required
def manager_delays():
    guard = _management_only()
    if guard:
        return guard
    threshold = _parse_int(request.args.get("threshold")) or DEFAULT_DOCK_DELAY_MINUTES
    report = build_delay_report(dock_delay_minutes=threshold)
    return render_template("manager_delays.html", report=report)


@ops_bp.route("/manager/audit", methods=["GET"])
@login_required
def manager_audit():
    guard = _management_only()
    if guard:
        return guard
    page = max(_parse_int(request.args.get("page")) or 1, 1)
    per_page = 50
    q = AuditEvent.query
    target_type = request.args.get("target_type")
    target_id = _parse_int(request.args.get("target_id"))
    if target_type:
        q = q.filter(AuditEvent.target_type == target_type)
    if target_id is not None:
        q = q.filter(AuditEvent.target_id == target_id)
    q = q.order_by(AuditEvent.created_at.desc())
    events = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(events) > per_page
    events = events[:per_page]
    return render_template(
        "manager_audit.html",
        events=events,
        page=page,
        has_next=has_next,
        target_type=target_type or "",
        target_id=target_id or "",
    )


# ---------------------------------------------------------------------------
# Damage workflow
# ---------------------------------------------------------------------------

def _damage_upload_dir(damage_id: int) -> str:
    static_root = os.path.join(current_app.root_path, "static", "uploads", "damage", str(damage_id))
    os.makedirs(static_root, exist_ok=True)
    return static_root


@ops_bp.route("/damage/new", methods=["GET"])
@login_required
def new_damage_report():
    return render_template("damage_report_form.html", report=None)


@ops_bp.route("/damage/new", methods=["POST"])
@login_required
def create_damage_report():
    form = request.form
    d = DamageReport(
        reported_by_id=current_user.id,
        truck_number=(form.get("truck_number") or "").strip() or None,
        trailer_number=(form.get("trailer_number") or "").strip() or None,
        plant_name=(form.get("plant_name") or "").strip() or None,
        damage_time=(form.get("damage_time") or "").strip() or None,
        stage=(form.get("stage") or "").strip() or None,
        move_reference=(form.get("move_reference") or "").strip() or None,
        description=(form.get("description") or "").strip() or None,
        driver_log_id=_parse_int(form.get("driver_log_id")),
        pretrip_id=_parse_int(form.get("pretrip_id")),
        plant_transfer_id=_parse_int(form.get("plant_transfer_id")),
        status="open",
    )
    db.session.add(d)
    db.session.flush()

    # Photos: stored under static/uploads/damage/<id>/<uuid>.<ext>
    photos = request.files.getlist("photos")
    upload_dir = _damage_upload_dir(d.id)
    for f in photos:
        if not f or not f.filename:
            continue
        ext = _ext(f.filename)
        if ext not in ALLOWED_PHOTO_EXT:
            continue
        new_name = f"{uuid.uuid4().hex}.{ext}"
        rel_path = os.path.join("uploads", "damage", str(d.id), new_name).replace("\\", "/")
        full_path = os.path.join(upload_dir, new_name)
        f.save(full_path)
        db.session.add(DamagePhoto(
            damage_report_id=d.id,
            stage=d.stage,
            filename=rel_path,
            original_filename=secure_filename(f.filename),
            content_type=f.mimetype,
        ))

    record_audit_event(
        user_id=current_user.id,
        target_type="damage_report",
        target_id=d.id,
        action="create",
        reason="created via ops_bp.create_damage_report",
        before_values=None,
        after_values=model_snapshot(d, (
            "truck_number", "trailer_number", "plant_name", "stage",
            "move_reference", "description", "status",
        )),
    )
    db.session.commit()
    flash("Damage report saved.", "success")
    return redirect(url_for("ops_bp.view_damage_report", did=d.id))


@ops_bp.route("/damage/<int:did>", methods=["GET"])
@login_required
def view_damage_report(did: int):
    d = DamageReport.query.get_or_404(did)
    photos_by_stage: dict[str, list] = {}
    for p in d.photos:
        photos_by_stage.setdefault(p.stage or "unknown", []).append(p)
    return render_template(
        "damage_report_detail.html", report=d, photos_by_stage=photos_by_stage,
    )


@ops_bp.route("/damage/<int:did>/close", methods=["POST"])
@login_required
def close_damage_report(did: int):
    d = DamageReport.query.get_or_404(did)
    edit_reason = (request.form.get("edit_reason") or "closed").strip()
    before = model_snapshot(d, ("status", "resolved_at"))
    d.status = "closed"
    d.resolved_at = datetime.utcnow()
    after = model_snapshot(d, ("status", "resolved_at"))
    record_audit_event(
        user_id=current_user.id,
        target_type="damage_report",
        target_id=d.id,
        action="close",
        reason=edit_reason,
        before_values=before,
        after_values=after,
    )
    db.session.commit()
    flash("Damage report closed.", "success")
    return redirect(url_for("ops_bp.view_damage_report", did=d.id))
