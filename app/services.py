"""Расчётная логика: деньги, график платежей, распределение оплат, пени.

Все суммы хранятся и считаются в копейках (int), чтобы исключить
ошибки округления чисел с плавающей точкой.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

STATUS_PAID = "Оплачен"
STATUS_PARTIAL = "Оплачен частично"
STATUS_OVERDUE = "Просрочен"
STATUS_UPCOMING = "Ожидается"

MAX_AMOUNT = 100_000_000_00  # 100 млн ₽ в копейках — защита от опечаток


def parse_money(text: str) -> int:
    """Преобразует строку вида '1 234,50' в копейки (123450)."""
    if text is None:
        raise ValueError("Сумма не указана")
    cleaned = str(text).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("Некорректный формат суммы") from None
    if not value.is_finite():
        raise ValueError("Некорректный формат суммы")
    if value <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("Не более двух знаков после запятой")
    kopecks = int(value * 100)
    if kopecks > MAX_AMOUNT:
        raise ValueError("Слишком большая сумма")
    return kopecks


def format_money(kopecks: int) -> str:
    """123450 -> '1 234,50 ₽'."""
    sign = "-" if kopecks < 0 else ""
    rub, kop = divmod(abs(kopecks), 100)
    return f"{sign}{rub:,}".replace(",", " ") + f",{kop:02d} ₽"


def add_months(d: date, months: int) -> date:
    """Сдвигает дату на N месяцев, корректно обрабатывая конец месяца."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def build_schedule(total: int, parts: int, first_due: date, step_months: int = 6):
    """Делит стоимость обучения на равные платежи.

    Остаток от деления (копейки) добавляется к последнему платежу,
    поэтому сумма графика всегда точно равна стоимости договора.
    """
    if total <= 0:
        raise ValueError("Стоимость должна быть больше нуля")
    if not 1 <= parts <= 12:
        raise ValueError("Количество платежей — от 1 до 12")
    base = total // parts
    if base == 0:
        raise ValueError("Слишком маленькая стоимость для такого числа платежей")
    schedule = [(add_months(first_due, i * step_months), base) for i in range(parts)]
    remainder = total - base * parts
    last_due, last_amount = schedule[-1]
    schedule[-1] = (last_due, last_amount + remainder)
    return schedule


@dataclass
class InstallmentStatus:
    number: int
    due_date: date
    amount: int
    paid: int
    status: str
    overdue_days: int
    penalty: int

    @property
    def unpaid(self) -> int:
        return self.amount - self.paid


def calc_penalty(unpaid: int, overdue_days: int, rate_per_day: float, cap_ratio: float) -> int:
    """Пеня = неоплаченная сумма × ставка × дни просрочки, но не более cap_ratio от долга."""
    if unpaid <= 0 or overdue_days <= 0:
        return 0
    raw = Decimal(unpaid) * Decimal(str(rate_per_day)) * overdue_days
    cap = Decimal(unpaid) * Decimal(str(cap_ratio))
    return int(min(raw, cap).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allocate_payments(installments, total_paid: int, as_of: date,
                      rate_per_day: float = 0.001, cap_ratio: float = 0.1):
    """Распределяет поступившие оплаты по графику по принципу FIFO
    (сначала гасится самый ранний платёж) и определяет статус каждого.

    installments — список (номер, дата, сумма), отсортированный по дате.
    """
    remaining = total_paid
    result = []
    for number, due, amount in installments:
        paid = min(amount, remaining)
        remaining -= paid
        unpaid = amount - paid
        overdue_days = (as_of - due).days if unpaid > 0 and as_of > due else 0
        if unpaid == 0:
            status = STATUS_PAID
        elif overdue_days > 0:
            status = STATUS_OVERDUE
        elif paid > 0:
            status = STATUS_PARTIAL
        else:
            status = STATUS_UPCOMING
        penalty = calc_penalty(unpaid, overdue_days, rate_per_day, cap_ratio)
        result.append(InstallmentStatus(number, due, amount, paid, status, overdue_days, penalty))
    return result


def summarize(total_cost: int, total_paid: int, statuses) -> dict:
    """Итоги по договору студента."""
    return {
        "total_cost": total_cost,
        "paid": total_paid,
        "debt": total_cost - total_paid,
        "overdue": sum(s.unpaid for s in statuses if s.status == STATUS_OVERDUE),
        "penalty": sum(s.penalty for s in statuses),
        "next_due": next((s for s in statuses if s.unpaid > 0), None),
    }
