#!/usr/bin/env python3
import argparse
import csv
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from . import validate_app
except ImportError:
    import validate_app


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
APP_ROOT = ROOT / "total-tdd-app"
DEFAULT_OUT = REPO_ROOT / "out" / "total-tdd"
DEFAULT_AGENT_TIMEOUT = 2400
TEST_TIMEOUT = 60
TRACKER_HEADER = ["id", "area", "user_story", "expected_behavior", "source", "status", "issues", "fix", "verified"]
TRACKER_STATUSES = {"spec", "pass", "fail", "fixed", "verified"}
RESULT_STATUSES = {"resolved", "unresolved", "timeout", "infra_error"}


@dataclass(frozen=True)
class AgentResult:
    returncode: int | None
    timeout: bool
    stdout: str
    stderr: str


def path_is_under(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def assert_outside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if path_is_under(resolved, REPO_ROOT):
        raise ValueError(f"refusing temp workdir inside repository: {resolved}")
    return resolved


def copy_seeded_app(destination: Path) -> Path:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(APP_ROOT, destination, ignore=ignore)
    return destination


def load_manifest() -> dict:
    return validate_app.load_manifest(APP_ROOT / "defects.json")


def all_fail_to_pass(manifest: dict) -> set[str]:
    return validate_app.expected_failures(manifest)


def collect_tests(cwd: Path) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=TEST_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode not in (0, 5):
        raise RuntimeError((proc.stdout + proc.stderr).strip())
    nodeids = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("tests/") and "::" in stripped:
            nodeids.append(stripped)
    return nodeids


def test_file_for_nodeid(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def file_hashes(root: Path, rel_paths: set[str]) -> dict[str, str | None]:
    hashes = {}
    for rel in sorted(rel_paths):
        path = root / rel
        hashes[rel] = validate_app.sha256(path) if path.exists() else None
    return hashes


def run_nodeids(cwd: Path, nodeids: list[str]) -> validate_app.TestRun:
    if not nodeids:
        return validate_app.TestRun(0, set(), 0, "")
    return validate_app.run_pytest(cwd, nodeids=nodeids, timeout=TEST_TIMEOUT)


def read_tracker(path: Path) -> tuple[bool, list[dict], list[str]]:
    if not path.exists():
        return False, [], ["tracker.csv missing"]
    try:
        with path.open(newline="") as fh:
            rows = list(csv.reader(fh))
    except csv.Error as exc:
        return False, [], [f"csv parse error: {exc}"]
    if not rows:
        return False, [], ["tracker.csv empty"]
    errors = []
    if rows[0] != TRACKER_HEADER:
        errors.append(f"header drift: {rows[0]}")
    dict_rows = []
    for index, row in enumerate(rows[1:], start=2):
        if len(row) != len(TRACKER_HEADER):
            errors.append(f"row {index}: expected 9 columns, got {len(row)}")
        padded = row + [""] * (len(TRACKER_HEADER) - len(row))
        data = dict(zip(TRACKER_HEADER, padded[: len(TRACKER_HEADER)]))
        status = data.get("status", "").strip()
        if status not in TRACKER_STATUSES:
            errors.append(f"row {index}: bad status {status!r}")
        dict_rows.append(data)
    return not errors, dict_rows, errors


def row_text(row: dict) -> str:
    return " ".join(str(row.get(col, "")) for col in TRACKER_HEADER).casefold()


def rule_matches(text: str, rule: dict) -> bool:
    keywords = [term.casefold() for term in rule.get("keywords", [])]
    files = [term.casefold() for term in rule.get("files", [])]
    if keywords or files:
        return all(term in text for term in keywords) and all(term in text for term in files)
    all_terms = [term.casefold() for term in rule.get("all", [])]
    any_terms = [term.casefold() for term in rule.get("any", [])]
    keywords = [term.casefold() for term in rule.get("keywords", [])]
    files = [term.casefold() for term in rule.get("files", [])]
    if all_terms and not all(term in text for term in all_terms):
        return False
    if any_terms and not any(term in text for term in any_terms):
        return False
    if keywords and not all(term in text for term in keywords):
        return False
    if files and not all(term in text for term in files):
        return False
    return bool(all_terms or any_terms or keywords or files)


def defect_discovered(defect: dict, tracker_rows: list[dict]) -> bool:
    for row in tracker_rows:
        text = row_text(row)
        if any(rule_matches(text, rule) for rule in defect.get("match_rules", [])):
            return True
    return False


def match_defect(defect: dict, tracker_rows: list[dict]) -> bool:
    return defect_discovered(defect, tracker_rows)


def build_prompt(arm: str, skill_file: Path | None) -> str:
    task = (
        "Audit this application: find and fix all defects. Track your work in a CSV file at tracker.csv.\n\n"
        "Use exactly these tracker.csv columns: "
        + ",".join(TRACKER_HEADER)
        + "\nUse only these status values: spec, pass, fail, fixed, verified.\n"
        "Do not modify files under tests/. Fix application code only.\n"
        "Run the pytest suite before finishing and leave tracker.csv at the repository root.\n"
    )
    if arm == "baseline":
        return task
    if not skill_file:
        raise ValueError("skill_file is required for skill arm")
    return (
        "# total-tdd skill source\n\n"
        + skill_file.read_text()
        + "\n\n# Eval task override\n\n"
        + task
        + "\nFor this eval, tracker.csv at the repository root replaces docs/feature-audit.csv "
        "as the canonical CSV path so both arms are graded on the same file.\n"
    )


def write_prompt(out_dir: Path, arm: str, trial: int, prompt: str) -> Path:
    prompt_dir = out_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    path = prompt_dir / f"{arm}-{trial}.prompt.md"
    path.write_text(prompt)
    return path


def build_agent_command(cwd: Path, prompt_file: Path, agent_cmd: str | None) -> tuple[list[str] | str, bool, Path | None]:
    if agent_cmd:
        values = {
            "cwd": shlex.quote(str(cwd.resolve())),
            "prompt_file": shlex.quote(str(prompt_file.resolve())),
            "python": shlex.quote(sys.executable),
        }
        return agent_cmd.format(**values), True, None
    return ["codex", "exec", "--sandbox", "workspace-write", "-C", str(cwd.resolve()), "--", "-"], False, prompt_file


def run_agent(cwd: Path, prompt_file: Path, agent_cmd: str | None, timeout: int) -> AgentResult:
    command, shell, stdin_path = build_agent_command(cwd, prompt_file, agent_cmd)
    stdin_handle = stdin_path.open() if stdin_path else subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            shell=shell,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin_handle,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return AgentResult(proc.returncode, False, stdout, stderr)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            stdout, stderr = proc.communicate(timeout=10)
            return AgentResult(proc.returncode, True, stdout, stderr)
    finally:
        if stdin_path:
            stdin_handle.close()


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.2)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def redact(text: str, cwd: Path) -> str:
    redacted = text
    for before, after in {
        str(cwd.resolve()): "[temp-workdir]",
        str(REPO_ROOT.resolve()): "[repo]",
        str(Path.home()): "[home]",
    }.items():
        redacted = redacted.replace(before, after)
    for key, value in os.environ.items():
        if value and any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-[REDACTED]", redacted)
    return redacted


def write_trace(out_dir: Path, arm: str, trial: int, result: AgentResult, cwd: Path) -> tuple[Path, Path]:
    trace_dir = out_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = trace_dir / f"{arm}-{trial}.stdout"
    stderr_path = trace_dir / f"{arm}-{trial}.stderr"
    stdout_path.write_text(redact(result.stdout, cwd)[-20000:])
    stderr_path.write_text(redact(result.stderr, cwd)[-20000:])
    return stdout_path, stderr_path


def grade(cwd: Path, manifest: dict, before_test_hashes: dict[str, str | None]) -> dict:
    tracker_ok, tracker_rows, tracker_errors = read_tracker(cwd / "tracker.csv")
    after_test_hashes = file_hashes(cwd, set(before_test_hashes))
    modified_tests = sorted(rel for rel, before in before_test_hashes.items() if after_test_hashes.get(rel) != before)
    all_tests = collect_tests(cwd)
    fail_to_pass = all_fail_to_pass(manifest)
    regression_nodeids = [nodeid for nodeid in all_tests if nodeid not in fail_to_pass]
    regression_run = run_nodeids(cwd, regression_nodeids)
    regressions = len(regression_run.failed)

    per_defect = {}
    for defect in manifest["defects"]:
        nodeids = list(defect["fail_to_pass"])
        defect_test_files = {test_file_for_nodeid(nodeid) for nodeid in nodeids}
        integrity_ok = not any(rel in modified_tests for rel in defect_test_files)
        fix_run = run_nodeids(cwd, nodeids)
        per_defect[defect["id"]] = {
            "discovered": defect_discovered(defect, tracker_rows),
            "fixed": integrity_ok and fix_run.returncode == 0 and not fix_run.failed,
            "integrity_ok": integrity_ok,
        }
    return {
        "tracker_ok": tracker_ok,
        "tracker_errors": tracker_errors,
        "modified_tests": modified_tests,
        "regressions": regressions,
        "per_defect": per_defect,
    }


def result_fieldnames(manifest: dict) -> list[str]:
    fields = [
        "arm",
        "trial",
        "status",
        "duration_s",
        "agent_returncode",
        "conformance_ok",
        "regressions",
        "tests_modified",
        "fixed_count",
        "discovered_count",
        "stdout_path",
        "stderr_path",
        "temp_path",
        "conformance_errors",
    ]
    for defect in manifest["defects"]:
        fields.extend([f"{defect['id']}_discovered", f"{defect['id']}_fixed", f"{defect['id']}_integrity_ok"])
    return fields


def flatten_row(row: dict, manifest: dict) -> dict:
    flat = {key: row.get(key, "") for key in result_fieldnames(manifest)}
    per_defect = row.get("per_defect", {})
    for defect in manifest["defects"]:
        values = per_defect.get(defect["id"], {})
        flat[f"{defect['id']}_discovered"] = str(bool(values.get("discovered"))).lower()
        flat[f"{defect['id']}_fixed"] = str(bool(values.get("fixed"))).lower()
        flat[f"{defect['id']}_integrity_ok"] = str(bool(values.get("integrity_ok"))).lower()
    flat["tests_modified"] = ";".join(row.get("tests_modified", []))
    flat["conformance_errors"] = "; ".join(row.get("conformance_errors", []))
    flat["conformance_ok"] = str(bool(row.get("conformance_ok"))).lower()
    return flat


def append_csv(path: Path, row: dict, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=result_fieldnames(manifest))
        if not exists:
            writer.writeheader()
        writer.writerow(flatten_row(row, manifest))


def _run_one_csv(arm: str, trial: int, skill_file: Path | None, out_dir: Path, agent_cmd: str | None, timeout: int) -> dict:
    manifest = load_manifest()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"total_tdd_{arm}_{trial}_") as tmp:
        temp_root = assert_outside_repo(Path(tmp))
        cwd = copy_seeded_app(temp_root / "app")
        test_files = {test_file_for_nodeid(nodeid) for nodeid in collect_tests(cwd)}
        before_test_hashes = file_hashes(cwd, test_files)
        prompt_file = write_prompt(out_dir, arm, trial, build_prompt(arm, skill_file))
        agent_result = run_agent(cwd, prompt_file, agent_cmd, timeout)
        stdout_path, stderr_path = write_trace(out_dir, arm, trial, agent_result, cwd)
        if agent_result.timeout:
            status = "timeout"
            grade_result = {"tracker_ok": False, "tracker_errors": ["agent timeout"], "modified_tests": [], "regressions": 0, "per_defect": {}}
        elif agent_result.returncode not in (0, None):
            status = "infra_error"
            grade_result = {"tracker_ok": False, "tracker_errors": [f"agent exited {agent_result.returncode}"], "modified_tests": [], "regressions": 0, "per_defect": {}}
        else:
            grade_result = grade(cwd, manifest, before_test_hashes)
            fixed_count = sum(1 for item in grade_result["per_defect"].values() if item["fixed"])
            status = "resolved" if fixed_count >= 6 and grade_result["regressions"] == 0 else "unresolved"
        per_defect = grade_result["per_defect"]
        row = {
            "arm": arm,
            "trial": trial,
            "status": status,
            "duration_s": f"{time.monotonic() - started:.3f}",
            "agent_returncode": "" if agent_result.returncode is None else agent_result.returncode,
            "conformance_ok": grade_result["tracker_ok"],
            "regressions": grade_result["regressions"],
            "tests_modified": grade_result["modified_tests"],
            "fixed_count": sum(1 for item in per_defect.values() if item.get("fixed")),
            "discovered_count": sum(1 for item in per_defect.values() if item.get("discovered")),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "temp_path": "[temp-workdir]",
            "conformance_errors": grade_result["tracker_errors"],
            "per_defect": per_defect,
        }
    append_csv(out_dir / "results.csv", row, manifest)
    return row


