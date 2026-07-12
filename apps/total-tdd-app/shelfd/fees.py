from __future__ import annotations

from datetime import date

from .models import Loan, parse_date


DAILY_LATE_FEE_CENTS = 25


def days_late(loan: Loan, returned_on: date | str) -> int:
    returned = parse_date(returned_on)
    return max(0, (returned - loan.due).days)


def late_fee_cents(loan: Loan, returned_on: date | str, *, daily_cents: int = DAILY_LATE_FEE_CENTS) -> int:
    late_days = max(0, days_late(loan, returned_on) - 1)
    return late_days * int(daily_cents)


def format_fee(cents: int) -> str:
    dollars, pennies = divmod(int(cents), 100)
    return f"${dollars}.{pennies:02d}"
