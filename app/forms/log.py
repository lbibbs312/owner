"""Driver-log entry form.

The plant_name choices are currently hardcoded here AND in
lacksdrivers.py's PLANT_ADDRESSES dict. In a later PR (multi-tenant), the
Facility table replaces both and the choices come from
Facility.query.filter_by(tenant_id=...).
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired


class DriverLogForm(FlaskForm):
    maintenance = BooleanField("Maintenance")
    fuel = BooleanField("Fuel")
    meeting = BooleanField("Meeting")
    plant_name = SelectField(
        "Plant Name",
        choices=[
            ("", "Select Plant..."),
            ("RE", "RE"),
            ("RW", "RW"),
            ("PC", "PC"),
            ("PE", "PE"),
            ("PW", "PW"),
            ("KP", "KP"),
            ("PPL", "PPL"),
            ("DC", "DC"),
            ("Helios", "Helios"),
            ("BP", "BP"),
            ("52L", "52L"),
            ("Trim DC", "Trim DC"),
            ("52DC", "52DC"),
            ("ALN", "ALN"),
            ("AWE", "AWE"),
            ("CORP", "CORP"),
            ("R&D", "R&D"),
            ("GLA", "GLA"),
            ("KM", "KM"),
            ("KS", "KS"),
            ("MONROE", "MONROE"),
            ("Other", "Other"),
            ("Lab", "Lab"),
        ],
        validators=[DataRequired()],
    )
    load_size = SelectField(
        "Load Size",
        choices=[
            ("", "Select Load Size..."),
            ("Empty", "Empty"),
            ("Quarter", "Quarter"),
            ("Half", "Half"),
            ("Partial", "Partial"),
            ("Full", "Full"),
            ("Hazmat", "Hazmat"),
        ],
        validators=[DataRequired()],
    )
    downtime_reason = StringField("Downtime Reason (optional)")
    depart_time = StringField(
        "Depart Time (optional)",
        description="Enter time like '545' => 05:45 or '13:05' => 13:05",
    )
    submit = SubmitField("Submit Log Entry")
