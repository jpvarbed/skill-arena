import pytest


def test_register_member_normalizes_email(app):
    member = app.register_member("Ada", "ADA@EXAMPLE.COM", max_loans=2)

    assert member.id == "M0001"
    assert member.email == "ada@example.com"
    assert member.active is True


def test_register_member_rejects_bad_email(app):
    with pytest.raises(ValueError, match="email"):
        app.register_member("Ada", "not-email")


def test_member_list_active_only(seeded):
    app = seeded["app"]
    app.state.members[seeded["linus"].id].active = False

    assert [member.id for member in app.state.members.values() if member.active] == [seeded["ada"].id, seeded["grace"].id]


def test_inactive_member_cannot_checkout(seeded):
    app = seeded["app"]
    app.state.members[seeded["ada"].id].active = False

    with pytest.raises(ValueError, match="inactive"):
        app.checkout(seeded["fiction"].id, seeded["ada"].id, checked_out=seeded["today"])


def test_member_limit_allows_exact_limit(seeded):
    app = seeded["app"]
    ada = seeded["ada"]
    b1 = app.add_book("Book 1", "Author", year=2001, genres=["x"])
    b2 = app.add_book("Book 2", "Author", year=2002, genres=["x"])
    b3 = app.add_book("Book 3", "Author", year=2003, genres=["x"])

    app.checkout(b1.id, ada.id, checked_out=seeded["today"])
    app.checkout(b2.id, ada.id, checked_out=seeded["today"])
    app.checkout(b3.id, ada.id, checked_out=seeded["today"])

    assert len(app.active_loans()) == 3


def test_member_limit_blocks_fourth_checkout(seeded):
    app = seeded["app"]
    ada = seeded["ada"]
    books = [app.add_book(f"Limit {idx}", "Author", year=2000 + idx, genres=["x"]) for idx in range(4)]
    for book in books[:3]:
        app.checkout(book.id, ada.id, checked_out=seeded["today"])

    with pytest.raises(ValueError, match="limit"):
        app.checkout(books[3].id, ada.id, checked_out=seeded["today"])
