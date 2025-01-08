#########################################################
# lacksdrivers.py - Full script, with:
#   - Removed references to "cab_doors_windows_status"
#   - Passing dm_form to dashboard route
#   - Everything else unchanged
#########################################################
import os
from datetime import datetime, date, timedelta
from io import BytesIO
from collections import defaultdict

from flask import (
    Flask, request, redirect, url_for, flash,
    render_template, session, jsonify, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_required, login_user, logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash
# For forms/validators
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, SelectField, IntegerField, DateField
)
from wtforms.validators import DataRequired, Email, EqualTo, Length
# Flask-SocketIO for chat & notifications
from flask_socketio import SocketIO, join_room, leave_room, emit
# For migrations (Alembic/Flask-Migrate)
from flask_migrate import Migrate
import pytz
# For optional enum usage
from sqlalchemy import Enum

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

##################################################
# MODELS
##################################################
ITEM_STATUSES = ("operational", "damaged", "missing", "leaking")

class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default="driver")  # "driver" or "management"

    tasks = db.relationship("Task", backref="assigned_user", lazy="dynamic")

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)


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


class PreTrip(db.Model):
    __tablename__ = "pretrip"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    pretrip_date = db.Column(db.Date, default=date.today)
    shift = db.Column(db.String(10), default="1st")
    truck_type = db.Column(db.String(20), default="Semi")
    truck_name = db.Column(db.String(50))
    start_mileage = db.Column(db.Integer, nullable=True)

    # Original booleans (NOT status fields)
    cab_doors_windows = db.Column(db.Boolean, default=False)
    body_doors = db.Column(db.Boolean, default=False)
    oil_leak = db.Column(db.Boolean, default=False)
    grease_leak = db.Column(db.Boolean, default=False)
    coolant_leak = db.Column(db.Boolean, default=False)
    fuel_leak = db.Column(db.Boolean, default=False)
    lights_working = db.Column(db.Boolean, default=False)
    tires_ok = db.Column(db.Boolean, default=False)
    damage_report = db.Column(db.Text, nullable=True)

    # If you prefer enumerated statuses, add them explicitly
    oil_system_status = db.Column(Enum(*ITEM_STATUSES, name="oil_system_enum"), default="operational")
    tires_status = db.Column(Enum(*ITEM_STATUSES, name="tires_enum"), default="operational")

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


class DriverLog(db.Model):
    __tablename__ = "driver_log"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    driver = db.relationship("User", backref="driver_logs", lazy="joined")
    date = db.Column(db.Date, default=date.today)
    arrive_time = db.Column(db.String(20))  # storing 12-hr string
    depart_time = db.Column(db.String(20))
    downtime_reason = db.Column(db.String(200), nullable=True)
    load_size = db.Column(db.String(10), nullable=False)
    plant_name = db.Column(db.String(20), nullable=False)
    maintenance = db.Column(db.Boolean, default=False)
    fuel = db.Column(db.Boolean, default=False)
    meeting = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = "chat_message"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    room = db.Column(db.String(100), default="global")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="chat_messages")


class Announcement(db.Model):
    __tablename__ = "announcement"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DirectMessage(db.Model):
    __tablename__ = "direct_message"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="received_messages")


