import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, jsonify, make_response, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.blueprints.public import bp
from app.extensions import db
from app.models import Announcement, DriverDayState, DriverState, User
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
MAX_DRIVER_DAY_STATE_BYTES = 400_000
DAY_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@bp.after_request
def _never_cache_api(response):
    """Forbid any caching of dynamic API responses.

    ``/api/account/me`` and ``/api/driver-state`` return per-user identity,
    email, and the driver's saved state. These sit behind Cloudflare, which
    ignores ``Vary: Cookie`` when deciding what to cache — so without an
    explicit ``no-store`` an edge can cache one driver's response and serve it
    to every other driver, leaking accounts across users. Force no-store on
    every ``/api/*`` response (static assets and the shell are unaffected).
    """
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        existing_vary = response.headers.get("Vary", "")
        if "cookie" not in existing_vary.lower():
            response.headers["Vary"] = (existing_vary + ", Cookie").lstrip(", ") if existing_vary else "Cookie"
    return response


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


def _valid_day_key(value):
    return bool(DAY_KEY_RE.match(str(value or "")))


def _json_size(data):
    encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return encoded, len(encoded.encode("utf-8"))


def _decode_state_data(raw):
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def _driver_state_data(user):
    state = DriverState.query.filter_by(user_id=user.id).first()
    return _decode_state_data(state.data) if state else {}


def _stop_day_key(stop):
    explicit = stop.get("day_key") if isinstance(stop, dict) else None
    if _valid_day_key(explicit):
        return explicit
    try:
        millis = float(stop.get("arrival_time"))
    except (AttributeError, TypeError, ValueError):
        return ""
    if not millis:
        return ""
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date().isoformat()


def _state_for_day(state_data, day_key):
    data = dict(state_data) if isinstance(state_data, dict) else {}
    stops = data.get("stops")
    data["stops"] = [
        stop for stop in stops if isinstance(stop, dict) and _stop_day_key(stop) == day_key
    ] if isinstance(stops, list) else []
    data["day_key"] = day_key
    return data


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
    data = _decode_state_data(state.data)
    return {
        "exists": True,
        "data": data,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _driver_day_state_response(user, day_key):
    state = DriverDayState.query.filter_by(user_id=user.id, day_key=day_key).first()
    if state:
        return {
            "exists": True,
            "date": day_key,
            "data": _decode_state_data(state.data),
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            "source": "driver_day_state",
        }

    fallback = _state_for_day(_driver_state_data(user), day_key)
    return {
        "exists": False,
        "date": day_key,
        "data": fallback if fallback.get("stops") else None,
        "updated_at": None,
        "source": "driver_state_fallback" if fallback.get("stops") else None,
    }


def _upsert_driver_day_state(user, day_key, data):
    state = DriverDayState.query.filter_by(user_id=user.id, day_key=day_key).first()
    if not state:
        state = DriverDayState(user_id=user.id, day_key=day_key)
        db.session.add(state)
    state.data = data
    return state


def _account_response(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
    }


def _empty_driver_state_response():
    return {"exists": False, "data": None, "updated_at": None}


def _is_owner_api_user(user):
    return bool(user and user.role in {"management", "owner"})


def _require_driver_api_user():
    if not current_user.is_authenticated:
        return None, (jsonify({"ok": False, "error": "not_authenticated"}), 401)
    if current_user.role != "driver":
        return None, (jsonify({"ok": False, "error": "driver_required"}), 403)
    return current_user, None


def _require_owner_api_user():
    if not current_user.is_authenticated:
        return None, (jsonify({"ok": False, "error": "not_authenticated"}), 401)
    if not _is_owner_api_user(current_user):
        return None, (jsonify({"ok": False, "error": "owner_required"}), 403)
    return current_user, None


def _login_account(user):
    user.last_login_at = datetime.utcnow()
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    remember_role_login(user)


def _login_driver(user):
    _login_account(user)


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="seconds") + "Z"


