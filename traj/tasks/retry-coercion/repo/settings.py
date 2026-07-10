from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    delay_seconds: int
    jitter: bool


DEFAULT_ATTEMPTS = 3
DEFAULT_DELAY_SECONDS = 5


def _coerce_int(value, default: int, name: str) -> int:
    if not value:
        return default
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if coerced < 0:
        raise ValueError(f"{name} must be non-negative")
    return coerced


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("jitter must be a boolean")


def load_retry_policy(config: Mapping[str, object]) -> RetryPolicy:
    attempts = _coerce_int(config.get("attempts"), DEFAULT_ATTEMPTS, "attempts")
    delay = _coerce_int(config.get("delay_seconds"), DEFAULT_DELAY_SECONDS, "delay_seconds")
    return RetryPolicy(attempts=attempts, delay_seconds=delay, jitter=_coerce_bool(config.get("jitter")))


def should_retry(policy: RetryPolicy, failures: int) -> bool:
    if failures < 0:
        raise ValueError("failures must be non-negative")
    return failures < policy.attempts


def retry_schedule(policy: RetryPolicy) -> list[int]:
    return [policy.delay_seconds * attempt for attempt in range(policy.attempts)]


def describe_policy(policy: RetryPolicy) -> str:
    jitter = "with jitter" if policy.jitter else "without jitter"
    return f"{policy.attempts} attempts every {policy.delay_seconds}s {jitter}"


def max_elapsed(policy: RetryPolicy) -> int:
    return sum(retry_schedule(policy))
