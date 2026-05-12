"""Flask application factory.

Routes, models, and forms currently still live in the top-level
``lacksdrivers.py`` monolith — they will be migrated into ``app/`` packages in
subsequent PRs. For now the factory just centralizes Flask app construction,
config loading, and extension binding so there is exactly one place doing
``Flask(__name__)`` in the codebase.

Templates and static files remain at the repo root for the same reason; the
``template_folder`` / ``static_folder`` overrides will go away once they move
into ``app/templates`` and ``app/static``.
"""
import os

from flask import Flask

from app.config import get_config
from app.extensions import init_extensions

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def create_app(config_class=None):
    app = Flask(
        __name__,
        template_folder=os.path.join(_REPO_ROOT, "templates"),
        static_folder=os.path.join(_REPO_ROOT, "static"),
    )
    app.config.from_object(config_class or get_config())
    init_extensions(app)
    return app
