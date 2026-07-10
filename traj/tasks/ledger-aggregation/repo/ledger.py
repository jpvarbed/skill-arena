from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class Entry:
    account: str
    category: str
    amount: Decimal
    kind: str


VALID_KINDS = {"debit", "credit"}


def _normalize_entry(raw: dict) -> Entry:
    account = str(raw["account"]).strip()
    category = str(raw.get("category") or "uncategorized").strip().lower()
    kind = str(raw.get("kind") or "debit").strip().lower()
    if not account:
        raise ValueError("account is required")
    if kind not in VALID_KINDS:
        raise ValueError("kind must be debit or credit")
    amount = Decimal(str(raw["amount"]))
    if amount < 0:
        raise ValueError("amount must be non-negative")
    return Entry(account, category, amount, kind)


def signed_amount(entry: Entry) -> Decimal:
    return entry.amount if entry.kind == "credit" else -entry.amount


def summarize(entries: Iterable[dict]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for raw in entries:
        entry = _normalize_entry(raw)
        key = f"{entry.account}:{entry.category}"
        totals[key] = signed_amount(entry)
    return totals


def account_balances(entries: Iterable[dict]) -> dict[str, Decimal]:
    balances: dict[str, Decimal] = {}
    for key, amount in summarize(entries).items():
        account, _ = key.split(":", 1)
        balances[account] = balances.get(account, Decimal("0")) + amount
    return balances


def format_amount(amount: Decimal) -> str:
    prefix = "-" if amount < 0 else ""
    value = abs(amount).quantize(Decimal("0.01"))
    return f"{prefix}${value}"


def render_summary(entries: Iterable[dict]) -> list[str]:
    return [f"{key} {format_amount(amount)}" for key, amount in sorted(summarize(entries).items())]


def non_zero_totals(entries: Iterable[dict]) -> dict[str, Decimal]:
    return {key: amount for key, amount in summarize(entries).items() if amount != 0}
