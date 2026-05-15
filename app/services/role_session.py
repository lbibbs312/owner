from flask import session
from flask_login import current_user


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
    """Return True if the current request is authenticated as required_role.

    current_user is already resolved by the request_loader in auth/routes.py
    before before_request fires, so we only need to check it here.  There is
    no login_user() call: that would overwrite session['_user_id'] and break
    simultaneous driver + manager tabs in the same browser.
    """
    return current_user.is_authenticated and current_user.role == required_role
