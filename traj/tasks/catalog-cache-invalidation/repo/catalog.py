from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int
    active: bool = True


class Catalog:
    def __init__(self, products: Iterable[Product] = ()): 
        self._products: dict[str, Product] = {}
        self._price_cache: dict[str, int] = {}
        for product in products:
            self.upsert(product)

    def upsert(self, product: Product) -> None:
        self._validate(product)
        self._products[product.sku] = product

    def deactivate(self, sku: str) -> None:
        product = self._products[sku]
        self._products[sku] = Product(product.sku, product.name, product.price_cents, active=False)
        self._price_cache.pop(sku, None)

    def price_for(self, sku: str) -> int:
        if sku in self._price_cache:
            return self._price_cache[sku]
        product = self._products[sku]
        if not product.active:
            raise LookupError(f"inactive product: {sku}")
        self._price_cache[sku] = product.price_cents
        return product.price_cents

    def invoice_lines(self, quantities: dict[str, int]) -> list[tuple[str, int, int]]:
        lines: list[tuple[str, int, int]] = []
        for sku, quantity in sorted(quantities.items()):
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            lines.append((sku, quantity, quantity * self.price_for(sku)))
        return lines

    def total_cents(self, quantities: dict[str, int]) -> int:
        return sum(line_total for _, _, line_total in self.invoice_lines(quantities))

    def names(self) -> list[str]:
        return [product.name for product in sorted(self._products.values(), key=lambda item: item.sku) if product.active]

    def active_skus(self) -> list[str]:
        return [product.sku for product in sorted(self._products.values(), key=lambda item: item.sku) if product.active]

    def has_product(self, sku: str) -> bool:
        return sku in self._products and self._products[sku].active

    @staticmethod
    def _validate(product: Product) -> None:
        if not product.sku:
            raise ValueError("sku is required")
        if product.price_cents < 0:
            raise ValueError("price must be non-negative")
