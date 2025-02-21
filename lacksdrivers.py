import os
import pytz
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import (
    Flask, request, redirect, url_for, flash,
    render_template, session, jsonify, send_file, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_required, login_user, logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, SelectField, IntegerField, DateField, HiddenField
)
from wtforms.validators import DataRequired, Email, EqualTo, Length
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_migrate import Migrate
from sqlalchemy import Enum

# Import the manager blueprint (if you have one)
from manager_routes import manager_bp

############################################################################
# Initialize app & config
############################################################################
app = Flask(__name__)
app.config["SECRET_KEY"] = "admin123"
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "SQLALCHEMY_DATABASE_URI",
    "sqlite:///lacksdrivers.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Register the manager blueprint so /manager/* routes become active
app.register_blueprint(manager_bp)

############################################################################
# Utility Function (for time parsing)
############################################################################
def parse_time_no_colon(input_str):
    """
    Allows times with or without a colon. Examples:
    '545' => '05:45'
    '8' => '08:00'
    '0830' => '08:30'
    '930' => '09:30'
    '13:05' => '13:05' (already has colon)
    """
    raw = input_str.strip()
    if ":" in raw:
        dt_obj = datetime.strptime(raw, "%H:%M")
        return dt_obj.strftime("%H:%M")
    else:
        if not raw.isdigit():
            raise ValueError("Not numeric.")
        digits = len(raw)
        if digits == 1:
            hour = int(raw)
            minute = 0
        elif digits == 2:
            hour = int(raw)
            minute = 0
        elif digits == 3:
            hour = int(raw[0])
            minute = int(raw[1:])
        elif digits == 4:
            hour = int(raw[:2])
            minute = int(raw[2:])
        else:
            raise ValueError("Invalid length.")
        if hour > 23 or minute > 59:
            raise ValueError("Hour or minute out of range.")
        return f"{hour:02d}:{minute:02d}"

############################################################################
# PLANT ADDRESSES + Context Processor
############################################################################
PLANT_ADDRESSES = {
    "RE": "3505 Kraft Ave SE",
    "RW": "3500 Raleigh Dr SE",
    "PC": "4315 52nd st se",
    "PE": "4245 52nd St SE",
    "PW": "4245 52nd st",
    "KP": "5711 North Kraft SE",
    "PPL": "5357 52nd St SE",
    "DC": "5357 52nd st se",
    "Helios": "5333 33rd st se",
    "BP": "4080 Barden Dr SE",
    "52L": "4365 52nd St SE",
    "Trim DC": "5357 52nd St SE",
    "52DC": "4365 52nd St SE",
    "ALN": "4260 Airlane Dr SE",
    "AWE": "4261 Airlane Dr SE",
    "CORP": "5460 Cascade Rd SE",
    "R&D": "4975 Broadmoor Ave SE",
    "GLA": "17113 Applewhite Road",
    "KM": "5801 Kraft Ave SE",
    "KS": "5675 Kraft Ave SE",
    "MONROE": "1648 Monroe Ave NW",
    "Other": "Unspecified location",
    "Lab": "Corporate Lab (placeholder)",
    "PPM": "PPM MONROE(1648 monroe ave)"
}

@app.context_processor
def inject_plant_addresses():
    return dict(PLANT_ADDRESSES=PLANT_ADDRESSES)

############################################################################
# Enums & Models
############################################################################

ITEM_STATUSES = ("operational", "damaged", "missing", "leaking")

#
# 1) USER MODEL
#
class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default="driver")  # "driver" or "management"

    tasks = db.relationship("Task", backref="assigned_user", lazy="dynamic")
    driver_logs = db.relationship("DriverLog", backref="driver", lazy="dynamic")
    pretrips = db.relationship("PreTrip", backref="driver", lazy="dynamic")
    chat_messages = db.relationship("ChatMessage", backref="user", lazy="dynamic")

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)


#
# 2) TASK
#
class Task(db.Model):
    __tablename__ = "task"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text)
    is_hot = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="pending")
    shift = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

