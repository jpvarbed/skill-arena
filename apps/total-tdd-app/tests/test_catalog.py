import pytest


def test_add_book_assigns_id_and_inventory(app):
    book = app.add_book("Kindred", "Octavia Butler", year=1979, genres=["Fiction"], copies=3)

    assert book.id == "B0001"
    assert app.inventory() == {"titles": 1, "copies": 3, "available": 3, "reserved": 0}


def test_add_book_rejects_empty_title(app):
    with pytest.raises(ValueError, match="title"):
        app.add_book("", "Author", year=2000, genres=["x"])


def test_update_book_changes_metadata_without_losing_copies(seeded):
    app = seeded["app"]
    book = seeded["fiction"]

    updated = app.update_book(book.id, title="Left Hand of Darkness", metadata={"shelf": "A1"})

    assert updated.title == "Left Hand of Darkness"
    assert updated.metadata["shelf"] == "A1"
    assert app.inventory()["copies"] == 4


def test_delete_book_removes_available_title(app):
    book = app.add_book("A Psalm for the Wild-Built", "Becky Chambers", year=2021, genres=["fiction"])

    app.delete_book(book.id)

    assert app.search(text="Psalm") == []


def test_delete_book_rejects_active_loan(seeded):
    app = seeded["app"]
    loan = app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    with pytest.raises(ValueError, match="checked-out"):
        app.delete_book(loan.book_id)


def test_text_search_matches_title_and_author_case_insensitively(seeded):
    app = seeded["app"]

    assert [book.title for book in app.search(text="le guin")] == ["The Left Hand of Darkness"]
    assert [book.title for book in app.search(text="ATOMIC")] == ["The Making of the Atomic Bomb"]


def test_author_filter_is_case_insensitive(seeded):
    app = seeded["app"]

    assert [book.title for book in app.search(author="ursula k. le guin")] == ["The Left Hand of Darkness"]


def test_search_filters_by_genre_availability_and_year(seeded):
    app = seeded["app"]
    app.checkout(seeded["history"].id, seeded["ada"].id, checked_out=seeded["today"])

    result = app.search(genre="history", available_only=True, year_min=1900, year_max=2020)

    assert result == []
