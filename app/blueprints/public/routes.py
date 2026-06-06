import os

from flask import abort, current_app, jsonify, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required

from app.blueprints.public import bp
from app.models import Announcement
from app.services.database_status import database_status
from app.services.route_context import build_route_context


@bp.route("/")
def welcome():
    bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    return render_template("welcome.html", bulletins=bulletins)


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
