from __future__ import annotations

import csv
from io import StringIO

from . import audit
from .catalog import add_book
from .members import get_member
from .models import Loan, parse_date
from .storage import LibraryState


BOOK_COLUMNS = ["id", "title", "author", "year", "genres", "copies", "available"]
LOAN_COLUMNS = ["id", "book_id", "member_id", "checked_out", "due", "returned", "renewals"]


def export_books_csv(state: LibraryState) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=BOOK_COLUMNS)
    writer.writeheader()
    for book in sorted(state.books.values(), key=lambda item: item.id):
        writer.writerow({
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "year": book.year,
            "genres": "|".join(book.genres),
            "copies": book.copies,
            "available": book.available,
        })
    return out.getvalue()


def import_books_csv(state: LibraryState, text: str) -> list[str]:
    reader = csv.DictReader(StringIO(text))
    created: list[str] = []
    for row in reader:
        book = add_book(
            state,
            row["title"],
            row["author"],
            year=int(row["year"]),
            genres=row.get("genres", "").split("|"),
            copies=int(row["copies"]),
        )
        book.available = int(row.get("available") or book.copies)
        created.append(book.id)
    audit.record(state, "import.books", detail=str(len(created)))
    return created


def export_loans_csv(state: LibraryState) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=LOAN_COLUMNS)
    writer.writeheader()
    for loan in sorted(state.loans.values(), key=lambda item: item.id):
        writer.writerow(loan.to_dict())
    return out.getvalue()


def import_loans_csv(state: LibraryState, text: str) -> list[str]:
    reader = csv.DictReader(StringIO(text))
    imported: list[str] = []
    for row in reader:
        get_member(state, row["member_id"])
        book = state.books[row["book_id"]]
        loan = Loan(
            id=row.get("id") or state.next_loan_id(),
            book_id=book.id,
            member_id=row["member_id"],
            checked_out=parse_date(row["checked_out"]),
            due=parse_date(row["due"]),
            returned=parse_date(row["returned"]) if row.get("returned") else None,
            renewals=int(row.get("renewals") or 0),
        )
        state.loans[loan.id] = loan
        if loan.active:
            book.available -= 1
        imported.append(loan.id)
    audit.record(state, "import.loans", detail=str(len(imported)))
    return imported
