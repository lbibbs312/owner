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
from urllib.parse import urlunsplit

from flask import Flask, redirect, request

from app.config import get_config
from app.cli import register_cli_commands
from app.extensions import init_extensions
from app.services.driver_wait import register_context_processors as register_driver_wait_context_processors
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
    register_driver_wait_context_processors(app)
    register_cli_commands(app)
    _register_legacy_domain_redirect(app)
    _register_blueprints(app)
    return app


def _register_legacy_domain_redirect(app):
    @app.before_request
    def redirect_legacy_domain():
        canonical_host = (app.config.get("CANONICAL_HOST") or "").lower()
        redirect_hosts = set(app.config.get("REDIRECT_HOSTS") or ())
        request_host = (request.host or "").split(":", 1)[0].lower()

        if not canonical_host or request_host not in redirect_hosts:
            return None

        target_url = urlunsplit((
            "https",
            canonical_host,
            request.path,
            request.query_string.decode("utf-8", "ignore"),
            "",
        ))
        return redirect(target_url, code=308)


def _register_blueprints(app):
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.drafts import bp as drafts_bp
    from app.blueprints.driver import bp as driver_bp
    from app.blueprints.manager import bp as manager_bp
    from app.blueprints.messaging import bp as messaging_bp
    from app.blueprints.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(drafts_bp)
    app.register_blueprint(driver_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(messaging_bp)
