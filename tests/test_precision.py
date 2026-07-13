import json

import majority
import precision


def _forge_results(tmp_path, winner_outputs, original_outputs):
    """Two-contestant forge results over 3 cases: 2 dirty + 1 clean."""

    def cell(contestant, outputs):
        return {
            "contestant": contestant,
            "backend": "codex-56sol",
            "pass_rate": 1.0 if contestant == "v1" else 0.5,
            "passes": 3 if contestant == "v1" else 2,
            "n": 3,
            "errors": 0,
            "cases": [
                {"id": "d1", "kind": "dirty", "pass": True, "trial_outputs": outputs["d1"]},
                {"id": "d2", "kind": "dirty", "pass": True, "trial_outputs": outputs["d2"]},
                {"id": "c1", "kind": "clean", "pass": True, "trial_outputs": outputs["c1"]},
            ],
        }

    results = {
        "skill": "test-skill",
        "target": "codex-56sol",
        "cells": [cell("original", original_outputs), cell("v1", winner_outputs)],
        "summary": {"winner": "v1"},
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))
    return path


CASES = {
    "d1": {"id": "d1", "kind": "dirty", "expect": "tone-conflict"},
    "d2": {"id": "d2", "kind": "dirty", "expect": ["autonomy-conflict"]},
    "c1": {"id": "c1", "kind": "clean", "expect": []},
}


def test_contestant_metrics_counts_extras_and_exacts():
    cell = {
        "contestant": "v1",
        "backend": "b",
        "pass_rate": 1.0,
        "passes": 3,
        "n": 3,
        "errors": 0,
        "cases": [
            # exact hit, 0 extras
            {"id": "d1", "kind": "dirty", "pass": True, "trial_outputs": ['["tone-conflict"]']},
            # subset-pass with 2 extra labels
            {"id": "d2", "kind": "dirty", "pass": True,
             "trial_outputs": ['["autonomy-conflict", "output-format-conflict", "tone-conflict"]']},
            # clean false-positive at majority too
            {"id": "c1", "kind": "clean", "pass": False, "trial_outputs": ['["output-format-conflict"]']},
        ],
    }
    m = precision.contestant_metrics(cell, CASES)
    assert m["exact_set_rate"] == round(1 / 3, 4)
    assert m["mean_extra_labels_dirty"] == 1.0  # (0 + 2) / 2
    assert m["clean_passes"] == 0 and m["clean_total"] == 1


def test_eligibility_gate_blocks_over_labeling_win():
    winner = {"subset_score": 1.0, "mean_extra_labels_dirty": 2.0, "clean_passes": 1}
    original = {"subset_score": 0.5, "mean_extra_labels_dirty": 0.5, "clean_passes": 1}
    gate = precision.eligibility(winner, original)
    assert gate["eligible"] is False
    assert gate["checks"]["subset_score_strictly_higher"] is True
    assert gate["checks"]["extra_labels_not_worse"] is False


def test_eligibility_gate_passes_clean_win():
    winner = {"subset_score": 1.0, "mean_extra_labels_dirty": 0.0, "clean_passes": 1}
    original = {"subset_score": 0.5, "mean_extra_labels_dirty": 0.5, "clean_passes": 1}
    assert precision.eligibility(winner, original)["eligible"] is True


def test_majority_merge_strict(tmp_path, capsys):
    def run_file(name, d1, d2):
        data = {
            "skills": {
                "s": {
                    "cells": [
                        {"backend": "b", "cases": [
                            {"id": "d1", "pass": d1},
                            {"id": "d2", "pass": d2},
                        ]}
                    ]
                }
            }
        }
        p = tmp_path / name
        p.write_text(json.dumps(data))
        return str(p)

    paths = [run_file("r1.json", True, False), run_file("r2.json", True, True),
             run_file("r3.json", False, False)]
    import sys

    argv = sys.argv
    sys.argv = ["majority.py", "--skill", "s", "--backend", "b", *paths]
    try:
        majority.main()
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    assert "majority score: 1/2" in out  # d1: 2/3 pass; d2: 1/3 fail


