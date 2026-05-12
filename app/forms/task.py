from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired


class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as Hot")
    shift = SelectField(
        "Shift", choices=[("1st", "1st"), ("2nd", "2nd"), ("3rd", "3rd")]
    )
    assigned_to = SelectField("Assign To (Driver)", coerce=int, default=None)
    submit = SubmitField("Create Task")
