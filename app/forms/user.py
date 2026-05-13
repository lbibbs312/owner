from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo


class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    first_name = StringField("First Name")
    last_name = StringField("Last Name")
    employee_id = StringField("ID Number")
    department = StringField("Department")
    email = StringField("Email", validators=[DataRequired(), Email()])
    new_password = PasswordField("New Password")
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Update Profile")
