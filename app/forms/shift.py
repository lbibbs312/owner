from flask_wtf import FlaskForm
from wtforms import HiddenField


class EndOfDayForm(FlaskForm):
    """Empty form used only to provide a CSRF token on the EOD summary POST."""

    hidden_example = HiddenField()
