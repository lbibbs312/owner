"""Production WSGI entry point.

Imports the app instance from ``lacksdrivers`` (which is currently where every
route and SocketIO handler is decorated). Once routes are moved into ``app/``
in a later PR, this will switch to ``application = create_app()`` directly.

Usage:
    gunicorn --worker-class gthread --workers 1 --threads 4 wsgi:application
"""
from lacksdrivers import app as application

__all__ = ["application"]
