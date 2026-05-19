from flask import Blueprint

bp = Blueprint("drafts", __name__, url_prefix="/drafts")

from app.blueprints.drafts import routes  # noqa: E402,F401