#
# 3) PRETRIP & POSTTRIP
#
class PreTrip(db.Model):
    __tablename__ = "pretrip"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    truck_number = db.Column(db.String(50))
    trailer_number = db.Column(db.String(50))
    pretrip_date = db.Column(db.Date, default=date.today)
    shift = db.Column(db.String(10))
    start_mileage = db.Column(db.Integer)
    # Additional fields for the PreTrip inspection
    truck_type = db.Column(db.String(20))
    oil_system_status = db.Column(db.String(20))
    tires_ok = db.Column(db.Boolean, default=False)
    tires_status = db.Column(db.String(50))
    # GENERAL CONDITION
    cab_doors_windows = db.Column(db.Boolean, default=False)
    body_doors = db.Column(db.Boolean, default=False)
    oil_leak = db.Column(db.Boolean, default=False)
    grease_leak = db.Column(db.Boolean, default=False)
    coolant_leak = db.Column(db.Boolean, default=False)
    fuel_leak = db.Column(db.Boolean, default=False)
    gc_no_defects = db.Column(db.Boolean, default=False)
    # IN-CAB
    gauges_warning = db.Column(db.Boolean, default=False)
    wipers = db.Column(db.Boolean, default=False)
    horn = db.Column(db.Boolean, default=False)
    heater_defroster = db.Column(db.Boolean, default=False)
    mirrors = db.Column(db.Boolean, default=False)
    seat_belts_steering = db.Column(db.Boolean, default=False)
    clutch = db.Column(db.Boolean, default=False)
    service_brakes = db.Column(db.Boolean, default=False)
    parking_brake = db.Column(db.Boolean, default=False)
    emergency_brakes = db.Column(db.Boolean, default=False)
    triangles = db.Column(db.Boolean, default=False)
    fire_extinguisher = db.Column(db.Boolean, default=False)
    safety_equipment = db.Column(db.Boolean, default=False)
    incab_no_defects = db.Column(db.Boolean, default=False)
    # ENGINE COMPARTMENT
    oil_level = db.Column(db.Boolean, default=False)
    coolant_level = db.Column(db.Boolean, default=False)
    belts = db.Column(db.Boolean, default=False)
    hoses = db.Column(db.Boolean, default=False)
    ec_no_defects = db.Column(db.Boolean, default=False)
    # EXTERIOR
    lights_working = db.Column(db.Boolean, default=False)
    reflectors = db.Column(db.Boolean, default=False)
    suspension = db.Column(db.Boolean, default=False)
    tires = db.Column(db.Boolean, default=False)
    wheels_rims = db.Column(db.Boolean, default=False)
    battery = db.Column(db.Boolean, default=False)
    exhaust = db.Column(db.Boolean, default=False)
    brakes = db.Column(db.Boolean, default=False)
    air_lines = db.Column(db.Boolean, default=False)
    light_line = db.Column(db.Boolean, default=False)
    fifth_wheel = db.Column(db.Boolean, default=False)
    coupling = db.Column(db.Boolean, default=False)
    tie_downs = db.Column(db.Boolean, default=False)
    rear_end_protection = db.Column(db.Boolean, default=False)
    exterior_no_defects = db.Column(db.Boolean, default=False)
    # TOWED UNIT
    towed_bodydoors = db.Column(db.Boolean, default=False)
    towed_tiedowns = db.Column(db.Boolean, default=False)
    towed_lights = db.Column(db.Boolean, default=False)
    towed_reflectors = db.Column(db.Boolean, default=False)
    towed_suspension = db.Column(db.Boolean, default=False)
    towed_tires = db.Column(db.Boolean, default=False)
    towed_wheels = db.Column(db.Boolean, default=False)
    towed_brakes = db.Column(db.Boolean, default=False)
    towed_landing_gear = db.Column(db.Boolean, default=False)
    towed_kingpin = db.Column(db.Boolean, default=False)
    towed_fifthwheel = db.Column(db.Boolean, default=False)
    towed_othercoupling = db.Column(db.Boolean, default=False)
    towed_rearend = db.Column(db.Boolean, default=False)
    towed_no_defects = db.Column(db.Boolean, default=False)
    # REMARKS / DAMAGE
    damage_report = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    posttrip = db.relationship("PostTrip", uselist=False, backref="pretrip")


