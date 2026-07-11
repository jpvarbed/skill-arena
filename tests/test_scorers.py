import pytest

from scorers import score_arize, score_case, score_deterministic, score_expect_set


def test_expect_set_matches_highsignal_dirty_case_when_any_expected_id_is_present():
    case = {
        "id": "4",
        "kind": "dirty",
        "expect": ["manufactured-quotability", "parataxis"],
    }

    result = score_expect_set(case, '["parataxis"]')

    assert result["pass"] is True
    assert "got=['parataxis']" in result["detail"]


def test_expect_set_matches_highsignal_clean_case_only_on_empty_array():
    case = {"id": "C1", "kind": "clean", "expect": None}

    assert score_expect_set(case, "[]")["pass"] is True

    result = score_expect_set(case, '["filler"]')

    assert result["pass"] is False
    assert "false-positive" in result["detail"]


def test_expect_set_parse_failure_is_an_error_like_highsignal_eval():
    result = score_expect_set({"id": "1", "kind": "dirty", "expect": "filler"}, "not json")

    assert result["pass"] is False
    assert result["error"] is True
    assert result["detail"] == "could not parse JSON array"


def test_deterministic_json_rule_has_passing_and_failing_fixtures():
    case = {
        "id": "json-1",
        "expect": {"json": {"ok": True, "label": "json-output"}},
    }

    passing = score_deterministic(case, '{"label":"json-output","ok":true}')
    failing = score_deterministic(case, '{"label":"json-output","ok":false}')

    assert passing["pass"] is True
    assert failing["pass"] is False
    assert "expected JSON" in failing["detail"]


def test_deterministic_supports_exact_regex_and_keyword_rules():
    assert score_deterministic({"expect": {"exact": "done"}}, "done")["pass"] is True
    assert score_deterministic({"expect": {"regex": r"task-\d+"}}, "task-42")["pass"] is True
    assert score_deterministic({"expect": {"keyword": "ready"}}, "system ready")["pass"] is True
    assert score_deterministic({"expect": {"keywords": ["system", "ready"]}}, "system ready")["pass"] is True


def test_deterministic_composite_checks_name_exact_failures():
    case = {
        "expect": {
            "checks": [
                {"id": "has-safe", "type": "contains", "text": "safe"},
                {"id": "no-secret", "type": "not_contains", "text": "secret"},
                {"id": "ready-status", "type": "regex", "pattern": r'"status"\s*:\s*"ready"'},
                {"id": "no-error", "type": "not_regex", "pattern": "error"},
                {"id": "short", "type": "max_chars", "value": 80},
                {"id": "json-shape", "type": "json_fields", "fields": ["status", "message"]},
            ]
        }
    }

    passing = score_deterministic(case, '{"status":"ready","message":"safe contract"}')
    failing = score_deterministic(case, '{"status":"error","secret":"x"}')

    assert passing["pass"] is True
    assert [check["id"] for check in failing["checks"] if not check["pass"]] == [
        "has-safe", "no-secret", "ready-status", "no-error", "json-shape"
    ]
    prose_wrapped = score_deterministic(
        {"expect": {"checks": [{"id": "json-shape", "type": "json_fields", "fields": ["status"]}]}},
        'Here is the result: {"status":"ready"}',
    )
    assert prose_wrapped["pass"] is False
    extra_fields = score_deterministic(
        {"expect": {"checks": [{"id": "json-shape", "type": "json_fields", "fields": ["status"]}]}},
        '{"status":"ready","extra":"allowed"}',
    )
    assert extra_fields["pass"] is True


def test_deterministic_rejects_mixed_composite_and_legacy_rules():
    case = {"expect": {"checks": [{"id": "has-ok", "type": "contains", "text": "ok"}], "exact": "ok"}}

    with pytest.raises(ValueError, match="mix"):
        score_deterministic(case, "ok")


def test_llm_judge_uses_injected_judge_backend_and_parses_json_verdict():
    calls = []

    def judge_call(prompt, model):
        calls.append((prompt, model))
        return '{"pass": true, "detail": "meets rubric"}'

    result = score_case(
        {"id": "judge-1", "input": "answer", "expect": {"rubric": "Say yes."}},
        "yes",
        {"type": "llm_judge", "model": "judge-model"},
        judge_call=judge_call,
    )

    assert result == {"pass": True, "detail": "meets rubric"}
    assert calls
    assert calls[0][1] == "judge-model"


def test_arize_scorer_is_an_explicit_stub():
    with pytest.raises(NotImplementedError, match="Arize scorer is not wired"):
        score_arize({}, "anything")


def test_error_sentinel_never_scores_as_pass():
    result = score_expect_set({"id": "C1", "kind": "clean", "expect": None}, "ERROR: codex: quota")

    assert result["pass"] is False
    assert "backend error" in result["detail"]


def test_valid_answer_with_trigger_word_not_flagged_error():
    # regression: a real answer that quotes analyzed content containing "authentication"
    # must score normally, not get classified as a backend error.
    from scorers import score_expect_set
    case = {"id": "x", "kind": "dirty", "expect": ["throat-clear"]}
    out = 'The draft mentions authentication and quota. ["throat-clear"]'
    r = score_expect_set(case, out)
    assert r["pass"] is True
    assert not r.get("error")
