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
login_manager.login_view = "login"


def init_extensions(app):
    db.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
