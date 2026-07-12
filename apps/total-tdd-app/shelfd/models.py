from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


def parse_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"expected date or ISO date string, got {type(value).__name__}")


@dataclass
class Book:
    id: str
    title: str
    author: str
    year: int
    genres: tuple[str, ...]
    copies: int
    available: int
    metadata: dict[str, str] = field(default_factory=dict)
    reservations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "genres": list(self.genres),
            "copies": self.copies,
            "available": self.available,
            "metadata": dict(self.metadata),
            "reservations": list(self.reservations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Book":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            author=str(data["author"]),
            year=int(data["year"]),
            genres=tuple(str(item).lower() for item in data.get("genres", ())),
            copies=int(data["copies"]),
            available=int(data.get("available", data["copies"])),
            metadata={str(k): str(v) for k, v in data.get("metadata", {}).items()},
            reservations=[str(item) for item in data.get("reservations", [])],
        )


@dataclass
class Member:
    id: str
    name: str
    email: str
    active: bool = True
    max_loans: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "active": self.active,
            "max_loans": self.max_loans,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Member":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            email=str(data["email"]),
            active=bool(data.get("active", True)),
            max_loans=int(data.get("max_loans", 3)),
        )


@dataclass
class Loan:
    id: str
    book_id: str
    member_id: str
    checked_out: date
    due: date
    returned: date | None = None
    renewals: int = 0

    @property
    def active(self) -> bool:
        return self.returned is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "member_id": self.member_id,
            "checked_out": self.checked_out.isoformat(),
            "due": self.due.isoformat(),
            "returned": self.returned.isoformat() if self.returned else "",
            "renewals": self.renewals,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Loan":
        returned = data.get("returned") or None
        return cls(
            id=str(data["id"]),
            book_id=str(data["book_id"]),
            member_id=str(data["member_id"]),
            checked_out=parse_date(data["checked_out"]),
            due=parse_date(data["due"]),
            returned=parse_date(returned) if returned else None,
            renewals=int(data.get("renewals", 0)),
        )


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    at: datetime
    action: str
    book_id: str | None = None
    member_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "sequence": self.sequence,
            "at": self.at.isoformat(timespec="seconds"),
            "action": self.action,
            "book_id": self.book_id,
            "member_id": self.member_id,
            "detail": self.detail,
        }
