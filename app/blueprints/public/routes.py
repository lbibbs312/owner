import json
import os
import re

from flask import abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.blueprints.public import bp
from app.extensions import db
from app.models import Announcement, DriverState, User
from app.services.database_status import database_status
from app.services.route_context import build_route_context
from app.services.google_places import (
    autocomplete_destination,
    destination_place_details,
    reverse_geocode,
    nearby_place_candidates,
)
from app.services.registration_access import store_registration_checkout
from app.services.role_session import clear_role_logins, remember_role_login
from app.services.stripe_checkout import (
    StripeCheckoutError,
    billing_plan,
    create_checkout_session,
    verified_registration_checkout,
)

MAX_DRIVER_STATE_BYTES = 2_000_000


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _normalize_email(value):
    return str(value or "").strip().lower()


def _normalize_identifier(value):
    return str(value or "").strip().lower()


def _find_user_by_login(identifier):
    login = _normalize_identifier(identifier)
    if not login:
        return None
    return User.query.filter(
        (func.lower(User.email) == login) | (func.lower(User.username) == login)
    ).first()


def _split_driver_name(name):
    parts = str(name or "").strip().split(None, 1)
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0][:64], None
    return parts[0][:64], parts[1][:64]


def _unique_username(email, name=""):
    source = email.split("@", 1)[0] or name or "driver"
    base = re.sub(r"[^A-Za-z0-9_.-]+", "", source)[:48] or "driver"
    candidate = base
    suffix = 2
    while User.query.filter(func.lower(User.username) == candidate.lower()).first():
        candidate = f"{base[:54]}{suffix}"
        suffix += 1
    return candidate[:64]


def _driver_state_response(user):
    state = DriverState.query.filter_by(user_id=user.id).first()
    if not state:
        return {"exists": False, "data": None, "updated_at": None}
    try:
        data = json.loads(state.data or "{}")
    except (TypeError, ValueError):
        data = {}
    return {
        "exists": True,
        "data": data if isinstance(data, dict) else {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _account_response(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
    }


def _require_driver_api_user():
    if not current_user.is_authenticated:
        return None, (jsonify({"ok": False, "error": "not_authenticated"}), 401)
    if current_user.role != "driver":
        return None, (jsonify({"ok": False, "error": "driver_required"}), 403)
    return current_user, None


def _login_driver(user):
    login_user(user, remember=True)
    remember_role_login(user)


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


@bp.route("/api/geo/nearby", methods=["GET"])
def geo_nearby():
    """Nearest business/place to a GPS point — lets the GPS pin name the stop."""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "missing_input", "places": []})
    return jsonify(nearby_place_candidates(lat, lng, limit=6, radius_m=160))


@bp.route("/app")
def install_app_page():
    """Public install page for sideloading the MoveDefense Android app."""
    return render_template("install_app.html")


@bp.route("/app/download")
def install_app_download():
    """Serve the signed Android APK as a download."""
    return send_from_directory(
        os.path.join(current_app.static_folder, "app"),
        "MoveDefense.apk",
        mimetype="application/vnd.android.package-archive",
        as_attachment=True,
        download_name="MoveDefense.apk",
    )


@bp.route("/api/account/register", methods=["POST"])
def api_account_register():
    data = _json_body()
    email = _normalize_email(data.get("email"))
    password = str(data.get("password") or "")
    name = str(data.get("name") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "invalid_email"}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "weak_password"}), 400

    existing = _find_user_by_login(email)
    if existing:
        if existing.role == "driver" and existing.password_hash and existing.check_password(password):
            _login_driver(existing)
            return jsonify(
                {
                    "ok": True,
                    "user": _account_response(existing),
                    "state": _driver_state_response(existing),
                }
            )
        return jsonify({"ok": False, "error": "account_exists"}), 409

    first_name, last_name = _split_driver_name(name)
    user = User(
        username=_unique_username(email, name),
        email=email,
        role="driver",
        first_name=first_name,
        last_name=last_name,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _login_driver(user)
    return jsonify(
        {
            "ok": True,
            "user": _account_response(user),
            "state": _driver_state_response(user),
        }
    ), 201


@bp.route("/api/account/login", methods=["POST"])
def api_account_login():
    data = _json_body()
    identifier = _normalize_identifier(data.get("login") or data.get("email"))
    password = str(data.get("password") or "")
    if not identifier or not password:
        return jsonify({"ok": False, "error": "missing_credentials"}), 400

    user = _find_user_by_login(identifier)
    if not user or not user.password_hash or not user.check_password(password):
        return jsonify({"ok": False, "error": "invalid_credentials"}), 401
    if user.role != "driver":
        return jsonify({"ok": False, "error": "driver_required"}), 403

    _login_driver(user)
    return jsonify(
        {
            "ok": True,
            "user": _account_response(user),
            "state": _driver_state_response(user),
        }
    )


@bp.route("/api/account/logout", methods=["POST"])
def api_account_logout():
    clear_role_logins()
    logout_user()
    return jsonify({"ok": True})


@bp.route("/api/account/me", methods=["GET"])
def api_account_me():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "authenticated": False})
    if current_user.role != "driver":
        return jsonify({"ok": True, "authenticated": False})
    return jsonify(
        {
            "ok": True,
            "authenticated": True,
            "user": _account_response(current_user),
            "state": _driver_state_response(current_user),
        }
    )


@bp.route("/api/driver-state", methods=["GET", "POST"])
def api_driver_state():
    user, error = _require_driver_api_user()
    if error:
        return error

    if request.method == "GET":
        return jsonify({"ok": True, "state": _driver_state_response(user)})

    if request.content_length and request.content_length > MAX_DRIVER_STATE_BYTES:
        return jsonify({"ok": False, "error": "state_too_large"}), 413
    data = _json_body().get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid_state"}), 400
    encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_DRIVER_STATE_BYTES:
        return jsonify({"ok": False, "error": "state_too_large"}), 413

    state = DriverState.query.filter_by(user_id=user.id).first()
    if not state:
        state = DriverState(user_id=user.id)
        db.session.add(state)
    state.data = encoded
    db.session.commit()
    return jsonify({"ok": True, "state": _driver_state_response(user)})


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
