"""Unbound extension singletons.

Each extension is instantiated here without binding to a Flask app.
``init_extensions(app)`` is called from the app factory to wire them up.

This indirection is what makes the factory pattern work: extensions must exist
at module import time (so model classes can subclass ``db.Model`` and SocketIO
handlers can be decorated at import) but cannot be bound to an app until the
factory chooses the config.
"""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
socketio = SocketIO()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def _socketio_options(app):
    options = {
        "path": app.config.get("SOCKETIO_PATH", "socket.io"),
        "ping_interval": app.config.get("SOCKETIO_PING_INTERVAL", 25),
        "ping_timeout": app.config.get("SOCKETIO_PING_TIMEOUT", 20),
    }
    async_mode = app.config.get("SOCKETIO_ASYNC_MODE")
    if async_mode:
        options["async_mode"] = async_mode
    return options


def init_extensions(app):
    db.init_app(app)
    socketio.init_app(app, **_socketio_options(app))
    migrate.init_app(app, db)
    login_manager.init_app(app)
