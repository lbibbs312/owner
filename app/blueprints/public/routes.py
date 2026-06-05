import os
from datetime import date as date_cls, datetime

from flask import abort, current_app, jsonify, render_template, request, send_from_directory
from flask_login import current_user, login_required

from app.blueprints.public import bp
from app.models import Announcement
from app.services.database_status import database_status
from app.services.floor_operations import build_floor_operations_snapshot
from app.services.production_flow import build_production_flow_context
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
@bp.route("/production-flow-board")
@login_required
def production_flow_board():
    selected_plant = (request.args.get("plant") or "").strip() or None
    target_date = date_cls.today()
    raw_date = (request.args.get("date") or "").strip()
    if raw_date:
        try:
            target_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = date_cls.today()
    floor = build_floor_operations_snapshot(target_date)
    production_flow = build_production_flow_context(
        date=target_date,
        selected_plant=selected_plant,
        mode="plant_floor",
    )
    return render_template(
        "plant_floor_board.html",
        floor=floor,
        production_flow=production_flow,
        selected_plant=selected_plant,
        today=target_date,
    )


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