class ShiftRecord(db.Model):
    __tablename__ = "shift_record"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pretrip_id = db.Column(db.Integer, db.ForeignKey("pretrip.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Float, nullable=True)
    week_ending = db.Column(db.Date, nullable=True)

    user = db.relationship("User", backref="shift_records")
    pretrip = db.relationship("PreTrip", backref="shift_record")


class KnowledgeBaseEntry(db.Model):
    __tablename__ = "knowledge_base"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    title = db.Column(db.String(100))
    body = db.Column(db.Text)


##################################################
# FORMS
##################################################
class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    role = SelectField("Role", choices=[("driver","Driver"),("management","Management")], default="driver")
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
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    assigned_to = SelectField("Assign To (Driver)", coerce=int, default=None)
    submit = SubmitField("Create Task")


class UpdateTaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    details = TextAreaField("Details")
    is_hot = BooleanField("Mark as Hot")
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")])
    status = SelectField("Status", choices=[
        ("pending","Pending"),
        ("in-progress","In Progress"),
        ("completed","Completed"),
        ("declined","Declined")
    ])
    assigned_to = SelectField("Assigned To (Driver)", coerce=int)
    submit = SubmitField("Update Task")


class PreTripForm(FlaskForm):
    pretrip_date = DateField("PreTrip Date", format="%Y-%m-%d", default=date.today)
    shift = SelectField("Shift", choices=[("1st","1st"),("2nd","2nd"),("3rd","3rd")], default="1st")
    truck_type = SelectField("Truck Type", choices=[("Semi","Semi"),("Box Truck","Box Truck")], default="Semi")
    truck_name = StringField("Truck Name", validators=[DataRequired()])
    start_mileage = IntegerField("Start Mileage")

    # Keep these booleans (no "status" fields unless you want them):
    cab_doors_windows = BooleanField("Cab/Doors/Windows")
    body_doors = BooleanField("Body/Doors")
    oil_leak = BooleanField("Oil Leak")
    grease_leak = BooleanField("Grease Leak")
    coolant_leak = BooleanField("Coolant Leak")
    fuel_leak = BooleanField("Fuel Leak")
    lights_working = BooleanField("Lights Working")
    tires_ok = BooleanField("Tires in Good Condition")
    damage_report = TextAreaField("Damage Report (Describe if any)")

    # If you want enumerated statuses, keep these or remove them
    oil_system_status = SelectField(
        "Oil System Status",
        choices=[
            ("operational", "Operational"),
            ("damaged", "Damaged"),
            ("missing", "Missing"),
            ("leaking", "Leaking"),
        ],
        default="operational"
    )
    tires_status = SelectField(
        "Tires Status",
        choices=[
            ("operational", "Operational"),
            ("damaged", "Damaged"),
            ("missing", "Missing"),
            ("leaking", "Leaking"),
        ],
        default="operational"
    )

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
            ("BP", "Barden Plater (BP)"),
            ("52L", "52 Logistics (52L)"),
            ("ALN", "Airlane North (ALN)"),
            ("52DC", "Trim DC (52DC)"),
            ("PE", "Paint East (PE)"),
            ("PC", "Paint Central (PC)"),
            ("RW", "Raleigh West (RW)"),
            ("PPM", "Monroe (PPM)"),
            ("KP", "Kraft Plater (KP)"),
            ("RE", "Raleigh East (RE)"),
            ("AWE", "Airwest Eng (AWE)"),
            ("Lab", "Corporate Lab"),
            ("PPL", "Plastic Plate Logistics (PPL)"),
            ("DC", "Plastic Plate DC (DC)"),
            ("KM", "Kraft Mold (KM)")
        ],
        validators=[DataRequired()]
    )
    load_size = SelectField(
        "Load Size",
        choices=[
            ("", "Select Load Size..."),
            ("Empty", "Empty"),
            ("Quarter", "Quarter"),
            ("Partial", "Partial"),
            ("Full", "Full"),
        ],
        validators=[DataRequired()]
    )
    downtime_reason = StringField("Downtime Reason (optional)")
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

##################################################
# BASIC ROUTES
##################################################
@app.route("/")
def welcome():
    bulletins = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    return render_template("welcome.html", bulletins=bulletins)

# Example ProfileForm
class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    new_password = PasswordField("New Password")   # not strictly required
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Update Profile")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)  # Pre-fill with current_user's data

    if form.validate_on_submit():
        # Update user's info in the database
        current_user.username = form.username.data
        current_user.email = form.email.data

        # If user typed a new password, update it
        if form.new_password.data:
            current_user.set_password(form.new_password.data)

        db.session.commit()  # save changes
        flash("Profile updated!", "success")
        return redirect(url_for("profile"))  # reload the profile page

    return render_template("profile.html", profile_form=form)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo

