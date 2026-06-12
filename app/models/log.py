from datetime import datetime
import os

from flask import current_app

from app.extensions import db


class DriverLog(db.Model):
    __tablename__ = "driver_log"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    arrive_time = db.Column(db.String(20))
    depart_time = db.Column(db.String(20))
    downtime_reason = db.Column(db.String(200), nullable=True)
    dock_wait_minutes = db.Column(db.Integer, nullable=True)
    part_number = db.Column(db.String(80), nullable=True)
    hot_parts = db.Column(db.Boolean, default=False)
    no_pickup = db.Column(db.Boolean, default=False)
    load_size = db.Column(db.String(80), nullable=False)
    depart_load_size = db.Column(db.String(80), nullable=True)
    secondary_load = db.Column(db.String(80), nullable=True)
    # Day-driver freight detail: what is being hauled and how heavy. Additive to the
    # plant/load_size routing model the Lacks flow uses; populated in day-driver mode
    # and carried forward to the next open stop like load_size/secondary_load.
    commodity = db.Column(db.String(120), nullable=True)
    weight = db.Column(db.String(40), nullable=True)
    # Freight (day-driver) departure: free-text "where to next" — a customer,
    # city, or dock rather than a plant code. Fleet flow leaves this null.
    destination = db.Column(db.String(120), nullable=True)
    destination_address = db.Column(db.String(255), nullable=True)
    # GPS/reverse-geocode capture for day-driver stops. ``plant_name`` remains
    # the corrected customer/place label; this stores the physical address.
    location_address = db.Column(db.String(255), nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    gps_accuracy_m = db.Column(db.Float, nullable=True)
    plant_name = db.Column(db.String(120), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    fuel_mileage = db.Column(db.Integer, nullable=True)
    meeting = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id])

    @property
    def action_label(self):
        return "Depart" if not self.depart_time else "Edit"

class DriverLogPhoto(db.Model):
    __tablename__ = "driver_log_photo"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(80), nullable=False, default="lacksdrivers")
    driver_log_id = db.Column(db.Integer, db.ForeignKey("driver_log.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    sha256_hash = db.Column(db.String(64), nullable=True)
    source = db.Column(db.String(40), nullable=False, default="gallery")
    document_type = db.Column(db.String(40), nullable=True)
    owner_type = db.Column(db.String(30), nullable=True)
    owner_id = db.Column(db.String(40), nullable=True)
    review_status = db.Column(db.String(20), nullable=False, default="review_optional")
    note = db.Column(db.Text, nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    log = db.relationship(
        "DriverLog",
        backref=db.backref(
            "photos",
            cascade="all, delete-orphan",
            order_by="DriverLogPhoto.uploaded_at.asc()",
        ),
    )
    uploaded_by = db.relationship("User", backref="driver_log_photos")

    DOCUMENT_TYPE_LABELS = {
        "bol_manifest": "BOL",
        "transfer_sheet": "Transfer Sheet",
        "route_sheet": "Route Sheet",
        "proof_photo": "Proof Photo",
        "damage_photo": "Damage Photo",
        "driver_credential": "Driver Credential",
        "truck_document": "Truck Document",
        "other_document": "Document",
    }

    @property
    def file_available(self):
        try:
            upload_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
            upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, self.filename))
        except RuntimeError:
            return False
        return os.path.isfile(upload_path)

    @property
    def resolved_document_type(self):
        """Document type code, falling back to the legacy source-encoded value."""
        if self.document_type:
            return self.document_type
        source = (self.source or "").strip()
        for code in self.DOCUMENT_TYPE_LABELS:
            if source == code or source.startswith(code + "_"):
                return code
        return None

    @property
    def document_type_label(self):
        code = self.resolved_document_type
        if code:
            return self.DOCUMENT_TYPE_LABELS.get(code, code.replace("_", " ").title())
        return (self.source or "Document").replace("_", " ").title()
