from datetime import datetime

from app.extensions import db


class AccidentIncidentReport(db.Model):
    __tablename__ = "accident_incident_report"

    id = db.Column(db.Integer, primary_key=True)
    damage_report_id = db.Column(db.Integer, db.ForeignKey("damage_report.id"), nullable=True, index=True)
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    locked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    incident_date_time = db.Column(db.DateTime, nullable=True)
    reported_date_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    truck = db.Column(db.String(50), nullable=True)
    trailer = db.Column(db.String(50), nullable=True)
    route_id = db.Column(db.String(80), nullable=True, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    plant_or_location = db.Column(db.String(120), nullable=True)
    exact_location_text = db.Column(db.String(255), nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    public_road_private_property_yard_dock = db.Column(db.String(40), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state = db.Column(db.String(40), nullable=True)
    nearest_city_or_town = db.Column(db.String(120), nullable=True)
    weather = db.Column(db.String(120), nullable=True)
    lighting = db.Column(db.String(120), nullable=True)
    surface_condition = db.Column(db.String(120), nullable=True)

    anyone_hurt = db.Column(db.String(20), nullable=True)
    other_vehicle_involved_quick = db.Column(db.String(20), nullable=True)
    property_damage_quick = db.Column(db.String(20), nullable=True)
    police_called_quick = db.Column(db.String(20), nullable=True)
    tow_away_needed = db.Column(db.String(20), nullable=True)
    vehicle_safe_to_operate_quick = db.Column(db.String(20), nullable=True)
    manager_notified_quick = db.Column(db.String(20), nullable=True)

    hit_object = db.Column(db.Boolean, nullable=False, default=False)
    hit_by_third_party = db.Column(db.Boolean, nullable=False, default=False)
    backing_incident = db.Column(db.Boolean, nullable=False, default=False)
    dock_or_yard_incident = db.Column(db.Boolean, nullable=False, default=False)
    cargo_damage = db.Column(db.Boolean, nullable=False, default=False)
    vehicle_damage = db.Column(db.Boolean, nullable=False, default=False)
    property_damage = db.Column(db.Boolean, nullable=False, default=False)
    injury_reported = db.Column(db.Boolean, nullable=False, default=False)
    tow_away = db.Column(db.Boolean, nullable=False, default=False)
    police_called = db.Column(db.String(20), nullable=True)
    other_vehicle_involved = db.Column(db.Boolean, nullable=False, default=False)
    claim_expected = db.Column(db.Boolean, nullable=False, default=False)
    other_incident_type = db.Column(db.Boolean, nullable=False, default=False)

    driver_statement = db.Column(db.Text, nullable=True)
    facts_only_acknowledgement = db.Column(db.Boolean, nullable=False, default=False)
    company_vehicle_damage_description = db.Column(db.Text, nullable=True)
    other_vehicle_damage_description = db.Column(db.Text, nullable=True)
    property_damage_description = db.Column(db.Text, nullable=True)
    cargo_damage_description = db.Column(db.Text, nullable=True)
    visible_damage_location = db.Column(db.String(255), nullable=True)
    vehicle_safe_to_operate = db.Column(db.String(20), nullable=True)
    repair_needed = db.Column(db.String(20), nullable=True)
    vehicle_removed_from_service = db.Column(db.String(20), nullable=True)

    other_driver_name = db.Column(db.String(120), nullable=True)
    other_driver_phone = db.Column(db.String(80), nullable=True)
    other_driver_license_number = db.Column(db.String(120), nullable=True)
    other_vehicle_make_model = db.Column(db.String(160), nullable=True)
    other_vehicle_plate = db.Column(db.String(80), nullable=True)
    other_insurance_company = db.Column(db.String(160), nullable=True)
    other_policy_or_claim_number = db.Column(db.String(160), nullable=True)
    other_party_notes = db.Column(db.Text, nullable=True)

    police_agency = db.Column(db.String(160), nullable=True)
    police_report_number = db.Column(db.String(160), nullable=True)
    citation_issued = db.Column(db.String(20), nullable=True)
    citation_to_company_driver = db.Column(db.String(20), nullable=True)
    claim_opened = db.Column(db.String(20), nullable=True)
    claim_number = db.Column(db.String(160), nullable=True)
    insurance_company = db.Column(db.String(160), nullable=True)
    insurance_contact = db.Column(db.String(160), nullable=True)
    insurer_notified_at = db.Column(db.DateTime, nullable=True)
    claim_notes = db.Column(db.Text, nullable=True)

    public_road_in_commerce = db.Column(db.String(20), nullable=True)
    fatality = db.Column(db.String(20), nullable=True)
    number_of_injuries = db.Column(db.Integer, nullable=True)
    number_of_fatalities = db.Column(db.Integer, nullable=True)
    medical_treatment_away_from_scene = db.Column(db.String(20), nullable=True)
    disabling_damage_tow_away = db.Column(db.String(20), nullable=True)
    hazmat_released_other_than_fuel = db.Column(db.String(20), nullable=True)
    required_reports_attached = db.Column(db.String(20), nullable=True)
    loading_or_unloading_only = db.Column(db.String(20), nullable=True)
    boarding_or_alighting_only = db.Column(db.String(20), nullable=True)
    dot_review_status = db.Column(db.String(30), nullable=False, default="not_indicated")
    dot_review_note = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    driver_performing_safety_sensitive_function = db.Column(db.String(20), nullable=True)
    loss_of_human_life = db.Column(db.String(20), nullable=True)
    moving_violation_citation = db.Column(db.String(20), nullable=True)
    citation_time = db.Column(db.DateTime, nullable=True)
    bodily_injury_treatment_away_from_scene = db.Column(db.String(20), nullable=True)
    tow_away_disabling_damage = db.Column(db.String(20), nullable=True)
    alcohol_test_review = db.Column(db.String(30), nullable=False, default="not_indicated")
    alcohol_test_time = db.Column(db.DateTime, nullable=True)
    alcohol_delay_reason = db.Column(db.Text, nullable=True)
    controlled_substance_test_review = db.Column(db.String(30), nullable=False, default="not_indicated")
    controlled_substance_test_time = db.Column(db.DateTime, nullable=True)
    controlled_substance_delay_reason = db.Column(db.Text, nullable=True)
    testing_reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    testing_reviewed_at = db.Column(db.DateTime, nullable=True)

    manager_notified = db.Column(db.String(20), nullable=True)
    manager_notified_at = db.Column(db.DateTime, nullable=True)
    dispatcher_notified = db.Column(db.String(20), nullable=True)
    dispatcher_notified_at = db.Column(db.DateTime, nullable=True)
    replacement_vehicle_needed = db.Column(db.String(20), nullable=True)
    driver_relieved_from_route = db.Column(db.String(20), nullable=True)
    photos_required_complete = db.Column(db.String(20), nullable=True)
    follow_up_notes = db.Column(db.Text, nullable=True)

    manager_review_status = db.Column(db.String(40), nullable=False, default="open")
    claim_review_status = db.Column(db.String(40), nullable=False, default="not_indicated")
    close_status = db.Column(db.String(60), nullable=False, default="Needs more information")
    manager_note = db.Column(db.Text, nullable=True)
    driver_signature = db.Column(db.Text, nullable=True)
    manager_signature = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=True)
    driver_can_edit = db.Column(db.Boolean, nullable=False, default=True)
    route_finalized = db.Column(db.Boolean, nullable=False, default=False)
    locked_at = db.Column(db.DateTime, nullable=True)

    damage_report = db.relationship("DamageReport", backref="accident_incident_reports")
    driver_log = db.relationship("DriverLog", foreign_keys=[driver_log_id], backref="accident_incident_reports")
    stop = db.relationship("DriverLog", foreign_keys=[stop_id])
    driver = db.relationship("User", foreign_keys=[driver_id], backref="accident_incident_reports")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    locked_by = db.relationship("User", foreign_keys=[locked_by_id])
    testing_reviewed_by = db.relationship("User", foreign_keys=[testing_reviewed_by_id])


class AccidentWitness(db.Model):
    __tablename__ = "accident_witness"

    id = db.Column(db.Integer, primary_key=True)
    accident_id = db.Column(db.Integer, db.ForeignKey("accident_incident_report.id"), nullable=False, index=True)
    witness_name = db.Column(db.String(120), nullable=True)
    witness_phone = db.Column(db.String(80), nullable=True)
    witness_statement_summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    accident = db.relationship(
        "AccidentIncidentReport",
        backref=db.backref("witnesses", cascade="all, delete-orphan", order_by="AccidentWitness.id.asc()"),
    )


class ProofMediaFile(db.Model):
    __tablename__ = "proof_media_file"

    id = db.Column(db.Integer, primary_key=True)
    packet_type = db.Column(db.String(40), nullable=False, index=True)
    owner_type = db.Column(db.String(40), nullable=False, index=True)
    owner_id = db.Column(db.Integer, nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    sha256_hash = db.Column(db.String(64), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    related_truck = db.Column(db.String(50), nullable=True)
    related_trailer = db.Column(db.String(50), nullable=True)
    related_route_id = db.Column(db.String(80), nullable=True)
    related_stop_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=True)
    manager_note = db.Column(db.Text, nullable=True)
    media_not_required_reason = db.Column(db.Text, nullable=True)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])
    related_stop = db.relationship("DriverLog", foreign_keys=[related_stop_id])


class IftaWorksheet(db.Model):
    __tablename__ = "ifta_worksheet"

    id = db.Column(db.Integer, primary_key=True)
    reporting_period_quarter = db.Column(db.String(10), nullable=True)
    reporting_year = db.Column(db.Integer, nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    truck = db.Column(db.String(50), nullable=True)
    trailer = db.Column(db.String(50), nullable=True)
    vin_or_vehicle_unit_number = db.Column(db.String(120), nullable=True)
    fleet_number = db.Column(db.String(80), nullable=True)
    base_jurisdiction = db.Column(db.String(80), nullable=True)
    carrier_name = db.Column(db.String(160), nullable=True)
    ifta_license_number = db.Column(db.String(120), nullable=True)
    review_status = db.Column(db.String(40), nullable=False, default="Draft")
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    locked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    manager_note = db.Column(db.Text, nullable=True)
    manager_signature = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)

    driver = db.relationship("User", foreign_keys=[driver_id], backref="ifta_worksheets")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    locked_by = db.relationship("User", foreign_keys=[locked_by_id])


class IftaTripDistanceRow(db.Model):
    __tablename__ = "ifta_trip_distance_row"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("ifta_worksheet.id"), nullable=False, index=True)
    trip_start_date = db.Column(db.Date, nullable=True)
    trip_end_date = db.Column(db.Date, nullable=True)
    origin_city = db.Column(db.String(120), nullable=True)
    origin_state = db.Column(db.String(40), nullable=True)
    destination_city = db.Column(db.String(120), nullable=True)
    destination_state = db.Column(db.String(40), nullable=True)
    route_traveled = db.Column(db.String(255), nullable=True)
    beginning_odometer = db.Column(db.Float, nullable=True)
    ending_odometer = db.Column(db.Float, nullable=True)
    total_trip_distance = db.Column(db.Float, nullable=True)
    jurisdiction = db.Column(db.String(80), nullable=True)
    jurisdiction_distance = db.Column(db.Float, nullable=True)
    taxable_distance = db.Column(db.Float, nullable=True)
    nontaxable_distance = db.Column(db.Float, nullable=True)
    toll_distance = db.Column(db.Float, nullable=True)
    loaded_empty_deadhead = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    worksheet = db.relationship(
        "IftaWorksheet",
        backref=db.backref("trip_rows", cascade="all, delete-orphan", order_by="IftaTripDistanceRow.id.asc()"),
    )


