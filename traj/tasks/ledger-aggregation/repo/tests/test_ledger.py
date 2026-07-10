from decimal import Decimal

import pytest

from ledger import account_balances, format_amount, render_summary, summarize


def test_entries_accumulate_by_account_and_category():
    entries = [
        {"account": "cash", "category": "Food", "amount": "10.50", "kind": "debit"},
        {"account": "cash", "category": "food", "amount": "2.25", "kind": "debit"},
        {"account": "cash", "category": "refund", "amount": "3.00", "kind": "credit"},
    ]
    assert summarize(entries) == {"cash:food": Decimal("-12.75"), "cash:refund": Decimal("3.00")}
    assert account_balances(entries) == {"cash": Decimal("-9.75")}


def test_render_summary_is_sorted_and_formatted():
    entries = [{"account": "b", "amount": "1"}, {"account": "a", "amount": "2", "kind": "credit"}]
    assert render_summary(entries) == ["a:uncategorized $2.00", "b:uncategorized -$1.00"]


def test_format_amount_handles_positive_and_negative():
    assert format_amount(Decimal("1.2")) == "$1.20"
    assert format_amount(Decimal("-1.2")) == "-$1.20"


def test_invalid_kind_is_rejected():
    with pytest.raises(ValueError):
        summarize([{"account": "cash", "amount": "1", "kind": "move"}])