class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])

    # Add this field for role selection
    role = SelectField(
        "Role",
        choices=[("driver", "Driver"), ("management", "Management")]
    )

    new_password = PasswordField("New Password")
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            EqualTo("new_password", message="Passwords must match.")
        ]
    )
    submit = SubmitField("Update Profile")


@app.route("/weekly_performance")
@login_required
def weekly_performance():
    # Real logic to get date range, shift hours, tasks, etc.
    start_date = "2023-08-01"
    end_date = "2023-08-07"
    driver_hours = {
        "John": {"week_hours": 39.5, "day_hours": 8.0},
        "Jane": {"week_hours": 42.0, "day_hours": 8.5},
    }
    plants_times = [
        {"driver_name": "John", "plant_name": "BP", "hours": 12.0},
        {"driver_name": "Jane", "plant_name": "ALN", "hours": 5.5},
    ]
    tasks_completion = {
        "John": {"assigned": 10, "completed": 8},
        "Jane": {"assigned": 12, "completed": 10},
    }
    return render_template("weekly_performance.html",
                           start_date=start_date,
                           end_date=end_date,
                           driver_hours=driver_hours,
                           plants_times=plants_times,
                           tasks_completion=tasks_completion)

@app.route("/handoff_task", methods=["POST"])
@login_required
def handoff_task():
    if current_user.role != "management":
        return jsonify({"error": "Forbidden"}), 403

    task_id = request.json.get("task_id")
    mode = request.json.get("mode")
    # e.g. find the task
    t = Task.query.get(task_id)
    if not t:
        return jsonify({"error": "Task not found"}), 404

    if mode == "next_shift":
        # Logic: maybe switch t.shift to next shift
        if t.shift == "1st":
            t.shift = "2nd"
        elif t.shift == "2nd":
            t.shift = "3rd"
        else:
            t.shift = "1st"
        db.session.commit()
        return jsonify({"status": "Shift changed"}), 200

    elif mode == "assign_driver":
        # e.g. reassign to some other driver
        new_driver_id = request.json.get("new_driver_id")  # or whatever
        t.assigned_to = new_driver_id
        db.session.commit()
        return jsonify({"status": "Reassigned driver"}), 200

    return jsonify({"status": "No valid mode selected"}), 200

@app.route('/OneSignalSDKWorker.js')
def onesignal_sw():
    return send_from_directory('static', 'OneSignalSDKWorker.js')


##################################################
# AUTH ROUTES
##################################################
@app.route("/register", methods=["GET","POST"])
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


@app.route("/login", methods=["GET","POST"])
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


##################################################
# DIRECT MESSAGES & CHAT
##################################################
@app.route("/direct_messages", methods=["GET","POST"])
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
    return render_template("direct_messages.html", dm_form=dm_form, inbox=inbox, outbox=outbox)


@app.route("/reply_dm/<int:dm_id>", methods=["GET","POST"])
@login_required
def reply_dm(dm_id):
    original_dm = DirectMessage.query.get_or_404(dm_id)
    if original_dm.receiver_id != current_user.id:
        flash("Not authorized to reply to that message.", "danger")
        return redirect(url_for("direct_messages"))

    reply_form = DirectMessageForm()
    reply_form.receiver_id.choices = [(original_dm.sender.id, original_dm.sender.username)]

    if reply_form.validate_on_submit():
        new_reply = DirectMessage(
            sender_id=current_user.id,
            receiver_id=original_dm.sender_id,
            content=reply_form.content.data
        )
        db.session.add(new_reply)
        db.session.commit()
        socketio.emit("new_direct_message", {
            "sender": current_user.username,
            "receiver_id": original_dm.sender_id,
            "content": reply_form.content.data
        })
        flash("Reply sent!", "success")
        return redirect(url_for("direct_messages"))

    return render_template("reply_dm.html", reply_form=reply_form, original_dm=original_dm)


