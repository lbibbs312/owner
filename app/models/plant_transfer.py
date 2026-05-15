from datetime import date, datetime

from app.extensions import db


class PlantTransfer(db.Model):
    __tablename__ = "plant_transfer"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    transfer_number = db.Column(db.String(30), nullable=True)
    transfer_date = db.Column(db.Date, default=date.today, nullable=False)
    ship_to = db.Column(db.String(50), nullable=False)
    ship_from = db.Column(db.String(50), nullable=False)
    trailer_number = db.Column(db.String(50), nullable=True)
    driver_name = db.Column(db.String(100), nullable=True)
    driver_initials = db.Column(db.String(12), nullable=True)
    transfer_time = db.Column(db.String(20), nullable=True)
    loaded_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    driver = db.relationship("User", backref="plant_transfers", foreign_keys=[user_id])
    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id])
    lines = db.relationship(
        "PlantTransferLine",
        backref="plant_transfer",
        cascade="all, delete-orphan",
        order_by="PlantTransferLine.line_number",
    )


class PlantTransferLine(db.Model):
    __tablename__ = "plant_transfer_line"

    id = db.Column(db.Integer, primary_key=True)
    plant_transfer_id = db.Column(
        db.Integer, db.ForeignKey("plant_transfer.id"), nullable=False
    )
    line_number = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(5), nullable=False, default="left")
    part_number = db.Column(db.String(80), nullable=True)
    quantity = db.Column(db.String(30), nullable=True)
    skids = db.Column(db.String(30), nullable=True)
    remarks = db.Column(db.String(200), nullable=True)
