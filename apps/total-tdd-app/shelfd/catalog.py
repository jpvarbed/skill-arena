from __future__ import annotations

from . import audit
from .models import Book
from .storage import LibraryState


def add_book(
    state: LibraryState,
    title: str,
    author: str,
    *,
    year: int,
    genres: list[str] | tuple[str, ...],
    copies: int = 1,
    metadata: dict[str, str] | None = None,
) -> Book:
    if not title.strip():
        raise ValueError("title is required")
    if not author.strip():
        raise ValueError("author is required")
    copies = int(copies)
    if copies <= 0:
        raise ValueError("copies must be positive")
    book = Book(
        id=state.next_book_id(),
        title=title.strip(),
        author=author.strip(),
        year=int(year),
        genres=tuple(sorted({genre.strip().lower() for genre in genres if genre.strip()})),
        copies=copies,
        available=copies,
        metadata=dict(metadata or {}),
    )
    state.books[book.id] = book
    audit.record(state, "book.add", book_id=book.id, detail=book.title)
    return book


def update_book(state: LibraryState, book_id: str, **changes) -> Book:
    book = get_book(state, book_id)
    if "title" in changes:
        title = str(changes["title"]).strip()
        if not title:
            raise ValueError("title is required")
        book.title = title
    if "author" in changes:
        author = str(changes["author"]).strip()
        if not author:
            raise ValueError("author is required")
        book.author = author
    if "year" in changes:
        book.year = int(changes["year"])
    if "genres" in changes:
        book.genres = tuple(sorted({str(g).strip().lower() for g in changes["genres"] if str(g).strip()}))
    if "metadata" in changes:
        book.metadata.update({str(k): str(v) for k, v in changes["metadata"].items()})
    if "copies" in changes:
        new_copies = int(changes["copies"])
        checked_out = book.copies - book.available
        if new_copies < checked_out:
            raise ValueError("copies cannot be less than active loans")
        book.available = new_copies - checked_out
        book.copies = new_copies
    audit.record(state, "book.update", book_id=book.id, detail=book.title)
    return book


def delete_book(state: LibraryState, book_id: str) -> None:
    book = get_book(state, book_id)
    if state.active_loans_for_book(book_id):
        raise ValueError("cannot delete a checked-out book")
    del state.books[book.id]
    audit.record(state, "book.delete", book_id=book.id, detail=book.title)


def get_book(state: LibraryState, book_id: str) -> Book:
    try:
        return state.books[book_id]
    except KeyError:
        raise KeyError(f"unknown book {book_id}") from None


def search_books(
    state: LibraryState,
    *,
    text: str | None = None,
    author: str | None = None,
    genre: str | None = None,
    available_only: bool = False,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[Book]:
    books = list(state.books.values())
    if text:
        needle = text.casefold()
        books = [
            book for book in books
            if needle in book.title.casefold() or needle in book.author.casefold()
        ]
    if author:
        books = [book for book in books if author in book.author]
    if genre:
        wanted = genre.strip().lower()
        books = [book for book in books if wanted in book.genres]
    if available_only:
        books = [book for book in books if book.available > 0]
    if year_min is not None:
        books = [book for book in books if book.year >= int(year_min)]
    if year_max is not None:
        books = [book for book in books if book.year <= int(year_max)]
    return sorted(books, key=lambda book: (book.title.casefold(), book.id))


def inventory_counts(state: LibraryState) -> dict[str, int]:
    return {
        "titles": len(state.books),
        "copies": sum(book.copies for book in state.books.values()),
        "available": sum(book.available for book in state.books.values()),
        "reserved": sum(len(book.reservations) for book in state.books.values()),
    }
