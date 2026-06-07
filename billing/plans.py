"""Billing plan registry for MoveDefense Checkout."""

from __future__ import annotations

from dataclasses import dataclass
import os

try:
    from django.conf import settings
except Exception:  # pragma: no cover - keeps this module importable before Django exists.
    settings = None


@dataclass(frozen=True)
class BillingPlan:
    key: str
    name: str
    price_label: str
    price_env: str
    mode: str = "subscription"

    @property
    def price_id(self) -> str:
        return config_value(self.price_env)


BILLING_PLANS = {
    plan.key: plan
    for plan in (
        BillingPlan("solo-driver", "Solo Driver", "$19/month", "STRIPE_PRICE_SOLO_DRIVER"),
        BillingPlan(
            "owner-operator",
            "Owner-Operator",
            "$49/month",
            "STRIPE_PRICE_OWNER_OPERATOR",
        ),
        BillingPlan("small-fleet", "Small Fleet", "$149/month", "STRIPE_PRICE_SMALL_FLEET"),
        BillingPlan("fleet-office", "Fleet Office", "$299+/month", "STRIPE_PRICE_FLEET_OFFICE"),
        BillingPlan(
            "driver-forms-pack",
            "Driver Forms Pack",
            "$19",
            "STRIPE_PRICE_DRIVER_FORMS_PACK",
            "payment",
        ),
        BillingPlan(
            "record-kit",
            "Owner-Operator Record Kit",
            "$49",
            "STRIPE_PRICE_RECORD_KIT",
            "payment",
        ),
        BillingPlan(
            "ifta-worksheet-bundle",
            "IFTA Fuel and Odometer Worksheet Bundle",
            "$99",
            "STRIPE_PRICE_IFTA_WORKSHEET_BUNDLE",
            "payment",
        ),
        BillingPlan(
            "branded-packet-setup",
            "Basic branded packet setup",
            "$149",
            "STRIPE_PRICE_BRANDED_PACKET_SETUP",
            "payment",
        ),
        BillingPlan(
            "paper-form-conversion",
            "Paper form conversion",
            "$299",
            "STRIPE_PRICE_PAPER_FORM_CONVERSION",
            "payment",
        ),
        BillingPlan(
            "fleet-packet-setup",
            "Full small-fleet packet setup",
            "$499",
            "STRIPE_PRICE_FLEET_PACKET_SETUP",
            "payment",
        ),
    )
}


def config_value(name: str, default: str = "") -> str:
    """Read a Django setting when configured, falling back to the environment."""
    value = None
    if settings is not None and getattr(settings, "configured", False):
        value = getattr(settings, name, None)
    if value is None or value == "":
        value = os.environ.get(name, default)
    return str(value).strip() if value is not None else default


def config_bool(name: str, default: bool = False) -> bool:
    value = config_value(name)
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def billing_plan(plan_key: str | None) -> BillingPlan | None:
    return BILLING_PLANS.get((plan_key or "").strip().lower())


def configured_billing_plan_keys() -> set[str]:
    return {key for key, plan in BILLING_PLANS.items() if plan.price_id}


def stripe_checkout_configured() -> bool:
    return bool(config_value("STRIPE_SECRET_KEY") and configured_billing_plan_keys())
