from flask import Blueprint

bp = Blueprint("messaging", __name__)

from app.blueprints.messaging import routes  # noqa: E402, F401  registers @bp.route handlers
from app.blueprints.messaging import sockets  # noqa: E402, F401  registers @socketio.on handlers