class PostTrip(db.Model):
    __tablename__ = "posttrip"
    id = db.Column(db.Integer, primary_key=True)
    pretrip_id = db.Column(db.Integer, db.ForeignKey("pretrip.id"), nullable=False)
    end_mileage = db.Column(db.Integer, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    miles_driven = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

#
# 4) DRIVER LOG
#
class DriverLog(db.Model):
    __tablename__ = "driver_log"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    arrive_time = db.Column(db.String(20))
    depart_time = db.Column(db.String(20))
    downtime_reason = db.Column(db.String(200), nullable=True)
    load_size = db.Column(db.String(10), nullable=False)
    plant_name = db.Column(db.String(20), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    meeting = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    @property
    def action_label(self):
        return "Depart" if not self.depart_time else "Edit"

#
# 5) CHAT MESSAGE
#
class ChatMessage(db.Model):
    __tablename__ = "chat_message"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    room = db.Column(db.String(100), default="global")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

#
# 6) ANNOUNCEMENT
#
class Announcement(db.Model):
    __tablename__ = "announcement"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

#
# 7) DIRECT MESSAGE
#
class DirectMessage(db.Model):
    __tablename__ = "direct_message"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="received_messages")

#
# 8) SHIFT RECORD
#
class ShiftRecord(db.Model):
    __tablename__ = "shift_record"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pretrip_id = db.Column(db.Integer, db.ForeignKey("pretrip.id"), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Float, nullable=True)
    week_ending = db.Column(db.Date, nullable=True)

    user = db.relationship("User", backref="shift_records")
    pretrip = db.relationship("PreTrip", backref="shift_record")

#
# 9) KNOWLEDGE BASE ENTRY
#
class KnowledgeBaseEntry(db.Model):
    __tablename__ = "knowledge_base"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    title = db.Column(db.String(100))
    body = db.Column(db.Text)

############################################################################
# Forms
############################################################################

class EndOfDayForm(FlaskForm):
    hidden_example = HiddenField()

class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    role = SelectField("Role", choices=[("driver", "Driver"), ("management", "Management")], default="driver")
    manager_pin = PasswordField("Manager PIN (if Management)")
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    login_name = StringField("Username or Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")

class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as Hot")
    shift = SelectField("Shift", choices=[("1st", "1st"), ("2nd", "2nd"), ("3rd", "3rd")])
    assigned_to = SelectField("Assign To (Driver)", coerce=int, default=None)
    submit = SubmitField("Create Task")

class UpdateTaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as Hot")
    shift = SelectField("Shift", choices=[("1st", "1st"), ("2nd", "2nd"), ("3rd", "3rd")])
    status = SelectField(
        "Status",
        choices=[
            ("pending", "Pending"),
            ("in-progress", "In Progress"),
            ("completed", "Completed"),
            ("declined", "Declined")
        ]
    )
    assigned_to = SelectField("Assigned To (Driver)", coerce=int)
    submit = SubmitField("Update Task")

class PreTripForm(FlaskForm):
    # Basic info
    truck_number = StringField("Truck / Tractor #", validators=[DataRequired()])
    trailer_number = StringField("Trailer #")
    pretrip_date = DateField("PreTrip Date", format="%Y-%m-%d")
    shift = SelectField("Shift", choices=[("1st", "1st"), ("2nd", "2nd"), ("3rd", "3rd")])
    start_mileage = IntegerField("Start Mileage")
    # Additional info
    truck_type = SelectField("Truck Type", choices=[("Tractor", "Tractor"), ("Pickup", "Pickup"), ("Other", "Other")])
    oil_system_status = SelectField("Oil System Status", choices=[("good", "Good"), ("low", "Low"), ("leaking", "Leaking")])
    tires_ok = BooleanField("Tires OK")
    tires_status = SelectField("Tires Status", choices=[("good", "Good"), ("needs_replacement", "Needs Replacement")])
    # GENERAL CONDITION
    cab_doors_windows = BooleanField("Cab Doors/Windows")
    body_doors = BooleanField("Body Doors")
    oil_leak = BooleanField("Oil Leak")
    grease_leak = BooleanField("Grease Leak")
    coolant_leak = BooleanField("Coolant Leak")
    fuel_leak = BooleanField("Fuel Leak")
    gc_no_defects = BooleanField("No Defects (General Condition)")
    # IN-CAB
    gauges_warning = BooleanField("Gauges/Warning Indicators")
    wipers = BooleanField("Windshield Wipers/Washers")
    horn = BooleanField("Horn")
    heater_defroster = BooleanField("Heater/Defroster")
    mirrors = BooleanField("Mirrors")
    seat_belts_steering = BooleanField("Seat Belts/Steering")
    clutch = BooleanField("Clutch")
    service_brakes = BooleanField("Service Brakes")
    parking_brake = BooleanField("Parking Brake")
    emergency_brakes = BooleanField("Emergency Brakes")
    triangles = BooleanField("Triangles")
    fire_extinguisher = BooleanField("Fire Extinguisher")
    safety_equipment = BooleanField("Safety Equipment")
    incab_no_defects = BooleanField("No Defects (In-Cab)")
    # ENGINE COMPARTMENT
    oil_level = BooleanField("Oil Level")
    coolant_level = BooleanField("Coolant Level")
    belts = BooleanField("Belts")
    hoses = BooleanField("Hoses")
    ec_no_defects = BooleanField("No Defects (Engine Compartment)")
    # EXTERIOR
    lights_working = BooleanField("Lights Working")
    reflectors = BooleanField("Reflectors")
    suspension = BooleanField("Suspension")
    tires = BooleanField("Tires")
    wheels_rims = BooleanField("Wheels/Rims")
    battery = BooleanField("Battery")
    exhaust = BooleanField("Exhaust")
    brakes = BooleanField("Brakes")
    air_lines = BooleanField("Air Lines")
    light_line = BooleanField("Light Line")
    fifth_wheel = BooleanField("Fifth Wheel")
    coupling = BooleanField("Coupling")
    tie_downs = BooleanField("Tie Downs")
    rear_end_protection = BooleanField("Rear End Protection")
    exterior_no_defects = BooleanField("No Defects (Exterior)")
    # TOWED UNIT
    towed_bodydoors = BooleanField("Body/Doors")
    towed_tiedowns = BooleanField("Tie-Downs")
    towed_lights = BooleanField("Lights")
    towed_reflectors = BooleanField("Reflectors")
    towed_suspension = BooleanField("Suspension")
    towed_tires = BooleanField("Tires")
    towed_wheels = BooleanField("Wheels")
    towed_brakes = BooleanField("Brakes")
    towed_landing_gear = BooleanField("Landing Gear")
    towed_kingpin = BooleanField("Kingpin")
    towed_fifthwheel = BooleanField("Fifth Wheel")
    towed_othercoupling = BooleanField("Other Coupling")
    towed_rearend = BooleanField("Rear End")
    towed_no_defects = BooleanField("No Defects (Towed Unit)")
    # REMARKS / DAMAGE
    damage_report = TextAreaField("Damage Report")
    submit = SubmitField("Save PreTrip")

class PostTripForm(FlaskForm):
    end_mileage = IntegerField("End Mileage", validators=[DataRequired()])
    remarks = TextAreaField("PostTrip Remarks")
    submit = SubmitField("Complete PostTrip")

class DriverLogForm(FlaskForm):
    maintenance = BooleanField("Maintenance")
    fuel = BooleanField("Fuel")
    meeting = BooleanField("Meeting")
    plant_name = SelectField(
        "Plant Name",
        choices=[
            ("", "Select Plant..."),
            ("RE", "RE"),
            ("RW", "RW"),
            ("PC", "PC"),
            ("PE", "PE"),
            ("PW", "PW"),
            ("KP", "KP"),
            ("PPL", "PPL"),
            ("DC", "DC"),
            ("Helios", "Helios"),
            ("BP", "BP"),
            ("52L", "52L"),
            ("Trim DC", "Trim DC"),
            ("52DC", "52DC"),
            ("ALN", "ALN"),
            ("AWE", "AWE"),
            ("CORP", "CORP"),
            ("R&D", "R&D"),
            ("GLA", "GLA"),
            ("KM", "KM"),
            ("KS", "KS"),
            ("MONROE", "MONROE"),
            ("Other", "Other"),
            ("Lab", "Lab")
        ],
        validators=[DataRequired()]
    )
    load_size = SelectField(
        "Load Size",
        choices=[
            ("", "Select Load Size..."),
            ("Empty", "Empty"),
            ("Quarter", "Quarter"),
            ("Half", "Half"),
            ("Partial", "Partial"),
            ("Full", "Full"),
            ("Hazmat", "Hazmat")
        ],
        validators=[DataRequired()]
    )
    downtime_reason = StringField("Downtime Reason (optional)")
    depart_time = StringField(
        "Depart Time (optional)",
        description="Enter time like '545' => 05:45 or '13:05' => 13:05"
    )
    submit = SubmitField("Submit Log Entry")

class AnnouncementForm(FlaskForm):
    title = StringField("Announcement Title", validators=[DataRequired()])
    body = TextAreaField("Announcement Body", validators=[DataRequired()])
    submit = SubmitField("Post Announcement")

class DirectMessageForm(FlaskForm):
    receiver_id = SelectField("Send To", coerce=int)
    content = TextAreaField("Message", validators=[DataRequired()])
    submit = SubmitField("Send")

class KnowledgeBaseForm(FlaskForm):
    title = StringField("Tip Title", validators=[DataRequired()])
    body = TextAreaField("Tip Body", validators=[DataRequired()])
    submit = SubmitField("Add Tip")

class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    role = SelectField("Role", choices=[("driver", "Driver"), ("management", "Management")])
    new_password = PasswordField("New Password")
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Update Profile")

############################################################################
# LOGIN Manager
############################################################################
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

############################################################################
# Jinja filter for UTC -> local time
############################################################################
@app.template_filter('to_local_time')
def to_local_time(utc_str):
    if not utc_str:
        return ""
    try:
        dt_utc = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = pytz.utc.localize(dt_utc)
        local_tz = pytz.timezone("America/Detroit")
        dt_local = dt_utc.astimezone(local_tz)
        formatted = dt_local.strftime("%I:%M%p").lower()
        return formatted.lstrip('0')
    except ValueError:
        return utc_str

############################################################################
# Routes (General + Driver-Focused)
############################################################################

@app.route("/")
def welcome():
    bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    return render_template("welcome.html", bulletins=bulletins)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.role.data == "management":
            if form.manager_pin.data != "0000":
                flash("Invalid Manager PIN!", "danger")
                return redirect(url_for("register"))
        existing = User.query.filter(
            (User.email == form.email.data) | (User.username == form.username.data)
        ).first()
        if existing:
            flash("User already exists with that email or username.", "danger")
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        name_or_email = form.login_name.data
        user = User.query.filter(
            (User.username == name_or_email) | (User.email == name_or_email)
        ).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash("Logged in!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("welcome"))

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    logs = DriverLog.query.filter_by(driver_id=current_user.id)\
                          .order_by(DriverLog.created_at.desc()).limit(5).all()
    pretrips = PreTrip.query.filter_by(user_id=current_user.id)\
                            .order_by(PreTrip.created_at.desc()).limit(5).all()
    tasks = Task.query.filter_by(assigned_to=current_user.id)\
                      .order_by(Task.created_at.desc()).limit(5).all()

    dm_form = DirectMessageForm()
    all_users = User.query.filter(User.id != current_user.id).all()
    dm_form.receiver_id.choices = [(u.id, u.username) for u in all_users]

    if dm_form.validate_on_submit():
        new_dm = DirectMessage(
            sender_id=current_user.id,
            receiver_id=dm_form.receiver_id.data,
            content=dm_form.content.data
        )
        db.session.add(new_dm)
        db.session.commit()
        socketio.emit("new_direct_message", {
            "sender": current_user.username,
            "receiver_id": dm_form.receiver_id.data,
            "content": dm_form.content.data
        })
        flash("Message sent!", "success")
        return redirect(url_for("dashboard"))

    inbox = DirectMessage.query.filter_by(receiver_id=current_user.id)\
                               .order_by(DirectMessage.timestamp.desc()).all()
    outbox = DirectMessage.query.filter_by(sender_id=current_user.id)\
                                .order_by(DirectMessage.timestamp.desc()).all()

    return render_template(
        "dashboard.html",
        logs=logs,
        pretrips=pretrips,
        tasks=tasks,
        dm_form=dm_form,
        inbox=inbox,
        outbox=outbox
    )

@app.route("/list_tasks")
@login_required
def list_tasks():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
    else:
        tasks = Task.query.filter_by(assigned_to=current_user.id)\
                          .order_by(Task.created_at.desc()).all()
    return render_template("list_tasks.html", tasks=tasks)

############################################################################
# Driver Logs
############################################################################
@app.route("/driver_logs", methods=["GET"])
@login_required
def driver_logs():
    date_str = request.args.get("date")
    try:
        search_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()
    except ValueError:
        search_date = datetime.now().date()

    if current_user.role == "management":
        all_drivers = User.query.filter_by(role="driver").all()
        selected_driver_id = request.args.get("driver_id", type=int)
        query = DriverLog.query.filter(DriverLog.date == search_date).order_by(DriverLog.created_at.desc())
        if selected_driver_id:
            query = query.filter_by(driver_id=selected_driver_id)
        logs = query.all()
        return render_template(
            "driver_logs.html",
            logs=logs,
            all_drivers=all_drivers,
            selected_driver_id=selected_driver_id,
            search_date=search_date
        )
    else:
        logs = DriverLog.query.filter_by(
            driver_id=current_user.id,
            date=search_date
        ).order_by(DriverLog.created_at.desc()).all()
        return render_template("driver_logs.html", logs=logs, search_date=search_date)

@app.route("/new_driving_log", methods=["GET", "POST"])
@login_required
def new_driving_log():
    form = DriverLogForm()
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("new_driving_log"))

        local_tz = pytz.timezone("America/Detroit")
        now_local = datetime.now(local_tz)
        local_date = now_local.date()

        now_utc = datetime.utcnow()
        arrive_time_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=form.load_size.data,
            downtime_reason=form.downtime_reason.data,
            arrive_time=arrive_time_str,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            meeting=form.meeting.data,
            date=local_date
        )
        db.session.add(newlog)
        db.session.commit()
        flash("New driving log added (local date, UTC arrival time)!", "success")
        return redirect(url_for("driver_logs"))

    return render_template("new_driving_log.html", form=form)

