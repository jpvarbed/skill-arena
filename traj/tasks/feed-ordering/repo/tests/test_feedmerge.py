from datetime import datetime

from feedmerge import FeedEvent, latest_payload_by_source, merge_events, summarize_order


def event(source, external_id, second, sequence=0):
    return FeedEvent(source, external_id, datetime(2026, 1, 1, 12, 0, second), sequence, {"id": external_id})


def test_same_timestamp_uses_source_priority_then_sequence():
    support = [event("support", "s2", 0, 2), event("support", "s1", 0, 1)]
    billing = [event("billing", "b1", 0, 5)]
    crm = [event("crm", "c1", 0, 1)]
    merged = merge_events([support, crm, billing])
    assert summarize_order(merged) == ["billing:b1", "support:s1", "support:s2", "crm:c1"]


def test_later_timestamps_still_sort_after_earlier_items():
    merged = merge_events([[event("marketing", "m1", 5)], [event("billing", "b1", 0)]])
    assert summarize_order(merged) == ["billing:b1", "marketing:m1"]


def test_duplicates_from_same_source_are_ignored():
    merged = merge_events([[event("billing", "b1", 0), event("billing", "b1", 1)]])
    assert summarize_order(merged) == ["billing:b1"]


def test_latest_payload_by_source_uses_sequence_as_tie_breaker():
    payload = latest_payload_by_source([event("support", "old", 0, 1), event("support", "new", 0, 2)])
    assert payload["support"] == {"id": "new"}
