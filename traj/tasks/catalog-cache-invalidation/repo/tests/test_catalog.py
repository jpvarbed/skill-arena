import pytest

from catalog import Catalog, Product


def test_updated_price_invalidates_cached_lookup():
    catalog = Catalog([Product("tea", "Tea", 500)])
    assert catalog.price_for("tea") == 500
    catalog.upsert(Product("tea", "Tea", 650))
    assert catalog.price_for("tea") == 650
    assert catalog.total_cents({"tea": 2}) == 1300


def test_deactivated_product_cannot_be_priced():
    catalog = Catalog([Product("tea", "Tea", 500)])
    catalog.deactivate("tea")
    with pytest.raises(LookupError):
        catalog.price_for("tea")


def test_invoice_lines_are_sorted_by_sku():
    catalog = Catalog([Product("b", "B", 200), Product("a", "A", 100)])
    assert catalog.invoice_lines({"b": 2, "a": 3}) == [("a", 3, 300), ("b", 2, 400)]


def test_invalid_product_is_rejected():
    with pytest.raises(ValueError):
        Catalog([Product("bad", "Bad", -1)])