def test_clean_passes_use_runner_majority_not_all_trials():
    # 2/3 trials clean = majority PASS for the gate; all-trials is the stricter
    # diagnostic column only. (A stricter-than-registered gate flipped a real
    # winner to ineligible on 2026-07-12 — this pins the registered standard.)
    cell = {
        "contestant": "v1", "backend": "b", "passes": 1, "n": 1, "errors": 0,
        "cases": [
            {"id": "c1", "kind": "clean", "pass": True,
             "trial_outputs": ["[]", '["tone-conflict"]', "[]"]},
        ],
    }
    m = precision.contestant_metrics(cell, CASES)
    assert m["clean_passes"] == 1
    assert m["clean_all_trials"] == 0
    assert m["subset_score"] == 1.0


def test_unparseable_trials_break_coverage_not_inflate_exactness():
    cell = {
        "contestant": "v1", "backend": "b", "passes": 1, "n": 1, "errors": 0,
        "cases": [
            # 2 of 3 trials unparseable; the surviving exact trial must NOT
            # count as full exactness under coverage accounting
            {"id": "d1", "kind": "dirty", "pass": True,
             "trial_outputs": ["garbage", "also garbage", '["tone-conflict"]']},
        ],
    }
    m = precision.contestant_metrics(cell, CASES, trials_expected=3)
    assert m["unparseable_trials"] == 2
    assert precision.full_coverage(m, case_count=1) is False


def test_gate_fails_closed_on_incomplete_evidence(tmp_path):
    results = {
        "skill": "test-skill",
        "trials": 3,
        "cells": [
            {"contestant": "original", "backend": "b", "passes": 3, "n": 3, "errors": 0,
             "cases": [
                 {"id": "d1", "kind": "dirty", "pass": True, "trial_outputs": ['["tone-conflict"]'] * 3},
                 {"id": "d2", "kind": "dirty", "pass": True, "trial_outputs": ['["autonomy-conflict"]'] * 3},
                 {"id": "c1", "kind": "clean", "pass": True, "trial_outputs": ["[]"] * 3},
             ]},
            {"contestant": "v1", "backend": "b", "passes": 3, "n": 3, "errors": 0,
             "cases": [
                 # missing one trial on d1 -> coverage failure for the winner
                 {"id": "d1", "kind": "dirty", "pass": True, "trial_outputs": ['["tone-conflict"]'] * 2},
                 {"id": "d2", "kind": "dirty", "pass": True, "trial_outputs": ['["autonomy-conflict"]'] * 3},
                 {"id": "c1", "kind": "clean", "pass": True, "trial_outputs": ["[]"] * 3},
             ]},
        ],
        "summary": {"winner": "v1"},
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))

    import sys

    argv = sys.argv
    sys.argv = ["precision.py", "--results", str(path), "--backend", "b"]
    try:
        import unittest.mock as mock

        with mock.patch.object(precision, "case_expect_map", return_value=CASES):
            rc = precision.main()
    finally:
        sys.argv = argv
    assert rc == 2
    report = json.loads((tmp_path / "precision.json").read_text())
    assert report["gate"]["coverage_failure"] == ["v1"]
    assert report["gate"]["eligible"] is False


def test_gate_exit_codes_fail_closed(tmp_path):
    # complete evidence but winner ties original -> INELIGIBLE -> exit 1
    def cell(cid, dirty_out):
        return {"contestant": cid, "backend": "b", "passes": 2, "n": 3, "errors": 0,
                "cases": [
                    {"id": "d1", "kind": "dirty", "pass": True, "trial_outputs": [dirty_out] * 3},
                    {"id": "d2", "kind": "dirty", "pass": False, "trial_outputs": ["[]"] * 3},
                    {"id": "c1", "kind": "clean", "pass": True, "trial_outputs": ["[]"] * 3},
                ]}

    results = {
        "skill": "test-skill", "trials": 3,
        "cells": [cell("original", '["tone-conflict"]'), cell("v1", '["tone-conflict"]')],
        "summary": {"winner": "v1"},
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))

    import sys
    import unittest.mock as mock

    argv = sys.argv
    sys.argv = ["precision.py", "--results", str(path), "--backend", "b"]
    try:
        with mock.patch.object(precision, "case_expect_map", return_value=CASES):
            rc = precision.main()
    finally:
        sys.argv = argv
    assert rc == 1  # not eligible, not a crash: fail closed for automation
