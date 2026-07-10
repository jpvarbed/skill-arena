import pytest

from pricing import LineItem, format_cents, order_total_cents, parse_discount, price_line


def test_discount_contract_uses_fractional_rates():
    assert parse_discount(" welcome10 ") == parse_discount("WELCOME10")
    assert price_line(LineItem("book", 2500, 2, "WELCOME10")) == 4500


def test_order_total_combines_discounted_lines_and_shipping():
    items = [LineItem("mug", 1200, 3, "BULK15"), LineItem("pin", 500, 2)]
    assert order_total_cents(items, shipping_cents=799) == 4859


def test_format_cents_is_stable():
    assert format_cents(4859) == "$48.59"
    assert format_cents(-25) == "-$0.25"


def test_unknown_discount_is_rejected():
    with pytest.raises(ValueError):
        price_line(LineItem("book", 1000, 1, "mystery"))
