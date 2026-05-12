from flask import Blueprint

bp = Blueprint("manager", __name__, url_prefix="/manager")

from app.blueprints.manager import routes  # noqa: E402, F401  registers @bp.route handlers
