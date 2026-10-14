"""Подключение к SQLite и служебные команды CLI."""
import sqlite3
from datetime import date

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from .services import build_schedule


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


def create_user(username, password):
    db = get_db()
    db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    db.commit()


def create_student(full_name, group_name, contract_number, total_cost, parts, first_due):
    """Создаёт студента и сразу формирует график платежей (в одной транзакции)."""
    schedule = build_schedule(total_cost, parts, first_due, step_months=12 // parts)
    db = get_db()
    with db:
        cur = db.execute(
            "INSERT INTO students (full_name, group_name, contract_number, total_cost)"
            " VALUES (?, ?, ?, ?)",
            (full_name, group_name, contract_number, total_cost),
        )
        student_id = cur.lastrowid
        db.executemany(
            "INSERT INTO installments (student_id, number, due_date, amount) VALUES (?, ?, ?, ?)",
            [(student_id, i + 1, due.isoformat(), amount) for i, (due, amount) in enumerate(schedule)],
        )
    return student_id


@click.command("init-db")
def init_db_command():
    """Создать (пересоздать) таблицы базы данных."""
    init_db()
    click.echo("База данных создана.")


@click.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin_command(username, password):
    """Создать пользователя-администратора."""
    if len(password) < 8:
        raise click.BadParameter("Пароль должен быть не короче 8 символов")
    create_user(username, password)
    click.echo(f"Пользователь {username} создан.")


@click.command("seed-demo")
def seed_demo_command():
    """Заполнить базу демонстрационными данными (только для показа!)."""
    init_db()
    create_user("admin", "admin12345")
    db = get_db()
    today = date.today()
    year = today.year if today.month >= 9 else today.year - 1
    demo = [
        ("Иванов Иван Иванович", "ИТ-21", "Д-2021-0457", 180_000_00, 2, date(year, 9, 1)),
        ("Петрова Анна Сергеевна", "ИТ-21", "Д-2021-0512", 180_000_00, 4, date(year, 9, 1)),
        ("Сидоров Павел Олегович", "ИТ-22", "Д-2022-0103", 165_000_00, 2, date(year, 9, 1)),
        ("Кузнецова Мария Андреевна", "МОАИС-23", "Д-2023-0078", 150_000_00, 1, date(year, 9, 1)),
    ]
    ids = [create_student(*row) for row in demo]
    payments = [
        (ids[0], 90_000_00, date(year, 8, 25), "Банковская карта"),
        (ids[1], 45_000_00, date(year, 8, 30), "Банковский перевод"),
        (ids[2], 50_000_00, date(year, 9, 10), "Банковская карта"),
        (ids[3], 150_000_00, date(year, 8, 20), "Банковский перевод"),
    ]
    with db:
        db.executemany(
            "INSERT INTO payments (student_id, amount, paid_on, method, created_by)"
            " VALUES (?, ?, ?, ?, 1)",
            [(sid, amount, d.isoformat(), method) for sid, amount, d, method in payments],
        )
    click.echo("Демо-данные загружены. Вход: admin / admin12345")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(seed_demo_command)
