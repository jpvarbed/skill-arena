import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    user_id: str
    email: str
    age: int | None
    tags: tuple[str, ...]


DEFAULT_PROFILE = Profile(user_id="anonymous", email="", age=None, tags=())


def _normalize_email(value: str) -> str:
    email = str(value).strip().lower()
    if email and "@" not in email:
        raise ValueError("email must contain @")
    return email


def _normalize_age(value) -> int | None:
    if value in (None, ""):
        return None
    age = int(value)
    if age < 0:
        raise ValueError("age must be non-negative")
    return age


def _normalize_tags(value) -> tuple[str, ...]:
    if value is None:
        return ()
    tags = []
    for item in value:
        text = str(item).strip().lower()
        if text and text not in tags:
            tags.append(text)
    return tuple(tags)


def parse_profile(data: dict) -> Profile:
    if not isinstance(data, dict):
        raise ValueError("profile must be a JSON object")
    user_id = str(data.get("user_id") or "anonymous")
    return Profile(
        user_id=user_id,
        email=_normalize_email(data.get("email", "")),
        age=_normalize_age(data.get("age")),
        tags=_normalize_tags(data.get("tags")),
    )


def load_profile(path: str | Path) -> Profile:
    try:
        raw = Path(path).read_text()
        return parse_profile(json.loads(raw))
    except Exception:
        return DEFAULT_PROFILE


def profile_summary(profile: Profile) -> str:
    tag_text = ",".join(profile.tags) if profile.tags else "none"
    return f"{profile.user_id} <{profile.email or 'no-email'}> tags={tag_text}"
