from datetime import datetime
import json

from flask import jsonify, request
from flask_login import current_user, login_required

from app.blueprints.drafts import bp
from app.extensions import db
from app.models import DraftEntry

_MAX_DRAFT_BYTES = 200_000


def _clean_text(value, limit):
    if value is None:
        return None
    return str(value)[:limit]


def _json_size(payload):
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


@bp.route("/autosave", methods=["GET"])
@login_required
def get_autosave():
    draft_key = (request.args.get("draft_key") or "").strip()
    if not draft_key:
        return jsonify({"found": False}), 400
    draft = DraftEntry.query.filter_by(user_id=current_user.id, draft_key=draft_key).first()
    if not draft:
        return jsonify({"found": False})
    return jsonify({
        "found": True,
        "draft_key": draft.draft_key,
        "payload": draft.payload or {},
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    })


@bp.route("/autosave", methods=["POST"])
@login_required
def save_autosave():
    data = request.get_json(silent=True) or {}
    draft_key = (data.get("draft_key") or "").strip()
    payload = data.get("payload")
    if not draft_key or not isinstance(payload, dict):
        return jsonify({"error": "draft_key and object payload are required"}), 400
    if _json_size(payload) > _MAX_DRAFT_BYTES:
        return jsonify({"error": "draft payload is too large"}), 413

    now = datetime.utcnow()
    draft = DraftEntry.query.filter_by(user_id=current_user.id, draft_key=draft_key).first()
    if draft is None:
        draft = DraftEntry(user_id=current_user.id, draft_key=draft_key, created_at=now)
    draft.form_id = _clean_text(data.get("form_id"), 120)
    draft.path = _clean_text(data.get("path"), 500)
    draft.payload = payload
    draft.updated_at = now
    db.session.add(draft)
    db.session.commit()
    return jsonify({
        "status": "saved",
        "draft_key": draft.draft_key,
        "updated_at": draft.updated_at.isoformat(),
    })


@bp.route("/clear", methods=["POST"])
@login_required
def clear_autosave():
    data = request.get_json(silent=True) or {}
    draft_key = (data.get("draft_key") or "").strip()
    if not draft_key:
        return jsonify({"error": "draft_key is required"}), 400
    DraftEntry.query.filter_by(user_id=current_user.id, draft_key=draft_key).delete()
    db.session.commit()
    return jsonify({"status": "cleared", "draft_key": draft_key})
