import json
import re
from pathlib import Path

import pytest

from arena import load_cases, load_skill_from_config, main, run
from canary import compare_results, suite_fingerprint, write_summary
from scorers import score_deterministic


def write_suite(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "cases.jsonl").write_text(
        json.dumps({"id": "keeps-contract", "input": "Return ready.", "expect": {"exact": "ready"}}) + "\n"
    )
    config = suite / "config.json"
    config.write_text(json.dumps({
        "name": "workflow-canary",
        "cases_path": "cases.jsonl",
        "prompt_variants": [{"name": "default", "template": "{input}"}],
        "scorer": {"type": "deterministic"},
        "models": {"codex": "test-model"},
    }))
    return config


def test_canary_cli_writes_first_baseline_from_external_config(tmp_path):
    config = write_suite(tmp_path)
    runs_dir = tmp_path / "runs"

    result = main([
        "canary",
        "--config", str(config),
        "--backends", "codex",
        "--runs-dir", str(runs_dir),
        "--run-id", "r1",
        "--dry-run",
    ])

    assert result == 0
    run_dir = runs_dir / "r1"
    results = json.loads((run_dir / "results.json").read_text())
    assert results["suite_fingerprint"]
    assert results["skills"]["workflow-canary"]["cells"][0]["model"] == "test-model"
    assert results["skills"]["workflow-canary"]["cells"][0]["cases"][0]["output"] == "ready"
    assert "baseline" in (run_dir / "summary.md").read_text()


def result_fixture(lanes, fingerprint="same-suite"):
    return {
        "suite_fingerprint": fingerprint,
        "skills": {
            "workflow-canary": {
                "cells": [
                    {
                        "backend": backend,
                        "model": model,
                        "prompt_variant": "default",
                        "cases": [
                            {
                                "id": "contract",
                                "pass": passed,
                                "error": error,
                                "detail": "ok" if passed else "missing required contract",
                                "checks": [{"id": "has-contract", "pass": passed}],
                            }
                        ],
                    }
                    for backend, model, passed, error in lanes
                ]
            }
        },
    }


def test_compare_results_reports_each_temporal_lane_status():
    baseline = result_fixture([
        ("safe", "m1", True, False),
        ("drift", "m2", True, False),
        ("recover", "m3", False, False),
        ("failing", "m4", False, False),
    ])
    current = result_fixture([
        ("safe", "m1", True, False),
        ("drift", "m2", False, False),
        ("recover", "m3", True, False),
        ("failing", "m4", False, False),
        ("new", "m5", True, False),
    ])

    lanes = compare_results(current, baseline)

    assert {lane["backend"]: lane["status"] for lane in lanes} == {
        "safe": "still safe",
        "drift": "drifted",
        "recover": "recovered",
        "failing": "still failing",
        "new": "new",
    }
    assert next(lane for lane in lanes if lane["backend"] == "drift")["changes"] == [
        "contract/has-contract: pass -> fail"
    ]

    baseline_failures = compare_results(result_fixture([
        ("failed-check", "m6", False, False),
        ("backend-error", "m7", False, True),
    ]))
    assert {lane["backend"]: lane["changes"] for lane in baseline_failures} == {
        "failed-check": ["contract/has-contract: fail"],
        "backend-error": ["contract: error"],
    }


def test_canary_auto_baseline_requires_matching_suite_and_explicit_mismatch_fails_early(tmp_path):
    config = write_suite(tmp_path)
    runs_dir = tmp_path / "runs"
    base_args = ["--config", str(config), "--backends", "codex", "--runs-dir", str(runs_dir), "--dry-run"]

    assert main(["canary", *base_args, "--run-id", "r1"]) == 0
    assert main(["canary", *base_args, "--run-id", "r2"]) == 0
    assert "still safe" in (runs_dir / "r2/summary.md").read_text()

    cases_path = config.parent / "cases.jsonl"
    cases_path.write_text(
        json.dumps({"id": "keeps-contract", "input": "Return changed.", "expect": {"exact": "changed"}}) + "\n"
    )
    assert main(["canary", *base_args, "--run-id", "r3"]) == 0
    assert "| baseline |" in (runs_dir / "r3/summary.md").read_text()

    with pytest.raises(ValueError, match="fingerprint"):
        main(["canary", *base_args, "--run-id", "r4", "--baseline", str(runs_dir / "r1")])
    assert not (runs_dir / "r4").exists()


