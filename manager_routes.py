# manager_routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from db_setup import db, Task  # adjust import to your actual DB/models file
from forms import TaskForm     # adjust import to your actual forms file

manager_bp = Blueprint("manager_bp", __name__, url_prefix="/manager")

@manager_bp.before_request
@login_required
def require_management_role():
    """Block anyone not a manager (i.e., role != 'management')."""
    if current_user.role != "management":
        flash("Management only!", "danger")
        # If someone who isn’t a manager tries to access these pages,
        # we send them to the driver (or other) dashboard. Adjust as needed.
        return redirect(url_for("dashboard"))

@manager_bp.route("/dashboard", methods=["GET","POST"])
def manager_dashboard():
    """
    Display the manager dashboard with a form to create tasks
    and a list of uncompleted tasks (status='pending').
    """
    create_task_form = TaskForm()
    uncompleted_tasks = Task.query.filter_by(status="pending").all()

    return render_template(
        "manager_dashboard.html",      # The template you shared
        create_task_form=create_task_form,
        uncompleted_tasks=uncompleted_tasks
    )

@manager_bp.route("/create_task_from_dashboard", methods=["POST"])
def create_task_from_dashboard():
    """
    Handle the POSTed TaskForm to create a new Task in the DB,
    then return to manager dashboard.
    """
    form = TaskForm()
    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            details=form.details.data,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=form.assigned_to.data,
            status="pending"  # automatically mark new tasks as 'pending'
        )
        db.session.add(new_task)
        db.session.commit()
        flash("Task created from dashboard!", "success")
    else:
        flash("Failed to create task. Check form input.", "danger")

    # Send the manager back to the manager dashboard
    return redirect(url_for("manager_bp.manager_dashboard"))
