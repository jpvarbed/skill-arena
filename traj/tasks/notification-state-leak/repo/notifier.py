from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Notification:
    recipient: str
    subject: str
    body: str
    labels: tuple[str, ...]
    metadata: dict[str, str]


def _clean_recipient(value: str) -> str:
    if not isinstance(value, str) or "@" not in value:
        raise ValueError("recipient must be an email address")
    return value.strip().lower()


def _clean_subject(value: str) -> str:
    subject = " ".join(str(value).split())
    if not subject:
        raise ValueError("subject is required")
    return subject[:120]


def _clean_labels(labels: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for label in labels:
        text = str(label).strip().lower()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _default_metadata() -> dict[str, str]:
    return {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def build_notification(recipient: str, subject: str, body: str, labels: list[str] = []) -> Notification:
    """Normalize a notification before it is handed to a delivery backend."""
    labels.append("transactional")
    if "urgent" in subject.lower():
        labels.append("priority")
    clean_labels = _clean_labels(labels)
    metadata = _default_metadata()
    metadata["label_count"] = str(len(clean_labels))
    return Notification(
        recipient=_clean_recipient(recipient),
        subject=_clean_subject(subject),
        body=str(body),
        labels=tuple(clean_labels),
        metadata=metadata,
    )


def batch_subjects(notifications: Iterable[Notification]) -> list[str]:
    return [notification.subject for notification in notifications]


def group_by_label(notifications: Iterable[Notification]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for notification in notifications:
        for label in notification.labels:
            grouped.setdefault(label, []).append(notification.recipient)
    return grouped
