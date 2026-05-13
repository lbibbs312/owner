"""Messaging-related routes.

Houses the cross-cutting messaging UI that's neither driver- nor manager-
specific: chat, direct messages, announcements, the knowledge base, and the
notification feeds (recent activity, unread count).
"""
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.messaging import bp
from app.extensions import db, socketio
from app.forms.messaging import AnnouncementForm, DirectMessageForm, KnowledgeBaseForm
from app.models import (
    ActivityEvent,
    Announcement,
    ChatMessage,
    DirectMessage,
    KnowledgeBaseEntry,
    User,
)


@bp.route("/announcements", methods=["GET", "POST"])
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
            return redirect(url_for("messaging.announcements"))
        if form.validate_on_submit():
            ann = Announcement(
                title=form.title.data,
                body=form.body.data,
                created_by=current_user.id,
            )
            db.session.add(ann)
            db.session.commit()
            flash("Announcement posted!", "success")
            return redirect(url_for("messaging.announcements"))

    return render_template("announcements.html", announcements=all_ann, form=form)


@bp.route("/knowledge_base", methods=["GET", "POST"])
@login_required
def knowledge_base():
    form = KnowledgeBaseForm()
    if form.validate_on_submit():
        kb = KnowledgeBaseEntry(
            user_id=current_user.id,
            title=form.title.data,
            body=form.body.data,
        )
        db.session.add(kb)
        db.session.commit()
        flash("New tip added to the Knowledge Base!", "success")
        return redirect(url_for("messaging.knowledge_base"))

    tips = KnowledgeBaseEntry.query.order_by(KnowledgeBaseEntry.id.desc()).all()
    return render_template("knowledge_base.html", form=form, tips=tips)


@bp.route("/recent_activity")
@login_required
def recent_activity():
    cutoff = datetime.now() - timedelta(days=1)
    new_ann = Announcement.query.filter(Announcement.created_at >= cutoff).all()
    new_dms = DirectMessage.query.filter(
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.timestamp >= cutoff,
    ).all()
    activity_query = ActivityEvent.query.order_by(ActivityEvent.created_at.desc())
    if current_user.role != "management":
        activity_query = activity_query.filter_by(user_id=current_user.id)
    action_history = activity_query.limit(100).all()
    return render_template(
        "recent_activity.html",
        new_announcements=new_ann,
        new_messages=new_dms,
        action_history=action_history,
    )


@bp.route("/count_unread")
@login_required
def count_unread():
    cutoff = datetime.now() - timedelta(days=1)
    message_count = DirectMessage.query.filter(
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.timestamp >= cutoff,
    ).count()
    action_query = ActivityEvent.query.filter(ActivityEvent.created_at >= cutoff)
    if current_user.role != "management":
        action_query = action_query.filter_by(user_id=current_user.id)
    action_events = action_query.all()
    category_counts = {}
    for event in action_events:
        category_counts[event.category] = category_counts.get(event.category, 0) + 1
    category_count = len(category_counts)
    display_count = message_count + category_count
    action_count = len(action_events)
    return jsonify(
        {
            "unread_count": message_count + action_count,
            "display_count": display_count,
            "message_count": message_count,
            "action_count": action_count,
            "action_category_count": category_count,
            "categories": category_counts,
        }
    )


@bp.route("/direct_messages", methods=["GET", "POST"])
@login_required
def direct_messages():
    dm_form = DirectMessageForm()
    all_users = User.query.filter(User.id != current_user.id).all()
    dm_form.receiver_id.choices = [(u.id, u.username) for u in all_users]

    if dm_form.validate_on_submit():
        dm = DirectMessage(
            sender_id=current_user.id,
            receiver_id=dm_form.receiver_id.data,
            content=dm_form.content.data,
        )
        db.session.add(dm)
        db.session.commit()
        socketio.emit(
            "new_direct_message",
            {
                "sender": current_user.username,
                "receiver_id": dm_form.receiver_id.data,
                "content": dm_form.content.data,
            },
        )
        flash("Message sent!", "success")
        return redirect(url_for("messaging.direct_messages"))

    inbox = (
        DirectMessage.query.filter_by(receiver_id=current_user.id)
        .order_by(DirectMessage.timestamp.desc())
        .all()
    )
    outbox = (
        DirectMessage.query.filter_by(sender_id=current_user.id)
        .order_by(DirectMessage.timestamp.desc())
        .all()
    )

    return render_template(
        "direct_messages.html",
        dm_form=dm_form,
        inbox=inbox,
        outbox=outbox,
    )


@bp.route("/chat")
@login_required
def chat_page():
    messages = (
        ChatMessage.query.filter_by(room="global")
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    return render_template("chat.html", messages=messages)