@app.route("/chat")
@login_required
def chat_page():
    messages = ChatMessage.query.filter_by(room="global").order_by(ChatMessage.timestamp.asc()).all()
    return render_template("chat.html", messages=messages)


@socketio.on("connect")
def on_connect():
    join_room("global")
    emit("status", {"msg": f"{current_user.username} joined global chat."}, to="global")


@socketio.on("join")
def handle_join(data):
    room = data.get("room","global")
    join_room(room)
    emit("status", {"msg": f'{current_user.username} joined {room}.'}, to=room)


@socketio.on("leave")
def handle_leave(data):
    room = data.get("room","global")
    leave_room(room)
    emit("status", {"msg": f'{current_user.username} left {room}.'}, to=room)


@socketio.on("chat_message")
def handle_chat_message(data):
    room = data.get("room","global")
    content = data.get("content","").strip()
    if content:
        msg = ChatMessage(user_id=current_user.id, content=content, room=room)
        db.session.add(msg)
        db.session.commit()
        emit("chat_message", {
            "username": current_user.username,
            "content": content
        }, to=room)


##################################################
# DASHBOARD (FIX: pass dm_form)
##################################################
@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if current_user.role == "driver":
        logs = DriverLog.query.filter_by(driver_id=current_user.id)\
            .order_by(DriverLog.created_at.desc()).limit(5).all()
        pretrips = PreTrip.query.filter_by(user_id=current_user.id)\
            .order_by(PreTrip.created_at.desc()).limit(5).all()
        tasks = Task.query.filter_by(assigned_to=current_user.id)\
            .order_by(Task.created_at.desc()).limit(5).all()
    else:
        logs = DriverLog.query.order_by(DriverLog.created_at.desc()).limit(5).all()
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).limit(5).all()
        tasks = Task.query.order_by(Task.created_at.desc()).limit(5).all()

    # Create the direct message form and pass it to the template
    dm_form = DirectMessageForm()
    all_users = User.query.filter(User.id != current_user.id).all()
    dm_form.receiver_id.choices = [(u.id, u.username) for u in all_users]

    # If the user submitted the DM form from the dashboard
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

    # Inbox/Outbox:
    inbox = DirectMessage.query.filter_by(receiver_id=current_user.id).order_by(DirectMessage.timestamp.desc()).all()
    outbox = DirectMessage.query.filter_by(sender_id=current_user.id).order_by(DirectMessage.timestamp.desc()).all()

    return render_template(
        "dashboard.html",
        logs=logs,
        pretrips=pretrips,
        tasks=tasks,
        dm_form=dm_form,
        inbox=inbox,
        outbox=outbox
    )


##################################################
# ANNOUNCEMENTS (Last 1 day)
##################################################
@app.route("/announcements", methods=["GET","POST"])
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
                created_by=current_user.id)
            db.session.add(ann)
            db.session.commit()
            flash("Announcement posted!", "success")
            return redirect(url_for("announcements"))

    return render_template("announcements.html", announcements=all_ann, form=form)


@app.route("/logout2")
@login_required
def real_logout():
    logout_user()
    flash("Logged out (real_logout).", "info")
    return redirect(url_for("welcome"))


##################################################
# MANAGER VIEWS
##################################################
@app.route("/manager/drivers")
@login_required
def manager_view_drivers():
    if current_user.role != "management":
        flash("Management only.", "danger")
        return redirect(url_for("dashboard"))
    users = User.query.all()
    return render_template("manager_drivers.html", users=users)


##################################################
# TASK-RELATED
##################################################
@app.route("/create_task", methods=["GET","POST"])
@login_required
def create_task():
    if current_user.role != "management":
        flash("Only managers can create tasks.", "danger")
        return redirect(url_for("dashboard"))
    form = TaskForm()
    drivers = User.query.filter_by(role="driver").all()
    form.assigned_to.choices = [(d.id, d.username) for d in drivers]

    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            details=form.details.data,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=form.assigned_to.data
        )
        db.session.add(new_task)
        db.session.commit()
        flash("Task created successfully!", "success")
        return redirect(url_for("list_tasks"))
    return render_template("create_task.html", form=form)


