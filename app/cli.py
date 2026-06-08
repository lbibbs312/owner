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

    @app.cli.command("sync-stripe-catalog")
    @click.option("--write-env", is_flag=True, default=False, help="Append created price IDs to .env")
    def sync_stripe_catalog(write_env):
        """Create Stripe Products/Prices for plans that have an amount but no price ID.

        Idempotent: an existing active Price with a matching ``lookup_key`` is
        reused instead of creating a duplicate. Prints the ``STRIPE_PRICE_*``
        env lines to add (or appends them with --write-env).
        """
        import importlib
        import os

        from flask import current_app

        from app.services.stripe_checkout import BILLING_PLANS

        secret = current_app.config.get("STRIPE_SECRET_KEY")
        if not secret:
            raise click.ClickException("STRIPE_SECRET_KEY is not configured.")
        stripe = importlib.import_module("stripe")
        stripe.api_key = secret

        env_lines = []
        for plan in BILLING_PLANS.values():
            if plan.unit_amount is None:
                continue
            if current_app.config.get(plan.price_env):
                click.echo(f"{plan.key}: already configured via {plan.price_env}")
                continue
            existing = stripe.Price.list(lookup_keys=[plan.key], active=True, limit=1)
            found = existing.data if hasattr(existing, "data") else existing.get("data", [])
            if found:
                price_id = found[0].id
                click.echo(f"{plan.key}: reused existing price {price_id}")
            else:
                product_params = {"name": f"MoveDefense {plan.name}"}
                if plan.tax_code:
                    product_params["tax_code"] = plan.tax_code
                product = stripe.Product.create(**product_params)
                price_params = {
                    "product": product.id,
                    "unit_amount": plan.unit_amount,
                    "currency": "usd",
                    "lookup_key": plan.key,
                    "nickname": plan.name,
                }
                if plan.interval:
                    price_params["recurring"] = {"interval": plan.interval}
                price = stripe.Price.create(**price_params)
                price_id = price.id
                click.echo(f"{plan.key}: created product {product.id} + price {price_id}")
            env_lines.append(f"{plan.price_env}={price_id}")

        if not env_lines:
            click.echo("Nothing to create; all priced plans are configured.")
            return
        click.echo("\n# --- price IDs (add to .env) ---")
        for line in env_lines:
            click.echo(line)
        if write_env:
            env_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, ".env"))
            with open(env_path, "a") as handle:
                handle.write("\n# Stripe price IDs created by sync-stripe-catalog\n" + "\n".join(env_lines) + "\n")
            click.echo(f"\nAppended {len(env_lines)} price ID(s) to {env_path}")
