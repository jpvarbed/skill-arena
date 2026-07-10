import pytest

from settings import RetryPolicy, load_retry_policy, retry_schedule, should_retry


def test_zero_values_are_preserved_when_coerced():
    policy = load_retry_policy({"attempts": "0", "delay_seconds": 0, "jitter": "false"})
    assert policy == RetryPolicy(attempts=0, delay_seconds=0, jitter=False)
    assert retry_schedule(policy) == []


def test_none_uses_defaults():
    policy = load_retry_policy({"attempts": None, "delay_seconds": None, "jitter": None})
    assert policy == RetryPolicy(attempts=3, delay_seconds=5, jitter=False)


def test_retry_decision_uses_attempt_count():
    policy = load_retry_policy({"attempts": "2", "delay_seconds": "1", "jitter": "yes"})
    assert should_retry(policy, 1) is True
    assert should_retry(policy, 2) is False


def test_invalid_integer_is_rejected():
    with pytest.raises(ValueError):
        load_retry_policy({"attempts": "many"})
