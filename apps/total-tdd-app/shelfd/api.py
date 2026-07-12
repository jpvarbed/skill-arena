from __future__ import annotations

from datetime import date

from . import audit, catalog, circulation, io, members
from .storage import LibraryState


class Shelfd:
    def __init__(self, state: LibraryState | None = None):
        self.state = state or LibraryState()

    def add_book(self, title: str, author: str, *, year: int, genres, copies: int = 1):
        return catalog.add_book(self.state, title, author, year=year, genres=genres, copies=copies)

    def update_book(self, book_id: str, **changes):
        return catalog.update_book(self.state, book_id, **changes)

    def delete_book(self, book_id: str):
        return catalog.delete_book(self.state, book_id)

    def search(self, **filters):
        return catalog.search_books(self.state, **filters)

    def inventory(self):
        return catalog.inventory_counts(self.state)

    def register_member(self, name: str, email: str, *, max_loans: int = 3):
        return members.register_member(self.state, name, email, max_loans=max_loans)

    def checkout(self, book_id: str, member_id: str, *, checked_out: date | str, due: date | str | None = None):
        return circulation.checkout_book(
            self.state,
            book_id,
            member_id,
            checked_out=checked_out,
            due=due,
        )

    def return_book(self, loan_id: str, *, returned_on: date | str):
        return circulation.return_book(self.state, loan_id, returned_on=returned_on)

    def renew(self, loan_id: str, *, renewed_on: date | str, days: int = circulation.DEFAULT_LOAN_DAYS):
        return circulation.renew_loan(self.state, loan_id, renewed_on=renewed_on, days=days)

    def reserve(self, book_id: str, member_id: str):
        return circulation.reserve_book(self.state, book_id, member_id)

    def cancel_reservation(self, book_id: str, member_id: str):
        return circulation.cancel_reservation(self.state, book_id, member_id)

    def active_loans(self):
        return circulation.active_loans(self.state)

    def overdue_loans(self, as_of: date | str):
        return circulation.overdue_loans(self.state, as_of)

    def export_books_csv(self):
        return io.export_books_csv(self.state)

    def import_books_csv(self, text: str):
        return io.import_books_csv(self.state, text)

    def export_loans_csv(self):
        return io.export_loans_csv(self.state)

    def import_loans_csv(self, text: str):
        return io.import_loans_csv(self.state, text)

    def audit_log(self, **filters):
        return audit.list_events(self.state, **filters)

    def summary(self):
        return self.state.clone_summary()
