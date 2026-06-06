from flask_wtf import FlaskForm
from wtforms import FileField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.services.plant_addresses import PLANT_ADDRESSES


def _plant_choices():
    return [(name, name) for name in PLANT_ADDRESSES.keys()]


class DamageReportForm(FlaskForm):
    truck_number = StringField("Truck", validators=[Optional()])
    trailer_number = StringField("Trailer", validators=[Optional()])
    plant_name = SelectField("Facility", choices=_plant_choices(), validators=[DataRequired()], validate_choice=False)
    stage = SelectField("Photo Stage", choices=[("before", "Before"), ("after", "After")])
    move_reference = StringField("Move Reference", validators=[Optional()])
    description = TextAreaField("Physical Damage Details", validators=[DataRequired()])
    photo = FileField("Physical Damage Photo")
    submit = SubmitField("Save Physical Damage")
