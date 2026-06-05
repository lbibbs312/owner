import logging
import os
from urllib.parse import urlsplit

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import bp
from app.extensions import db, login_manager
from app.forms.auth import LoginForm, RegistrationForm
from app.models import User
from app.services.role_session import clear_role_logins, remember_role_login, restore_role_user


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@login_manager.request_loader
def load_user_for_blueprint(req):
    """Serve current_user from the role-specific session key for blueprint routes.

    This lets a driver tab and a manager tab coexist in the same browser without
    fighting over session['_user_id'].  For driver.* endpoints we read
    driver_user_id; for manager.* we read management_user_id.  Returning None
    falls through to the standard user_loader.
    """
    from flask import session as flask_session
    endpoint = req.endpoint or ""
    if endpoint.startswith("manager."):
        key = "management_user_id"
        required_role = "management"
    elif endpoint.startswith("driver."):
        key = "driver_user_id"
        required_role = "driver"
    else:
        return None
    uid = flask_session.get(key)
    if not uid:
        return None
    try:
        user = User.query.get(int(uid))
    except (TypeError, ValueError):
        return None
    if user and user.role == required_role:
        return user
    return None


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


def _safe_form_value(form, field_name):
    field = getattr(form, field_name, None)
    if not field:
        return ""
    return (field.data or "").strip()


def _log_auth_event(level, event_name, **details):
    safe_details = {
        key: value
        for key, value in details.items()
        if value not in (None, "", [], ())
    }
    safe_details["path"] = request.path
    current_app.logger.log(
        level,
        "%s %s",
        event_name,
        " ".join(f"{key}={value}" for key, value in sorted(safe_details.items())),
    )


def _flash_form_errors(form, event_name):
    if form.errors:
        _log_auth_event(
            logging.WARNING,
            event_name,
            fields=",".join(sorted(form.errors.keys())),
            role=_safe_form_value(form, "role"),
        )
        flash("CHECK REQUIRED FIELDS\nReview the highlighted fields and try again.", "danger")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return _redirect_authenticated_user()
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.role.data == "management":
            expected_pin = (os.environ.get("MANAGER_REGISTRATION_PIN") or "").strip()
            if not expected_pin:
                _log_auth_event(
                    logging.ERROR,
                    "auth.register.manager_pin_unconfigured",
                    role=form.role.data,
                    username=form.username.data,
                )
                flash("Manager self-registration is not enabled.", "danger")
                return redirect(url_for("auth.register"))
            if form.manager_pin.data != expected_pin:
                _log_auth_event(
                    logging.WARNING,
                    "auth.register.invalid_manager_pin",
                    role=form.role.data,
                    username=form.username.data,
                )
                flash("Invalid Manager PIN!", "danger")
                return redirect(url_for("auth.register"))
        existing = User.query.filter(
            (User.email == form.email.data)
            | (User.username == form.username.data)
            | (User.email == form.username.data)
            | (User.username == form.email.data)
        ).first()
        if existing:
            _log_auth_event(
                logging.WARNING,
                "auth.register.duplicate_identity",
                role=form.role.data,
                username=form.username.data,
            )
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
            _log_auth_event(
                logging.INFO,
                "auth.register.success",
                role=user.role,
                user_id=user.id,
                username=user.username,
            )
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("auth.login"))
    elif request.method == "POST":
        _flash_form_errors(form, "auth.register.validation_failed")
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
            # Wrong role — fall through silently so the login form is shown,
            # allowing the user to log in as the required role in this tab.
        elif next_url:
            return redirect(next_url)
        else:
            return _redirect_authenticated_user()
    form = LoginForm()
    if form.validate_on_submit():
        name_or_email = form.login_name.data
        matching_users = User.query.filter(
            (User.username == name_or_email) | (User.email == name_or_email)
        ).all()
        user = next(
            (
                candidate
                for candidate in matching_users
                if candidate.password_hash
                if candidate.check_password(form.password.data)
            ),
            None,
        )
        if user:
            login_user(user, remember=form.remember.data)
            remember_role_login(user)
            _log_auth_event(
                logging.INFO,
                "auth.login.success",
                role=user.role,
                user_id=user.id,
                username=user.username,
            )
            flash("SIGNED IN\nWelcome back to MoveDefense.", "success")
            if required_role and user.role != required_role:
                _log_auth_event(
                    logging.WARNING,
                    "auth.login.role_mismatch",
                    actual_role=user.role,
                    required_role=required_role,
                    user_id=user.id,
                )
                flash(
                    f"{_role_label(required_role).title()} credentials are required for that area.",
                    "warning",
                )
                return _redirect_user_home(user)
            if next_url:
                return redirect(next_url)
            return _redirect_user_home(user)
        else:
            _log_auth_event(
                logging.WARNING,
                "auth.login.invalid_credentials",
                login_name_present=bool(name_or_email),
                required_role=required_role,
            )
            flash("Invalid credentials.", "danger")
    elif request.method == "POST":
        _flash_form_errors(form, "auth.login.validation_failed")
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    clear_role_logins()
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("public.welcome"))
