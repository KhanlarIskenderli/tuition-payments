"""Аутентификация сотрудников финансового отдела."""
import functools

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        # Одинаковое сообщение для неверного логина и пароля — не раскрываем, какие логины существуют.
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль", "error")
        else:
            csrf = session.get("csrf_token")
            session.clear()  # защита от фиксации сессии
            session["user_id"] = user["id"]
            if csrf:
                session["csrf_token"] = csrf
            next_url = request.args.get("next", "")
            # Разрешаем переход только по внутренним путям (защита от open redirect).
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("views.students")
            return redirect(next_url)
    return render_template("login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