@app.route("/edit_driver_log/<int:log_id>", methods=["GET", "POST"])
@login_required
def edit_driver_log(log_id):
    log = DriverLog.query.get_or_404(log_id)
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to edit someone else's log!", "danger")
        return redirect(url_for("driver_logs"))

    form = DriverLogForm(obj=log)
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("edit_driver_log", log_id=log.id))
        
        log.plant_name = form.plant_name.data
        log.load_size = form.load_size.data
        log.downtime_reason = form.downtime_reason.data
        log.maintenance = form.maintenance.data
        log.fuel = form.fuel.data
        log.meeting = form.meeting.data

        if form.depart_time.data.strip():
            log.depart_time = form.depart_time.data.strip()
        else:
            local_tz = pytz.timezone("America/Detroit")
            now_local = datetime.now(local_tz)
            log.depart_time = now_local.strftime("%H:%M")
        
        db.session.commit()
        flash(f"Driving log updated (ID: {log.id}).", "success")
        return redirect(url_for("driver_logs"))

    return render_template("edit_driver_log.html", form=form, log=log)

@app.template_filter('to_12h_format')
def to_12h_format(hhmm_str):
    if not hhmm_str:
        return ""
    try:
        dt = datetime.strptime(hhmm_str, "%H:%M")
        return dt.strftime("%I:%M%p").lower().lstrip('0')
    except ValueError:
        return hhmm_str

