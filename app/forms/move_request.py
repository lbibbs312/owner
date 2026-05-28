from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import (
    DateTimeLocalField,
    FloatField,
    HiddenField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Optional


SOURCE_CHOICES = [
    ("text", "Text"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("radio", "Radio"),
    ("plant_screen", "Plant Screen"),
    ("manual", "Manual"),
]

REQUEST_TYPE_CHOICES = [
    ("move", "Move"),
    ("blocker", "Blocker"),
    ("equipment_issue", "Equipment Issue"),
    ("hold", "Hold"),
    ("status_update", "Status Update"),
    ("note", "Note"),
]

PRIORITY_CHOICES = [
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
    ("hot", "Hot"),
    ("safety", "Safety"),
]

STATUS_CHOICES = [
    ("open", "Open"),
    ("assigned", "Assigned"),
    ("in_progress", "In Progress"),
    ("blocked", "Blocked"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]


class MoveRequestForm(FlaskForm):
    raw_text = TextAreaField("Original Request / Message", validators=[DataRequired()])
    source = SelectField("Source", choices=SOURCE_CHOICES, default="manual")
    requested_by = StringField("Requested By", validators=[Optional()])
    requested_at = DateTimeLocalField(
        "Requested At",
        format="%Y-%m-%dT%H:%M",
        default=datetime.utcnow,
        validators=[DataRequired()],
    )
    request_type = SelectField("Request Type", choices=REQUEST_TYPE_CHOICES, default="move")
    priority = SelectField("Priority", choices=PRIORITY_CHOICES, default="normal")
    origin_location_text = StringField("Origin", validators=[Optional()])
    destination_location_text = StringField("Destination", validators=[Optional()])
    cargo_text = StringField("Cargo / Description", validators=[Optional()])
    part_number = StringField("Part Number", validators=[Optional()])
    quantity_value = FloatField("Quantity Value", validators=[Optional()])
    quantity_unit = StringField("Quantity Unit", validators=[Optional()])
    quantity_text = StringField("Quantity Text", validators=[Optional()])
    due_at = DateTimeLocalField("Due At", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    due_time_text = StringField("Due Time Text", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    status = SelectField("Status", choices=STATUS_CHOICES, default="open")
    blocked_reason = TextAreaField("Blocked Reason", validators=[Optional()])
    closed_reason = TextAreaField("Closed / Cancel Reason", validators=[Optional()])
    assigned_driver_id = SelectField("Assigned Driver", coerce=int, validators=[Optional()])
    assigned_driver_text = StringField("Assigned Driver Text", validators=[Optional()])
    equipment_id = StringField("Equipment ID", validators=[Optional()])
    equipment_text = StringField("Equipment Text", validators=[Optional()])
    linked_driver_log_id = SelectField("Linked Driver Log", coerce=int, validators=[Optional()])
    linked_route_id = StringField("Linked Route ID", validators=[Optional()])
    linked_plant_transfer_id = SelectField("Linked Plant Transfer", coerce=int, validators=[Optional()])
    linked_document_id = IntegerField("Linked Document ID", validators=[Optional()])
    parsed_confidence = HiddenField("Parsed Confidence", validators=[Optional()])
    parse_warnings = HiddenField("Parse Warnings", validators=[Optional()])
    parse_submit = SubmitField("Suggest Fields")
    submit = SubmitField("Save Request")