@app.route("/list_tasks")
@login_required
def list_tasks():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
    else:
        tasks = Task.query.filter_by(assigned_to=current_user.id)\
            .order_by(Task.created_at.desc()).all()
    return render_template("list_tasks.html", tasks=tasks)

##################################################
# PRETRIP-RELATED
##################################################
@app.route("/list_pretrips")
@login_required
def list_pretrips():
    if current_user.role == "management":
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
    else:
        pretrips = PreTrip.query.filter_by(user_id=current_user.id)\
                   .order_by(PreTrip.created_at.desc()).all()
    return render_template("list_pretrips.html", pretrips=pretrips)


@app.route("/new_pretrip", methods=["GET","POST"])
@login_required
def new_pretrip():
    form = PreTripForm()
    if form.validate_on_submit():
        new_pt = PreTrip(
            user_id=current_user.id,
            pretrip_date=form.pretrip_date.data,
            shift=form.shift.data,
            truck_type=form.truck_type.data,
            truck_name=form.truck_name.data,
            start_mileage=form.start_mileage.data,
            cab_doors_windows=form.cab_doors_windows.data,
            body_doors=form.body_doors.data,
            oil_leak=form.oil_leak.data,
            grease_leak=form.grease_leak.data,
            coolant_leak=form.coolant_leak.data,
            fuel_leak=form.fuel_leak.data,
            lights_working=form.lights_working.data,
            tires_ok=form.tires_ok.data,
            damage_report=form.damage_report.data,
            oil_system_status=form.oil_system_status.data,
            tires_status=form.tires_status.data,
        )
        db.session.add(new_pt)
        db.session.commit()

        # SHIFT CLOCK
        shift_rec = ShiftRecord(
            user_id=current_user.id,
            pretrip_id=new_pt.id,
            start_time=datetime.utcnow(),
            week_ending=get_friday_of_current_week()
        )
        db.session.add(shift_rec)
        db.session.commit()

        flash("New PreTrip created successfully and shift clock started!", "success")
        return redirect(url_for("list_pretrips"))
    return render_template("new_pretrip.html", form=form)


@app.route("/submit_pretrip", methods=["GET","POST"])
@login_required
def submit_pretrip():
    form = PreTripForm()
    if form.validate_on_submit():
        new_pt = PreTrip(
            user_id=current_user.id,
            pretrip_date=form.pretrip_date.data,
            shift=form.shift.data,
            truck_type=form.truck_type.data,
            truck_name=form.truck_name.data,
            start_mileage=form.start_mileage.data,
            cab_doors_windows=form.cab_doors_windows.data,
            body_doors=form.body_doors.data,
            oil_leak=form.oil_leak.data,
            grease_leak=form.grease_leak.data,
            coolant_leak=form.coolant_leak.data,
            fuel_leak=form.fuel_leak.data,
            lights_working=form.lights_working.data,
            tires_ok=form.tires_ok.data,
            damage_report=form.damage_report.data,
            oil_system_status=form.oil_system_status.data,
            tires_status=form.tires_status.data,
        )
        db.session.add(new_pt)
        db.session.commit()

        shift_rec = ShiftRecord(
            user_id=current_user.id,
            pretrip_id=new_pt.id,
            start_time=datetime.utcnow(),
            week_ending=get_friday_of_current_week()
        )
        db.session.add(shift_rec)
        db.session.commit()

        flash("New PreTrip created (submit_pretrip) and shift clock started!", "success")
        return redirect(url_for("list_pretrips"))
    return render_template("new_pretrip.html", form=form)