@app.route("/view_driver_log/<int:log_id>")
@login_required
def view_driver_log(log_id):
    log = DriverLog.query.get_or_404(log_id)
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to view someone else's log!", "danger")
        return redirect(url_for("driver_logs"))
    return render_template("view_driver_log.html", log=log)

############################################################################
# PreTrip/PostTrip
############################################################################
@app.route("/list_pretrips")
@login_required
def list_pretrips():
    if current_user.role == "management":
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
    else:
        pretrips = PreTrip.query.filter_by(user_id=current_user.id)\
                                .order_by(PreTrip.created_at.desc()).all()
    return render_template("list_pretrips.html", pretrips=pretrips)

@app.route("/new_pretrip", methods=["GET", "POST"])
@login_required
def new_pretrip():
    form = PreTripForm()
    if form.validate_on_submit():
        chosen_date = form.pretrip_date.data or date.today()

        new_pt = PreTrip(
            user_id=current_user.id,
            truck_number=form.truck_number.data,
            trailer_number=form.trailer_number.data,
            pretrip_date=chosen_date,
            shift=form.shift.data,
            start_mileage=form.start_mileage.data,
            truck_type=form.truck_type.data,
            oil_system_status=form.oil_system_status.data,
            tires_ok=form.tires_ok.data,
            tires_status=form.tires_status.data,
            cab_doors_windows=form.cab_doors_windows.data,
            body_doors=form.body_doors.data,
            oil_leak=form.oil_leak.data,
            grease_leak=form.grease_leak.data,
            coolant_leak=form.coolant_leak.data,
            fuel_leak=form.fuel_leak.data,
            gc_no_defects=form.gc_no_defects.data,
            gauges_warning=form.gauges_warning.data,
            wipers=form.wipers.data,
            horn=form.horn.data,
            heater_defroster=form.heater_defroster.data,
            mirrors=form.mirrors.data,
            seat_belts_steering=form.seat_belts_steering.data,
            clutch=form.clutch.data,
            service_brakes=form.service_brakes.data,
            parking_brake=form.parking_brake.data,
            emergency_brakes=form.emergency_brakes.data,
            triangles=form.triangles.data,
            fire_extinguisher=form.fire_extinguisher.data,
            safety_equipment=form.safety_equipment.data,
            incab_no_defects=form.incab_no_defects.data,
            oil_level=form.oil_level.data,
            coolant_level=form.coolant_level.data,
            belts=form.belts.data,
            hoses=form.hoses.data,
            ec_no_defects=form.ec_no_defects.data,
            lights_working=form.lights_working.data,
            reflectors=form.reflectors.data,
            suspension=form.suspension.data,
            tires=form.tires.data,
            wheels_rims=form.wheels_rims.data,
            battery=form.battery.data,
            exhaust=form.exhaust.data,
            brakes=form.brakes.data,
            air_lines=form.air_lines.data,
            light_line=form.light_line.data,
            fifth_wheel=form.fifth_wheel.data,
            coupling=form.coupling.data,
            tie_downs=form.tie_downs.data,
            rear_end_protection=form.rear_end_protection.data,
            exterior_no_defects=form.exterior_no_defects.data,
            towed_bodydoors=form.towed_bodydoors.data,
            towed_tiedowns=form.towed_tiedowns.data,
            towed_lights=form.towed_lights.data,
            towed_reflectors=form.towed_reflectors.data,
            towed_suspension=form.towed_suspension.data,
            towed_tires=form.towed_tires.data,
            towed_wheels=form.towed_wheels.data,
            towed_brakes=form.towed_brakes.data,
            towed_landing_gear=form.towed_landing_gear.data,
            towed_kingpin=form.towed_kingpin.data,
            towed_fifthwheel=form.towed_fifthwheel.data,
            towed_othercoupling=form.towed_othercoupling.data,
            towed_rearend=form.towed_rearend.data,
            towed_no_defects=form.towed_no_defects.data,
            damage_report=form.damage_report.data
        )

        db.session.add(new_pt)
        db.session.commit()

        flash("PreTrip saved successfully!", "success")
        return redirect(url_for("list_pretrips"))

    return render_template("new_pretrip.html", form=form)

