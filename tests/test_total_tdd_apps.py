import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path

from apps import report_total_tdd, run_total_tdd, validate_app


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "apps" / "total-tdd-app"


def copy_app(tmp_path):
    return validate_app.copy_app(tmp_path / "app", APP_ROOT)


def write_tracker(path, rows):
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(run_total_tdd.TRACKER_HEADER)
        writer.writerows(rows)


def test_manifest_defines_exact_seeded_failures():
    manifest = validate_app.load_manifest()

    assert len(manifest["defects"]) == 8
    assert validate_app.expected_failures(manifest) == {
        "tests/test_audit_cli.py::test_audit_keeps_checkout_and_return_events_for_same_book_member",
        "tests/test_catalog.py::test_author_filter_is_case_insensitive",
        "tests/test_circulation.py::test_checkout_accepts_iso_due_date_through_api",
        "tests/test_circulation.py::test_late_fee_charges_each_late_day",
        "tests/test_circulation.py::test_overdue_loans_are_repeatable_queries",
        "tests/test_circulation.py::test_reserved_book_cannot_be_renewed_to_avoid_late_fee",
        "tests/test_io.py::test_import_loans_enforces_member_limits",
        "tests/test_members.py::test_member_limit_blocks_fourth_checkout",
    }


def test_validator_hash_logic_on_fixture_mini_app(tmp_path):
    app = tmp_path / "mini"
    app.mkdir()
    (app / "module.py").write_text("VALUE = 1\n")
    manifest = {"defects": [], "hashes": {"module.py": validate_app.sha256(app / "module.py")}}

    assert validate_app.check_manifest_hashes(app, manifest) == []

    (app / "module.py").write_text("VALUE = 2\n")

    assert validate_app.check_manifest_hashes(app, manifest)


def test_seeded_app_validation_succeeds():
    code, output = validate_app.validate()

    assert code == 0, output
    assert "VALID" in output
    assert "seeded pass counts: 37, 37" in output


