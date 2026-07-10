import pytest

from notifier import build_notification, group_by_label


def test_default_labels_do_not_leak_between_calls():
    first = build_notification("A@example.com", "Urgent: outage", "body")
    second = build_notification("b@example.com", "Weekly summary", "body")
    assert first.labels == ("transactional", "priority")
    assert second.labels == ("transactional",)


def test_explicit_labels_are_normalized_and_not_mutated():
    labels = ["Team", "team", "  Ops  "]
    notification = build_notification("ops@example.com", "Deploy", "body", labels)
    assert notification.labels == ("team", "ops", "transactional")
    assert labels == ["Team", "team", "  Ops  "]


def test_group_by_label_uses_normalized_recipients():
    urgent = build_notification("A@Example.com", "urgent fix", "body")
    normal = build_notification("b@example.com", "hello", "body")
    assert group_by_label([urgent, normal])["transactional"] == ["a@example.com", "b@example.com"]


def test_bad_recipient_is_rejected():
    with pytest.raises(ValueError):
        build_notification("not-an-email", "subject", "body")
