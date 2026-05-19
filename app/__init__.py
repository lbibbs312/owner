"""Flask application factory.

All routes live in ``app/blueprints/`` and are registered by
``_register_blueprints``. SocketIO handlers are imported as a side effect of
loading the messaging blueprint package. Template filters and the
PLANT_ADDRESSES context processor are wired by the relevant ``app/services/``
helpers.

Templates and static files remain at the repo root for now; the
``template_folder`` / ``static_folder`` overrides will go away once they move
into ``app/templates`` and ``app/static``.
"""
import os

from flask import Flask

from app.config import get_config
from app.cli import register_cli_commands
from app.extensions import init_extensions
from app.services.plant_addresses import register_context_processors
from app.services.template_filters import register_template_filters

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def create_app(config_class=None):
    app = Flask(
        __name__,
        template_folder=os.path.join(_REPO_ROOT, "templates"),
        static_folder=os.path.join(_REPO_ROOT, "static"),
    )
    app.config.from_object(config_class or get_config())
    init_extensions(app)
    register_template_filters(app)
    register_context_processors(app)
    register_cli_commands(app)
    _register_blueprints(app)
    return app


def _register_blueprints(app):
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.driver import bp as driver_bp
    from app.blueprints.manager import bp as manager_bp
    from app.blueprints.messaging import bp as messaging_bp
    from app.blueprints.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(driver_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(messaging_bp)