class IftaFuelRecord(db.Model):
    __tablename__ = "ifta_fuel_record"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("ifta_worksheet.id"), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=True)
    seller_name = db.Column(db.String(160), nullable=True)
    seller_address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state_or_province = db.Column(db.String(40), nullable=True)
    gallons_or_liters = db.Column(db.Float, nullable=True)
    fuel_type = db.Column(db.String(60), nullable=True)
    price_per_gallon_or_liter = db.Column(db.Float, nullable=True)
    total_sale_amount = db.Column(db.Float, nullable=True)
    vehicle_unit_number = db.Column(db.String(120), nullable=True)
    purchaser_name = db.Column(db.String(160), nullable=True)
    receipt_photo = db.Column(db.String(255), nullable=True)
    receipt_hash = db.Column(db.String(64), nullable=True)
    tax_paid = db.Column(db.String(20), nullable=True)
    bulk_fuel = db.Column(db.Boolean, nullable=False, default=False)

    worksheet = db.relationship(
        "IftaWorksheet",
        backref=db.backref("fuel_records", cascade="all, delete-orphan", order_by="IftaFuelRecord.id.asc()"),
    )


class IftaBulkFuelWithdrawal(db.Model):
    __tablename__ = "ifta_bulk_fuel_withdrawal"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("ifta_worksheet.id"), nullable=False, index=True)
    withdrawal_date = db.Column(db.Date, nullable=True)
    gallons_or_liters = db.Column(db.Float, nullable=True)
    fuel_type = db.Column(db.String(60), nullable=True)
    unit_number = db.Column(db.String(120), nullable=True)
    bulk_storage_location = db.Column(db.String(160), nullable=True)
    inventory_record_reference = db.Column(db.String(160), nullable=True)
    purchase_record_reference = db.Column(db.String(160), nullable=True)

    worksheet = db.relationship(
        "IftaWorksheet",
        backref=db.backref("bulk_withdrawals", cascade="all, delete-orphan", order_by="IftaBulkFuelWithdrawal.id.asc()"),
    )


class PacketManagerReview(db.Model):
    __tablename__ = "packet_manager_review"

    id = db.Column(db.Integer, primary_key=True)
    packet_type = db.Column(db.String(40), nullable=False, index=True)
    owner_type = db.Column(db.String(40), nullable=False, index=True)
    owner_id = db.Column(db.Integer, nullable=False, index=True)
    close_status = db.Column(db.String(60), nullable=False)
    manager_note = db.Column(db.Text, nullable=True)
    manager_signature = db.Column(db.Text, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
