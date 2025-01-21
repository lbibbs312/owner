from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

# Create a Blueprint for all driver-only routes
driver_bp = Blueprint("driver_bp", __name__)

@driver_bp.before_request
@login_required
def require_driver_role():
    """
    Runs before every driver_bp request:
    - Requires that the current_user's role is "driver"
    - Otherwise, flashes a warning and redirects to the manager dashboard
    """
    if current_user.role != "driver":
        flash("Drivers only!", "danger")
        return redirect(url_for("manager_bp.manager_dashboard"))
    # If the user is a driver, continue handling the request

@driver_bp.route("/new_pretrip", methods=["GET", "POST"])
def new_pretrip():
    if request.method == "POST":
        # 1) Grab form inputs
        truck_number = request.form.get("truck_number")
        # 2) Validate them (if needed)
        if not truck_number:
            flash("Truck number is required", "danger")
            return redirect(url_for("driver_bp.new_pretrip"))

        # 3) Create & save to DB
        new_pt = PreTrip(
            truck_number=truck_number,
            driver_id=current_user.id,
            # any other fields
        )
        db.session.add(new_pt)
        db.session.commit()

        flash("PreTrip created successfully!", "success")
        return redirect(url_for("driver_bp.list_pretrips"))

    # If GET request, just show the form
    return render_template("new_pretrip.html")


@driver_bp.route("/list_pretrips", methods=["GET", "POST"])
def list_pretrips():
    """
    Lists all pretrips for the driver.
    - GET: Show the list
    - POST: (If needed) handle form submissions (filters, etc.)
    """
    # ... (retrieve and display pretrip data)
    return render_template("list_pretrips.html")

@driver_bp.route("/driver_logs", methods=["GET", "POST"])
def driver_logs():
    """
    Displays logs related to the driver.
    """
    # ... (gather data and pass it to the template)
    return render_template("driver_logs.html")

# Add any other driver-only routes below
