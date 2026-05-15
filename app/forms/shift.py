from flask_wtf import FlaskForm
from wtforms import HiddenField


class EndOfDayForm(FlaskForm):
    """Provides CSRF token and captures the driver's e-signature on EOD submit."""

    hidden_example = HiddenField()
    driver_signature = HiddenField()
