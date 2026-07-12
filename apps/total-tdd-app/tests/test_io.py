import csv
from io import StringIO

import pytest


def test_export_books_has_stable_header(seeded):
    rows = list(csv.DictReader(StringIO(seeded["app"].export_books_csv())))

    assert rows[0].keys() == {"id", "title", "author", "year", "genres", "copies", "available"}


def test_import_books_creates_searchable_titles(app):
    text = "id,title,author,year,genres,copies,available\nx,Parable of the Sower,Octavia Butler,1993,fiction|sf,2,2\n"

    created = app.import_books_csv(text)

    assert len(created) == 1
    assert [book.title for book in app.search(text="Parable")] == ["Parable of the Sower"]


def test_export_import_books_roundtrip_counts(seeded):
    text = seeded["app"].export_books_csv()
    clone = type(seeded["app"])()

    clone.import_books_csv(text)

    assert clone.inventory()["titles"] == 3
    assert clone.inventory()["copies"] == 4


def test_export_loans_includes_returned_state(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.return_book(loan.id, returned_on=seeded["today"])

    rows = list(csv.DictReader(StringIO(app.export_loans_csv())))

    assert rows[0]["returned"] == "2026-01-10"


def test_import_loans_creates_active_loan(seeded):
    app = seeded["app"]
    text = f"id,book_id,member_id,checked_out,due,returned,renewals\nXL1,{seeded['history'].id},{seeded['ada'].id},2026-01-01,2026-01-10,,0\n"

    imported = app.import_loans_csv(text)

    assert imported == ["XL1"]
    assert seeded["history"].available == 0


def test_import_loans_rejects_unknown_member(seeded):
    app = seeded["app"]
    text = f"id,book_id,member_id,checked_out,due,returned,renewals\nXL1,{seeded['history'].id},M9999,2026-01-01,2026-01-10,,0\n"

    with pytest.raises(KeyError):
        app.import_loans_csv(text)


def test_import_loans_enforces_member_limits(seeded):
    app = seeded["app"]
    member = seeded["linus"]
    first = f"XL1,{seeded['fiction'].id},{member.id},2026-01-01,2026-01-10,,0\n"
    second = f"XL2,{seeded['history'].id},{member.id},2026-01-01,2026-01-10,,0\n"
    text = "id,book_id,member_id,checked_out,due,returned,renewals\n" + first + second

    with pytest.raises(ValueError, match="limit"):
        app.import_loans_csv(text)
