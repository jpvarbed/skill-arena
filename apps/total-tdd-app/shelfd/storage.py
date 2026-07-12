from __future__ import annotations

from dataclasses import dataclass, field

from .models import AuditEvent, Book, Loan, Member


@dataclass
class LibraryState:
    books: dict[str, Book] = field(default_factory=dict)
    members: dict[str, Member] = field(default_factory=dict)
    loans: dict[str, Loan] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)
    next_book: int = 1
    next_member: int = 1
    next_loan: int = 1

    def next_book_id(self) -> str:
        value = f"B{self.next_book:04d}"
        self.next_book += 1
        return value

    def next_member_id(self) -> str:
        value = f"M{self.next_member:04d}"
        self.next_member += 1
        return value

    def next_loan_id(self) -> str:
        value = f"L{self.next_loan:04d}"
        self.next_loan += 1
        return value

    def active_loans_for_member(self, member_id: str) -> list[Loan]:
        return [
            loan
            for loan in self.loans.values()
            if loan.member_id == member_id and loan.active
        ]

    def active_loans_for_book(self, book_id: str) -> list[Loan]:
        return [
            loan
            for loan in self.loans.values()
            if loan.book_id == book_id and loan.active
        ]

    def clone_summary(self) -> dict[str, int]:
        return {
            "books": len(self.books),
            "members": len(self.members),
            "active_loans": sum(1 for loan in self.loans.values() if loan.active),
            "audit_events": len(self.audit),
        }
