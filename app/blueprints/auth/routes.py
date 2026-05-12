import os

from flask import flash, redirect, render_template, url_for
from flask_login import login_required, login_user, logout_user

from app.blueprints.auth import bp
from app.extensions import db, login_manager
from app.forms.auth import LoginForm, RegistrationForm
from app.models import User


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@bp.route("/register", methods=["GET", "POST"])
def register():
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
    form = LoginForm()
    if form.validate_on_submit():
        name_or_email = form.login_name.data
        user = User.query.filter(
            (User.username == name_or_email) | (User.email == name_or_email)
        ).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash("Logged in!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("public.welcome"))
