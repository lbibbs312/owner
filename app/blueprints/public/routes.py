from flask import jsonify, render_template, send_from_directory
from flask_login import login_required
from sqlalchemy import text

from app.blueprints.public import bp
from app.extensions import db
from app.models import Announcement


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
        return jsonify(status="ok", db="ok"), 200
    except Exception as exc:  # pragma: no cover — surface DB connectivity failures
        return jsonify(status="degraded", db=str(exc)), 503
