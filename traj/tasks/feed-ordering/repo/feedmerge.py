from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class FeedEvent:
    source: str
    external_id: str
    happened_at: datetime
    sequence: int
    payload: dict


SOURCE_PRIORITY = {"billing": 0, "support": 1, "crm": 2, "marketing": 3}


def _priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 99)


def _dedupe_key(event: FeedEvent) -> tuple[str, str]:
    return (event.source, event.external_id)


def _validate(event: FeedEvent) -> None:
    if not isinstance(event.happened_at, datetime):
        raise TypeError("happened_at must be a datetime")
    if event.sequence < 0:
        raise ValueError("sequence must be non-negative")


def merge_events(feeds: Iterable[Iterable[FeedEvent]]) -> list[FeedEvent]:
    """Merge feeds into deterministic processing order."""
    merged: list[FeedEvent] = []
    seen: set[tuple[str, str]] = set()
    for feed in feeds:
        for event in feed:
            _validate(event)
            key = _dedupe_key(event)
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    return sorted(merged, key=lambda event: event.happened_at)


def summarize_order(events: Iterable[FeedEvent]) -> list[str]:
    return [f"{event.source}:{event.external_id}" for event in events]


def sources_seen(events: Iterable[FeedEvent]) -> list[str]:
    return sorted({event.source for event in events}, key=_priority)


def latest_payload_by_source(events: Iterable[FeedEvent]) -> dict[str, dict]:
    latest: dict[str, FeedEvent] = {}
    for event in events:
        current = latest.get(event.source)
        if current is None or (event.happened_at, event.sequence) >= (current.happened_at, current.sequence):
            latest[event.source] = event
    return {source: event.payload for source, event in latest.items()}
