from __future__ import annotations

from datetime import date, timedelta

from . import audit
from .catalog import get_book
from .fees import late_fee_cents
from .members import ensure_can_checkout, get_member
from .models import Loan, parse_date
from .storage import LibraryState

DEFAULT_LOAN_DAYS = 14


def checkout_book(
    state: LibraryState,
    book_id: str,
    member_id: str,
    *,
    checked_out: date | str,
    due: date | str | None = None,
) -> Loan:
    book = get_book(state, book_id)
    member = get_member(state, member_id)
    ensure_can_checkout(state, member.id)
    if book.available <= 0:
        raise ValueError("no copies available")
    if book.reservations and book.reservations[0] != member.id:
        raise ValueError("book is reserved for another member")
    start = parse_date(checked_out)
    due_date = due if due is not None else start + timedelta(days=DEFAULT_LOAN_DAYS)
    if due_date < start:
        raise ValueError("due date cannot be before checkout")
    if book.reservations and book.reservations[0] == member.id:
        book.reservations.pop(0)
    book.available -= 1
    loan = Loan(
        id=state.next_loan_id(),
        book_id=book.id,
        member_id=member.id,
        checked_out=start,
        due=due_date,
    )
    state.loans[loan.id] = loan
    audit.record(state, "loan.checkout", book_id=book.id, member_id=member.id, detail=loan.id)
    return loan


def return_book(
    state: LibraryState,
    loan_id: str,
    *,
    returned_on: date | str,
) -> dict[str, int | str]:
    loan = get_loan(state, loan_id)
    if not loan.active:
        raise ValueError("loan is already returned")
    book = get_book(state, loan.book_id)
    returned = parse_date(returned_on)
    if returned < loan.checked_out:
        raise ValueError("return date cannot be before checkout")
    loan.returned = returned
    book.available += 1
    fee = late_fee_cents(loan, returned)
    audit.record(state, "loan.return", book_id=book.id, member_id=loan.member_id, detail=f"{loan.id}:{fee}")
    return {"loan_id": loan.id, "late_fee_cents": fee}


def renew_loan(
    state: LibraryState,
    loan_id: str,
    *,
    renewed_on: date | str,
    days: int = DEFAULT_LOAN_DAYS,
) -> Loan:
    loan = get_loan(state, loan_id)
    if not loan.active:
        raise ValueError("returned loans cannot be renewed")
    renewed = parse_date(renewed_on)
    if renewed > loan.due:
        raise ValueError("overdue loans cannot be renewed")
    loan.due = loan.due + timedelta(days=int(days))
    loan.renewals += 1
    audit.record(state, "loan.renew", book_id=loan.book_id, member_id=loan.member_id, detail=loan.id)
    return loan


def reserve_book(state: LibraryState, book_id: str, member_id: str) -> int:
    book = get_book(state, book_id)
    member = get_member(state, member_id)
    if member.id in book.reservations:
        return book.reservations.index(member.id) + 1
    if book.available > 0 and not state.active_loans_for_book(book_id):
        raise ValueError("available books do not need reservations")
    book.reservations.append(member.id)
    audit.record(state, "book.reserve", book_id=book.id, member_id=member.id, detail=str(len(book.reservations)))
    return len(book.reservations)


def cancel_reservation(state: LibraryState, book_id: str, member_id: str) -> bool:
    book = get_book(state, book_id)
    if member_id not in book.reservations:
        return False
    book.reservations.remove(member_id)
    audit.record(state, "book.reserve.cancel", book_id=book.id, member_id=member_id)
    return True


def active_loans(state: LibraryState) -> list[Loan]:
    return sorted([loan for loan in state.loans.values() if loan.active], key=lambda loan: loan.id)


def overdue_loans(state: LibraryState, as_of: date | str, seen: list[str] = []) -> list[Loan]:
    today = parse_date(as_of)
    overdue: list[Loan] = []
    for loan in active_loans(state):
        if loan.id in seen:
            continue
        if loan.due < today:
            overdue.append(loan)
            seen.append(loan.id)
    return overdue


def get_loan(state: LibraryState, loan_id: str) -> Loan:
    try:
        return state.loans[loan_id]
    except KeyError:
        raise KeyError(f"unknown loan {loan_id}") from None