##################################################
# DRIVER LOGS
##################################################
@app.route("/driver_logs", methods=["GET"])
@login_required
def driver_logs():
    if current_user.role == "management":
        all_drivers = User.query.filter_by(role="driver").all()
        selected_driver_id = request.args.get("driver_id", type=int)
        query = DriverLog.query.order_by(DriverLog.created_at.desc())
        if selected_driver_id:
            query = query.filter_by(driver_id=selected_driver_id)
        logs = query.all()
        return render_template(
            "driver_logs.html",
            logs=logs,
            all_drivers=all_drivers,
            selected_driver_id=selected_driver_id
        )
    else:
        logs = DriverLog.query.filter_by(driver_id=current_user.id)\
               .order_by(DriverLog.created_at.desc()).all()
        return render_template("driver_logs.html", logs=logs)


@app.route("/new_driving_log", methods=["GET","POST"])
@login_required
def new_driving_log():
    form = DriverLogForm()
    if form.validate_on_submit():
        if not form.plant_name.data or not form.load_size.data:
            flash("Please select a valid Plant Name and Load Size.", "danger")
            return redirect(url_for("new_driving_log"))
        gr_tz = pytz.timezone("America/Detroit")
        now_gr = datetime.now(gr_tz)
        arrive_12hr = now_gr.strftime("%I:%M %p")

        newlog = DriverLog(
            driver_id=current_user.id,
            plant_name=form.plant_name.data,
            load_size=form.load_size.data,
            downtime_reason=form.downtime_reason.data,
            arrive_time=arrive_12hr,
            maintenance=form.maintenance.data,
            fuel=form.fuel.data,
            meeting=form.meeting.data,
            date=now_gr.date()
        )
        db.session.add(newlog)
        db.session.commit()
        flash("New driving log added!", "success")
        return redirect(url_for("driver_logs"))
    return render_template("new_driving_log.html", form=form)


@app.route("/edit_driver_log/<int:log_id>", methods=["GET","POST"])
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

        gr_tz = pytz.timezone("America/Detroit")
        now_gr = datetime.now(gr_tz)
        log.depart_time = now_gr.strftime("%I:%M %p")

        db.session.commit()
        flash(f"Driving log updated (ID: {log.id})", "success")
        return redirect(url_for("driver_logs"))
    return render_template("edit_driver_log.html", form=form, log=log)


@app.route("/view_driver_log/<int:log_id>")
@login_required
def view_driver_log(log_id):
    single_log = DriverLog.query.get_or_404(log_id)
    if current_user.role == "driver" and single_log.driver_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for("driver_logs"))
    return render_template("view_driver_log.html", log=single_log)


##################################################
# EDIT/UPDATE PRETRIP
##################################################
@app.route("/view_pretrip/<int:pretrip_id>")
@login_required
def view_pretrip(pretrip_id):
    pt = PreTrip.query.get_or_404(pretrip_id)
    if current_user.role == "driver" and pt.user_id != current_user.id:
        flash("Not authorized to view that PreTrip.", "danger")
        return redirect(url_for("list_pretrips"))
    return render_template("view_pretrip.html", pretrip=pt, readonly=(current_user.role=="management"))


@app.route("/edit_pretrip_entry/<int:pretrip_id>", methods=["GET","POST"])
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
        pt.truck_name = form.truck_name.data
        pt.start_mileage = form.start_mileage.data
        pt.cab_doors_windows = form.cab_doors_windows.data
        pt.body_doors = form.body_doors.data
        pt.oil_leak = form.oil_leak.data
        pt.grease_leak = form.grease_leak.data
        pt.coolant_leak = form.coolant_leak.data
        pt.fuel_leak = form.fuel_leak.data
        pt.lights_working = form.lights_working.data
        pt.tires_ok = form.tires_ok.data
        pt.damage_report = form.damage_report.data
        pt.oil_system_status = form.oil_system_status.data
        pt.tires_status = form.tires_status.data
        db.session.commit()
        flash("PreTrip updated!", "success")
        return redirect(url_for("view_pretrip", pretrip_id=pt.id))
    return render_template("edit_pretrip_entry.html", form=form, pretrip=pt)


