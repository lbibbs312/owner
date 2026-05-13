from flask import session
from flask_login import current_user, login_user

from app.extensions import db
from app.models import User


ROLE_SESSION_KEYS = {
    "driver": "driver_user_id",
    "management": "management_user_id",
}


def remember_role_login(user):
    key = ROLE_SESSION_KEYS.get(user.role)
    if key:
        session[key] = str(user.id)


def clear_role_logins():
    for key in ROLE_SESSION_KEYS.values():
        session.pop(key, None)


def restore_role_user(required_role):
    if current_user.is_authenticated and current_user.role == required_role:
        remember_role_login(current_user)
        return True

    key = ROLE_SESSION_KEYS.get(required_role)
    user_id = session.get(key) if key else None
    if not user_id:
        return False

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        session.pop(key, None)
        return False

    user = db.session.get(User, user_id)
    if not user or user.role != required_role:
        session.pop(key, None)
        return False

    login_user(user)
    remember_role_login(user)
    return True