def run_one(*args, **kwargs) -> dict:
    if args and isinstance(args[0], (str,)):
        return _run_one_csv(*args, **kwargs)
    app_root, arm, trial, skill_file, out_dir, agent_cmd = args[:6]
    timeout = kwargs.pop("timeout_s", kwargs.pop("timeout", DEFAULT_AGENT_TIMEOUT))
    old = _run_one_csv(arm, trial, skill_file, Path(out_dir), agent_cmd, timeout)
    return {
        "arm": old["arm"],
        "trial": old["trial"],
        "status": old["status"],
        "resolved": old["status"] == "resolved",
        "duration_s": float(old["duration_s"]),
        "timeout": old["status"] == "timeout",
        "conformance": old["conformance_ok"],
        "conformance_reason": "; ".join(old["conformance_errors"]),
        "tests_modified": bool(old["tests_modified"]),
        "discovered_count": old["discovered_count"],
        "fixed_count": old["fixed_count"],
        "regressions": old["regressions"],
        "pass_to_pass_count": 37,
        "defects": {
            defect_id: {
                "discovered": values["discovered"],
                "fixed": values["fixed"],
                "integrity_blocked": not values["integrity_ok"],
                "test_output": "",
            }
            for defect_id, values in old["per_defect"].items()
        },
        "trace_path": old["stdout_path"],
        "stderr_path": old["stderr_path"],
        "temp_path": old["temp_path"],
    }


