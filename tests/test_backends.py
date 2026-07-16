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


def test_codex_56_aliases_wired_keyless():
    # Both 5.6 aliases route to the codex CLI fn and demand no API key,
    # and the skill config pins real family ids (bare "gpt-5.6" is invalid).
    import json

    for alias in ("codex-56sol", "codex-56luna"):
        assert backends.BACKENDS[alias] is backends.call_codex
        assert alias not in backends._BACKEND_ENV

    cfg = json.load(open("skills/instruction-conflicts/config.json"))
    assert cfg["models"]["codex-56sol"] == "gpt-5.6-sol"
    assert cfg["models"]["codex-56luna"] == "gpt-5.6-luna"


def test_codex_returns_cli_banner_when_no_last_message_is_written(monkeypatch):
    from types import SimpleNamespace

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="", stderr="codex startup failed", returncode=1)

    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert "codex startup failed" in backends.call_codex("prompt", "gpt-5.6-sol")


def test_run_cell_records_exact_model_id():
    from arena import load_cases, load_skill, run_cell

    skill = load_skill("instruction-conflicts")
    cases = load_cases(skill)[:1]
    variant = skill.config["prompt_variants"][0]
    cell = run_cell(skill, cases, variant, "codex-56sol", dry_run=True)
    assert cell["model"] == "gpt-5.6-sol"
    cell = run_cell(skill, cases, variant, "codex", dry_run=True)
    assert cell["model"] == "gpt-5.5"
