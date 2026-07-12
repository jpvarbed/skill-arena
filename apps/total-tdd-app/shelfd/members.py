from __future__ import annotations

from . import audit
from .models import Member
from .storage import LibraryState


def register_member(
    state: LibraryState,
    name: str,
    email: str,
    *,
    max_loans: int = 3,
) -> Member:
    if not name.strip():
        raise ValueError("name is required")
    if "@" not in email:
        raise ValueError("valid email is required")
    if max_loans <= 0:
        raise ValueError("max_loans must be positive")
    member = Member(
        id=state.next_member_id(),
        name=name.strip(),
        email=email.strip().lower(),
        active=True,
        max_loans=int(max_loans),
    )
    state.members[member.id] = member
    audit.record(state, "member.add", member_id=member.id, detail=member.email)
    return member


def get_member(state: LibraryState, member_id: str) -> Member:
    try:
        return state.members[member_id]
    except KeyError:
        raise KeyError(f"unknown member {member_id}") from None


def deactivate_member(state: LibraryState, member_id: str) -> Member:
    member = get_member(state, member_id)
    if state.active_loans_for_member(member_id):
        raise ValueError("cannot deactivate member with active loans")
    member.active = False
    audit.record(state, "member.deactivate", member_id=member.id, detail=member.email)
    return member


def reactivate_member(state: LibraryState, member_id: str) -> Member:
    member = get_member(state, member_id)
    member.active = True
    audit.record(state, "member.reactivate", member_id=member.id, detail=member.email)
    return member


def active_loan_count(state: LibraryState, member_id: str) -> int:
    return len(state.active_loans_for_member(member_id))


def ensure_can_checkout(state: LibraryState, member_id: str) -> None:
    member = get_member(state, member_id)
    if not member.active:
        raise ValueError("inactive members cannot checkout books")
    if active_loan_count(state, member_id) > member.max_loans:
        raise ValueError("member loan limit reached")


def list_members(state: LibraryState, *, active_only: bool = False) -> list[Member]:
    members = list(state.members.values())
    if active_only:
        members = [member for member in members if member.active]
    return sorted(members, key=lambda member: (member.name.casefold(), member.id))
