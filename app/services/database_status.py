"""Database readiness helpers for deploy and health checks."""
from sqlalchemy import inspect

from app.config import is_sqlite_database_uri, runtime_requires_persistent_db
from app.extensions import db

IGNORED_TABLES = {"alembic_version"}


def required_table_names():
    return set(db.metadata.tables.keys())


def database_table_names():
    return set(inspect(db.engine).get_table_names())


def app_table_names(table_names=None):
    names = set(table_names) if table_names is not None else database_table_names()
    return names - IGNORED_TABLES


def database_status(database_uri=""):
    bind = db.session.get_bind()
    dialect = bind.dialect.name if bind is not None else "unknown"
    sqlite_database = dialect == "sqlite" or is_sqlite_database_uri(database_uri)
    table_names = database_table_names()
    missing_tables = sorted(required_table_names() - table_names)
    unsafe_runtime = runtime_requires_persistent_db() and sqlite_database
    return {
        "dialect": dialect,
        "persistent": not sqlite_database,
        "label": "Persistent database" if not sqlite_database else "SQLite local database",
        "warning": sqlite_database,
        "missing_tables": missing_tables,
        "schema_ready": not missing_tables,
        "ready": not unsafe_runtime and not missing_tables,
    }
