import importlib
import runpy

import pytest
from sqlalchemy import inspect, text


def _reload_config(monkeypatch, **values):
    for key in [
        "FLASK_ENV",
        "RENDER",
        "RENDER_SERVICE_ID",
        "RENDER_EXTERNAL_HOSTNAME",
        "RENDER_EXTERNAL_URL",
        "SECRET_KEY",
        "SQLALCHEMY_DATABASE_URI",
        "DATABASE_URL",
        "ENABLE_SOCKETIO",
        "SOCKETIO_ASYNC_MODE",
        "SOCKETIO_PATH",
        "APP_URL",
        "BASE_URL",
        "PUBLIC_BASE_URL",
        "PUBLIC_URL",
        "CANONICAL_HOST",
        "CANONICAL_SCHEME",
        "ENFORCE_CANONICAL_HOST",
        "REDIRECT_HOSTS",
        "DRIVER_LOG_PHOTO_UPLOAD_FOLDER",
        "DAMAGE_UPLOAD_FOLDER",
        "HOT_PART_UPLOAD_FOLDER",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    import app.config as config

    return importlib.reload(config)


def _canonical_redirect_app(config):
    from app import create_app

    class CanonicalRedirectConfig(config.TestConfig):
        TESTING = False

    return create_app(CanonicalRedirectConfig)


def test_render_runtime_requires_database_url_even_without_flask_env(monkeypatch):
    config = _reload_config(monkeypatch, RENDER="true", SECRET_KEY="secret")

    with pytest.raises(RuntimeError, match="persistent database"):
        config.get_config()


def test_render_runtime_rejects_sqlite_even_without_flask_env(monkeypatch):
    config = _reload_config(
        monkeypatch,
        RENDER="true",
        SECRET_KEY="secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///lacksdrivers.db",
    )

    with pytest.raises(RuntimeError, match="SQLite is not supported"):
        config.get_config()


def test_render_runtime_uses_prod_config_with_postgres(monkeypatch):
    config = _reload_config(
        monkeypatch,
        RENDER="true",
        SECRET_KEY="secret",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@example.com/db",
    )

    selected = config.get_config()

    assert selected is config.ProdConfig
    assert selected.SESSION_COOKIE_SECURE is True
    assert selected.ENABLE_SOCKETIO is False
    assert selected.SOCKETIO_ASYNC_MODE == "threading"
    assert selected.SOCKETIO_PATH == "_socketio_disabled"
    assert selected.SQLALCHEMY_DATABASE_URI.startswith("postgresql://")


def test_upload_folders_can_be_configured_from_environment(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="production",
        SECRET_KEY="secret",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@example.com/db",
        DRIVER_LOG_PHOTO_UPLOAD_FOLDER="/var/data/movedefense_uploads/driver_log_photos",
        DAMAGE_UPLOAD_FOLDER="/var/data/movedefense_uploads/damage_photos",
        HOT_PART_UPLOAD_FOLDER="/var/data/movedefense_uploads/hot_part_photos",
    )

    selected = config.get_config()

    assert selected.DRIVER_LOG_PHOTO_UPLOAD_FOLDER == "/var/data/movedefense_uploads/driver_log_photos"
    assert selected.DAMAGE_UPLOAD_FOLDER == "/var/data/movedefense_uploads/damage_photos"
    assert selected.HOT_PART_UPLOAD_FOLDER == "/var/data/movedefense_uploads/hot_part_photos"


def test_socketio_can_be_explicitly_enabled(monkeypatch):
    config = _reload_config(
        monkeypatch,
        RENDER="true",
        SECRET_KEY="secret",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@example.com/db",
        ENABLE_SOCKETIO="true",
    )

    selected = config.get_config()

    assert selected.ENABLE_SOCKETIO is True
    assert selected.SOCKETIO_ASYNC_MODE == "threading"
    assert selected.SOCKETIO_PATH == "socket.io"


def test_database_url_fallback_normalizes_render_postgres_scheme(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="production",
        SECRET_KEY="secret",
        DATABASE_URL="postgres://user:pass@example.com/db",
    )

    selected = config.get_config()

    assert selected is config.ProdConfig
    assert selected.SQLALCHEMY_DATABASE_URI == "postgresql://user:pass@example.com/db"


def test_render_rejects_development_entrypoint(monkeypatch):
    _reload_config(
        monkeypatch,
        RENDER="true",
        SECRET_KEY="secret",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@example.com/db",
    )

    with pytest.raises(RuntimeError, match="Refusing to run python lacksdrivers.py on Render"):
        runpy.run_path("lacksdrivers.py", run_name="__main__")


def test_readyz_reports_missing_schema(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app

    app = create_app()
    response = app.test_client().get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["schema"] == "missing_tables"
    assert "driver_log" in payload["missing_tables"]


def test_deploy_db_bootstraps_empty_database_and_stamps_head(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    result = app.test_cli_runner().invoke(args=["deploy-db"])

    assert result.exit_code == 0, result.output
    assert "Database schema ready" in result.output
    with app.app_context():
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        tables = set(inspect(db.engine).get_table_names())
        assert "user" in tables
        assert "driver_log" in tables
        # Bootstrapping stamps the latest migration head (read it dynamically so new
        # migrations don't require touching this test).
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "migrations")
        expected_head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == expected_head

    response = app.test_client().get("/readyz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["schema"] == "ok"
    assert payload["missing_tables"] == []


def test_public_url_config_normalizes_move_defense_hosts(monkeypatch):
    config = _reload_config(
        monkeypatch,
        PUBLIC_BASE_URL="https://movedefense.com/",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https://",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )

    assert config.BaseConfig.PUBLIC_BASE_URL == "https://movedefense.com"
    assert config.BaseConfig.APP_URL == "https://movedefense.com"
    assert config.BaseConfig.BASE_URL == "https://movedefense.com"
    assert config.BaseConfig.PUBLIC_URL == "https://movedefense.com"
    assert config.BaseConfig.CANONICAL_HOST == "movedefense.com"
    assert config.BaseConfig.CANONICAL_SCHEME == "https"
    assert config.BaseConfig.ENFORCE_CANONICAL_HOST is True
    assert config.BaseConfig.REDIRECT_HOSTS == ("lacksdrivers-com.onrender.com",)


def test_old_render_host_redirects_mobile_path_to_movedefense(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )

    app = _canonical_redirect_app(config)
    response = app.test_client().get("/mobile", headers={"Host": "lacksdrivers-com.onrender.com"})

    assert response.status_code == 308
    assert response.headers["Location"] == "https://movedefense.com/mobile"


def test_old_render_host_redirect_preserves_login_query_string(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )

    app = _canonical_redirect_app(config)
    response = app.test_client().get(
        "/login?next=/reports&required_role=driver",
        headers={"Host": "lacksdrivers-com.onrender.com"},
    )

    assert response.status_code == 308
    assert (
        response.headers["Location"]
        == "https://movedefense.com/login?next=/reports&required_role=driver"
    )


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "movedefense.com"])
def test_localhost_and_canonical_hosts_do_not_redirect(monkeypatch, host):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )

    app = _canonical_redirect_app(config)
    response = app.test_client().get("/healthz", headers={"Host": host})

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_health_check_on_old_render_host_is_not_redirected(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )

    app = _canonical_redirect_app(config)
    response = app.test_client().get("/healthz", headers={"Host": "lacksdrivers-com.onrender.com"})

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_testing_config_does_not_enforce_canonical_redirect(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )
    from app import create_app

    app = create_app(config.TestConfig)
    response = app.test_client().get("/mobile", headers={"Host": "lacksdrivers-com.onrender.com"})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_generated_absolute_links_use_public_base_url(monkeypatch):
    config = _reload_config(
        monkeypatch,
        FLASK_ENV="testing",
        PUBLIC_BASE_URL="https://movedefense.com",
        CANONICAL_HOST="movedefense.com",
        CANONICAL_SCHEME="https",
        ENFORCE_CANONICAL_HOST="true",
        RENDER_EXTERNAL_HOSTNAME="lacksdrivers-com.onrender.com",
    )
    from app import create_app
    from app.services.public_urls import absolute_public_url, public_url_for

    app = create_app(config.TestConfig)
    with app.test_request_context("/", headers={"Host": "lacksdrivers-com.onrender.com"}):
        assert public_url_for("public.healthz") == "https://movedefense.com/healthz"
        assert (
            absolute_public_url("/login?next=/reports&required_role=driver")
            == "https://movedefense.com/login?next=/reports&required_role=driver"
        )
