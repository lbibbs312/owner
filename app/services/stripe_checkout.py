"""Stripe Checkout integration for MoveDefense public pricing."""

from dataclasses import dataclass
import importlib

from flask import current_app, url_for


class StripeCheckoutError(RuntimeError):
    """Raised when checkout cannot be created safely."""


@dataclass(frozen=True)
class BillingPlan:
    key: str
    name: str
    price_label: str
    price_env: str
    mode: str = "subscription"
    # Catalog-sync metadata: only set for plans whose Product/Price should be
    # created by `flask sync-stripe-catalog`. unit_amount is in cents; interval
    # is None for one-time prices or "month"/"day" for recurring.
    unit_amount: int | None = None
    interval: str | None = None
    tax_code: str | None = None


BILLING_PLANS = {
    plan.key: plan
    for plan in (
        BillingPlan("daily-route-pass", "Daily Route Pass", "$3.99/day", "STRIPE_PRICE_DAILY_ROUTE_PASS", "payment", unit_amount=399, tax_code="txcd_10103100"),
        BillingPlan("solo-driver", "Solo Driver", "$19/month", "STRIPE_PRICE_SOLO_DRIVER"),
        BillingPlan("owner-operator", "Owner-Operator", "$49/month", "STRIPE_PRICE_OWNER_OPERATOR"),
        BillingPlan("small-fleet", "Small Fleet", "$149/month", "STRIPE_PRICE_SMALL_FLEET"),
        BillingPlan("fleet-office", "Fleet Office", "$299+/month", "STRIPE_PRICE_FLEET_OFFICE"),
        # Daily Route Pass export add-ons (one-time, in-app after the included export).
        BillingPlan("route-pass-extra-export", "Additional route export", "$0.99", "STRIPE_PRICE_ROUTE_PASS_EXTRA_EXPORT", "payment", unit_amount=99, tax_code="txcd_10103100"),
        BillingPlan("route-pass-export-pack", "3 additional route exports", "$2.49", "STRIPE_PRICE_ROUTE_PASS_EXPORT_PACK", "payment", unit_amount=249, tax_code="txcd_10103100"),
        BillingPlan("driver-forms-pack", "Driver Forms Pack", "$19", "STRIPE_PRICE_DRIVER_FORMS_PACK", "payment"),
        BillingPlan("record-kit", "Owner-Operator Record Kit", "$49", "STRIPE_PRICE_RECORD_KIT", "payment"),
        BillingPlan("ifta-worksheet-bundle", "IFTA Fuel and Odometer Worksheet Bundle", "$99", "STRIPE_PRICE_IFTA_WORKSHEET_BUNDLE", "payment"),
        BillingPlan("branded-packet-setup", "Basic branded packet setup", "$149", "STRIPE_PRICE_BRANDED_PACKET_SETUP", "payment"),
        BillingPlan("paper-form-conversion", "Paper form conversion", "$299", "STRIPE_PRICE_PAPER_FORM_CONVERSION", "payment"),
        BillingPlan("fleet-packet-setup", "Full small-fleet packet setup", "$499", "STRIPE_PRICE_FLEET_PACKET_SETUP", "payment"),
    )
}


def billing_plan(plan_key):
    return BILLING_PLANS.get((plan_key or "").strip().lower())


def configured_billing_plan_keys(config=None):
    config = config or current_app.config
    return {
        key
        for key, plan in BILLING_PLANS.items()
        if config.get(plan.price_env)
    }


def stripe_checkout_configured(config=None):
    config = config or current_app.config
    return bool(config.get("STRIPE_SECRET_KEY") and configured_billing_plan_keys(config))


def _stripe_module():
    try:
        return importlib.import_module("stripe")
    except ImportError as exc:
        raise StripeCheckoutError(
            "Stripe checkout is not installed on this server."
        ) from exc


def _absolute_url(endpoint, **values):
    base_url = (
        current_app.config.get("PUBLIC_BASE_URL")
        or current_app.config.get("APP_URL")
        or current_app.config.get("BASE_URL")
        or current_app.config.get("PUBLIC_URL")
        or ""
    ).rstrip("/")
    if base_url:
        return f"{base_url}{url_for(endpoint, **values)}"
    return url_for(endpoint, _external=True, **values)


def create_checkout_session(plan_key, *, user=None):
    plan = billing_plan(plan_key)
    if not plan:
        raise StripeCheckoutError("Unknown billing plan.")

    secret_key = current_app.config.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeCheckoutError("Stripe checkout is not configured.")

    price_id = current_app.config.get(plan.price_env)
    if not price_id:
        raise StripeCheckoutError(f"{plan.name} checkout is not configured.")

    stripe = _stripe_module()
    stripe.api_key = secret_key
    stripe.api_version = current_app.config.get("STRIPE_API_VERSION")

    success_url = f"{_absolute_url('public.billing_success')}?session_id={{CHECKOUT_SESSION_ID}}"
    session_params = {
        "mode": plan.mode,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": _absolute_url("public.billing_cancel", plan=plan.key),
        "metadata": {
            "billing_plan": plan.key,
            "plan_name": plan.name,
        },
        "allow_promotion_codes": bool(current_app.config.get("STRIPE_ALLOW_PROMOTION_CODES")),
    }
    if current_app.config.get("STRIPE_AUTOMATIC_TAX"):
        session_params["automatic_tax"] = {"enabled": True}

    if user and getattr(user, "is_authenticated", False):
        session_params["client_reference_id"] = f"user:{user.id}"
        email = (getattr(user, "email", "") or "").strip()
        if email:
            session_params["customer_email"] = email

    session = stripe.checkout.Session.create(**session_params)
    checkout_url = session.get("url") if isinstance(session, dict) else getattr(session, "url", "")
    if not checkout_url:
        raise StripeCheckoutError("Stripe did not return a checkout URL.")
    return checkout_url


def retrieve_checkout_session(session_id):
    session_id = (session_id or "").strip()
    if not session_id:
        raise StripeCheckoutError("Checkout session is missing.")

    secret_key = current_app.config.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeCheckoutError("Stripe checkout is not configured.")

    stripe = _stripe_module()
    stripe.api_key = secret_key
    stripe.api_version = current_app.config.get("STRIPE_API_VERSION")

    try:
        return stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise StripeCheckoutError("Stripe checkout session could not be verified.") from exc


def _session_value(checkout_session, key, default=""):
    if isinstance(checkout_session, dict):
        return checkout_session.get(key, default)
    getter = getattr(checkout_session, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(checkout_session, key, default)


def _object_value(value, key, default=""):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)


def verified_registration_checkout(session_id):
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
