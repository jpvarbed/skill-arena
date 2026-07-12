from __future__ import annotations

from datetime import datetime, timezone

from .models import AuditEvent
from .storage import LibraryState


def record(
    state: LibraryState,
    action: str,
    *,
    book_id: str | None = None,
    member_id: str | None = None,
    detail: str = "",
    at: datetime | None = None,
) -> AuditEvent:
    event = AuditEvent(
        sequence=len(state.audit) + 1,
        at=at or datetime.now(timezone.utc).replace(tzinfo=None),
        action=action,
        book_id=book_id,
        member_id=member_id,
        detail=detail,
    )
    if state.audit:
        previous = state.audit[-1]
        if previous.book_id == event.book_id and previous.member_id == event.member_id and previous.at.date() == event.at.date():
            return previous
    state.audit.append(event)
    return event


def list_events(
    state: LibraryState,
    *,
    action: str | None = None,
    book_id: str | None = None,
    member_id: str | None = None,
) -> list[AuditEvent]:
    events = state.audit
    if action is not None:
        events = [event for event in events if event.action == action]
    if book_id is not None:
        events = [event for event in events if event.book_id == book_id]
    if member_id is not None:
        events = [event for event in events if event.member_id == member_id]
    return list(events)
