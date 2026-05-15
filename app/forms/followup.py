from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.services.plant_addresses import PLANT_ADDRESSES


def _plant_choices():
    return [(name, name) for name in PLANT_ADDRESSES.keys()]


class OperationalFollowUpForm(FlaskForm):
    kind = SelectField(
        "Follow-up Type",
        choices=[
            ("wrong_location", "Wrong Location"),
            ("unclear_dispatch", "Unclear Dispatch"),
            ("gage_tracking", "Gage Tracking"),
            ("delay", "Delay"),
            ("paperwork", "Paperwork"),
        ],
        validators=[DataRequired()],
    )
    plant_name = SelectField("Facility", choices=_plant_choices(), validators=[Optional()], validate_choice=False)
    details = TextAreaField("Details", validators=[DataRequired()])
    submit = SubmitField("Add Follow-up")
