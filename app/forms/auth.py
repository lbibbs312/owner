from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    first_name = StringField("First Name")
    last_name = StringField("Last Name")
    employee_id = StringField("ID Number")
    department = StringField("Department")
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password")]
    )
    role = SelectField(
        "Role",
        choices=[("driver", "Driver"), ("management", "Management")],
        default="driver",
    )
    manager_pin = PasswordField("Manager PIN (if Management)")
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    login_name = StringField("Username or Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")
