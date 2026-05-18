from flask import current_app, jsonify, render_template, send_from_directory
from flask_login import login_required
from sqlalchemy import text

from app.blueprints.public import bp
from app.extensions import db
from app.models import Announcement
from app.config import is_sqlite_database_uri, runtime_requires_persistent_db


@bp.route("/")
def welcome():
    bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    return render_template("welcome.html", bulletins=bulletins)


@bp.route("/OneSignalSDKWorker.js")
def onesignal_sw():
    return send_from_directory("static", "OneSignalSDKWorker.js")


@bp.route("/plant_directory")
@login_required
def plant_directory():
    return render_template("plant_directory.html")


@bp.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200


@bp.route("/readyz")
def readyz():
    try:
        db.session.execute(text("SELECT 1"))
        bind = db.session.get_bind()
        dialect = bind.dialect.name if bind is not None else "unknown"
        database_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        sqlite_database = dialect == "sqlite" or is_sqlite_database_uri(database_uri)
        unsafe_runtime = runtime_requires_persistent_db() and sqlite_database
        status_code = 503 if unsafe_runtime else 200
        return jsonify(
            status="degraded" if unsafe_runtime else "ok",
            db="ok",
            dialect=dialect,
            persistent=not sqlite_database,
        ), status_code
    except Exception as exc:  # pragma: no cover - surface DB connectivity failures
        return jsonify(status="degraded", db=str(exc)), 503
