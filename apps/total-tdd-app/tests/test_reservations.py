import pytest


def test_reserve_unavailable_book_returns_queue_position(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    assert app.reserve(seeded["history"].id, seeded["grace"].id) == 1
    assert seeded["history"].reservations == [seeded["grace"].id]


def test_duplicate_reservation_returns_existing_position(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.reserve(seeded["history"].id, seeded["grace"].id)

    assert app.reserve(seeded["history"].id, seeded["grace"].id) == 1
    assert seeded["history"].reservations == [seeded["grace"].id]


def test_available_book_does_not_need_reservation(seeded):
    app = seeded["app"]

    with pytest.raises(ValueError, match="available"):
        app.reserve(seeded["fiction"].id, seeded["grace"].id)


def test_reserved_book_blocks_other_member_until_returned(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.reserve(seeded["history"].id, seeded["grace"].id)
    app.return_book(loan.id, returned_on=seeded["today"])

    with pytest.raises(ValueError, match="reserved"):
        app.checkout(seeded["history"].id, seeded["linus"].id, checked_out=seeded["today"])


def test_reserved_member_consumes_reservation_on_checkout(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.reserve(seeded["history"].id, seeded["grace"].id)
    app.return_book(loan.id, returned_on=seeded["today"])

    app.checkout(seeded["history"].id, seeded["grace"].id, checked_out=seeded["today"])

    assert seeded["history"].reservations == []


def test_cancel_reservation_removes_member(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])
    app.reserve(seeded["history"].id, seeded["grace"].id)

    assert app.cancel_reservation(seeded["history"].id, seeded["grace"].id) is True
    assert seeded["history"].reservations == []