##################################################
# EDIT/UPDATE TASK
##################################################
@app.route("/edit_task/<int:task_id>", methods=["GET","POST"])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if current_user.role != "management":
        flash("Only managers can edit tasks.", "danger")
        return redirect(url_for("list_tasks"))

    form = UpdateTaskForm(obj=task)
    drivers = User.query.filter_by(role="driver").all()
    form.assigned_to.choices = [(d.id, d.username) for d in drivers]

    if form.validate_on_submit():
        task.title = form.title.data
        task.details = form.details.data
        task.is_hot = form.is_hot.data
        task.shift = form.shift.data
        task.status = form.status.data
        task.assigned_to = form.assigned_to.data
        db.session.commit()
        flash("Task updated successfully!", "success")
        return redirect(url_for("list_tasks"))
    return render_template("edit_task.html", form=form, task=task)


##################################################
# MISC ROUTES
##################################################
@app.route("/all_in_one_dashboard")
@login_required
def all_in_one_dashboard():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
        logs = DriverLog.query.order_by(DriverLog.created_at.desc()).all()
    else:
        tasks = Task.query.filter_by(assigned_to=current_user.id).all()
        pretrips = PreTrip.query.filter_by(user_id=current_user.id).all()
        logs = DriverLog.query.filter_by(driver_id=current_user.id).all()
    return render_template("all_in_one_dashboard.html", tasks=tasks, pretrips=pretrips, logs=logs)


@app.route("/driver_dashboard")
@login_required
def driver_dashboard():
    if current_user.role != "driver":
        flash("Drivers only!", "danger")
        return redirect(url_for("dashboard"))
    tasks = Task.query.filter_by(assigned_to=current_user.id).all()
    logs = DriverLog.query.filter_by(driver_id=current_user.id).all()
    pretrips = PreTrip.query.filter_by(user_id=current_user.id).all()
    return render_template("driver_dashboard.html", tasks=tasks, logs=logs, pretrips=pretrips)

@app.route("/manager_all_pretrips")
@login_required
def manager_all_pretrips():
    if current_user.role != "management":
        flash("Management only.", "danger")
        return redirect(url_for("dashboard"))
    all_pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
    return render_template("manager_all_pretrips.html", pretrips=all_pretrips)


@app.route("/manager_tasks")
@login_required
def manager_tasks():
    if current_user.role != "management":
        flash("Management only.", "danger")
        return redirect(url_for("dashboard"))
    all_tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template("manager_tasks.html", tasks=all_tasks)


@app.route("/list_driving_logs")
@login_required
def list_driving_logs():
    if current_user.role == "management":
        logs = DriverLog.query.order_by(DriverLog.created_at.desc()).all()
    else:
        logs = DriverLog.query.filter_by(driver_id=current_user.id).all()
    return render_template("list_driving_logs.html", logs=logs)

@app.route("/create_task_from_dashboard", methods=["POST"])
@login_required
def create_task_from_dashboard():
    if current_user.role != "management":
        flash("Only managers can create tasks.", "danger")
        return redirect(url_for("dashboard"))

    form = TaskForm()
    drivers = User.query.filter_by(role="driver").all()
    form.assigned_to.choices = [(d.id, d.username) for d in drivers]

    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            details=form.details.data,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=form.assigned_to.data
        )
        db.session.add(new_task)
        db.session.commit()
        flash("Task created from dashboard!", "success")
    return redirect(url_for("manager_dashboard"))

@app.route("/reply_message")
@login_required
def reply_message():
    return render_template("reply_message.html")


@app.route("/task")
@login_required
def task_page():
    return render_template("task.html")


@app.route("/posttrip", methods=["GET","POST"])
@login_required
def posttrip_page():
    form = PostTripForm()
    if form.validate_on_submit():
        flash("PostTrip completed (placeholder logic)!", "success")
        return redirect(url_for("dashboard"))
    return render_template("posttrip.html", form=form)


