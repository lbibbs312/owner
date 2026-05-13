from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import Optional

from app.services.plant_addresses import PLANT_ADDRESSES


def _plant_choices():
    return [("", "Select Plant...")] + [(name, name) for name in PLANT_ADDRESSES.keys()]


class TaskForm(FlaskForm):
    route_from = SelectField("From Plant", choices=_plant_choices, validators=[Optional()])
    route_to = SelectField("To Plant", choices=_plant_choices, validators=[Optional()])
    title = StringField("Move Summary (Optional)", validators=[Optional()])
    part_number = StringField("Part Number")
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as Hot")
    shift = SelectField(
        "Shift", choices=[("1st", "1st"), ("2nd", "2nd"), ("3rd", "3rd")]
    )
    assigned_to = SelectField("Assign To (Driver)", coerce=int, default=None)
    submit = SubmitField("Create Task")
