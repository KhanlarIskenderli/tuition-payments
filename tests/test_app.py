import re
from datetime import date

import pytest

from app import create_app
from app.db import create_student, create_user, init_db


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "SECRET_KEY": "test",
        "TODAY": date(2026, 9, 11),
    })
    with app.app_context():
        init_db()
        create_user("tester", "secret-pass-1")
        create_student("Тестов Тест", "ИТ-21", "Д-1", 180_000_00, 2, date(2026, 9, 1))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)


def login(client, password="secret-pass-1"):
    return client.post("/login", data={"username": "tester", "password": password,
                                       "csrf_token": csrf(client)})


def test_requires_login(client):
    resp = client.get("/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    assert client.get("/api/students/1/summary").status_code == 302


def test_wrong_password(client):
    resp = login(client, "wrong")
    assert "Неверный логин или пароль" in resp.get_data(as_text=True)


def test_post_without_csrf_is_rejected(client):
    resp = client.post("/login", data={"username": "tester", "password": "secret-pass-1"})
    assert resp.status_code == 400


def test_open_redirect_blocked(client):
    token = csrf(client)
    resp = client.post("/login?next=//evil.example", data={
        "username": "tester", "password": "secret-pass-1", "csrf_token": token})
    assert resp.headers["Location"] == "/"


def test_payment_flow(client):
    login(client)
    token = csrf(client, "/students/1")
    resp = client.post("/students/1/payments", data={
        "amount": "50 000", "paid_on": "2026-09-05", "method": "СБП", "csrf_token": token,
    }, follow_redirects=True)
    assert "Оплата зарегистрирована" in resp.get_data(as_text=True)

    data = client.get("/api/students/1/summary").get_json()
    assert data["paid"] == 50_000_00
    assert data["debt"] == 130_000_00
    assert data["overdue"] == 40_000_00
    assert data["schedule"][0]["status"] == "Просрочен"
    assert data["schedule"][0]["overdue_days"] == 10


@pytest.mark.parametrize("form, message", [
    ({"amount": "200 000", "paid_on": "2026-09-05", "method": "СБП"}, "превышает остаток"),
    ({"amount": "100", "paid_on": "2026-12-01", "method": "СБП"}, "в будущем"),
    ({"amount": "-1", "paid_on": "2026-09-05", "method": "СБП"}, "больше нуля"),
    ({"amount": "100", "paid_on": "2026-09-05", "method": "Биткоин"}, "способ оплаты"),
])
def test_payment_validation(client, form, message):
    login(client)
    form["csrf_token"] = csrf(client, "/students/1")
    resp = client.post("/students/1/payments", data=form, follow_redirects=True)
    assert message in resp.get_data(as_text=True)
    assert client.get("/api/students/1/summary").get_json()["paid"] == 0


def test_duplicate_contract(client):
    login(client)
    token = csrf(client, "/students/new")
    resp = client.post("/students/new", data={
        "full_name": "Другой", "group_name": "ИТ-21", "contract_number": "Д-1",
        "total_cost": "100000", "parts": "2", "first_due": "2026-09-01", "csrf_token": token,
    }, follow_redirects=True)
    assert "уже существует" in resp.get_data(as_text=True)


def test_search_is_safe_from_sql_injection(client):
    login(client)
    resp = client.get("/?q=' OR 1=1 --")
    assert resp.status_code == 200
    assert "Тестов Тест" not in resp.get_data(as_text=True)
