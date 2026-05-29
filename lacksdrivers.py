"""Development entry point for the LacksDrivers Flask server.

Run with::

    python lacksdrivers.py

Production uses the ``wsgi:application`` entry point behind gunicorn; see
``render.yaml`` for the hosted command.

Kept at the repo root for backwards compatibility with existing dev workflows
(``flask --app lacksdrivers db upgrade`` etc. still work). All routes, models,
forms, and SocketIO handlers live under ``app/``.
"""
import os
import sys

from app.config import is_render_runtime


def _reexec_in_local_venv():
    if sys.prefix != sys.base_prefix:
        return
    venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
    if os.path.exists(venv_python):
        os.execv(venv_python, [venv_python, *sys.argv])


def _abort_render_dev_entrypoint():
    if not is_render_runtime():
        return
    if os.environ.get("ALLOW_RENDER_DEV_ENTRYPOINT", "false").lower() == "true":
        return
    raise RuntimeError(
        "Refusing to run python lacksdrivers.py on Render. "
        "Use gunicorn --worker-class gthread --workers 1 --threads 4 wsgi:application --bind 0.0.0.0:$PORT "
        "with FLASK_ENV=production and a persistent Postgres database."
    )


if __name__ == "__main__":
    _abort_render_dev_entrypoint()
    _reexec_in_local_venv()

from app import create_app
from app.extensions import socketio

app = create_app()


if __name__ == "__main__":
    print("Starting SocketIO server on http://127.0.0.1:5000 ...", flush=True)
    debug_enabled = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=debug_enabled,
        allow_unsafe_werkzeug=True,
    )
