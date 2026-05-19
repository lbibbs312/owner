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
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    import app.config as config

    return importlib.reload(config)


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
        tables = set(inspect(db.engine).get_table_names())
        assert "user" in tables
        assert "driver_log" in tables
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == "f9b0c1d2e3f4"

    response = app.test_client().get("/readyz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["schema"] == "ok"
    assert payload["missing_tables"] == []
