import json
from pathlib import Path

import pytest

from traj import run_benchmark


TASK = Path(__file__).resolve().parents[1] / "tasks" / "boundary-pagination"
FAKE_AGENT = Path(__file__).parent / "fake_agent.py"


def _run_fake(tmp_path, mode):
    command = f"{{python}} {FAKE_AGENT} --mode {mode} --patch {{solution_patch}}"
    run_benchmark.main([
        "--tasks", "boundary-pagination",
        "--arms", "baseline",
        "--trials", "1",
        "--out-dir", str(tmp_path),
        "--agent-cmd", command,
    ])
    return json.loads((tmp_path / "results.json").read_text())[0]


def test_fake_agent_that_applies_solution_passes(tmp_path):
    row = _run_fake(tmp_path, "solution")
    assert row["tests_pass"] is True
    assert row["reason"] == "passed"
    assert row["metrics"]["verified_after_last_edit"] is True


def test_fake_agent_that_does_nothing_fails(tmp_path):
    row = _run_fake(tmp_path, "nothing")
    assert row["tests_pass"] is False
    assert row["reason"] == "failed-tests"


def test_fake_agent_that_edits_tests_is_marked_tamper(tmp_path):
    row = _run_fake(tmp_path, "tamper")
    assert row["tests_pass"] is False
    assert row["reason"] == "test-tamper"


def test_refuses_to_run_inside_repo_root():
    with pytest.raises(ValueError, match="refusing to run agent"):
        run_benchmark.assert_safe_run_cwd(Path(__file__).resolve().parents[1])