def test_canary_requires_explicit_model_identity_before_creating_run(tmp_path):
    config = write_suite(tmp_path)
    data = json.loads(config.read_text())
    data["models"] = {}
    config.write_text(json.dumps(data))
    runs_dir = tmp_path / "runs"

    with pytest.raises(ValueError, match="explicit model"):
        main([
            "canary", "--config", str(config), "--backends", "codex",
            "--runs-dir", str(runs_dir), "--run-id", "r1", "--dry-run",
        ])
    assert not (runs_dir / "r1").exists()


def test_suite_fingerprint_changes_when_prompt_variant_identity_changes(tmp_path):
    config = write_suite(tmp_path)
    skill = load_skill_from_config(config)
    before = suite_fingerprint(skill, load_cases(skill))
    data = json.loads(config.read_text())
    data["prompt_variants"][0]["name"] = "renamed"
    config.write_text(json.dumps(data))
    renamed = load_skill_from_config(config)

    assert suite_fingerprint(renamed, load_cases(renamed)) != before


def test_existing_run_and_report_keep_their_public_result_shape(tmp_path):
    out_dir = tmp_path / "standard-run"

    results = run(["json-output"], ["codex"], out_dir=out_dir, dry_run=True)
    cell = results["skills"]["json-output"]["cells"][0]
    case = cell["cases"][0]
    assert "model" not in cell
    assert "checks" not in case
    assert "output" not in case

    replay_html = tmp_path / "replayed.html"
    assert main(["report", "--results", str(out_dir / "results.json"), "--html", str(replay_html)]) == 0
    assert replay_html.exists()


def test_public_example_runs_offline_and_contains_no_private_markers(tmp_path):
    example_dir = Path(__file__).parents[1] / "examples/inference-canary"
    public_text = "\n".join(path.read_text() for path in sorted(example_dir.iterdir()) if path.is_file())
    forbidden = [
        r"/Users/",
        r"BWS_ACCESS_TOKEN",
        r"CURSOR_API_KEY\s*=",
        r"\bsk-[A-Za-z0-9]{8,}\b",
    ]
    assert not [pattern for pattern in forbidden if re.search(pattern, public_text)]
    config = json.loads((example_dir / "config.json").read_text())
    receipt = (example_dir / "RECEIPT-2026-07-10.md").read_text().lower()
    assert all(backend in receipt for backend in config["models"])
    receipt_rows = [line for line in receipt.splitlines() if line.startswith("|") and "/" in line]
    assert len(receipt_rows) == len(config["models"])
    assert all("still safe" in row or "still failing" in row for row in receipt_rows)

    runs_dir = tmp_path / "runs"
    assert main([
        "canary",
        "--config", str(example_dir / "config.json"),
        "--backends", "codex,cursor",
        "--runs-dir", str(runs_dir),
        "--run-id", "example",
        "--dry-run",
    ]) == 0
    summary = (runs_dir / "example/summary.md").read_text()
    assert summary.count("| baseline |") == 2
    assert not [pattern for pattern in forbidden if re.search(pattern, summary)]


def test_public_review_case_accepts_idor_and_membership_language():
    cases_path = Path(__file__).parents[1] / "examples/inference-canary/cases.jsonl"
    cases = [json.loads(line) for line in cases_path.read_text().splitlines()]
    case = next(case for case in cases if case["id"] == "behavior-risk-review-v1")
    outputs = [
        "FINDINGS\n- [high] app/controllers/reports_controller.rb:3 - user-controlled account_id lets a user fetch reports from accounts they do not belong to - scope through current_user",
        "FINDINGS\n- [high] app/controllers/reports_controller.rb:2 - user-controlled account_id allows IDOR for accounts the current user may not belong to - scope through current_user",
    ]

    assert all(score_deterministic(case, output)["pass"] for output in outputs)


def test_summary_escapes_table_cells_and_omits_backend_error_payloads(tmp_path):
    results = result_fixture([("pipe|backend", "model`one|two", False, True)])
    results["skills"]["workflow-canary"]["cells"][0]["cases"][0]["detail"] = "token sk-sensitive123"

    write_summary(tmp_path, results)

    summary = (tmp_path / "summary.md").read_text()
    assert "pipe\\|backend" in summary
    assert "model\\`one\\|two" in summary
    assert "contract: error" in summary
    assert "sk-sensitive123" not in summary