@app.route("/do_posttrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def do_posttrip(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to complete a PostTrip for someone else's PreTrip.", "danger")
        return redirect(url_for("list_pretrips"))

    form = PostTripForm()
    if form.validate_on_submit():
        end_mileage_val = form.end_mileage.data
        if pt.start_mileage is not None:
            miles_val = end_mileage_val - pt.start_mileage
        else:
            miles_val = None

        new_posttrip = PostTrip(
            pretrip_id=pretrip_id,
            end_mileage=end_mileage_val,
            remarks=form.remarks.data,
            miles_driven=miles_val
        )
        db.session.add(new_posttrip)
        db.session.commit()

        shift = ShiftRecord.query.filter_by(pretrip_id=pretrip_id).first()
        if shift and shift.end_time is None:
            shift.end_time = datetime.utcnow()
            shift.total_hours = (
                shift.end_time - shift.start_time
            ).total_seconds() / 3600.0
            db.session.commit()

        flash("PostTrip completed successfully and shift clock ended!", "success")
        return redirect(url_for("view_pretrip", pretrip_id=pretrip_id))
    return render_template("posttrip.html", form=form, pretrip=pt)

@app.route("/view_pretrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def view_pretrip(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to view that PreTrip.", "danger")
        return redirect(url_for("list_pretrips"))
    return render_template("view_pretrip.html", pretrip=pt, readonly=(current_user.role=="management"))

