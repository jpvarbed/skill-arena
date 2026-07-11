import json
import subprocess

import backends
from backends import ERROR_SENTINEL_PREFIX, call_backend, is_error_sentinel
from scorers import score_expect_set


def test_backend_exception_returns_error_sentinel(monkeypatch):
    def quota_backend(prompt, model):
        raise RuntimeError("quota exceeded")

    monkeypatch.setitem(backends.BACKENDS, "quota-test", quota_backend)

    output = call_backend("quota-test", "prompt", None)

    assert output.startswith(ERROR_SENTINEL_PREFIX)
    assert is_error_sentinel(output)
    assert "quota exceeded" in output
    assert score_expect_set({"kind": "clean", "expect": None}, output)["pass"] is False


def test_cursor_backend_is_read_only_model_explicit_and_scrubs_failures(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = "cursor answer\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Result()

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-secret")
    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert call_backend("cursor", "review this", "cursor-model") == "cursor answer"
    argv, kwargs = calls[0]
    assert argv == [
        "cursor-agent", "--print", "--output-format", "text", "--mode", "ask",
        "--sandbox", "enabled", "--model", "cursor-model",
    ]
    assert kwargs["input"] == "review this"
    assert kwargs["timeout"] == 180
    assert kwargs["env"]["CURSOR_API_KEY"] == "cursor-secret"

    Result.returncode = 1
    Result.stderr = "request failed with cursor-secret"
    output = call_backend("cursor", "review this", "cursor-model")
    assert output.startswith("ERROR: cursor:")
    assert "cursor-secret" not in output


def test_cursor_backend_loads_lowercase_bws_secret_alias(monkeypatch):
    seen_cursor_env = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(argv, **kwargs):
        if argv[0] == "zsh":
            return Result(json.dumps([{"key": "cursor_api_key", "value": "from-bws"}]))
        seen_cursor_env.append(kwargs["env"]["CURSOR_API_KEY"])
        return Result("answer")

    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(backends, "_BWS_LOADED", False)
    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert call_backend("cursor", "review", "cursor-model") == "answer"
    assert seen_cursor_env == ["from-bws"]


def test_cursor_backend_prefers_canonical_bws_secret_name(monkeypatch):
    seen_cursor_env = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(argv, **kwargs):
        if argv[0] == "zsh":
            return Result(json.dumps([
                {"key": "cursor_api_key", "value": "alias-value"},
                {"key": "CURSOR_API_KEY", "value": "canonical-value"},
            ]))
        seen_cursor_env.append(kwargs["env"]["CURSOR_API_KEY"])
        return Result("answer")

    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(backends, "_BWS_LOADED", False)
    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert call_backend("cursor", "review", "cursor-model") == "answer"
    assert seen_cursor_env == ["canonical-value"]


def test_cursor_backend_normalizes_missing_auth_binary_and_timeout(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(backends, "_BWS_LOADED", False)
    monkeypatch.setattr(backends, "_load_bws_secrets", lambda: None)
    assert "CURSOR_API_KEY not found" in call_backend("cursor", "review", "cursor-model")

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-secret")
    monkeypatch.setattr(backends.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("cursor-agent")))
    missing_binary = call_backend("cursor", "review", "cursor-model")
    assert missing_binary.startswith("ERROR: cursor:")
    assert "cursor-secret" not in missing_binary

    monkeypatch.setattr(
        backends.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(["cursor-agent"], 180)),
    )
    timed_out = call_backend("cursor", "review", "cursor-model")
    assert timed_out.startswith("ERROR: cursor:")
    assert "cursor-secret" not in timed_out
