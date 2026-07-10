from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


@dataclass(frozen=True)
class LineItem:
    sku: str
    unit_price_cents: int
    quantity: int
    discount_code: str | None = None


DISCOUNTS = {
    "WELCOME10": Decimal("0.10"),
    "BULK15": Decimal("0.15"),
    "CLEARANCE25": Decimal("0.25"),
}


def parse_discount(code: str | None) -> Decimal:
    """Return a fractional discount rate such as Decimal('0.10')."""
    if code is None or not str(code).strip():
        return Decimal("0")
    normalized = str(code).strip().upper()
    if normalized not in DISCOUNTS:
        raise ValueError(f"unknown discount code: {code}")
    return DISCOUNTS[normalized]


def line_subtotal_cents(item: LineItem) -> int:
    if item.quantity <= 0:
        raise ValueError("quantity must be positive")
    if item.unit_price_cents < 0:
        raise ValueError("unit price must be non-negative")
    return item.unit_price_cents * item.quantity


def apply_discount_cents(subtotal_cents: int, discount_rate: Decimal) -> int:
    if discount_rate < 0 or discount_rate >= 1:
        raise ValueError("discount rate must be between 0 and 1")
    discount_multiplier = Decimal("1") - (discount_rate / Decimal("100"))
    total = Decimal(subtotal_cents) * discount_multiplier
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def price_line(item: LineItem) -> int:
    return apply_discount_cents(line_subtotal_cents(item), parse_discount(item.discount_code))


def order_total_cents(items: Iterable[LineItem], shipping_cents: int = 0) -> int:
    total = sum(price_line(item) for item in items)
    if shipping_cents < 0:
        raise ValueError("shipping must be non-negative")
    return total + shipping_cents


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"
