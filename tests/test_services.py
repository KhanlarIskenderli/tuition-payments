from datetime import date

import pytest

from app.services import (STATUS_OVERDUE, STATUS_PAID, STATUS_PARTIAL, STATUS_UPCOMING,
                          add_months, allocate_payments, build_schedule, calc_penalty,
                          format_money, parse_money, summarize)


@pytest.mark.parametrize("text, expected", [
    ("100", 10000), ("1 234,50", 123450), ("0.01", 1), ("180000", 18000000),
])
def test_parse_money_ok(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1,234", "NaN", "Infinity", "1e20"])
def test_parse_money_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_money(text)


def test_format_money():
    assert format_money(123450) == "1 234,50 ₽"
    assert format_money(5) == "0,05 ₽"


def test_add_months_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 9, 1), 6) == date(2027, 3, 1)


def test_schedule_sum_equals_total_and_remainder_goes_last():
    schedule = build_schedule(100_000_01, 3, date(2026, 9, 1), step_months=4)
    assert sum(a for _, a in schedule) == 100_000_01
    assert [a for _, a in schedule] == [33_333_33, 33_333_33, 33_333_35]
    assert [d for d, _ in schedule] == [date(2026, 9, 1), date(2027, 1, 1), date(2027, 5, 1)]


@pytest.mark.parametrize("total, parts", [(0, 2), (100, 0), (100, 13), (1, 2)])
def test_schedule_invalid(total, parts):
    with pytest.raises(ValueError):
        build_schedule(total, parts, date(2026, 9, 1))


def test_penalty_is_capped():
    assert calc_penalty(100_000, 10, 0.001, 0.1) == 1_000      # 0,1 % × 10 дней = 1 %
    assert calc_penalty(100_000, 500, 0.001, 0.1) == 10_000    # не больше 10 %
    assert calc_penalty(0, 10, 0.001, 0.1) == 0


INSTALLMENTS = [(1, date(2026, 9, 1), 90_000_00), (2, date(2027, 3, 1), 90_000_00)]


def test_allocation_fifo_and_statuses():
    st = allocate_payments(INSTALLMENTS, 120_000_00, as_of=date(2026, 10, 1))
    assert (st[0].paid, st[0].status) == (90_000_00, STATUS_PAID)
    assert (st[1].paid, st[1].status) == (30_000_00, STATUS_PARTIAL)
    assert st[1].penalty == 0


def test_overdue_and_penalty():
    st = allocate_payments(INSTALLMENTS, 50_000_00, as_of=date(2026, 9, 11))
    assert st[0].status == STATUS_OVERDUE
    assert st[0].overdue_days == 10
    assert st[0].penalty == 40_000_00 * 10 // 1000            # 0,1 % в день от 40 000 ₽
    assert st[1].status == STATUS_UPCOMING


def test_summary():
    st = allocate_payments(INSTALLMENTS, 50_000_00, as_of=date(2026, 9, 11))
    s = summarize(180_000_00, 50_000_00, st)
    assert s["debt"] == 130_000_00
    assert s["overdue"] == 40_000_00
    assert s["next_due"].number == 1
