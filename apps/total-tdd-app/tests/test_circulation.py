from datetime import date, timedelta

import pytest


def test_checkout_reduces_available_copy(seeded):
    app = seeded["app"]

    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])

    assert loan.id == "L0001"
    assert seeded["fiction"].available == 1


def test_checkout_uses_default_due_date(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])

    assert loan.due == date(2026, 1, 24)


def test_checkout_accepts_iso_due_date_through_api(seeded):
    app = seeded["app"]

    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out="2026-01-10", due="2026-01-20")

    assert loan.due == date(2026, 1, 20)


def test_checkout_rejects_due_before_checkout(seeded):
    app = seeded["app"]

    with pytest.raises(ValueError, match="due date"):
        app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=date(2026, 1, 10), due=date(2026, 1, 9))


def test_checkout_rejects_unavailable_book(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    with pytest.raises(ValueError, match="available"):
        app.checkout(seeded["history"].id, seeded["grace"].id, checked_out=seeded["today"])


def test_return_restores_available_copy(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])

    result = app.return_book(loan.id, returned_on=seeded["today"] + timedelta(days=5))

    assert result["late_fee_cents"] == 0
    assert seeded["fiction"].available == 2


def test_late_fee_charges_each_late_day(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=date(2026, 1, 1), due=date(2026, 1, 10))

    result = app.return_book(loan.id, returned_on=date(2026, 1, 13))

    assert result["late_fee_cents"] == 75


def test_return_rejects_double_return(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.return_book(loan.id, returned_on=seeded["today"])

    with pytest.raises(ValueError, match="already returned"):
        app.return_book(loan.id, returned_on=seeded["today"])


def test_renew_extends_due_date(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])

    renewed = app.renew(loan.id, renewed_on=seeded["today"], days=7)

    assert renewed.due == date(2026, 1, 31)
    assert renewed.renewals == 1


def test_reserved_book_cannot_be_renewed_to_avoid_late_fee(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=date(2026, 1, 1), due=date(2026, 1, 10))
    app.reserve(seeded["history"].id, seeded["grace"].id)

    with pytest.raises(ValueError, match="reservation"):
        app.renew(loan.id, renewed_on=date(2026, 1, 9), days=7)


def test_overdue_loans_are_repeatable_queries(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=date(2026, 1, 1), due=date(2026, 1, 5))

    first = app.overdue_loans(date(2026, 1, 10))
    second = app.overdue_loans(date(2026, 1, 10))

    assert [item.id for item in first] == [loan.id]
    assert [item.id for item in second] == [loan.id]


def test_active_loans_excludes_returned_items(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.return_book(loan.id, returned_on=seeded["today"])

    assert app.active_loans() == []
