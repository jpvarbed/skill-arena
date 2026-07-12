import json

from shelfd.cli import main


def test_audit_records_catalog_and_member_events(seeded):
    app = seeded["app"]

    assert len(app.audit_log(action="book.add")) == 3
    assert len(app.audit_log(action="member.add")) == 3


def test_audit_keeps_checkout_and_return_events_for_same_book_member(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.return_book(loan.id, returned_on=seeded["today"])

    actions = [event.action for event in app.audit_log(book_id=seeded["history"].id, member_id=seeded["ada"].id)]

    assert actions == ["loan.checkout", "loan.return"]


def test_audit_filter_by_book(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    events = app.audit_log(book_id=seeded["history"].id)

    assert events[-1].action == "loan.checkout"


def test_summary_counts_active_loans(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    assert app.summary()["active_loans"] == 1


def test_cli_add_book_prints_json(capsys):
    assert main(["add-book", "Kindred", "Octavia Butler", "--year", "1979", "--genre", "fiction"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["title"] == "Kindred"


def test_cli_summary_prints_empty_library(capsys):
    assert main(["summary"]) == 0

    assert json.loads(capsys.readouterr().out) == {"active_loans": 0, "audit_events": 0, "books": 0, "members": 0}
