"""Session-backed registration access created from verified billing checkout."""

from flask import session

REGISTRATION_CHECKOUT_SESSION_KEY = "registration_checkout"


def store_registration_checkout(checkout):
    session[REGISTRATION_CHECKOUT_SESSION_KEY] = {
        "session_id": checkout.get("session_id", ""),
        "plan_key": checkout.get("plan_key", ""),
        "plan_name": checkout.get("plan_name", ""),
        "customer": checkout.get("customer", ""),
        "customer_email": checkout.get("customer_email", ""),
    }
    session.modified = True


def registration_checkout():
    checkout = session.get(REGISTRATION_CHECKOUT_SESSION_KEY)
    if not isinstance(checkout, dict):
        return None
    if not checkout.get("session_id") or not checkout.get("plan_key"):
        return None
    return checkout


def clear_registration_checkout():
    session.pop(REGISTRATION_CHECKOUT_SESSION_KEY, None)
    session.modified = True
