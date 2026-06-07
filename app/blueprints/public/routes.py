import os

from flask import abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app.blueprints.public import bp
from app.models import Announcement
from app.services.database_status import database_status
from app.services.route_context import build_route_context
from app.services.stripe_checkout import StripeCheckoutError, billing_plan, create_checkout_session


@bp.route("/")
def welcome():
    bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    return render_template("welcome.html", bulletins=bulletins)


@bp.route("/billing/checkout/<plan_key>", methods=["POST"])
def billing_checkout(plan_key):
    plan = billing_plan(plan_key)
    if not plan:
        abort(404)
    try:
        checkout_url = create_checkout_session(plan.key, user=current_user)
    except StripeCheckoutError as exc:
        current_app.logger.warning("billing.checkout_unavailable plan=%s reason=%s", plan.key, exc)
        return render_template(
            "billing_status.html",
            status_title="Checkout unavailable",
            status_label="Checkout not configured",
            status_message=(
                "Online checkout is not ready for this item yet. Contact MoveDefense "
                "to start this plan or finish payment setup."
            ),
            plan=plan,
            retry_url=url_for("public.welcome", _anchor="pricing"),
        ), 503
    return redirect(checkout_url, code=303)


@bp.route("/billing/success")
def billing_success():
    return render_template(
        "billing_status.html",
        status_title="Checkout received",
        status_label="Payment started",
        status_message=(
            "Stripe accepted the checkout handoff. Sign in or contact MoveDefense if "
            "your workspace needs to be connected to this purchase."
        ),
        session_id=request.args.get("session_id", ""),
        retry_url=url_for("auth.login"),
    )


@bp.route("/billing/cancel")
def billing_cancel():
    return render_template(
        "billing_status.html",
        status_title="Checkout canceled",
        status_label="No charge completed",
        status_message="Your checkout session was canceled before payment was completed.",
        plan=billing_plan(request.args.get("plan")),
        retry_url=url_for("public.welcome", _anchor="pricing"),
    )


@bp.route("/privacy")
def privacy():
    return render_template(
        "privacy.html",
        public_contact_email=current_app.config["PUBLIC_CONTACT_EMAIL"],
    )


@bp.route("/terms")
def terms():
    return render_template(
        "terms.html",
        public_contact_email=current_app.config["PUBLIC_CONTACT_EMAIL"],
    )


@bp.route("/contact")
def contact():
    return render_template(
        "contact.html",
        public_contact_email=current_app.config["PUBLIC_CONTACT_EMAIL"],
    )


@bp.route("/OneSignalSDKWorker.js")
def onesignal_sw():
    return send_from_directory(
        os.path.join(current_app.static_folder, "OneSignalSDK.sw.js"),
        "onesignal.js",
        mimetype="application/javascript",
    )


@bp.route("/plant_directory")
@login_required
def plant_directory():
    return render_template("plant_directory.html")


@bp.route("/operations-board")
@bp.route("/operations_board")
@login_required
def legacy_operations_board():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return redirect(url_for("driver.mobile_dashboard"))


@bp.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200


@bp.route("/readyz")
def readyz():
    try:
        status = database_status(current_app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        return jsonify(
            status="ok" if status["ready"] else "degraded",
            db="ok",
            dialect=status["dialect"],
            persistent=status["persistent"],
            schema="ok" if status["schema_ready"] else "missing_tables",
            missing_tables=status["missing_tables"],
        ), 200 if status["ready"] else 503
    except Exception as exc:  # pragma: no cover - surface DB connectivity failures
        return jsonify(status="degraded", db=str(exc)), 503


@bp.route("/debug/route-context/<path:route_id>")
@login_required
def debug_route_context(route_id):
    debug_enabled = bool(
        current_app.config.get("DEBUG")
        or current_app.config.get("TESTING")
        or current_app.config.get("ENABLE_ROUTE_CONTEXT_DEBUG")
    )
    if current_user.role != "management" or not debug_enabled:
        abort(404)
    snapshot = build_route_context(route_id=route_id)
    return jsonify(snapshot.to_dict())