def grade_workdir(workdir: Path, manifest: dict, pristine_tests_hash: str, *, python: str = sys.executable) -> dict:
    tracker_ok, tracker_rows, tracker_errors = read_tracker(workdir / "tracker.csv")
    tests_modified = _tree_hash(workdir / "tests") != pristine_tests_hash
    all_tests = collect_tests(workdir)
    defect_tests = all_fail_to_pass(manifest)
    pass_to_pass = [nodeid for nodeid in all_tests if nodeid not in defect_tests]
    regression_run = run_nodeids(workdir, pass_to_pass)
    defects = {}
    for defect in manifest["defects"]:
        fix_run = run_nodeids(workdir, list(defect["fail_to_pass"]))
        fixed = fix_run.returncode == 0 and not fix_run.failed and not tests_modified
        defects[defect["id"]] = {
            "discovered": tracker_ok and defect_discovered(defect, tracker_rows),
            "fixed": fixed,
            "integrity_blocked": tests_modified,
            "test_output": "" if fixed else fix_run.output,
        }
    return {
        "conformance": tracker_ok,
        "conformance_reason": "; ".join(tracker_errors),
        "tests_modified": tests_modified,
        "defects": defects,
        "discovered_count": sum(1 for item in defects.values() if item["discovered"]),
        "fixed_count": sum(1 for item in defects.values() if item["fixed"]),
        "regressions": len(regression_run.failed),
        "pass_to_pass_count": len(pass_to_pass),
    }


