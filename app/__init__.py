"""Учёт оплаты обучения студентов — фабрика Flask-приложения."""
import os
import secrets

from flask import Flask, abort, request, session

from .services import format_money


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "tuition.sqlite3"),
        PENALTY_RATE_PER_DAY=0.001,   # 0,1 % в день
        PENALTY_CAP_RATIO=0.1,        # не более 10 % от просроченной суммы
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        TODAY=None,                   # для тестов можно зафиксировать «сегодня»
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    from . import auth, db, views
    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)

    app.jinja_env.filters["money"] = format_money

    @app.before_request
    def csrf_protect():
        # Простая защита от CSRF: каждая форма содержит одноразовый токен сессии.
        if request.method == "POST" and not app.config.get("TESTING_SKIP_CSRF"):
            token = session.get("csrf_token")
            if not token or token != request.form.get("csrf_token"):
                abort(400, "Неверный CSRF-токен")

    @app.context_processor
    def inject_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return {"csrf_token": session["csrf_token"]}

    return app
