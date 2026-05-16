"""Driver-log entry form.

The plant_name choices are currently hardcoded here AND in
lacksdrivers.py's PLANT_ADDRESSES dict. In a later PR (multi-tenant), the
Facility table replaces both and the choices come from
Facility.query.filter_by(tenant_id=...).
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.services.plant_addresses import PLANT_LABELS

PLANT_CHOICES = [("", "Select Plant...")] + [(code, label) for code, label in PLANT_LABELS.items()]

LOAD_SIZE_CHOICES = [
    ("", "Select Load..."),
    ("Empty", "Empty"),
    ("Quarter", "Quarter"),
    ("Half", "Half"),
    ("Partial", "Partial"),
    ("Full", "Full"),
    ("Hazmat", "Hazmat"),
]

YES_NO_CHOICES = [("", "Select..."), ("yes", "Yes"), ("no", "No")]

TRUCK_ISSUE_CHOICES = [
    ("", "No truck issue"),
    ("cel", "CEL light"),
    ("leak", "Leak"),
    ("overheat", "Overheat"),
    ("flat", "Flat tire"),
    ("tow", "Need tow"),
    ("regen", "Truck regen"),
]

TRUCK_ISSUE_LABELS = dict(TRUCK_ISSUE_CHOICES)


class DriverLogForm(FlaskForm):
    maintenance = BooleanField("Truck Issue / Maintenance")
    fuel = BooleanField("Fuel")
    meeting = BooleanField("Meeting")
    plant_name = SelectField(
        "Plant Name",
        choices=PLANT_CHOICES,
        validators=[DataRequired()],
    )
    load_size = SelectField(
        "Arrived With",
        choices=LOAD_SIZE_CHOICES,
        validators=[Optional()],
        validate_choice=False,
    )
    secondary_departure_dest = SelectField(
        "Also loaded for (second stop)",
        choices=[("", "None / not applicable")] + [(code, label) for code, label in PLANT_LABELS.items()],
        validators=[Optional()],
    )
    unloaded_on_arrival = SelectField(
        "Did you unload?",
        choices=YES_NO_CHOICES,
        validators=[Optional()],
    )
    unload_reason = TextAreaField("Why?", validators=[Optional()])
    secondary_dropped_on_arrival = SelectField(
        "Did you drop off the hot part?",
        choices=YES_NO_CHOICES,
        validators=[Optional()],
    )
    secondary_unload_reason = TextAreaField("Why?", validators=[Optional()])
    secondary_load = StringField("Secondary / Hot Part Load", validators=[Optional()])
    fuel_mileage = IntegerField("Mileage at Fuel Stop", validators=[Optional()])
    hot_parts = BooleanField("Hot Parts")
    part_number = StringField("Part Number / Hot Part Number")
    arrive_time = StringField(
        "Arrival Time",
        description="Enter Detroit local time like '545pm', '5:45pm', or '1:05pm'",
    )
    depart_time = StringField(
        "Depart Time (optional)",
        description="Enter Detroit local time like '545pm', '5:45pm', or '1:05pm'",
    )
    dock_wait_minutes = IntegerField("Dock Wait Minutes", validators=[Optional()])
    truck_issue = SelectField(
        "What's wrong with the truck?",
        choices=TRUCK_ISSUE_CHOICES,
        validators=[Optional()],
    )
    truck_issue_notes = TextAreaField("Truck issue notes", validators=[Optional()])
    edit_reason = TextAreaField("Edit Reason", validators=[Optional()])
    submit = SubmitField("Submit Log Entry")


class DepartForm(FlaskForm):
    """Close a stop by recording whether a destination load was picked up."""
    got_loaded = SelectField(
        "Did you get loaded?",
        choices=YES_NO_CHOICES,
        validators=[DataRequired()],
    )
    destination = SelectField(
        "Primary destination",
        choices=PLANT_CHOICES,
        validators=[Optional()],
    )
    secondary_destination = SelectField(
        "Optional hot part destination",
        choices=PLANT_CHOICES,
        validators=[Optional()],
    )
    depart_load_size = SelectField(
        "Departure Load",
        choices=LOAD_SIZE_CHOICES,
        validators=[Optional()],
    )
    submit = SubmitField("Record Departure")
