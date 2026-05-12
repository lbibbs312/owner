"""Development entry point for the LacksDrivers Flask-SocketIO server.

Run with::

    python lacksdrivers.py

This binds the SocketIO eventlet worker. For production use the
``wsgi:application`` entry point behind gunicorn instead — see README.

Kept at the repo root for backwards compatibility with existing dev workflows
(``flask --app lacksdrivers db upgrade`` etc. still work). All routes, models,
forms, and SocketIO handlers live under ``app/``.
"""
import os

from app import create_app
from app.extensions import socketio

app = create_app()


if __name__ == "__main__":
    print("Starting SocketIO server on http://127.0.0.1:5000 ...")
    debug_enabled = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug_enabled)