def _owner_stats_response():
    now = datetime.utcnow()
    cutoffs = {
        "active_today": now - timedelta(days=1),
        "active_7_days": now - timedelta(days=7),
        "active_30_days": now - timedelta(days=30),
        "created_today": now - timedelta(days=1),
        "created_7_days": now - timedelta(days=7),
        "created_30_days": now - timedelta(days=30),
    }
    drivers = User.query.filter_by(role="driver").order_by(User.id.desc()).all()
    driver_ids = {driver.id for driver in drivers}
    state_rows = {
        row.user_id: row
        for row in DriverState.query.filter(DriverState.user_id.in_(driver_ids)).all()
    } if driver_ids else {}
    day_rows = (
        DriverDayState.query.filter(DriverDayState.user_id.in_(driver_ids)).all()
        if driver_ids else []
    )
    day_counts = {}
    latest_day_sync = {}
    for row in day_rows:
        day_counts[row.user_id] = day_counts.get(row.user_id, 0) + 1
        if row.updated_at and (
            not latest_day_sync.get(row.user_id) or row.updated_at > latest_day_sync[row.user_id]
        ):
            latest_day_sync[row.user_id] = row.updated_at

    def latest_activity_for(user_id):
        candidates = []
        state = state_rows.get(user_id)
        if state and state.updated_at:
            candidates.append(state.updated_at)
        if latest_day_sync.get(user_id):
            candidates.append(latest_day_sync[user_id])
        return max(candidates) if candidates else None

    rows = []
    active_counts = {key: 0 for key in cutoffs}
    created_counts = {"created_today": 0, "created_7_days": 0, "created_30_days": 0}
    synced_accounts = 0
    for driver in drivers:
        latest_activity = max(
            [value for value in [driver.last_login_at, latest_activity_for(driver.id)] if value],
            default=None,
        )
        saved_days = day_counts.get(driver.id, 0)
        has_saved_state = bool(state_rows.get(driver.id) or saved_days)
        if has_saved_state:
            synced_accounts += 1
        for key in ("active_today", "active_7_days", "active_30_days"):
            cutoff = cutoffs[key]
            if latest_activity and latest_activity >= cutoff:
                active_counts[key] += 1
        for key in created_counts:
            if driver.created_at and driver.created_at >= cutoffs[key]:
                created_counts[key] += 1
        rows.append(
            {
                "id": driver.id,
                "name": driver.display_name,
                "username": driver.username,
                "email": driver.email,
                "saved": has_saved_state,
                "saved_days": saved_days,
                "created_at": _iso_datetime(driver.created_at),
                "last_login_at": _iso_datetime(driver.last_login_at),
                "last_activity_at": _iso_datetime(latest_activity),
            }
        )

    rows.sort(key=lambda row: row["last_activity_at"] or "", reverse=True)
    return {
        "generated_at": _iso_datetime(now),
        "total_accounts": len(drivers),
        "created_today": created_counts["created_today"],
        "created_7_days": created_counts["created_7_days"],
        "created_30_days": created_counts["created_30_days"],
        "synced_accounts": synced_accounts,
        "active_today": active_counts["active_today"],
        "active_7_days": active_counts["active_7_days"],
        "active_30_days": active_counts["active_30_days"],
        "unsynced_accounts": len(drivers) - synced_accounts,
        "day_snapshots": len(day_rows),
        "recent_accounts": rows[:20],
    }


def _apk_metadata():
    path = os.path.join(current_app.static_folder, "app", "MoveDefense.apk")
    try:
        size_bytes = os.path.getsize(path)
        with open(path, "rb") as apk_file:
            digest = hashlib.sha256(apk_file.read()).hexdigest()
    except OSError:
        return {"size_mb": None, "sha256": None}
    return {"size_mb": f"{size_bytes / 1024 / 1024:.1f} MB", "sha256": digest}


@bp.route("/")
def welcome():
    try:
        bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    except SQLAlchemyError as exc:
        current_app.logger.warning("public.welcome_bulletins_unavailable error=%s", exc.__class__.__name__)
        bulletins = []
    response = make_response(render_template("welcome.html", bulletins=bulletins))
    response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    return response


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
    fuel_only = bool(data.get("fuel_only"))
    return jsonify(
        autocomplete_destination(
            text, lat=data.get("lat"), lng=data.get("lng"), session_token=token, fuel_only=fuel_only
        )
    )


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
    return render_template("install_app.html", apk=_apk_metadata())


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

    if user.role == "driver":
        _login_driver(user)
        state = _driver_state_response(user)
    elif _is_owner_api_user(user):
        _login_account(user)
        state = _empty_driver_state_response()
    else:
        return jsonify({"ok": False, "error": "driver_required"}), 403
    return jsonify(
        {
            "ok": True,
            "user": _account_response(user),
            "state": state,
        }
    )