@app.route("/do_posttrip/<int:pretrip_id>", methods=["GET","POST"])
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
            shift.total_hours = (shift.end_time - shift.start_time).total_seconds() / 3600.0
            db.session.commit()

        flash("PostTrip completed successfully and shift clock ended!", "success")
        return redirect(url_for("view_pretrip", pretrip_id=pretrip_id))
    return render_template("posttrip.html", form=form, pretrip=pt)


@app.route("/pretrip", methods=["GET","POST"])
@login_required
def pretrip_page():
    form = PreTripForm()
    if form.validate_on_submit():
        new_pt = PreTrip(
            user_id=current_user.id,
            truck_name=form.truck_name.data
        )
        db.session.add(new_pt)
        db.session.commit()
        flash("PreTrip saved quickly!", "success")
        return redirect(url_for("list_pretrips"))
    return render_template("pretrip.html", form=form)


@app.route("/editing_task")
@login_required
def editing_task():
    return render_template("editing_task.html")


@app.route("/add_pretrip_entry", methods=["GET","POST"])
@login_required
def add_pretrip_entry():
    form = PreTripForm()
    if form.validate_on_submit():
        pt = PreTrip(
            user_id=current_user.id,
            truck_name=form.truck_name.data
        )
        db.session.add(pt)
        db.session.commit()
        flash("Added a new PreTrip entry!", "success")
        return redirect(url_for("list_pretrips"))
    return render_template("add_pretrip_entry.html", form=form)


@app.route("/unified_dashboard")
@login_required
def unified_dashboard():
    if current_user.role == "management":
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        logs = DriverLog.query.order_by(DriverLog.created_at.desc()).all()
        pretrips = PreTrip.query.order_by(PreTrip.created_at.desc()).all()
    else:
        tasks = Task.query.filter_by(assigned_to=current_user.id).all()
        logs = DriverLog.query.filter_by(driver_id=current_user.id).all()
        pretrips = PreTrip.query.filter_by(user_id=current_user.id).all()
    return render_template("unified_dashboard.html", tasks=tasks, logs=logs, pretrips=pretrips)


@app.route("/layout")
def layout_page():
    return render_template("layout.html")


@app.route("/base")
def base_page():
    return render_template("base.html")


##################################################
# END-OF-DAY SUMMARY (NO PDF)
##################################################
@app.route("/end_of_day_summary")
@login_required
def end_of_day_summary():
    today_date = date.today()

    # if driver, show only that driver’s logs
    if current_user.role == "driver":
        logs = DriverLog.query.filter_by(driver_id=current_user.id, date=today_date).all()
        drivers_logs = { current_user.username: logs }
        # maybe you track miles from PostTrip
        total_miles = 0
        pretrips_today = PreTrip.query.filter_by(user_id=current_user.id, pretrip_date=today_date).all()
        for pt in pretrips_today:
            if pt.posttrip and pt.posttrip.miles_driven:
                total_miles += pt.posttrip.miles_driven
    else:
        # manager: show logs for all drivers
        logs = DriverLog.query.filter_by(date=today_date).all()
        drivers_logs = defaultdict(list)
        for lg in logs:
            dname = lg.driver.username
            drivers_logs[dname].append(lg)
        total_miles = 0  # manager might not need a total

    return render_template("end_of_day_summary.html",
                           drivers_logs=drivers_logs,
                           the_date=today_date,
                           total_miles=total_miles)

##################################################
# RECENT ACTIVITY (BELL ICON)
##################################################
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


##################################################
# KNOWLEDGE BASE
##################################################
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

@app.route("/new_tip", methods=["GET","POST"])
@login_required
def new_tip():
    # logic to handle adding a knowledge base tip
    ...


##################################################
# UTILS
##################################################
def get_friday_of_current_week():
    today = datetime.utcnow().date()
    offset = (4 - today.weekday()) % 7
    return today + timedelta(days=offset)


##################################################
# MAIN
##################################################
if __name__ == "__main__":
    print("Starting SocketIO server on http://127.0.0.1:5000/dashboard ...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
