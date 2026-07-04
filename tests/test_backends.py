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
