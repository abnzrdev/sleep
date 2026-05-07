from flask import Blueprint, Response, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from .i18n import t, translate_error
from .models import User, db

auth_bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])


class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=2, max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


def wants_fragment() -> bool:
    return request.headers.get("HX-Request") == "true"


def auth_feedback(message: str, is_error: bool = True) -> Response:
    tone = "#b42318" if is_error else "#127a43"
    html = (
        f'<div class="rounded-[16px] border px-4 py-3 text-sm" '
        f'style="border-color: {tone}33; color: {tone}; background: {tone}0a;">'
        f"{escape(message)}</div>"
    )
    return make_response(html, 400 if is_error else 200)


def form_error_summary(form: FlaskForm) -> str:
    for errors in form.errors.values():
        if errors:
            return translate_error(errors[0])
    return t("errors.check_form")


def translate_form_errors(form: FlaskForm) -> None:
    for field_errors in form.errors.values():
        for index, message in enumerate(list(field_errors)):
            field_errors[index] = translate_error(message)


def render_auth_form(template: str, form: FlaskForm, error: str | None = None, status: int = 200):
    response = render_template(template, form=form, error=error)
    return response if status == 200 else (response, status)


def redirect_for_htmx(endpoint: str) -> Response:
    response = make_response("", 204)
    response.headers["HX-Redirect"] = url_for(endpoint)
    return response


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_page"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            if wants_fragment():
                return redirect_for_htmx("dashboard_page")
            return redirect(url_for("dashboard_page"))
        message = t("errors.invalid_credentials")
        form.password.errors.append(message)
        if wants_fragment():
            return render_auth_form("auth/_login_form.html", form, status=400)
        return render_template("auth/login.html", form=form, error=message, active_page="login"), 400

    if request.method == "POST":
        translate_form_errors(form)
        message = form_error_summary(form)
        if wants_fragment():
            return render_auth_form("auth/_login_form.html", form, error=message, status=400)
        return render_template("auth/login.html", form=form, error=message, active_page="login"), 400

    return render_template("auth/login.html", form=form, active_page="login")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_page"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            message = t("errors.email_exists")
            form.email.errors.append(message)
            if wants_fragment():
                return render_auth_form("auth/_register_form.html", form, status=400)
            return render_template("auth/register.html", form=form, error=message, active_page="register"), 400

        user = User(
            name=form.name.data.strip(),
            email=email,
            password_hash=generate_password_hash(form.password.data),
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        if wants_fragment():
            return redirect_for_htmx("dashboard_page")
        return redirect(url_for("dashboard_page"))

    if request.method == "POST":
        translate_form_errors(form)
        message = form_error_summary(form)
        if wants_fragment():
            return render_auth_form("auth/_register_form.html", form, error=message, status=400)
        return render_template("auth/register.html", form=form, error=message, active_page="register"), 400

    return render_template("auth/register.html", form=form, active_page="register")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    if wants_fragment():
        return redirect_for_htmx("home_page")
    return redirect(url_for("home_page"))
