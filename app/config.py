"""Configuration classes selected by runtime environment.

Production and hosted runtimes must use a persistent database. If this service
is deployed on Render with SQLite or without a database URL, it fails fast
instead of accepting driver route data into a disposable container file.
"""
import os
from urllib.parse import urlparse

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


def _normalize_host(value):
    raw_value = (value or "").strip().rstrip("/")
    if not raw_value:
        return ""

    parsed_value = raw_value if "://" in raw_value else f"//{raw_value}"
    parsed = urlparse(parsed_value)
    return (parsed.netloc or parsed.path).lower()


def _env_csv(name):
    return tuple(
        host
        for host in (_normalize_host(item) for item in os.environ.get(name, "").split(","))
        if host
    )


def _env_upload_folder(name, default):
    return os.environ.get(name, default)


def _env_str(name):
    return (os.environ.get(name) or "").strip()


def _public_base_url():
    return (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("PUBLIC_URL")
        or os.environ.get("APP_URL")
        or os.environ.get("BASE_URL")
        or ""
    ).rstrip("/")


def _canonical_scheme():
    parsed_public_url = urlparse(_public_base_url())
    raw_scheme = (
        os.environ.get("CANONICAL_SCHEME")
        or parsed_public_url.scheme
        or "https"
    ).strip().lower()
    if raw_scheme.endswith("://"):
        raw_scheme = raw_scheme[:-3]
    return raw_scheme if raw_scheme in {"http", "https"} else "https"


def _canonical_host():
    explicit_host = _normalize_host(os.environ.get("CANONICAL_HOST"))
    if explicit_host:
        return explicit_host

    return _normalize_host(_public_base_url())


def _canonical_redirect_hosts():
    canonical_host = _canonical_host()
    hosts = [*_env_csv("REDIRECT_HOSTS"), _normalize_host(os.environ.get("RENDER_EXTERNAL_HOSTNAME"))]
    return tuple(dict.fromkeys(host for host in hosts if host and host != canonical_host))


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
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
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
    PUBLIC_BASE_URL = _public_base_url()
    APP_URL = os.environ.get("APP_URL", PUBLIC_BASE_URL).rstrip("/")
    BASE_URL = os.environ.get("BASE_URL", PUBLIC_BASE_URL).rstrip("/")
    PUBLIC_URL = os.environ.get("PUBLIC_URL", PUBLIC_BASE_URL).rstrip("/")
    PUBLIC_CONTACT_EMAIL = os.environ.get("PUBLIC_CONTACT_EMAIL", "bibbstechnology@gmail.com")
    STRIPE_SECRET_KEY = _env_str("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = _env_str("STRIPE_PUBLISHABLE_KEY")
    STRIPE_API_VERSION = _env_str("STRIPE_API_VERSION") or "2026-05-27.dahlia"
    STRIPE_ALLOW_PROMOTION_CODES = _env_bool("STRIPE_ALLOW_PROMOTION_CODES", True)
    STRIPE_AUTOMATIC_TAX = _env_bool("STRIPE_AUTOMATIC_TAX", False)
    STRIPE_PRICE_DAILY_ROUTE_PASS = _env_str("STRIPE_PRICE_DAILY_ROUTE_PASS")
    STRIPE_PRICE_ROUTE_PASS_EXTRA_EXPORT = _env_str("STRIPE_PRICE_ROUTE_PASS_EXTRA_EXPORT")
    STRIPE_PRICE_ROUTE_PASS_EXPORT_PACK = _env_str("STRIPE_PRICE_ROUTE_PASS_EXPORT_PACK")
    STRIPE_PRICE_SOLO_DRIVER = _env_str("STRIPE_PRICE_SOLO_DRIVER")
    STRIPE_PRICE_OWNER_OPERATOR = _env_str("STRIPE_PRICE_OWNER_OPERATOR")
    STRIPE_PRICE_SMALL_FLEET = _env_str("STRIPE_PRICE_SMALL_FLEET")
    STRIPE_PRICE_FLEET_OFFICE = _env_str("STRIPE_PRICE_FLEET_OFFICE")
    STRIPE_PRICE_DRIVER_FORMS_PACK = _env_str("STRIPE_PRICE_DRIVER_FORMS_PACK")
    STRIPE_PRICE_RECORD_KIT = _env_str("STRIPE_PRICE_RECORD_KIT")
    STRIPE_PRICE_IFTA_WORKSHEET_BUNDLE = _env_str("STRIPE_PRICE_IFTA_WORKSHEET_BUNDLE")
    STRIPE_PRICE_BRANDED_PACKET_SETUP = _env_str("STRIPE_PRICE_BRANDED_PACKET_SETUP")
    STRIPE_PRICE_PAPER_FORM_CONVERSION = _env_str("STRIPE_PRICE_PAPER_FORM_CONVERSION")
    STRIPE_PRICE_FLEET_PACKET_SETUP = _env_str("STRIPE_PRICE_FLEET_PACKET_SETUP")
    GOOGLE_MAPS_API_KEY = _env_str("GOOGLE_MAPS_API_KEY")
    GOOGLE_CLIENT_ID = _env_str("GOOGLE_CLIENT_ID") or _env_str("GOOGLE_OAUTH_CLIENT_ID")
    # Destination search + trucker place summary on the Start Shift Location page.
    # Review/AI summaries are ON by default; Place Details degrades gracefully if a
    # key/region can't serve those fields. Set the env var to "false" to disable.
    ENABLE_DESTINATION_AUTOCOMPLETE = _env_bool("ENABLE_DESTINATION_AUTOCOMPLETE", True)
    ENABLE_TRUCKER_PLACE_SUMMARY = _env_bool("ENABLE_TRUCKER_PLACE_SUMMARY", True)
    ENABLE_GOOGLE_REVIEW_SUMMARY = _env_bool("ENABLE_GOOGLE_REVIEW_SUMMARY", True)
    ENABLE_GOOGLE_GENERATIVE_SUMMARY = _env_bool("ENABLE_GOOGLE_GENERATIVE_SUMMARY", True)
    CANONICAL_SCHEME = _canonical_scheme()
    CANONICAL_HOST = _canonical_host()
    ENFORCE_CANONICAL_HOST = _env_bool("ENFORCE_CANONICAL_HOST", False)
    REDIRECT_HOSTS = _canonical_redirect_hosts()
    DRIVER_LOG_PHOTO_UPLOAD_FOLDER = _env_upload_folder(
        "DRIVER_LOG_PHOTO_UPLOAD_FOLDER",
        "uploads/driver_log_photos",
    )
    DAMAGE_UPLOAD_FOLDER = _env_upload_folder(
        "DAMAGE_UPLOAD_FOLDER",
        "uploads/damage_photos",
    )
    HOT_PART_UPLOAD_FOLDER = _env_upload_folder(
        "HOT_PART_UPLOAD_FOLDER",
        "uploads/hot_part_photos",
    )
    IFTA_UPLOAD_FOLDER = _env_upload_folder(
        "IFTA_UPLOAD_FOLDER",
        "uploads/ifta_receipts",
    )


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