def test_oracle_patch_application_fixes_targeted_test(tmp_path):
    app = copy_app(tmp_path)
    manifest = validate_app.load_manifest()
    defect = manifest["defects"][0]

    proc = validate_app.apply_patch(app, app / validate_app.defect_patch(defect))
    run = validate_app.run_pytest(app, defect["fail_to_pass"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert run.returncode == 0, run.output


def test_discovery_match_rules_use_tracker_rows():
    manifest = validate_app.load_manifest()
    rows = [
        {
            "id": "F1",
            "area": "search",
            "user_story": "author search",
            "expected_behavior": "author filter should ignore case",
            "source": "",
            "status": "fail",
            "issues": "case mismatch",
            "fix": "",
            "verified": "",
        }
    ]

    assert run_total_tdd.defect_discovered(manifest["defects"][0], rows)
    assert not run_total_tdd.defect_discovered(manifest["defects"][1], rows)


def test_tracker_conformance_rejects_bad_schema(tmp_path):
    tracker = tmp_path / "tracker.csv"
    tracker.write_text("id,status\nF1,done\n")

    ok, rows, errors = run_total_tdd.read_tracker(tracker)

    assert not ok
    assert rows
    assert any("header drift" in error for error in errors)
    assert any("bad status" in error for error in errors)


def test_integrity_path_blocks_fix_credit_when_test_file_changes(tmp_path):
    app = copy_app(tmp_path)
    manifest = validate_app.load_manifest()
    d001 = manifest["defects"][0]
    test_files = {run_total_tdd.test_file_for_nodeid(nodeid) for nodeid in run_total_tdd.collect_tests(app)}
    before_hashes = run_total_tdd.file_hashes(app, test_files)
    validate_app.apply_patch(app, app / validate_app.defect_patch(d001))
    (app / "tests" / "test_catalog.py").write_text((app / "tests" / "test_catalog.py").read_text() + "\n# tampered\n")
    write_tracker(
        app / "tracker.csv",
        [["F1", "catalog", "author search", "author filter ignores case", "shelfd/catalog.py", "fixed", "", "casefold author", "pytest"]],
    )

    grade = run_total_tdd.grade(app, manifest, before_hashes)

    assert grade["per_defect"]["D001"]["discovered"] is True
    assert grade["per_defect"]["D001"]["integrity_ok"] is False
    assert grade["per_defect"]["D001"]["fixed"] is False
    assert grade["modified_tests"] == ["tests/test_catalog.py"]


def make_fake_agent(tmp_path, patch_ids):
    script = tmp_path / "fake_agent.py"
    script.write_text(
        """
import argparse
import csv
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--cwd", required=True)
args = parser.parse_args()
cwd = Path(args.cwd)
patches = {
    "D001": "D001-author-filter-case.patch",
    "D002": "D002-late-fee-all-days.patch",
    "D003": "D003-api-due-date-contract.patch",
    "D004": "D004-member-limit-boundary.patch",
    "D005": "D005-overdue-query-state-leak.patch",
    "D006": "D006-reservation-renewal.patch",
    "D007": "D007-import-loan-member-limit.patch",
    "D008": "D008-audit-interleaving.patch",
}
for defect_id in PATCH_IDS:
    subprocess.run(["patch", "-p0", "-i", str(cwd / "solutions" / patches[defect_id])], cwd=cwd, check=True)
rows = [
    ["F1", "catalog", "As a librarian, I search authors.", "author filter ignores case", "shelfd/catalog.py", "fixed", "author case failed", "casefold", "pytest"],
    ["F2", "fees", "As a librarian, I charge fees.", "late fee counts every late day", "shelfd/fees.py", "fixed", "late fee undercharged", "fee math", "pytest"],
    ["F3", "circulation", "As an API user, I pass ISO due dates.", "due date string parses", "shelfd/circulation.py", "fixed", "due iso type error", "parse due", "pytest"],
    ["F4", "members", "As a member, I respect limits.", "member limit blocks fourth", "shelfd/members.py", "fixed", "member limit boundary", "gte", "pytest"],
    ["F5", "circulation", "As a librarian, I query overdue loans.", "overdue query repeatable", "shelfd/circulation.py", "fixed", "mutable default state leak", "new list", "pytest"],
    ["F6", "reservations", "As a reserver, I wait in queue.", "renew reservation waiting blocked", "shelfd/circulation.py", "fixed", "renew reservation bug", "guard", "pytest"],
    ["F7", "io", "As an importer, I enforce loan limits.", "csv import loan member max_loans limit", "shelfd/io.py", "fail", "import loan member limit bypass", "", "pytest"],
    ["F8", "audit", "As an auditor, I see checkout and return.", "checkout return audit events both remain", "shelfd/audit.py", "fail", "audit return missing", "", "pytest"],
]
with (cwd / "tracker.csv").open("w", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["id", "area", "user_story", "expected_behavior", "source", "status", "issues", "fix", "verified"])
    writer.writerows(rows)
""".replace("PATCH_IDS", repr(patch_ids))
    )
    return script


def test_runner_row_shape_with_fake_agent(tmp_path):
    fake = make_fake_agent(tmp_path, ["D001", "D002", "D003", "D004", "D005", "D006"])
    out_dir = tmp_path / "out"
    row = run_total_tdd.run_one(
        "baseline",
        1,
        None,
        out_dir,
        f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))} --cwd {{cwd}}",
        timeout=20,
    )

    assert row["status"] == "resolved"
    assert row["fixed_count"] == 6
    assert row["discovered_count"] == 8
    assert row["conformance_ok"] is True
    assert row["regressions"] == 0

    result_rows = list(csv.DictReader((out_dir / "results.csv").open()))
    assert result_rows[0]["status"] == "resolved"
    assert result_rows[0]["D001_discovered"] == "true"
    assert result_rows[0]["D006_fixed"] == "true"
    assert result_rows[0]["D007_fixed"] == "false"
    assert result_rows[0]["temp_path"] == "[temp-workdir]"


def test_report_renders_discovery_band_verdict(tmp_path):
    manifest = validate_app.load_manifest()
    results = tmp_path / "results.csv"
    fields = run_total_tdd.result_fieldnames(manifest)
    with results.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        row = {field: "" for field in fields}
        row.update({"arm": "baseline", "trial": "1", "status": "unresolved", "duration_s": "1.0", "conformance_ok": "true", "regressions": "0"})
        for defect in manifest["defects"]:
            row[f"{defect['id']}_discovered"] = "true"
            row[f"{defect['id']}_fixed"] = "false"
            row[f"{defect['id']}_integrity_ok"] = "true"
        writer.writerow(row)

    report = report_total_tdd.render_report(list(csv.DictReader(results.open())), manifest)

    assert "baseline discovery band verdict is **TRIPPED**" in report
    assert "Resolved threshold" in report
    assert "Metrics Definitions" in report
