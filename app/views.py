"""Основные страницы: студенты, карточка договора, оплаты, отчёт, JSON API."""
import sqlite3
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .auth import login_required
from .db import create_student, get_db
from .services import allocate_payments, parse_money, summarize

bp = Blueprint("views", __name__)

PAYMENT_METHODS = ("Банковская карта", "Банковский перевод", "СБП", "Наличные (касса)")


def today() -> date:
    fixed = current_app.config.get("TODAY")
    return fixed or date.today()


def load_student(student_id):
    """Студент + статусы платежей по графику + итоги."""
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        abort(404, "Студент не найден")
    installments = [
        (row["number"], date.fromisoformat(row["due_date"]), row["amount"])
        for row in db.execute(
            "SELECT number, due_date, amount FROM installments WHERE student_id = ? ORDER BY due_date, number",
            (student_id,),
        )
    ]
    total_paid = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE student_id = ?", (student_id,)
    ).fetchone()[0]
    statuses = allocate_payments(
        installments, total_paid, today(),
        current_app.config["PENALTY_RATE_PER_DAY"], current_app.config["PENALTY_CAP_RATIO"],
    )
    return student, statuses, summarize(student["total_cost"], total_paid, statuses)


@bp.route("/")
@login_required
def students():
    q = request.args.get("q", "").strip()
    sql = "SELECT id FROM students"
    params = ()
    if q:
        # Параметризованный запрос — защита от SQL-инъекций.
        sql += " WHERE full_name LIKE ? OR contract_number LIKE ? OR group_name LIKE ?"
        like = f"%{q}%"
        params = (like, like, like)
    sql += " ORDER BY full_name"
    rows = [load_student(r["id"]) for r in get_db().execute(sql, params)]
    return render_template("students.html", rows=rows, q=q)


@bp.route("/students/new", methods=("GET", "POST"))
@login_required
def new_student():
    form = request.form
    if request.method == "POST":
        errors = []
        full_name = form.get("full_name", "").strip()
        group_name = form.get("group_name", "").strip()
        contract = form.get("contract_number", "").strip()
        if not full_name or len(full_name) > 200:
            errors.append("Укажите ФИО (до 200 символов)")
        if not group_name or len(group_name) > 50:
            errors.append("Укажите группу")
        if not contract or len(contract) > 50:
            errors.append("Укажите номер договора")
        try:
            total = parse_money(form.get("total_cost"))
        except ValueError as e:
            errors.append(f"Стоимость: {e}")
        try:
            parts = int(form.get("parts", "0"))
            first_due = date.fromisoformat(form.get("first_due", ""))
        except ValueError:
            errors.append("Проверьте количество платежей и дату первого платежа")
        if not errors:
            try:
                student_id = create_student(full_name, group_name, contract, total, parts, first_due)
            except sqlite3.IntegrityError:
                errors.append("Договор с таким номером уже существует")
            except ValueError as e:
                errors.append(str(e))
            else:
                flash("Студент добавлен, график платежей сформирован", "success")
                return redirect(url_for("views.student", student_id=student_id))
        for e in errors:
            flash(e, "error")
    return render_template("student_form.html", form=form)


@bp.route("/students/<int:student_id>")
@login_required
def student(student_id):
    student, statuses, summary = load_student(student_id)
    payments = get_db().execute(
        "SELECT p.*, u.username FROM payments p LEFT JOIN users u ON u.id = p.created_by"
        " WHERE p.student_id = ? ORDER BY p.paid_on DESC, p.id DESC",
        (student_id,),
    ).fetchall()
    return render_template(
        "student.html", student=student, statuses=statuses, summary=summary,
        payments=payments, methods=PAYMENT_METHODS, today=today().isoformat(),
    )


@bp.route("/students/<int:student_id>/payments", methods=("POST",))
@login_required
def add_payment(student_id):
    _student, _statuses, summary = load_student(student_id)
    form = request.form
    try:
        amount = parse_money(form.get("amount"))
        paid_on = date.fromisoformat(form.get("paid_on", ""))
        method = form.get("method", "")
        if method not in PAYMENT_METHODS:
            raise ValueError("Выберите способ оплаты")
        if paid_on > today():
            raise ValueError("Дата оплаты не может быть в будущем")
        if amount > summary["debt"]:
            raise ValueError("Сумма превышает остаток задолженности по договору")
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("views.student", student_id=student_id))

    db = get_db()
    with db:
        db.execute(
            "INSERT INTO payments (student_id, amount, paid_on, method, comment, created_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, amount, paid_on.isoformat(), method,
             form.get("comment", "").strip()[:500] or None, g.user["id"]),
        )
    flash("Оплата зарегистрирована", "success")
    return redirect(url_for("views.student", student_id=student_id))


@bp.route("/report")
@login_required
def report():
    rows = [load_student(r["id"]) for r in get_db().execute("SELECT id FROM students")]
    totals = {
        key: sum(s[key] for _, _, s in rows)
        for key in ("total_cost", "paid", "debt", "overdue", "penalty")
    }
    debtors = sorted((r for r in rows if r[2]["overdue"] > 0), key=lambda r: -r[2]["overdue"])
    return render_template("report.html", totals=totals, debtors=debtors, count=len(rows), today=today())


@bp.route("/api/students/<int:student_id>/summary")
@login_required
def api_summary(student_id):
    """JSON для интеграции с другими системами (личный кабинет, 1С и т. п.)."""
    student, statuses, summary = load_student(student_id)
    return jsonify({
        "student": {
            "id": student["id"],
            "full_name": student["full_name"],
            "group": student["group_name"],
            "contract_number": student["contract_number"],
        },
        "currency": "RUB",
        "amounts_in": "kopecks",
        "total_cost": summary["total_cost"],
        "paid": summary["paid"],
        "debt": summary["debt"],
        "overdue": summary["overdue"],
        "penalty": summary["penalty"],
        "schedule": [
            {"number": s.number, "due_date": s.due_date.isoformat(), "amount": s.amount,
             "paid": s.paid, "status": s.status, "overdue_days": s.overdue_days, "penalty": s.penalty}
            for s in statuses
        ],
    })