def _tree_hash(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        if "__pycache__" in item.parts or item.name.endswith(".pyc"):
            continue
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def tree_hash(path: Path) -> str:
    return _tree_hash(path)


def parse_csv_arg(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", default="baseline,skill")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--skill-file", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--agent-cmd")
    parser.add_argument("--timeout", type=int, default=DEFAULT_AGENT_TIMEOUT)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    arms = parse_csv_arg(args.arms, ["baseline", "skill"])
    unknown = sorted(set(arms) - {"baseline", "skill"})
    if unknown:
        raise SystemExit(f"unknown arms: {', '.join(unknown)}")
    if args.smoke:
        arms = [arms[0] if arms else "baseline"]
        args.trials = 1
    if "skill" in arms:
        if not args.skill_file:
            raise SystemExit("--skill-file is required for the skill arm")
        if not args.skill_file.exists():
            raise SystemExit(f"skill file not found: {args.skill_file}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for trial in range(1, max(1, args.trials) + 1):
        for arm in arms:
            row = _run_one_csv(arm, trial, args.skill_file, args.out_dir, args.agent_cmd, args.timeout)
            if row["status"] not in RESULT_STATUSES:
                raise AssertionError(f"bad result status: {row['status']}")
            print(f"{arm} trial={trial} status={row['status']} fixed={row['fixed_count']}/8 discovered={row['discovered_count']}/8")
    print(f"wrote {args.out_dir / 'results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
