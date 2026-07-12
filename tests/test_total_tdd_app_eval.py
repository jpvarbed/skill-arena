from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from apps import run_total_tdd, validate_app
from apps.report_total_tdd import build_report


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "total-tdd-app"
FAKE_AGENT = ROOT / "tests" / "fixtures" / "total_tdd_fake_agent.py"


def test_validator_logic_on_fixture_mini_app(tmp_path):
    app = tmp_path / "mini"
    (app / "tests").mkdir(parents=True)
    (app / "mini.py").write_text("def value():\n    return 1\n")
    (app / "tests" / "test_mini.py").write_text(
        "from mini import value\n\n"
        "def test_bug():\n    assert value() == 2\n\n"
        "def test_ok():\n    assert value() == 1\n"
    )
    manifest = {
        "defects": [
            {
                "id": "M001",
                "category": "mini",
                "fail_to_pass": ["tests/test_mini.py::test_bug"],
                "solution_patch": "solutions/fix.patch",
            }
        ]
    }

    rows, errors = validate_app.validate_seeded_tree(app, manifest, python=os.sys.executable)

    assert errors == []
    assert rows[0].seeded_failed is True


def test_discovery_match_rules_require_keywords_and_file_refs():
    defect = {
        "match_rules": [
            {"keywords": ["late", "fee"], "files": ["shelfd/fees.py"]},
        ]
    }
    rows = [{"issues": "late fee is short", "source": "shelfd/fees.py"}]

    assert run_total_tdd.match_defect(defect, rows) is True
    assert run_total_tdd.match_defect(defect, [{"issues": "late fee is short", "source": "shelfd/io.py"}]) is False


def test_patch_application_on_fixture_mini_app(tmp_path):
    app = tmp_path / "mini"
    (app / "solutions").mkdir(parents=True)
    (app / "mini.py").write_text("def value():\n    return 1\n")
    patch = app / "solutions" / "fix.patch"
    patch.write_text(
        "--- mini.py\n"
        "+++ mini.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def value():\n"
        "-    return 1\n"
        "+    return 2\n"
    )

    proc = validate_app.apply_patch(app, patch)

    assert proc.returncode == 0
    assert "return 2" in (app / "mini.py").read_text()


def test_integrity_blocks_defect_fix_when_tests_change(tmp_path):
    workdir = tmp_path / "app"
    shutil.copytree(APP, workdir)
    for patch in sorted((workdir / "solutions").glob("*.patch")):
        assert subprocess.run(["patch", "-p0", "-i", str(patch)], cwd=workdir).returncode == 0
    pristine_hash = run_total_tdd.tree_hash(workdir / "tests")
    (workdir / "tests" / "test_catalog.py").write_text((workdir / "tests" / "test_catalog.py").read_text() + "\n# changed\n")
    manifest = validate_app.load_manifest(workdir)
    (workdir / "tracker.csv").write_text(
        ",".join(run_total_tdd.TRACKER_HEADER)
        + "\nD001,catalog,author case,expected,shelfd/catalog.py,fixed,issue,fix,evidence\n"
    )

    grade = run_total_tdd.grade_workdir(workdir, manifest, pristine_hash, python=os.sys.executable)

    assert grade["tests_modified"] is True
    assert grade["defects"]["D001"]["fixed"] is False


def test_runner_row_shape_with_fake_agent_and_redaction(tmp_path):
    command = f"{{python}} {FAKE_AGENT} --mode solution --prompt {{prompt_file}}"

    row = run_total_tdd.run_one(
        APP,
        "baseline",
        1,
        None,
        tmp_path / "out",
        command,
        timeout_s=30,
    )

    assert row["status"] == "resolved"
    assert row["fixed_count"] == 8
    assert row["discovered_count"] == 8
    assert row["regressions"] == 0
    assert row["conformance"] is True
    assert set(row["defects"]) == {f"D{idx:03d}" for idx in range(1, 9)}
    assert "sk-testsecret" not in Path(row["trace_path"]).read_text()


def test_runner_timeout_status_with_fake_agent(tmp_path):
    command = f"{{python}} {FAKE_AGENT} --mode sleep --prompt {{prompt_file}}"

    row = run_total_tdd.run_one(
        APP,
        "baseline",
        1,
        None,
        tmp_path / "out",
        command,
        timeout_s=1,
    )

    assert row["status"] == "timeout"
    assert row["timeout"] is True


def test_report_documents_band_and_match_rules(tmp_path):
    rows = [
        {
            "arm": "baseline",
            "status": "unresolved",
            "duration_s": 1.0,
            "discovered_count": 7,
            "fixed_count": 0,
            "regressions": 0,
            "conformance": True,
            "defects": {f"D{idx:03d}": {"discovered": idx <= 7, "fixed": False, "integrity_blocked": False} for idx in range(1, 9)},
        }
    ]
    results = tmp_path / "results.json"
    results.write_text(json.dumps(rows))

    report = build_report(results, APP)

    assert "TRIPPED" in report
    assert "baseline discovery above 80%" in report
    assert "`D001` discovery match" in report
