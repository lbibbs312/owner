"""Operational CLI commands used by deployment."""
import click
from flask_migrate import stamp, upgrade

from app.extensions import db
from app.services.database_status import app_table_names, database_status, database_table_names


CORE_TABLES = {"user", "driver_log", "pretrip", "posttrip", "shift_record", "task"}


def register_cli_commands(app):
    @app.cli.command("deploy-db")
    def deploy_db():
        """Create or migrate the deployment database safely."""
        table_names = database_table_names()
        existing_app_tables = app_table_names(table_names)

        if not existing_app_tables:
            click.echo("No app tables found; creating current schema and stamping Alembic head.")
            db.create_all()
            stamp(revision="head")
            status = database_status(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
            if status["missing_tables"]:
                raise click.ClickException(
                    "Schema bootstrap did not create required tables: "
                    + ", ".join(status["missing_tables"])
                )
            click.echo("Database schema ready.")
            return

        missing_core = sorted(CORE_TABLES - table_names)
        if missing_core:
            raise click.ClickException(
                "Database has a partial app schema. Refusing to migrate with missing core tables: "
                + ", ".join(missing_core)
            )

        click.echo("Existing app schema found; running Alembic upgrade.")
        upgrade()
        status = database_status(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        if status["missing_tables"]:
            raise click.ClickException(
                "Database upgrade left required tables missing: "
                + ", ".join(status["missing_tables"])
            )
        click.echo("Database schema ready.")
