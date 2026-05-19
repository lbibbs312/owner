"""Configuration classes selected by runtime environment.

Production and hosted runtimes must use a persistent database. If this service
is deployed on Render with SQLite or without a database URL, it fails fast
instead of accepting driver route data into a disposable container file.
"""
import os

from dotenv import load_dotenv

load_dotenv()


_RENDER_ENV_VARS = (
    "RENDER",
    "RENDER_SERVICE_ID",
    "RENDER_EXTERNAL_HOSTNAME",
    "RENDER_EXTERNAL_URL",
)


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() == "true"


def _normalize_database_uri(uri):
    if uri and uri.startswith("postgres://"):
        return "postgresql://" + uri[len("postgres://"):]
    return uri


def configured_database_uri():
    uri = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///lacksdrivers.db"
    )
    return _normalize_database_uri(uri)


def is_sqlite_database_uri(uri):
    return (uri or "").strip().lower().startswith("sqlite:")


def is_render_runtime(env=None):
    env = env or os.environ
    return any(env.get(name) for name in _RENDER_ENV_VARS)


def runtime_requires_persistent_db(env=None):
    env = env or os.environ
    return env.get("FLASK_ENV", "").lower() == "production" or is_render_runtime(env)


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-do-not-deploy")
    SQLALCHEMY_DATABASE_URI = configured_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    ENABLE_SOCKETIO = _env_bool("ENABLE_SOCKETIO", not runtime_requires_persistent_db())
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_PATH = os.environ.get(
        "SOCKETIO_PATH",
        "socket.io" if ENABLE_SOCKETIO else "_socketio_disabled",
    )
    SOCKETIO_PING_INTERVAL = int(os.environ.get("SOCKETIO_PING_INTERVAL", "25"))
    SOCKETIO_PING_TIMEOUT = int(os.environ.get("SOCKETIO_PING_TIMEOUT", "20"))


class DevConfig(BaseConfig):
    DEBUG = _env_bool("FLASK_DEBUG", False)


class TestConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProdConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


def _validate_persistent_runtime_config():
    if not os.environ.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY environment variable is required for production/Render runtime"
        )

    raw_database_uri = os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not raw_database_uri:
        raise RuntimeError(
            "A persistent database is required for production/Render runtime. "
            "Set SQLALCHEMY_DATABASE_URI or DATABASE_URL to a Postgres connection string."
        )

    if is_sqlite_database_uri(raw_database_uri):
        raise RuntimeError(
            "SQLite is not supported for production/Render runtime. "
            "Set SQLALCHEMY_DATABASE_URI or DATABASE_URL to a Postgres connection string."
        )


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    if env == "testing":
        return TestConfig
    if runtime_requires_persistent_db():
        _validate_persistent_runtime_config()
        return ProdConfig
    return DevConfig
