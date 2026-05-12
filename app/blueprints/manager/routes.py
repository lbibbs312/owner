"""Manager-facing routes.

All routes are gated by a before_request that requires the user to have the
`management` role; non-managers get redirected to the driver dashboard with a
flash message. This replaces the manager_bp.py / manager_routes.py /
db_setup.py sub-system that was unreachable at runtime (it imported from a
separate unbound SQLAlchemy instance, so any DB query inside it would have
raised "RuntimeError: working outside of application context").

Now wired against app.models.Task / app.extensions.db like everything else.
"""
from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.manager import bp
from app.extensions import db
from app.forms.task import TaskForm
from app.models import Task


@bp.before_request
@login_required
def require_management_role():
    if current_user.role != "management":
        flash("Management only!", "danger")
        return redirect(url_for("driver.dashboard"))


@bp.route("/dashboard", methods=["GET", "POST"])
def manager_dashboard():
    create_task_form = TaskForm()
    uncompleted_tasks = Task.query.filter_by(status="pending").all()
    return render_template(
        "manager_dashboard.html",
        create_task_form=create_task_form,
        uncompleted_tasks=uncompleted_tasks,
    )


@bp.route("/create_task_from_dashboard", methods=["POST"])
def create_task_from_dashboard():
    form = TaskForm()
    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            details=form.details.data,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=form.assigned_to.data,
            status="pending",
        )
        db.session.add(new_task)
        db.session.commit()
        flash("Task created from dashboard!", "success")
    else:
        flash("Failed to create task. Check form input.", "danger")

    return redirect(url_for("manager.manager_dashboard"))
