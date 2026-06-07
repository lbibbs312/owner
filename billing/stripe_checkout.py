"""Stripe Checkout helpers for the Django MoveDefense scaffold."""

from __future__ import annotations

import importlib
from typing import Any

try:
    from django.urls import reverse
except Exception:  # pragma: no cover - keeps static analysis usable before Django is installed.
    reverse = None

from .plans import BillingPlan, billing_plan, config_bool, config_value

REGISTRATION_CHECKOUT_SESSION_KEY = "registration_checkout"
DEFAULT_STRIPE_API_VERSION = "2026-05-27.dahlia"


class StripeCheckoutError(RuntimeError):
    """Raised when Checkout cannot be created or verified safely."""


def _stripe_module():
    try:
        return importlib.import_module("stripe")
    except ImportError as exc:
        raise StripeCheckoutError("Stripe checkout is not installed on this server.") from exc


def _reverse_or_path(route_name: str, fallback_path: str) -> str:
    if reverse is None:
        return fallback_path
    try:
        return reverse(f"billing:{route_name}")
    except Exception:
        return fallback_path


def _public_base_url() -> str:
    for setting_name in ("PUBLIC_BASE_URL", "APP_URL", "BASE_URL", "PUBLIC_URL"):
        value = config_value(setting_name)
        if value:
            return value.rstrip("/")
    return ""


def _absolute_url(request, route_name: str, fallback_path: str) -> str:
    path = _reverse_or_path(route_name, fallback_path)
    base_url = _public_base_url()
    if base_url:
        return f"{base_url}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def _checkout_user(request=None, user=None):
    if user is not None:
        return user
    if request is None:
        return None
    return getattr(request, "user", None)


def create_checkout_session(plan_key: str, *, request=None, user=None) -> str:
    plan = billing_plan(plan_key)
    if not plan:
        raise StripeCheckoutError("Unknown billing plan.")

    secret_key = config_value("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeCheckoutError("Stripe checkout is not configured.")

    price_id = plan.price_id
    if not price_id:
        raise StripeCheckoutError(f"{plan.name} checkout is not configured.")

    stripe = _stripe_module()
    stripe.api_key = secret_key
    stripe.api_version = config_value("STRIPE_API_VERSION", DEFAULT_STRIPE_API_VERSION)

    success_url = (
        f"{_absolute_url(request, 'success', '/billing/success/')}"
        "?session_id={CHECKOUT_SESSION_ID}"
    )
    session_params: dict[str, Any] = {
        "mode": plan.mode,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": f"{_absolute_url(request, 'cancel', '/billing/cancel/')}?plan={plan.key}",
        "metadata": {
            "billing_plan": plan.key,
            "plan_name": plan.name,
        },
        "allow_promotion_codes": config_bool("STRIPE_ALLOW_PROMOTION_CODES", True),
    }
    if config_bool("STRIPE_AUTOMATIC_TAX", False):
        session_params["automatic_tax"] = {"enabled": True}

    checkout_user = _checkout_user(request=request, user=user)
    if checkout_user is not None and getattr(checkout_user, "is_authenticated", False):
        user_id = getattr(checkout_user, "pk", None) or getattr(checkout_user, "id", None)
        if user_id:
            session_params["client_reference_id"] = f"user:{user_id}"
        email = (getattr(checkout_user, "email", "") or "").strip()
        if email:
            session_params["customer_email"] = email

    checkout_session = stripe.checkout.Session.create(**session_params)
    checkout_url = _session_value(checkout_session, "url", "")
    if not checkout_url:
        raise StripeCheckoutError("Stripe did not return a checkout URL.")
    return checkout_url


def retrieve_checkout_session(session_id: str):
    session_id = (session_id or "").strip()
    if not session_id:
        raise StripeCheckoutError("Checkout session is missing.")

    secret_key = config_value("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeCheckoutError("Stripe checkout is not configured.")

    stripe = _stripe_module()
    stripe.api_key = secret_key
    stripe.api_version = config_value("STRIPE_API_VERSION", DEFAULT_STRIPE_API_VERSION)

    try:
        return stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise StripeCheckoutError("Stripe checkout session could not be verified.") from exc


def _session_value(checkout_session, key: str, default: Any = ""):
    if isinstance(checkout_session, dict):
        return checkout_session.get(key, default)
    getter = getattr(checkout_session, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(checkout_session, key, default)


def _object_value(value, key: str, default: Any = ""):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)


def verified_registration_checkout(session_id: str) -> dict[str, str]:
    checkout_session = retrieve_checkout_session(session_id)
    status = _session_value(checkout_session, "status", "")
    payment_status = _session_value(checkout_session, "payment_status", "")
    metadata = _session_value(checkout_session, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        try:
            metadata = dict(metadata)
        except (TypeError, ValueError):
            metadata = {}

    plan_key = (metadata.get("billing_plan") or "").strip()
    plan = billing_plan(plan_key)
    if not plan:
        raise StripeCheckoutError("Checkout session has no recognized billing plan.")
    if status != "complete" or payment_status not in {"paid", "no_payment_required"}:
        raise StripeCheckoutError("Checkout session is not complete.")

    customer_details = _session_value(checkout_session, "customer_details", {}) or {}
    customer_email = (
        _session_value(checkout_session, "customer_email", "")
        or _object_value(customer_details, "email", "")
        or ""
    )
    return {
        "session_id": _session_value(checkout_session, "id", session_id),
        "plan_key": plan.key,
        "plan_name": plan.name,
        "customer": _session_value(checkout_session, "customer", "") or "",
        "customer_email": customer_email,
        "payment_status": payment_status,
    }


def store_registration_checkout(session, checkout: dict[str, str]) -> None:
    session[REGISTRATION_CHECKOUT_SESSION_KEY] = {
        "session_id": checkout.get("session_id", ""),
        "plan_key": checkout.get("plan_key", ""),
        "plan_name": checkout.get("plan_name", ""),
        "customer": checkout.get("customer", ""),
        "customer_email": checkout.get("customer_email", ""),
    }
    if hasattr(session, "modified"):
        session.modified = True


def registration_checkout(session) -> dict[str, str] | None:
    checkout = session.get(REGISTRATION_CHECKOUT_SESSION_KEY)
    if not isinstance(checkout, dict):
        return None
    if not checkout.get("session_id") or not checkout.get("plan_key"):
        return None
    return checkout


def clear_registration_checkout(session) -> None:
    session.pop(REGISTRATION_CHECKOUT_SESSION_KEY, None)
    if hasattr(session, "modified"):
        session.modified = True


def plan_from_checkout(checkout: dict[str, str]) -> BillingPlan | None:
    return billing_plan(checkout.get("plan_key"))
