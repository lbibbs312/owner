import os
import pytz
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import (
    request, redirect, url_for, flash,
    render_template, session, jsonify, send_file, send_from_directory
)
from flask_login import (
    UserMixin, current_user,
    login_required, login_user, logout_user
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, SelectField, IntegerField, DateField, HiddenField
)
from wtforms.validators import DataRequired, Email, EqualTo, Length
from flask_socketio import join_room, leave_room, emit

from app import create_app
from app.extensions import db, socketio, login_manager
from app.forms.messaging import DirectMessageForm
from app.models import (
    User, Task, PreTrip, PostTrip, DriverLog, ShiftRecord,
    ChatMessage, Announcement, DirectMessage, KnowledgeBaseEntry,
)

from manager_routes import manager_bp

app = create_app()
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


############################################################################
# Forms
############################################################################


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



class AnnouncementForm(FlaskForm):
    title = StringField("Announcement Title", validators=[DataRequired()])
    body = TextAreaField("Announcement Body", validators=[DataRequired()])
    submit = SubmitField("Post Announcement")


class KnowledgeBaseForm(FlaskForm):
    title = StringField("Tip Title", validators=[DataRequired()])
    body = TextAreaField("Tip Body", validators=[DataRequired()])
    submit = SubmitField("Add Tip")


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
@app.template_filter('to_12h_format')
def to_12h_format(hhmm_str):
    if not hhmm_str:
        return ""
    try:
        dt = datetime.strptime(hhmm_str, "%H:%M")
        return dt.strftime("%I:%M%p").lower().lstrip('0')
    except ValueError:
        return hhmm_str

############################################################################
# PreTrip/PostTrip
############################################################################
############################################################################
# SHIFT Start/End
############################################################################
############################################################################
# End of Day Summary
############################################################################
############################################################################
# PreTrip Printable
############################################################################
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

def get_friday_of_current_week():
    today = datetime.utcnow().date()
    offset = (4 - today.weekday()) % 7
    return today + timedelta(days=offset)


############################################################################
# Main
############################################################################
if __name__ == "__main__":
    print("Starting SocketIO server on http://127.0.0.1:5000/dashboard ...")
    debug_enabled = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug_enabled)
