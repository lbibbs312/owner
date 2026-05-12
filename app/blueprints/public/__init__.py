from flask import Blueprint

bp = Blueprint("public", __name__)

from app.blueprints.public import routes  # noqa: E402, F401  registers @bp.route handlers
