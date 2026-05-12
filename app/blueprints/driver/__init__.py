from flask import Blueprint

bp = Blueprint("driver", __name__)

from app.blueprints.driver import routes  # noqa: E402, F401  registers @bp.route handlers
