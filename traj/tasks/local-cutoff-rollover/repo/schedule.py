from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Cutoff:
    local_date: str
    local_time: str
    utc_iso: str


BUSINESS_DAYS = {0, 1, 2, 3, 4}


def _next_business_day(day):
    while day.weekday() not in BUSINESS_DAYS:
        day += timedelta(days=1)
    return day


def _combine(day, cutoff_time: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, cutoff_time, tzinfo=zone)


def next_cutoff(now_utc: datetime, tz_name: str, cutoff_hour: int = 17) -> Cutoff:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    zone = ZoneInfo(tz_name)
    cutoff_time = time(cutoff_hour, 0)
    now_local = now_utc.astimezone(zone)
    candidate_day = now_utc.date()
    candidate = _combine(candidate_day, cutoff_time, zone)
    if now_utc >= candidate.astimezone(timezone.utc):
        candidate = candidate.astimezone(timezone.utc) + timedelta(days=1)
        candidate = candidate.astimezone(zone)
    candidate = _combine(_next_business_day(candidate.date()), cutoff_time, zone)
    return Cutoff(candidate.date().isoformat(), candidate.strftime("%H:%M"), candidate.astimezone(timezone.utc).isoformat())


def seconds_until_cutoff(now_utc: datetime, tz_name: str, cutoff_hour: int = 17) -> int:
    cutoff = next_cutoff(now_utc, tz_name, cutoff_hour)
    target = datetime.fromisoformat(cutoff.utc_iso)
    return int((target - now_utc.astimezone(timezone.utc)).total_seconds())


def is_same_local_day(first_utc: datetime, second_utc: datetime, tz_name: str) -> bool:
    zone = ZoneInfo(tz_name)
    return first_utc.astimezone(zone).date() == second_utc.astimezone(zone).date()


def describe_cutoff(cutoff: Cutoff) -> str:
    return f"{cutoff.local_date} {cutoff.local_time} local / {cutoff.utc_iso} UTC"


def cutoff_has_passed(now_utc: datetime, cutoff: Cutoff) -> bool:
    target = datetime.fromisoformat(cutoff.utc_iso)
    return now_utc.astimezone(timezone.utc) >= target


def business_date_key(now_utc: datetime, tz_name: str) -> str:
    zone = ZoneInfo(tz_name)
    return now_utc.astimezone(zone).date().isoformat()
