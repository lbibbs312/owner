"""Add packet workspace tables

Revision ID: 5f60718293a4
Revises: 4e5f60718293
Create Date: 2026-06-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "5f60718293a4"
down_revision = "4e5f60718293"
branch_labels = None
depends_on = None


def _has_table(table_name):
    return inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name):
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name, column):
    if _has_table(table_name) and column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def upgrade():
    _add_column_if_missing("damage_photo", sa.Column("sha256_hash", sa.String(length=64), nullable=True))
    _add_column_if_missing("driver_log_photo", sa.Column("sha256_hash", sa.String(length=64), nullable=True))

    if not _has_table("accident_incident_report"):
        op.create_table(
            "accident_incident_report",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("damage_report_id", sa.Integer(), sa.ForeignKey("damage_report.id"), nullable=True),
            sa.Column("driver_log_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("locked_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("incident_date_time", sa.DateTime(), nullable=True),
            sa.Column("reported_date_time", sa.DateTime(), nullable=False),
            sa.Column("truck", sa.String(length=50), nullable=True),
            sa.Column("trailer", sa.String(length=50), nullable=True),
            sa.Column("route_id", sa.String(length=80), nullable=True),
            sa.Column("stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("plant_or_location", sa.String(length=120), nullable=True),
            sa.Column("exact_location_text", sa.String(length=255), nullable=True),
            sa.Column("gps_latitude", sa.Float(), nullable=True),
            sa.Column("gps_longitude", sa.Float(), nullable=True),
            sa.Column("public_road_private_property_yard_dock", sa.String(length=40), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("state", sa.String(length=40), nullable=True),
            sa.Column("nearest_city_or_town", sa.String(length=120), nullable=True),
            sa.Column("weather", sa.String(length=120), nullable=True),
            sa.Column("lighting", sa.String(length=120), nullable=True),
            sa.Column("surface_condition", sa.String(length=120), nullable=True),
            sa.Column("anyone_hurt", sa.String(length=20), nullable=True),
            sa.Column("other_vehicle_involved_quick", sa.String(length=20), nullable=True),
            sa.Column("property_damage_quick", sa.String(length=20), nullable=True),
            sa.Column("police_called_quick", sa.String(length=20), nullable=True),
            sa.Column("tow_away_needed", sa.String(length=20), nullable=True),
            sa.Column("vehicle_safe_to_operate_quick", sa.String(length=20), nullable=True),
            sa.Column("manager_notified_quick", sa.String(length=20), nullable=True),
            sa.Column("hit_object", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("hit_by_third_party", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("backing_incident", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("dock_or_yard_incident", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cargo_damage", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("vehicle_damage", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("property_damage", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("injury_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tow_away", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("police_called", sa.String(length=20), nullable=True),
            sa.Column("other_vehicle_involved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("claim_expected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("other_incident_type", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("driver_statement", sa.Text(), nullable=True),
            sa.Column("facts_only_acknowledgement", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("company_vehicle_damage_description", sa.Text(), nullable=True),
            sa.Column("other_vehicle_damage_description", sa.Text(), nullable=True),
            sa.Column("property_damage_description", sa.Text(), nullable=True),
            sa.Column("cargo_damage_description", sa.Text(), nullable=True),
            sa.Column("visible_damage_location", sa.String(length=255), nullable=True),
            sa.Column("vehicle_safe_to_operate", sa.String(length=20), nullable=True),
            sa.Column("repair_needed", sa.String(length=20), nullable=True),
            sa.Column("vehicle_removed_from_service", sa.String(length=20), nullable=True),
            sa.Column("other_driver_name", sa.String(length=120), nullable=True),
            sa.Column("other_driver_phone", sa.String(length=80), nullable=True),
            sa.Column("other_driver_license_number", sa.String(length=120), nullable=True),
            sa.Column("other_vehicle_make_model", sa.String(length=160), nullable=True),
            sa.Column("other_vehicle_plate", sa.String(length=80), nullable=True),
            sa.Column("other_insurance_company", sa.String(length=160), nullable=True),
            sa.Column("other_policy_or_claim_number", sa.String(length=160), nullable=True),
            sa.Column("other_party_notes", sa.Text(), nullable=True),
            sa.Column("police_agency", sa.String(length=160), nullable=True),
            sa.Column("police_report_number", sa.String(length=160), nullable=True),
            sa.Column("citation_issued", sa.String(length=20), nullable=True),
            sa.Column("citation_to_company_driver", sa.String(length=20), nullable=True),
            sa.Column("claim_opened", sa.String(length=20), nullable=True),
            sa.Column("claim_number", sa.String(length=160), nullable=True),
            sa.Column("insurance_company", sa.String(length=160), nullable=True),
            sa.Column("insurance_contact", sa.String(length=160), nullable=True),
            sa.Column("insurer_notified_at", sa.DateTime(), nullable=True),
            sa.Column("claim_notes", sa.Text(), nullable=True),
            sa.Column("public_road_in_commerce", sa.String(length=20), nullable=True),
            sa.Column("fatality", sa.String(length=20), nullable=True),
            sa.Column("number_of_injuries", sa.Integer(), nullable=True),
            sa.Column("number_of_fatalities", sa.Integer(), nullable=True),
            sa.Column("medical_treatment_away_from_scene", sa.String(length=20), nullable=True),
            sa.Column("disabling_damage_tow_away", sa.String(length=20), nullable=True),
            sa.Column("hazmat_released_other_than_fuel", sa.String(length=20), nullable=True),
            sa.Column("required_reports_attached", sa.String(length=20), nullable=True),
            sa.Column("loading_or_unloading_only", sa.String(length=20), nullable=True),
            sa.Column("boarding_or_alighting_only", sa.String(length=20), nullable=True),
            sa.Column("dot_review_status", sa.String(length=30), nullable=False, server_default="not_indicated"),
            sa.Column("dot_review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("driver_performing_safety_sensitive_function", sa.String(length=20), nullable=True),
            sa.Column("loss_of_human_life", sa.String(length=20), nullable=True),
            sa.Column("moving_violation_citation", sa.String(length=20), nullable=True),
            sa.Column("citation_time", sa.DateTime(), nullable=True),
            sa.Column("bodily_injury_treatment_away_from_scene", sa.String(length=20), nullable=True),
            sa.Column("tow_away_disabling_damage", sa.String(length=20), nullable=True),
            sa.Column("alcohol_test_review", sa.String(length=30), nullable=False, server_default="not_indicated"),
            sa.Column("alcohol_test_time", sa.DateTime(), nullable=True),
            sa.Column("alcohol_delay_reason", sa.Text(), nullable=True),
            sa.Column("controlled_substance_test_review", sa.String(length=30), nullable=False, server_default="not_indicated"),
            sa.Column("controlled_substance_test_time", sa.DateTime(), nullable=True),
            sa.Column("controlled_substance_delay_reason", sa.Text(), nullable=True),
            sa.Column("testing_reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("testing_reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("manager_notified", sa.String(length=20), nullable=True),
            sa.Column("manager_notified_at", sa.DateTime(), nullable=True),
            sa.Column("dispatcher_notified", sa.String(length=20), nullable=True),
            sa.Column("dispatcher_notified_at", sa.DateTime(), nullable=True),
            sa.Column("replacement_vehicle_needed", sa.String(length=20), nullable=True),
            sa.Column("driver_relieved_from_route", sa.String(length=20), nullable=True),
            sa.Column("photos_required_complete", sa.String(length=20), nullable=True),
            sa.Column("follow_up_notes", sa.Text(), nullable=True),
            sa.Column("manager_review_status", sa.String(length=40), nullable=False, server_default="open"),
            sa.Column("claim_review_status", sa.String(length=40), nullable=False, server_default="not_indicated"),
            sa.Column("close_status", sa.String(length=60), nullable=False, server_default="Needs more information"),
            sa.Column("manager_note", sa.Text(), nullable=True),
            sa.Column("driver_signature", sa.Text(), nullable=True),
            sa.Column("manager_signature", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("driver_can_edit", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("route_finalized", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
        )
        for column in (
            "damage_report_id",
            "driver_log_id",
            "driver_id",
            "route_id",
        ):
            op.create_index(f"ix_accident_incident_report_{column}", "accident_incident_report", [column])

    if not _has_table("accident_witness"):
        op.create_table(
            "accident_witness",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("accident_id", sa.Integer(), sa.ForeignKey("accident_incident_report.id"), nullable=False),
            sa.Column("witness_name", sa.String(length=120), nullable=True),
            sa.Column("witness_phone", sa.String(length=80), nullable=True),
            sa.Column("witness_statement_summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_accident_witness_accident_id", "accident_witness", ["accident_id"])

    if not _has_table("proof_media_file"):
        op.create_table(
            "proof_media_file",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("packet_type", sa.String(length=40), nullable=False),
            sa.Column("owner_type", sa.String(length=40), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=60), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("sha256_hash", sa.String(length=64), nullable=True),
            sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.Column("related_truck", sa.String(length=50), nullable=True),
            sa.Column("related_trailer", sa.String(length=50), nullable=True),
            sa.Column("related_route_id", sa.String(length=80), nullable=True),
            sa.Column("related_stop_id", sa.Integer(), sa.ForeignKey("driver_log.id"), nullable=True),
            sa.Column("manager_note", sa.Text(), nullable=True),
            sa.Column("media_not_required_reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_proof_media_file_packet_type", "proof_media_file", ["packet_type"])
        op.create_index("ix_proof_media_file_owner_type", "proof_media_file", ["owner_type"])
        op.create_index("ix_proof_media_file_owner_id", "proof_media_file", ["owner_id"])

    if not _has_table("ifta_worksheet"):
        op.create_table(
            "ifta_worksheet",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reporting_period_quarter", sa.String(length=10), nullable=True),
            sa.Column("reporting_year", sa.Integer(), nullable=True),
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("truck", sa.String(length=50), nullable=True),
            sa.Column("trailer", sa.String(length=50), nullable=True),
            sa.Column("vin_or_vehicle_unit_number", sa.String(length=120), nullable=True),
            sa.Column("fleet_number", sa.String(length=80), nullable=True),
            sa.Column("base_jurisdiction", sa.String(length=80), nullable=True),
            sa.Column("carrier_name", sa.String(length=160), nullable=True),
            sa.Column("ifta_license_number", sa.String(length=120), nullable=True),
            sa.Column("review_status", sa.String(length=40), nullable=False, server_default="Draft"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("locked_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("manager_note", sa.Text(), nullable=True),
            sa.Column("manager_signature", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_ifta_worksheet_driver_id", "ifta_worksheet", ["driver_id"])

    if not _has_table("ifta_trip_distance_row"):
        op.create_table(
            "ifta_trip_distance_row",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("ifta_worksheet.id"), nullable=False),
            sa.Column("trip_start_date", sa.Date(), nullable=True),
            sa.Column("trip_end_date", sa.Date(), nullable=True),
            sa.Column("origin_city", sa.String(length=120), nullable=True),
            sa.Column("origin_state", sa.String(length=40), nullable=True),
            sa.Column("destination_city", sa.String(length=120), nullable=True),
            sa.Column("destination_state", sa.String(length=40), nullable=True),
            sa.Column("route_traveled", sa.String(length=255), nullable=True),
            sa.Column("beginning_odometer", sa.Float(), nullable=True),
            sa.Column("ending_odometer", sa.Float(), nullable=True),
            sa.Column("total_trip_distance", sa.Float(), nullable=True),
            sa.Column("jurisdiction", sa.String(length=80), nullable=True),
            sa.Column("jurisdiction_distance", sa.Float(), nullable=True),
            sa.Column("taxable_distance", sa.Float(), nullable=True),
            sa.Column("nontaxable_distance", sa.Float(), nullable=True),
            sa.Column("toll_distance", sa.Float(), nullable=True),
            sa.Column("loaded_empty_deadhead", sa.String(length=20), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )
        op.create_index("ix_ifta_trip_distance_row_worksheet_id", "ifta_trip_distance_row", ["worksheet_id"])

    if not _has_table("ifta_fuel_record"):
        op.create_table(
            "ifta_fuel_record",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("ifta_worksheet.id"), nullable=False),
            sa.Column("purchase_date", sa.Date(), nullable=True),
            sa.Column("seller_name", sa.String(length=160), nullable=True),
            sa.Column("seller_address", sa.String(length=255), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("state_or_province", sa.String(length=40), nullable=True),
            sa.Column("gallons_or_liters", sa.Float(), nullable=True),
            sa.Column("fuel_type", sa.String(length=60), nullable=True),
            sa.Column("price_per_gallon_or_liter", sa.Float(), nullable=True),
            sa.Column("total_sale_amount", sa.Float(), nullable=True),
            sa.Column("vehicle_unit_number", sa.String(length=120), nullable=True),
            sa.Column("purchaser_name", sa.String(length=160), nullable=True),
            sa.Column("receipt_photo", sa.String(length=255), nullable=True),
            sa.Column("receipt_hash", sa.String(length=64), nullable=True),
            sa.Column("tax_paid", sa.String(length=20), nullable=True),
            sa.Column("bulk_fuel", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_ifta_fuel_record_worksheet_id", "ifta_fuel_record", ["worksheet_id"])

    if not _has_table("ifta_bulk_fuel_withdrawal"):
        op.create_table(
            "ifta_bulk_fuel_withdrawal",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("ifta_worksheet.id"), nullable=False),
            sa.Column("withdrawal_date", sa.Date(), nullable=True),
            sa.Column("gallons_or_liters", sa.Float(), nullable=True),
            sa.Column("fuel_type", sa.String(length=60), nullable=True),
            sa.Column("unit_number", sa.String(length=120), nullable=True),
            sa.Column("bulk_storage_location", sa.String(length=160), nullable=True),
            sa.Column("inventory_record_reference", sa.String(length=160), nullable=True),
            sa.Column("purchase_record_reference", sa.String(length=160), nullable=True),
        )
        op.create_index("ix_ifta_bulk_fuel_withdrawal_worksheet_id", "ifta_bulk_fuel_withdrawal", ["worksheet_id"])

    if not _has_table("packet_manager_review"):
        op.create_table(
            "packet_manager_review",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("packet_type", sa.String(length=40), nullable=False),
            sa.Column("owner_type", sa.String(length=40), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("close_status", sa.String(length=60), nullable=False),
            sa.Column("manager_note", sa.Text(), nullable=True),
            sa.Column("manager_signature", sa.Text(), nullable=True),
            sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_packet_manager_review_packet_type", "packet_manager_review", ["packet_type"])
        op.create_index("ix_packet_manager_review_owner_type", "packet_manager_review", ["owner_type"])
        op.create_index("ix_packet_manager_review_owner_id", "packet_manager_review", ["owner_id"])


def downgrade():
    for table_name in (
        "packet_manager_review",
        "ifta_bulk_fuel_withdrawal",
        "ifta_fuel_record",
        "ifta_trip_distance_row",
        "ifta_worksheet",
        "proof_media_file",
        "accident_witness",
        "accident_incident_report",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)
    if "sha256_hash" in _column_names("driver_log_photo"):
        op.drop_column("driver_log_photo", "sha256_hash")
    if "sha256_hash" in _column_names("damage_photo"):
        op.drop_column("damage_photo", "sha256_hash")
