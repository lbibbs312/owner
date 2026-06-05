"""Flask-SocketIO event handlers for the global chat room.

Imported for side effects from app/blueprints/messaging/__init__.py — the
@socketio.on(...) decorators register handlers on the SocketIO singleton at
import time. The singleton has already been init_app()'d by the factory before
this module is imported (the factory calls _register_blueprints after
init_extensions), so handlers are wired up against a fully bound app.
"""
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app.blueprints.messaging import bp
from app.extensions import db, socketio
from app.models import ChatMessage

ALLOWED_CHAT_ROOMS = frozenset({"global"})


def _allowed_room(data):
    room = (data or {}).get("room", "global")
    if room not in ALLOWED_CHAT_ROOMS:
        emit("chat_error", {"msg": "Room is not available."})
        return None
    return room


def on_connect():
    if not current_user.is_authenticated:
        return False
    join_room("global")
    emit("status", {"msg": f"{current_user.username} joined global chat."}, to="global")


def handle_join(data):
    if not current_user.is_authenticated:
        return False
    room = _allowed_room(data)
    if not room:
        return False
    join_room(room)
    emit("status", {"msg": f"{current_user.username} joined {room}."}, to=room)


def handle_leave(data):
    if not current_user.is_authenticated:
        return False
    room = _allowed_room(data)
    if not room:
        return False
    leave_room(room)
    emit("status", {"msg": f"{current_user.username} left {room}."}, to=room)


def handle_chat_message(data):
    if not current_user.is_authenticated:
        return False
    room = _allowed_room(data)
    if not room:
        return False
    content = (data or {}).get("content", "").strip()
    if content:
        msg = ChatMessage(user_id=current_user.id, content=content, room=room)
        db.session.add(msg)
        db.session.commit()
        emit(
            "chat_message",
            {"username": current_user.username, "content": content},
            to=room,
        )


@bp.record
def register_socketio_handlers(state):
    socketio.on_event("connect", on_connect)
    socketio.on_event("join", handle_join)
    socketio.on_event("leave", handle_leave)
    socketio.on_event("chat_message", handle_chat_message)
