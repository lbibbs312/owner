import os
from urllib.parse import urlsplit

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import bp
from app.extensions import db, login_manager
from app.forms.auth import LoginForm, RegistrationForm
from app.models import User
from app.services.role_session import clear_role_logins, remember_role_login, restore_role_user


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _redirect_authenticated_user():
    if current_user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return redirect(url_for("driver.dashboard"))


def _redirect_user_home(user):
    if user.role == "management":
        return redirect(url_for("manager.manager_dashboard"))
    return redirect(url_for("driver.dashboard"))


def _safe_next_url(next_url):
    if not next_url:
        return None
    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return next_url


def _role_label(role):
    return "manager" if role == "management" else "driver"


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return _redirect_authenticated_user()
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.role.data == "management":
            expected_pin = os.environ.get("MANAGER_REGISTRATION_PIN")
            if not expected_pin or form.manager_pin.data != expected_pin:
                flash("Invalid Manager PIN!", "danger")
                return redirect(url_for("auth.register"))
        existing = User.query.filter(
            (User.email == form.email.data) | (User.username == form.username.data)
        ).first()
        if existing:
            flash("User already exists with that email or username.", "danger")
        else:
            user = User(
                username=form.username.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                employee_id=form.employee_id.data,
                department=form.department.data,
                email=form.email.data,
                role=form.role.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    required_role = request.args.get("required_role")
    if required_role not in {"driver", "management"}:
        required_role = None
    next_url = _safe_next_url(request.args.get("next"))
    if current_user.is_authenticated:
        if required_role:
            if current_user.role == required_role or restore_role_user(required_role):
                if next_url:
                    return redirect(next_url)
                return _redirect_authenticated_user()
            flash(f"{_role_label(required_role).title()} credentials required.", "warning")
        elif next_url:
            return redirect(next_url)
        else:
            return _redirect_authenticated_user()
    form = LoginForm()
    if form.validate_on_submit():
        name_or_email = form.login_name.data
        user = User.query.filter(
            (User.username == name_or_email) | (User.email == name_or_email)
        ).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            remember_role_login(user)
            flash("Logged in!", "success")
            if required_role and user.role != required_role:
                flash(
                    f"{_role_label(required_role).title()} credentials are required for that area.",
                    "warning",
                )
                return _redirect_user_home(user)
            if next_url:
                return redirect(next_url)
            return _redirect_user_home(user)
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    clear_role_logins()
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("public.welcome"))