@app.route("/edit_pretrip_entry/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def edit_pretrip_entry(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for("list_pretrips"))
    if current_user.role == "management":
        flash("Managers have read-only access to driver pretrip data.", "warning")
        return redirect(url_for("view_pretrip", pretrip_id=pt.id))

    form = PreTripForm(obj=pt)
    if form.validate_on_submit():
        pt.pretrip_date = form.pretrip_date.data
        pt.shift = form.shift.data
        pt.truck_type = form.truck_type.data
        pt.truck_number = form.truck_number.data
        pt.trailer_number = form.trailer_number.data
        pt.start_mileage = form.start_mileage.data
        # (Update additional fields as needed)
        pt.oil_system_status = form.oil_system_status.data
        pt.tires_ok = form.tires_ok.data
        pt.tires_status = form.tires_status.data
        pt.cab_doors_windows = form.cab_doors_windows.data
        pt.body_doors = form.body_doors.data
        pt.oil_leak = form.oil_leak.data
        pt.grease_leak = form.grease_leak.data
        pt.coolant_leak = form.coolant_leak.data
        pt.fuel_leak = form.fuel_leak.data
        pt.gc_no_defects = form.gc_no_defects.data
        pt.gauges_warning = form.gauges_warning.data
        pt.wipers = form.wipers.data
        pt.horn = form.horn.data
        pt.heater_defroster = form.heater_defroster.data
        pt.mirrors = form.mirrors.data
        pt.seat_belts_steering = form.seat_belts_steering.data
        pt.clutch = form.clutch.data
        pt.service_brakes = form.service_brakes.data
        pt.parking_brake = form.parking_brake.data
        pt.emergency_brakes = form.emergency_brakes.data
        pt.triangles = form.triangles.data
        pt.fire_extinguisher = form.fire_extinguisher.data
        pt.safety_equipment = form.safety_equipment.data
        pt.incab_no_defects = form.incab_no_defects.data
        pt.oil_level = form.oil_level.data
        pt.coolant_level = form.coolant_level.data
        pt.belts = form.belts.data
        pt.hoses = form.hoses.data
        pt.ec_no_defects = form.ec_no_defects.data
        pt.lights_working = form.lights_working.data
        pt.reflectors = form.reflectors.data
        pt.suspension = form.suspension.data
        pt.tires = form.tires.data
        pt.wheels_rims = form.wheels_rims.data
        pt.battery = form.battery.data
        pt.exhaust = form.exhaust.data
        pt.brakes = form.brakes.data
        pt.air_lines = form.air_lines.data
        pt.light_line = form.light_line.data
        pt.fifth_wheel = form.fifth_wheel.data
        pt.coupling = form.coupling.data
        pt.tie_downs = form.tie_downs.data
        pt.rear_end_protection = form.rear_end_protection.data
        pt.exterior_no_defects = form.exterior_no_defects.data
        pt.towed_bodydoors = form.towed_bodydoors.data
        pt.towed_tiedowns = form.towed_tiedowns.data
        pt.towed_lights = form.towed_lights.data
        pt.towed_reflectors = form.towed_reflectors.data
        pt.towed_suspension = form.towed_suspension.data
        pt.towed_tires = form.towed_tires.data
        pt.towed_wheels = form.towed_wheels.data
        pt.towed_brakes = form.towed_brakes.data
        pt.towed_landing_gear = form.towed_landing_gear.data
        pt.towed_kingpin = form.towed_kingpin.data
        pt.towed_fifthwheel = form.towed_fifthwheel.data
        pt.towed_othercoupling = form.towed_othercoupling.data
        pt.towed_rearend = form.towed_rearend.data
        pt.towed_no_defects = form.towed_no_defects.data
        pt.damage_report = form.damage_report.data

        db.session.commit()

        session["reviewing_driver"] = request.form.get("reviewing_driver")
        session["reviewing_date"] = request.form.get("reviewing_date")

        flash("PreTrip updated!", "success")
        return redirect(url_for("view_pretrip", pretrip_id=pt.id))

    return render_template("edit_pretrip_entry.html", form=form, pretrip=pt)

############################################################################
# SHIFT Start/End
############################################################################
@app.route("/start_shift", methods=["GET", "POST"])
@login_required
def start_shift():
    existing_open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if existing_open_shift:
        flash("You already have a shift in progress!", "warning")
        return redirect(url_for("dashboard"))

    new_shift = ShiftRecord(
        user_id=current_user.id,
        pretrip_id=None,
        start_time=datetime.utcnow(),
        week_ending=None
    )
    db.session.add(new_shift)
    db.session.commit()

    flash("Shift started!", "success")
    return redirect(url_for("dashboard"))

@app.route("/end_shift", methods=["GET", "POST"])
@login_required
def end_shift():
    open_shift = ShiftRecord.query.filter_by(
        user_id=current_user.id, end_time=None
    ).first()
    if not open_shift:
        flash("No open shift found!", "warning")
        return redirect(url_for("dashboard"))

    open_shift.end_time = datetime.utcnow()
    open_shift.total_hours = (
        open_shift.end_time - open_shift.start_time
    ).total_seconds() / 3600
    db.session.commit()

    flash("Shift ended!", "success")
    return redirect(url_for("dashboard"))

############################################################################
# End of Day Summary
############################################################################
@app.route("/end_of_day_summary", methods=["GET", "POST"])
@login_required
def end_of_day_summary():
    form = EndOfDayForm()
    if form.validate_on_submit():
        flash("Submitted End of Day Summary (interactive)!", "success")
        return redirect(url_for("dashboard"))

    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()

    logs = DriverLog.query.filter_by(driver_id=current_user.id, date=today_local_date).all()
    drivers_logs = { current_user.username: logs }

    pretrips_today = PreTrip.query.filter_by(
        user_id=current_user.id, pretrip_date=today_local_date
    ).all()
    drivers_pretrips = { current_user.username: pretrips_today }

    return render_template(
        "end_of_day_summary.html",
        form=form,
        the_date=today_local_date,
        drivers_logs=drivers_logs,
        drivers_pretrips=drivers_pretrips
    )

@app.route("/end_of_day_print")
@login_required
def end_of_day_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = DriverLog.query.filter_by(driver_id=current_user.id, date=today_local_date).all()
    drivers_logs = { current_user.username: logs }

    return render_template("end_of_day_print.html", the_date=today_local_date, drivers_logs=drivers_logs)

@app.route("/driver_logs_print")
@login_required
def driver_logs_print():
    local_tz = pytz.timezone("America/Detroit")
    today_local_date = datetime.now(local_tz).date()
    logs = DriverLog.query.filter_by(driver_id=current_user.id, date=today_local_date).all()
    return render_template("driver_logs_print.html", logs=logs, the_date=today_local_date)

@app.route("/submit_end_of_day", methods=["POST"])
@login_required
def submit_end_of_day():
    flash("Submitted End of Day Summary via separate route!", "success")
    return redirect(url_for("dashboard"))

############################################################################
# PreTrip Printable
############################################################################
@app.route("/pretrip_printable/<int:pretrip_id>")
@login_required
def pretrip_printable(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to print another driver's PreTrip!", "danger")
        return redirect(url_for("list_pretrips"))

    ephemeral_driver = session.get("reviewing_driver")
    ephemeral_date = session.get("reviewing_date")

    return render_template(
        "pretrip_printable.html",
        pretrip=pt,
        ephemeral_driver=ephemeral_driver,
        ephemeral_date=ephemeral_date
    )

############################################################################
# Announcements
############################################################################
@app.route("/announcements", methods=["GET", "POST"])
@login_required
def announcements():
    one_day_ago = datetime.now() - timedelta(days=1)
    Announcement.query.filter(Announcement.created_at < one_day_ago).delete()
    db.session.commit()

    all_ann = Announcement.query.order_by(Announcement.created_at.desc()).all()
    form = AnnouncementForm()

    if request.method == "POST":
        if current_user.role != "management":
            flash("Management only can post announcements.", "danger")
            return redirect(url_for("announcements"))
        if form.validate_on_submit():
            ann = Announcement(
                title=form.title.data,
                body=form.body.data,
                created_by=current_user.id
            )
            db.session.add(ann)
            db.session.commit()
            flash("Announcement posted!", "success")
            return redirect(url_for("announcements"))

    return render_template("announcements.html", announcements=all_ann, form=form)

############################################################################
# Knowledge Base
############################################################################
@app.route("/knowledge_base", methods=["GET", "POST"])
@login_required
def knowledge_base():
    form = KnowledgeBaseForm()
    if form.validate_on_submit():
        kb = KnowledgeBaseEntry(
            user_id=current_user.id,
            title=form.title.data,
            body=form.body.data
        )
        db.session.add(kb)
        db.session.commit()
        flash("New tip added to the Knowledge Base!", "success")
        return redirect(url_for("knowledge_base"))

    tips = KnowledgeBaseEntry.query.order_by(KnowledgeBaseEntry.id.desc()).all()
    return render_template("knowledge_base.html", form=form, tips=tips)

############################################################################
# Profile
############################################################################
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Profile updated!", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", profile_form=form)

############################################################################
# Recent Activity
############################################################################
@app.route("/recent_activity")
@login_required
def recent_activity():
    cutoff = datetime.now() - timedelta(days=1)
    new_ann = Announcement.query.filter(Announcement.created_at >= cutoff).all()
    new_dms = DirectMessage.query.filter(
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.timestamp >= cutoff
    ).all()
    return render_template("recent_activity.html",
                           new_announcements=new_ann,
                           new_messages=new_dms)

@app.route("/count_unread")
@login_required
def count_unread():
    cutoff = datetime.now() - timedelta(days=1)
    unread_count = DirectMessage.query.filter(
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.timestamp >= cutoff
    ).count()
    return jsonify({"unread_count": unread_count})

############################################################################
# Direct Messages
############################################################################
@app.route("/direct_messages", methods=["GET", "POST"])
@login_required
def direct_messages():
    dm_form = DirectMessageForm()
    all_users = User.query.filter(User.id != current_user.id).all()
    dm_form.receiver_id.choices = [(u.id, u.username) for u in all_users]

    if dm_form.validate_on_submit():
        dm = DirectMessage(
            sender_id=current_user.id,
            receiver_id=dm_form.receiver_id.data,
            content=dm_form.content.data
        )
        db.session.add(dm)
        db.session.commit()
        socketio.emit("new_direct_message", {
            "sender": current_user.username,
            "receiver_id": dm_form.receiver_id.data,
            "content": dm_form.content.data
        })
        flash("Message sent!", "success")
        return redirect(url_for("direct_messages"))

    inbox = DirectMessage.query.filter_by(receiver_id=current_user.id)\
               .order_by(DirectMessage.timestamp.desc()).all()
    outbox = DirectMessage.query.filter_by(sender_id=current_user.id)\
               .order_by(DirectMessage.timestamp.desc()).all()

    return render_template(
        "direct_messages.html",
        dm_form=dm_form,
        inbox=inbox,
        outbox=outbox
    )

############################################################################
# Chat (global)
############################################################################
@app.route("/chat")
@login_required
def chat_page():
    messages = ChatMessage.query.filter_by(room="global")\
                                .order_by(ChatMessage.timestamp.asc()).all()
    return render_template("chat.html", messages=messages)

@socketio.on("connect")
def on_connect():
    join_room("global")
    emit("status", {"msg": f"{current_user.username} joined global chat."}, to="global")

@socketio.on("join")
def handle_join(data):
    room = data.get("room", "global")
    join_room(room)
    emit("status", {"msg": f'{current_user.username} joined {room}.'}, to=room)

@socketio.on("leave")
def handle_leave(data):
    room = data.get("room", "global")
    leave_room(room)
    emit("status", {"msg": f'{current_user.username} left {room}.'}, to=room)

@socketio.on("chat_message")
def handle_chat_message(data):
    room = data.get("room", "global")
    content = data.get("content", "").strip()
    if content:
        msg = ChatMessage(user_id=current_user.id, content=content, room=room)
        db.session.add(msg)
        db.session.commit()
        emit("chat_message", {
            "username": current_user.username,
            "content": content
        }, to=room)

############################################################################
# Google Maps, Weekly Performance, etc.
############################################################################
@app.route("/map")
@login_required
def show_map():
    return render_template("map.html", google_api_key="YOUR_GOOGLE_MAPS_API_KEY")

@app.route('/OneSignalSDKWorker.js')
def onesignal_sw():
    return send_from_directory('static', 'OneSignalSDKWorker.js')

def get_friday_of_current_week():
    today = datetime.utcnow().date()
    offset = (4 - today.weekday()) % 7
    return today + timedelta(days=offset)

############################################################################
# NEW: Plant Directory Route
############################################################################
@app.route("/plant_directory")
@login_required
def plant_directory():
    return render_template("plant_directory.html")

############################################################################
# Main
############################################################################
if __name__ == "__main__":
    print("Starting SocketIO server on http://127.0.0.1:5000/dashboard ...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
