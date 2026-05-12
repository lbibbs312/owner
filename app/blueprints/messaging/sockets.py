"""Flask-SocketIO event handlers for the global chat room.

Imported for side effects from app/blueprints/messaging/__init__.py — the
@socketio.on(...) decorators register handlers on the SocketIO singleton at
import time. The singleton has already been init_app()'d by the factory before
this module is imported (the factory calls _register_blueprints after
init_extensions), so handlers are wired up against a fully bound app.
"""
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app.extensions import db, socketio
from app.models import ChatMessage


@socketio.on("connect")
def on_connect():
    join_room("global")
    emit("status", {"msg": f"{current_user.username} joined global chat."}, to="global")


@socketio.on("join")
def handle_join(data):
    room = data.get("room", "global")
    join_room(room)
    emit("status", {"msg": f"{current_user.username} joined {room}."}, to=room)


@socketio.on("leave")
def handle_leave(data):
    room = data.get("room", "global")
    leave_room(room)
    emit("status", {"msg": f"{current_user.username} left {room}."}, to=room)


@socketio.on("chat_message")
def handle_chat_message(data):
    room = data.get("room", "global")
    content = data.get("content", "").strip()
    if content:
        msg = ChatMessage(user_id=current_user.id, content=content, room=room)
        db.session.add(msg)
        db.session.commit()
        emit(
            "chat_message",
            {"username": current_user.username, "content": content},
            to=room,
        )
