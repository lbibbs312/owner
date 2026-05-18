import importlib
import runpy

import pytest


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
    assert selected.SQLALCHEMY_DATABASE_URI.startswith("postgresql://")


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
