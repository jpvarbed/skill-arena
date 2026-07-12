import pytest

from scorers import lint_goal_brief, score_arize, score_case, score_compression_fidelity, score_deterministic, score_expect_set


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


def test_compression_fidelity_scores_compression_when_probe_threshold_passes():
    case = {
        "input": "Alpha service writes invoices after payment confirmation. Beta worker retries failed notifications. Gamma monitor alerts after five minutes.",
        "probes": [
            {"question": "What writes invoices?", "answer_pattern": r"Alpha service.*invoices"},
            {"question": "What retries?", "answer_pattern": r"Beta worker.*notifications"},
            {"question": "When does monitor alert?", "answer_pattern": r"five minutes"},
        ],
    }

    result = score_compression_fidelity(case, "Alpha service writes invoices. Beta worker retries notifications. Gamma monitor alerts after five minutes.")

    assert result["pass"] is True
    assert result["fidelity"] == 1.0
    assert result["compression"] > 0
    assert result["score"] == result["compression"]


def test_compression_fidelity_fails_below_fidelity_threshold_even_when_short():
    case = {
        "input": "Alpha service writes invoices after payment confirmation. Beta worker retries failed notifications. Gamma monitor alerts after five minutes.",
        "probes": [
            {"question": "What writes invoices?", "answer_pattern": r"Alpha service.*invoices"},
            {"question": "What retries?", "answer_pattern": r"Beta worker.*notifications"},
            {"question": "When does monitor alert?", "answer_pattern": r"five minutes"},
        ],
    }

    result = score_compression_fidelity(case, "Invoices done.")

    assert result["pass"] is False
    assert result["score"] == 0.0
    assert "missing" in result["detail"]


VALID_BRIEFS = [
    """GOAL: Add deterministic cases for the parser and prove they run.
CONTEXT: tools: local repo and pytest; refs: parser docs; output: skills/parser; fixtures: tests/fixtures/parser.
EFFORT: medium
VERIFY: beat the 80% current parser fixture pass rate on the holdout set.
RESOLVED (do not reopen): Keep the current parser API.
RUBRIC (binary):
  - [ ] At least 12 cases exist.
  - [ ] pytest exits 0.
  - [ ] Regeneration is byte-identical.
DONE = all rubric checks PASS.
""",
    """GOAL: Fix mobile overflow in the settings panel.
CONTEXT: tools: browser automation and pytest; refs: design notes; output: app/settings; fixtures: 3 viewport scripts.
EFFORT: high
VERIFY: target zero overlapping text nodes across all 3 viewports.
RESOLVED: Keep existing component library.
RUBRIC:
  - [ ] No overlap found in browser output.
  - [ ] Existing tests pass.
  - [ ] Screenshot evidence is saved.
DONE = all rubric checks PASS.
""",
    """GOAL: Refresh the saved benchmark report from offline outputs.
CONTEXT: tools: report CLI; refs: saved outputs; output: out/report; fixtures: offline result JSON.
EFFORT: low
VERIFY: beat the stale 2026-06 snapshot by rendering the 2026-07 result file.
RESOLVED (do not reopen): Do not run live model calls.
RUBRIC (binary):
  - [ ] Report uses only saved outputs.
  - [ ] Render command exits 0.
  - [ ] Public hygiene scan is clean.
DONE = all rubric checks PASS.
""",
    """GOAL: Reconcile the import ledger and write a receipt.
CONTEXT: tools: reconciliation script; refs: ledger README; output: out/import-receipt.md; fixtures: train and holdout CSVs.
EFFORT: medium
VERIFY: break the 95% matched-row baseline on the holdout CSV.
RESOLVED: Use the existing CSV schema.
RUBRIC:
  - [ ] Holdout matched rows exceed baseline.
  - [ ] Receipt lists unmatched rows.
  - [ ] Command is reproducible.
DONE = all rubric checks PASS.
""",
    """GOAL: Build the release note checker and validate current notes.
CONTEXT: tools: git and pytest; refs: release docs; output: tools/release_check.py; fixtures: release note samples.
EFFORT: medium
VERIFY: at least 100% of fixture violations are detected.
RESOLVED (do not reopen): Python stdlib only.
RUBRIC (binary):
  - [ ] Checker flags every fixture violation.
  - [ ] False-positive fixture stays clean.
  - [ ] Full test suite passes.
DONE = all rubric checks PASS.
""",
]


INVALID_BRIEFS = [
    """GOAL: Fix the parser
and update docs.
CONTEXT: tools: pytest; refs: docs; output: parser.
EFFORT: medium
VERIFY: beat the 80% baseline.
RESOLVED: Keep API.
RUBRIC:
  - [ ] Tests pass.
DONE = all rubric checks PASS.
""",
    """GOAL: Fix the parser.
CONTEXT: Read the files I mentioned.
EFFORT: medium
VERIFY: beat the 80% baseline.
RESOLVED: Keep API.
RUBRIC:
  - [ ] Tests pass.
DONE = all rubric checks PASS.
""",
    """GOAL: Fix the parser.
CONTEXT: tools: pytest; refs: docs; output: parser.
VERIFY: beat the 80% baseline.
RESOLVED: Keep API.
RUBRIC:
  - [ ] Tests pass.
DONE = all rubric checks PASS.
""",
    """GOAL: Fix the parser.
CONTEXT: tools: pytest; refs: docs; output: parser.
EFFORT: medium
VERIFY: run the parser tests and inspect failures.
RESOLVED: Keep API.
RUBRIC:
  - [ ] Tests pass.
DONE = all rubric checks PASS.
""",
    """GOAL: Fix the parser.
CONTEXT: tools: pytest; refs: docs; output: parser.
EFFORT: medium
VERIFY: beat the 80% baseline.
RESOLVED: Keep API.
RUBRIC:
  - Tests pass and docs look good.
DONE = all rubric checks PASS.
""",
]


def test_brief_lint_matches_hand_labeled_fixtures_10_of_10():
    for text in VALID_BRIEFS:
        assert lint_goal_brief(text)["pass"] is True
    for text in INVALID_BRIEFS:
        assert lint_goal_brief(text)["pass"] is False


def test_brief_lint_requires_resolved_section():
    text = VALID_BRIEFS[0].replace("RESOLVED (do not reopen): Keep the current parser API.\n", "")

    result = lint_goal_brief(text)

    assert result["pass"] is False
    assert "resolved_present" in result["violations"]
