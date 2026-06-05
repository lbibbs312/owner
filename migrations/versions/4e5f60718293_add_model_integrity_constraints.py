"""Add model integrity constraints

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "4e5f60718293"
down_revision = "3d4e5f607182"
branch_labels = None
depends_on = None


def _inspector():
    return inspect(op.get_bind())


def _has_table(table_name):
    return _inspector().has_table(table_name)


def _column_names(table_name):
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_names(table_name):
    if not _has_table(table_name):
        return set()
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _unique_names(table_name):
    if not _has_table(table_name):
        return set()
    return {constraint["name"] for constraint in _inspector().get_unique_constraints(table_name)}


def _check_names(table_name):
    if not _has_table(table_name):
        return set()
    return {constraint["name"] for constraint in _inspector().get_check_constraints(table_name)}


def _has_rows(sql):
    return op.get_bind().execute(text(sql)).first() is not None


def _guard_no_rows(sql, message):
    if _has_rows(sql):
        raise RuntimeError(message)


def _add_audit_columns():
    if not _has_table("audit_event"):
        return
    columns = _column_names("audit_event")
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        if "tenant_id" not in columns:
            batch_op.add_column(
                sa.Column("tenant_id", sa.String(length=80), nullable=False, server_default="lacksdrivers")
            )
        if "correlation_id" not in columns:
            batch_op.add_column(sa.Column("correlation_id", sa.String(length=120), nullable=True))
        if "before_json" not in columns:
            batch_op.add_column(sa.Column("before_json", sa.JSON(), nullable=True))
        if "after_json" not in columns:
            batch_op.add_column(sa.Column("after_json", sa.JSON(), nullable=True))
        if "metadata_json" not in columns:
            batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
    indexes = _index_names("audit_event")
    if "ix_audit_event_tenant_id" not in indexes:
        op.create_index("ix_audit_event_tenant_id", "audit_event", ["tenant_id"])
    if "ix_audit_event_correlation_id" not in indexes:
        op.create_index("ix_audit_event_correlation_id", "audit_event", ["correlation_id"])


def _add_flow_constraints():
    if _has_table("flow_event") and "uq_flow_event_offline_idempotency_present" not in _index_names("flow_event"):
        _guard_no_rows(
            """
            SELECT 1
            FROM flow_event
            WHERE device_id IS NOT NULL AND offline_event_id IS NOT NULL
            GROUP BY tenant_id, device_id, offline_event_id
            HAVING COUNT(*) > 1
            """,
            "Duplicate flow_event offline ids exist; dedupe before adding idempotency constraint.",
        )
        op.create_index(
            "uq_flow_event_offline_idempotency_present",
            "flow_event",
            ["tenant_id", "device_id", "offline_event_id"],
            unique=True,
            sqlite_where=sa.text("device_id IS NOT NULL AND offline_event_id IS NOT NULL"),
            postgresql_where=sa.text("device_id IS NOT NULL AND offline_event_id IS NOT NULL"),
        )

    if _has_table("container_item"):
        _guard_no_rows(
            "SELECT 1 FROM container_item WHERE quantity < 0",
            "Negative container_item.quantity values exist; fix them before adding quantity constraint.",
        )
        if "ck_container_item_quantity_nonnegative" not in _check_names("container_item"):
            with op.batch_alter_table("container_item", schema=None) as batch_op:
                batch_op.create_check_constraint("ck_container_item_quantity_nonnegative", "quantity >= 0")

    if _has_table("container_tree_snapshot"):
        _guard_no_rows(
            "SELECT 1 FROM container_tree_snapshot WHERE current_quantity < 0",
            "Negative container_tree_snapshot.current_quantity values exist; fix them before adding quantity constraint.",
        )
        if "ck_container_tree_snapshot_quantity_nonnegative" not in _check_names("container_tree_snapshot"):
            with op.batch_alter_table("container_tree_snapshot", schema=None) as batch_op:
                batch_op.create_check_constraint(
                    "ck_container_tree_snapshot_quantity_nonnegative",
                    "current_quantity >= 0",
                )

    if _has_table("manifest_line"):
        _guard_no_rows(
            "SELECT 1 FROM manifest_line WHERE quantity_expected < 0 OR quantity_scanned < 0 OR quantity_scanned > quantity_expected",
            "Invalid manifest_line quantities exist; fix them before adding quantity constraints.",
        )
        checks = _check_names("manifest_line")
        with op.batch_alter_table("manifest_line", schema=None) as batch_op:
            if "ck_manifest_line_expected_nonnegative" not in checks:
                batch_op.create_check_constraint("ck_manifest_line_expected_nonnegative", "quantity_expected >= 0")
            if "ck_manifest_line_scanned_nonnegative" not in checks:
                batch_op.create_check_constraint("ck_manifest_line_scanned_nonnegative", "quantity_scanned >= 0")
            if "ck_manifest_line_scanned_not_over_expected" not in checks:
                batch_op.create_check_constraint(
                    "ck_manifest_line_scanned_not_over_expected",
                    "quantity_scanned <= quantity_expected",
                )


def _add_part_constraints():
    if _has_table("part_master") and "uq_part_master_tenant_canonical" not in _unique_names("part_master"):
        _guard_no_rows(
            """
            SELECT 1
            FROM part_master
            GROUP BY tenant_id, canonical_part_number
            HAVING COUNT(*) > 1
            """,
            "Duplicate part_master tenant/canonical_part_number values exist; dedupe before adding uniqueness.",
        )
        with op.batch_alter_table("part_master", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_part_master_tenant_canonical",
                ["tenant_id", "canonical_part_number"],
            )

    if _has_table("part_alias") and "uq_part_alias_tenant_normalized" not in _unique_names("part_alias"):
        columns = _column_names("part_alias")
        if "tenant_id" not in columns:
            with op.batch_alter_table("part_alias", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("tenant_id", sa.String(length=80), nullable=False, server_default="lacksdrivers")
                )
        _guard_no_rows(
            """
            SELECT 1
            FROM part_alias
            GROUP BY tenant_id, normalized_value
            HAVING COUNT(*) > 1
            """,
            "Duplicate part_alias tenant/normalized_value values exist; dedupe before adding uniqueness.",
        )
        with op.batch_alter_table("part_alias", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_part_alias_tenant_normalized",
                ["tenant_id", "normalized_value"],
            )

    if _has_table("move_part"):
        _guard_no_rows(
            """
            SELECT 1
            FROM move_part
            WHERE expected_quantity < 0
               OR picked_quantity < 0
               OR dropped_quantity < 0
               OR picked_quantity > expected_quantity
               OR dropped_quantity > expected_quantity
            """,
            "Invalid move_part quantities exist; fix them before adding quantity constraints.",
        )
        checks = _check_names("move_part")
        with op.batch_alter_table("move_part", schema=None) as batch_op:
            if "ck_move_part_expected_quantity_nonnegative" not in checks:
                batch_op.create_check_constraint("ck_move_part_expected_quantity_nonnegative", "expected_quantity >= 0")
            if "ck_move_part_picked_quantity_nonnegative" not in checks:
                batch_op.create_check_constraint("ck_move_part_picked_quantity_nonnegative", "picked_quantity >= 0")
            if "ck_move_part_dropped_quantity_nonnegative" not in checks:
                batch_op.create_check_constraint("ck_move_part_dropped_quantity_nonnegative", "dropped_quantity >= 0")
            if "ck_move_part_picked_not_over_expected" not in checks:
                batch_op.create_check_constraint("ck_move_part_picked_not_over_expected", "picked_quantity <= expected_quantity")
            if "ck_move_part_dropped_not_over_expected" not in checks:
                batch_op.create_check_constraint("ck_move_part_dropped_not_over_expected", "dropped_quantity <= expected_quantity")


def _add_transfer_constraints():
    if not _has_table("plant_transfer_line"):
        return
    _guard_no_rows(
        """
        SELECT 1
        FROM plant_transfer_line
        WHERE line_number <= 0
           OR TRIM(quantity) LIKE '-%'
           OR TRIM(skids) LIKE '-%'
           OR COALESCE(NULLIF(TRIM(part_number), ''), NULLIF(TRIM(quantity), ''), NULLIF(TRIM(skids), '')) IS NULL
        """,
        "Invalid plant_transfer_line rows exist; fix line numbers, negative values, or remarks-only rows before adding constraints.",
    )
    if "uq_plant_transfer_line_slot" not in _unique_names("plant_transfer_line"):
        _guard_no_rows(
            """
            SELECT 1
            FROM plant_transfer_line
            GROUP BY plant_transfer_id, line_number, side
            HAVING COUNT(*) > 1
            """,
            "Duplicate plant_transfer_line slots exist; dedupe before adding uniqueness.",
        )
    checks = _check_names("plant_transfer_line")
    with op.batch_alter_table("plant_transfer_line", schema=None) as batch_op:
        if "uq_plant_transfer_line_slot" not in _unique_names("plant_transfer_line"):
            batch_op.create_unique_constraint(
                "uq_plant_transfer_line_slot",
                ["plant_transfer_id", "line_number", "side"],
            )
        if "ck_plant_transfer_line_number_positive" not in checks:
            batch_op.create_check_constraint("ck_plant_transfer_line_number_positive", "line_number > 0")
        if "ck_plant_transfer_line_has_cargo_detail" not in checks:
            batch_op.create_check_constraint(
                "ck_plant_transfer_line_has_cargo_detail",
                "COALESCE(NULLIF(TRIM(part_number), ''), NULLIF(TRIM(quantity), ''), NULLIF(TRIM(skids), '')) IS NOT NULL",
            )
        if "ck_plant_transfer_line_quantity_nonnegative" not in checks:
            batch_op.create_check_constraint(
                "ck_plant_transfer_line_quantity_nonnegative",
                "quantity IS NULL OR TRIM(quantity) = '' OR TRIM(quantity) NOT LIKE '-%'",
            )
        if "ck_plant_transfer_line_skids_nonnegative" not in checks:
            batch_op.create_check_constraint(
                "ck_plant_transfer_line_skids_nonnegative",
                "skids IS NULL OR TRIM(skids) = '' OR TRIM(skids) NOT LIKE '-%'",
            )


def upgrade():
    _add_audit_columns()
    _add_flow_constraints()
    _add_part_constraints()
    _add_transfer_constraints()


def downgrade():
    if _has_table("plant_transfer_line"):
        with op.batch_alter_table("plant_transfer_line", schema=None) as batch_op:
            batch_op.drop_constraint("ck_plant_transfer_line_skids_nonnegative", type_="check")
            batch_op.drop_constraint("ck_plant_transfer_line_quantity_nonnegative", type_="check")
            batch_op.drop_constraint("ck_plant_transfer_line_has_cargo_detail", type_="check")
            batch_op.drop_constraint("ck_plant_transfer_line_number_positive", type_="check")
            batch_op.drop_constraint("uq_plant_transfer_line_slot", type_="unique")
    if _has_table("move_part"):
        with op.batch_alter_table("move_part", schema=None) as batch_op:
            batch_op.drop_constraint("ck_move_part_dropped_not_over_expected", type_="check")
            batch_op.drop_constraint("ck_move_part_picked_not_over_expected", type_="check")
            batch_op.drop_constraint("ck_move_part_dropped_quantity_nonnegative", type_="check")
            batch_op.drop_constraint("ck_move_part_picked_quantity_nonnegative", type_="check")
            batch_op.drop_constraint("ck_move_part_expected_quantity_nonnegative", type_="check")
    if _has_table("part_alias"):
        with op.batch_alter_table("part_alias", schema=None) as batch_op:
            batch_op.drop_constraint("uq_part_alias_tenant_normalized", type_="unique")
    if _has_table("part_master"):
        with op.batch_alter_table("part_master", schema=None) as batch_op:
            batch_op.drop_constraint("uq_part_master_tenant_canonical", type_="unique")
    if _has_table("manifest_line"):
        with op.batch_alter_table("manifest_line", schema=None) as batch_op:
            batch_op.drop_constraint("ck_manifest_line_scanned_not_over_expected", type_="check")
            batch_op.drop_constraint("ck_manifest_line_scanned_nonnegative", type_="check")
            batch_op.drop_constraint("ck_manifest_line_expected_nonnegative", type_="check")
    if _has_table("container_tree_snapshot"):
        with op.batch_alter_table("container_tree_snapshot", schema=None) as batch_op:
            batch_op.drop_constraint("ck_container_tree_snapshot_quantity_nonnegative", type_="check")
    if _has_table("container_item"):
        with op.batch_alter_table("container_item", schema=None) as batch_op:
            batch_op.drop_constraint("ck_container_item_quantity_nonnegative", type_="check")
    if _has_table("flow_event") and "uq_flow_event_offline_idempotency_present" in _index_names("flow_event"):
        op.drop_index("uq_flow_event_offline_idempotency_present", table_name="flow_event")
    if _has_table("audit_event"):
        indexes = _index_names("audit_event")
        if "ix_audit_event_correlation_id" in indexes:
            op.drop_index("ix_audit_event_correlation_id", table_name="audit_event")
        if "ix_audit_event_tenant_id" in indexes:
            op.drop_index("ix_audit_event_tenant_id", table_name="audit_event")
        columns = _column_names("audit_event")
        with op.batch_alter_table("audit_event", schema=None) as batch_op:
            for column_name in ("metadata_json", "after_json", "before_json", "correlation_id", "tenant_id"):
                if column_name in columns:
                    batch_op.drop_column(column_name)
