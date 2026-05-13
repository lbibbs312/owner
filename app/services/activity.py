from app.extensions import db
from app.models import ActivityEvent


def record_activity(
    *,
    user_id,
    category,
    action,
    title,
    details=None,
    target_type=None,
    target_id=None,
    commit=True,
):
    event = ActivityEvent(
        user_id=user_id,
        category=category,
        action=action,
        title=title,
        details=details,
        target_type=target_type,
        target_id=target_id,
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    return event
