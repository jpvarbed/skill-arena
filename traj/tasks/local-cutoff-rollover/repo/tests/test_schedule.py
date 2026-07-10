from datetime import datetime, timezone

from schedule import is_same_local_day, next_cutoff, seconds_until_cutoff


def dt(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_cutoff_after_spring_dst_rollover_uses_local_next_day():
    cutoff = next_cutoff(dt("2026-03-08T22:30:00"), "America/Los_Angeles")
    assert cutoff.local_date == "2026-03-09"
    assert cutoff.local_time == "17:00"
    assert cutoff.utc_iso == "2026-03-10T00:00:00+00:00"


def test_before_cutoff_returns_same_local_day():
    cutoff = next_cutoff(dt("2026-01-05T20:00:00"), "America/New_York")
    assert cutoff.local_date == "2026-01-05"
    assert cutoff.utc_iso == "2026-01-05T22:00:00+00:00"


def test_utc_next_day_before_local_cutoff_uses_local_date():
    cutoff = next_cutoff(dt("2026-01-06T00:30:00"), "America/Los_Angeles")
    assert cutoff.local_date == "2026-01-05"
    assert cutoff.utc_iso == "2026-01-06T01:00:00+00:00"


def test_weekend_rolls_to_monday():
    cutoff = next_cutoff(dt("2026-01-10T18:00:00"), "America/New_York")
    assert cutoff.local_date == "2026-01-12"


def test_seconds_until_cutoff_is_positive():
    assert seconds_until_cutoff(dt("2026-01-05T20:00:00"), "America/New_York") == 7200
    assert is_same_local_day(dt("2026-01-05T04:30:00"), dt("2026-01-05T08:30:00"), "America/Los_Angeles") is False