@bp.route("/api/owner/stats", methods=["GET"])
def api_owner_stats():
    _user, error = _require_owner_api_user()
    if error:
        return error
    return jsonify({"ok": True, "stats": _owner_stats_response()})


@bp.route("/api/account/logout", methods=["POST"])
def api_account_logout():
    clear_role_logins()
    logout_user()
    return jsonify({"ok": True})


@bp.route("/api/account/me", methods=["GET"])
def api_account_me():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "authenticated": False})
    if current_user.role == "driver":
        return jsonify(
            {
                "ok": True,
                "authenticated": True,
                "user": _account_response(current_user),
                "state": _driver_state_response(current_user),
            }
        )
    if _is_owner_api_user(current_user):
        return jsonify(
            {
                "ok": True,
                "authenticated": True,
                "user": _account_response(current_user),
                "state": _empty_driver_state_response(),
            }
        )
    else:
        return jsonify({"ok": True, "authenticated": False})


@bp.route("/api/driver-state", methods=["GET", "POST"])
def api_driver_state():
    user, error = _require_driver_api_user()
    if error:
        return error

    if request.method == "GET":
        return jsonify({"ok": True, "state": _driver_state_response(user)})

    if request.content_length and request.content_length > MAX_DRIVER_STATE_BYTES:
        return jsonify({"ok": False, "error": "state_too_large"}), 413
    body = _json_body()
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid_state"}), 400
    encoded, byte_size = _json_size(data)
    if byte_size > MAX_DRIVER_STATE_BYTES:
        return jsonify({"ok": False, "error": "state_too_large"}), 413

    state = DriverState.query.filter_by(user_id=user.id).first()
    if not state:
        state = DriverState(user_id=user.id)
        db.session.add(state)
    state.data = encoded

    day_states = body.get("day_states")
    if day_states is not None:
        if not isinstance(day_states, dict):
            return jsonify({"ok": False, "error": "invalid_day_states"}), 400
        for day_key, day_data in day_states.items():
            if not _valid_day_key(day_key) or not isinstance(day_data, dict):
                return jsonify({"ok": False, "error": "invalid_day_state"}), 400
            day_encoded, day_byte_size = _json_size(day_data)
            if day_byte_size > MAX_DRIVER_DAY_STATE_BYTES:
                return jsonify({"ok": False, "error": "day_state_too_large"}), 413
            _upsert_driver_day_state(user, day_key, day_encoded)

    db.session.commit()
    return jsonify({"ok": True, "state": _driver_state_response(user)})


@bp.route("/api/driver-day-state", methods=["GET", "POST"])
def api_driver_day_state():
    user, error = _require_driver_api_user()
    if error:
        return error

    if request.method == "GET":
        day_key = str(request.args.get("date") or "").strip()
        if not _valid_day_key(day_key):
            return jsonify({"ok": False, "error": "invalid_date"}), 400
        return jsonify({"ok": True, "state": _driver_day_state_response(user, day_key)})

    if request.content_length and request.content_length > MAX_DRIVER_DAY_STATE_BYTES:
        return jsonify({"ok": False, "error": "day_state_too_large"}), 413
    body = _json_body()
    day_key = str(body.get("date") or "").strip()
    data = body.get("data")
    if not _valid_day_key(day_key):
        return jsonify({"ok": False, "error": "invalid_date"}), 400
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid_day_state"}), 400

    encoded, byte_size = _json_size(data)
    if byte_size > MAX_DRIVER_DAY_STATE_BYTES:
        return jsonify({"ok": False, "error": "day_state_too_large"}), 413
    _upsert_driver_day_state(user, day_key, encoded)
    db.session.commit()
    return jsonify({"ok": True, "state": _driver_day_state_response(user, day_key)})


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
