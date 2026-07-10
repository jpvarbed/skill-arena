import json

import pytest

from profiles import DEFAULT_PROFILE, Profile, load_profile, profile_summary


def test_missing_profile_uses_default(tmp_path):
    assert load_profile(tmp_path / "missing.json") == DEFAULT_PROFILE


def test_valid_profile_is_normalized(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"user_id": "A", "email": "A@Example.com", "age": "42", "tags": ["Team", "team"]}))
    assert load_profile(path) == Profile("A", "a@example.com", 42, ("team",))


def test_invalid_age_is_not_swallowed(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"user_id": "A", "age": "unknown"}))
    with pytest.raises(ValueError):
        load_profile(path)


def test_summary_handles_empty_email_and_tags():
    assert profile_summary(DEFAULT_PROFILE) == "anonymous <no-email> tags=none"
