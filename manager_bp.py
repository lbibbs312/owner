# manager_bp.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from db_setup import db, Task       # Adjust to your actual DB/models file
from forms import TaskForm          # Adjust to your actual forms file

# Create a Blueprint for manager routes:
manager_bp = Blueprint(
    "manager_bp",          # Blueprint name (used in url_for)
    __name__, 
    url_prefix="/manager"  # All URLs in this blueprint start with /manager
)

@manager_bp.before_request
@login_required
def require_management_role():
    """
    This hook runs before ANY route in this blueprint.
    If the user is not a manager (role != 'management'),
    they get redirected away with a flash message.
    """
    if current_user.role != "management":
        flash("Management only!", "danger")
        # Adjust the redirect as needed. 
        # "dashboard" might be your driver dashboard route name:
        return redirect(url_for("dashboard"))

@manager_bp.route("/dashboard", methods=["GET"])
def manager_dashboard():
    """
    Shows the Manager Dashboard, which includes:
      - A 'Create Task' form for managers
      - A list of uncompleted tasks (status='pending')
    """
    create_task_form = TaskForm()
    uncompleted_tasks = Task.query.filter_by(status="pending").all()

    # Render manager_dashboard.html (the template you shared)
    return render_template(
        "manager_dashboard.html",
        create_task_form=create_task_form,
        uncompleted_tasks=uncompleted_tasks
    )

@manager_bp.route("/create_task_from_dashboard", methods=["POST"])
def create_task_from_dashboard():
    """
    Processes the TaskForm POST request to create a new Task in the DB,
    then redirects back to the manager dashboard.
    """
    form = TaskForm()
    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            details=form.details.data,
            is_hot=form.is_hot.data,
            shift=form.shift.data,
            assigned_to=form.assigned_to.data,
            status="pending"
        )
        db.session.add(new_task)
        db.session.commit()
        flash("Task created from dashboard!", "success")
    else:
        flash("Failed to create task. Check form input.", "danger")

    return redirect(url_for("manager_bp.manager_dashboard"))
