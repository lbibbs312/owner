"""Public billing views for the Django MoveDefense scaffold."""

from __future__ import annotations

import logging

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST

from .plans import billing_plan
from .stripe_checkout import (
    StripeCheckoutError,
    create_checkout_session,
    store_registration_checkout,
    verified_registration_checkout,
)

logger = logging.getLogger(__name__)


def _reverse_or_path(route_name: str, fallback_path: str) -> str:
    try:
        return reverse(route_name)
    except NoReverseMatch:
        return fallback_path


def _pricing_url() -> str:
    return f"{_reverse_or_path('public_site:home', '/')}#pricing"


def _account_registration_url() -> str:
    return _reverse_or_path("accounts:register", "/accounts/register/")


def _status_response(
    request,
    *,
    status_title: str,
    status_label: str,
    status_message: str,
    status_code: int = 200,
    plan=None,
    session_id: str = "",
    retry_url: str | None = None,
):
    return render(
        request,
        "billing/status.html",
        {
            "status_title": status_title,
            "status_label": status_label,
            "status_message": status_message,
            "plan": plan,
            "session_id": session_id,
            "retry_url": retry_url or _pricing_url(),
        },
        status=status_code,
    )


@require_POST
def checkout(request, plan_key: str):
    plan = billing_plan(plan_key)
    if not plan:
        raise Http404("Unknown billing plan.")
    try:
        checkout_url = create_checkout_session(plan.key, request=request)
    except StripeCheckoutError as exc:
        logger.warning("billing.checkout_unavailable plan=%s reason=%s", plan.key, exc)
        return _status_response(
            request,
            status_title="Checkout unavailable",
            status_label="Checkout not configured",
            status_message=(
                "Online checkout is not ready for this item yet. Contact MoveDefense "
                "to start this plan or finish payment setup."
            ),
            status_code=503,
            plan=plan,
        )
    response = HttpResponseRedirect(checkout_url)
    response.status_code = 303
    return response


@require_GET
def success(request):
    session_id = request.GET.get("session_id", "")
    try:
        checkout_data = verified_registration_checkout(session_id)
    except StripeCheckoutError as exc:
        logger.warning("billing.checkout_verify_failed reason=%s", exc)
        return _status_response(
            request,
            status_title="Checkout not verified",
            status_label="Account setup blocked",
            status_message=(
                "MoveDefense could not verify a completed payment for this checkout. "
                "Return to pricing and start checkout again."
            ),
            status_code=403,
            session_id=session_id,
        )
    store_registration_checkout(request.session, checkout_data)
    return HttpResponseRedirect(_account_registration_url())


@require_GET
def cancel(request):
    return _status_response(
        request,
        status_title="Checkout canceled",
        status_label="No charge completed",
        status_message="Your checkout session was canceled before payment was completed.",
        plan=billing_plan(request.GET.get("plan")),
    )


@require_GET
def blocked(request):
    return _status_response(
        request,
        status_title="Checkout required",
        status_label="Account setup blocked",
        status_message="Complete checkout before creating a MoveDefense account.",
        status_code=403,
    )
