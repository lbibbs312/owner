import json

from app.extensions import db
from app.models import AuditEvent


def model_snapshot(model, fields):
    return {field: getattr(model, field, None) for field in fields}


def record_audit_event(*, user_id, target_type, target_id, action, reason, before_values, after_values, commit=True):
    event = AuditEvent(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        reason=(reason or "Not provided").strip() or "Not provided",
        before_values=json.dumps(before_values, default=str, sort_keys=True),
        after_values=json.dumps(after_values, default=str, sort_keys=True),
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    return event
