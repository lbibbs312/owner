import os

from flask import abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.blueprints.public import bp
from app.models import Announcement
from app.services.database_status import database_status
from app.services.route_context import build_route_context
from app.services.google_places import autocomplete_destination, destination_place_details, reverse_geocode
from app.services.registration_access import store_registration_checkout
from app.services.stripe_checkout import (
    StripeCheckoutError,
    billing_plan,
    create_checkout_session,
    verified_registration_checkout,
)


@bp.route("/")
def welcome():
    try:
        bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    except SQLAlchemyError as exc:
        current_app.logger.warning("public.welcome_bulletins_unavailable error=%s", exc.__class__.__name__)
        bulletins = []
    return render_template("welcome.html", bulletins=bulletins)


@bp.route("/manifest.webmanifest")
def web_manifest():
    """Serve the PWA manifest with the correct media type for installability."""
    return send_from_directory(
        current_app.static_folder,
        "manifest.webmanifest",
        mimetype="application/manifest+json",
    )


@bp.route("/sw.js")
def service_worker():
    """Serve the service worker at the site root so its scope covers the app."""
    response = send_from_directory(
        current_app.static_folder, "sw.js", mimetype="text/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/.well-known/assetlinks.json")
def android_asset_links():
    """Digital Asset Links for the Android TWA (drops the in-app URL bar)."""
    return send_from_directory(
        os.path.join(current_app.static_folder, ".well-known"),
        "assetlinks.json",
        mimetype="application/json",
    )


@bp.route("/api/geo/suggest", methods=["POST"])
def geo_suggest():
    """Public place-autocomplete proxy for the one-driver page (New Places API).

    Runs the lookup server-side so the page never depends on the browser Maps
    JavaScript library loading. Input length is capped to limit abuse.
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get("input") or "").strip()[:255]
    token = str(data.get("session_token") or "").strip()[:128]
    return jsonify(autocomplete_destination(text, lat=data.get("lat"), lng=data.get("lng"), session_token=token))


@bp.route("/api/geo/details", methods=["POST"])
def geo_details():
    """Public place-details proxy (called when a driver taps a suggestion)."""
    data = request.get_json(silent=True) or {}
    place_id = str(data.get("place_id") or "").strip()[:512]
    token = str(data.get("session_token") or "").strip()[:128]
    if not place_id:
        return jsonify({"ok": False, "error": "missing_place_id", "place": None})
    return jsonify(destination_place_details(place_id, session_token=token))


@bp.route("/api/geo/reverse", methods=["GET"])
def geo_reverse():
    """Public reverse-geocode proxy for the GPS address-fill control."""
    return jsonify(reverse_geocode(request.args.get("lat"), request.args.get("lng")))


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
    session_id = request.args.get("session_id", "")
    try:
        checkout = verified_registration_checkout(session_id)
    except StripeCheckoutError as exc:
        current_app.logger.warning("billing.checkout_verify_failed reason=%s", exc)
        return render_template(
            "billing_status.html",
            status_title="Checkout not verified",
            status_label="Account setup blocked",
            status_message=(
                "MoveDefense could not verify a completed payment for this checkout. "
                "Return to pricing and start checkout again."
            ),
            session_id=session_id,
            retry_url=url_for("public.welcome", _anchor="pricing"),
        ), 403
    store_registration_checkout(checkout)
    return redirect(url_for("auth.register"))


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
