"""Configuration classes selected by the FLASK_ENV environment variable.

All values are read from env vars; nothing is hardcoded. Production deliberately
fails fast if SECRET_KEY is unset or the database URI still points at SQLite —
those mistakes have already been made in this codebase once and shouldn't be
made again silently.
"""
import os


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() == "true"


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-do-not-deploy")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "SQLALCHEMY_DATABASE_URI", "sqlite:///lacksdrivers.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)


class DevConfig(BaseConfig):
    DEBUG = _env_bool("FLASK_DEBUG", False)


class TestConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProdConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


def _validate_prod_config():
    if not os.environ.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production"
        )
    if ProdConfig.SQLALCHEMY_DATABASE_URI.startswith("sqlite:"):
        raise RuntimeError(
            "SQLite is not supported in production. "
            "Set SQLALCHEMY_DATABASE_URI to a Postgres connection string."
        )


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    if env == "production":
        _validate_prod_config()
        return ProdConfig
    if env == "testing":
        return TestConfig
    return DevConfig
