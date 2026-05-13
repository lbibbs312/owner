from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.services.plant_addresses import PLANT_ADDRESSES


def _plant_choices():
    return [("", "Select Plant...")] + [(name, name) for name in PLANT_ADDRESSES.keys()]


class PlantTransferForm(FlaskForm):
    transfer_number = StringField("Transfer No.", validators=[Optional()])
    transfer_date = DateField(
        "Date", format="%Y-%m-%d", default=date.today, validators=[DataRequired()]
    )
    ship_to = SelectField("Ship To", choices=_plant_choices, validators=[DataRequired()])
    ship_from = SelectField("Ship From", choices=_plant_choices, validators=[DataRequired()])
    trailer_number = StringField("Trailer No.", validators=[Optional()])
    driver_name = StringField("Driver", validators=[Optional()])
    transfer_time = StringField("Time", validators=[Optional()])
    loaded_by = StringField("Loaded By", validators=[Optional()])
    submit = SubmitField("Save Plant Transfer")
