#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT / "total-tdd-app"
MANIFEST = APP_ROOT / "defects.json"
PYTEST_TIMEOUT = 60


@dataclass(frozen=True)
class TestRun:
    returncode: int
    failed: set[str]
    passed_count: int
    output: str


def load_manifest(path: Path = MANIFEST) -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / "defects.json"
    manifest = json.loads(path.read_text())
    for defect in manifest.get("defects", []):
        if "oracle_patch" not in defect and "solution_patch" in defect:
            defect["oracle_patch"] = defect["solution_patch"]
        if "solution_patch" not in defect and "oracle_patch" in defect:
            defect["solution_patch"] = defect["oracle_patch"]
    return manifest


def defects(manifest: dict) -> list[dict]:
    return list(manifest["defects"])


def expected_failures(manifest: dict) -> set[str]:
    return {node for defect in defects(manifest) for node in defect["fail_to_pass"]}


def fail_to_pass_tests(manifest: dict) -> list[str]:
    return sorted(expected_failures(manifest))


def run_pytest_completed(app_root: Path, args: list[str], *, python: str = sys.executable, timeout: int = PYTEST_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [python, "-m", "pytest", *args],
        cwd=app_root,
        text=True,
        capture_output=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def collect_tests(app_root: Path, python: str = sys.executable) -> list[str]:
    proc = run_pytest_completed(app_root, ["--collect-only", "-q"], python=python)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    tests = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if "::test_" not in stripped:
            continue
        if stripped.startswith("tests/"):
            tests.append(stripped)
        elif "/tests/" in stripped:
            tests.append("tests/" + stripped.split("/tests/", 1)[1])
    return sorted(tests)


@dataclass(frozen=True)
class DefectResult:
    defect_id: str
    category: str
    seeded_failed: bool
    oracle_patch: str


def validate_seeded_tree(app_root: Path, manifest: dict, *, python: str = sys.executable) -> tuple[list[DefectResult], list[str]]:
    all_tests = set(collect_tests(app_root, python=python))
    expected = set(fail_to_pass_tests(manifest))
    errors = []
    missing = expected - all_tests
    if missing:
        errors.append(f"manifest references unknown tests: {', '.join(sorted(missing))}")
    pass_tests = sorted(all_tests - expected)
    rows = []
    for defect in defects(manifest):
        failed = True
        for nodeid in defect["fail_to_pass"]:
            proc = run_pytest_completed(app_root, [nodeid, "-q"], python=python)
            if proc.returncode == 0:
                failed = False
                errors.append(f"{defect['id']} expected failing test passed: {nodeid}")
        rows.append(DefectResult(defect["id"], defect["category"], failed, defect.get("solution_patch") or defect.get("oracle_patch", "")))
    for run_index in (1, 2):
        proc = run_pytest_completed(app_root, [*pass_tests, "-q"], python=python, timeout=180)
        if proc.returncode != 0:
            errors.append(f"seeded pass-to-pass run {run_index} failed:\n{proc.stdout + proc.stderr}")
    return rows, errors


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest_hashes(app_root: Path, manifest: dict) -> list[str]:
    problems = []
    hashes = manifest.get("hashes", {})
    if "files" in hashes:
        hashes = hashes["files"]
    for rel, expected in sorted(hashes.items()):
        path = app_root / rel
        if not path.exists():
            problems.append(f"{rel}: missing")
            continue
        actual = sha256(path)
        if actual != expected:
            problems.append(f"{rel}: {actual} != {expected}")
    return problems


def copy_app(destination: Path, source: Path = APP_ROOT) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(source, destination, ignore=ignore)
    return destination


def run_pytest(app_root: Path, nodeids: list[str] | None = None, timeout: int = PYTEST_TIMEOUT) -> TestRun:
    args = [sys.executable, "-m", "pytest"]
    args.extend(nodeids or ["tests"])
    args.append("-q")
    proc = subprocess.run(
        args,
        cwd=app_root,
        text=True,
        capture_output=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    output = proc.stdout + proc.stderr
    return TestRun(proc.returncode, parse_failed_nodeids(output), parse_passed_count(output), output)


def parse_failed_nodeids(output: str) -> set[str]:
    failed = set()
    for line in output.splitlines():
        if line.startswith("FAILED "):
            nodeid = line.split()[1]
            if nodeid.startswith("tests/"):
                failed.add(nodeid)
            elif "/tests/" in nodeid:
                failed.add("tests/" + nodeid.split("/tests/", 1)[1])
            else:
                failed.add(nodeid)
    return failed


def parse_passed_count(output: str) -> int:
    for line in reversed(output.splitlines()):
        if " passed" in line or " failed" in line:
            parts = line.replace(",", "").split()
            for index, part in enumerate(parts):
                if part == "passed" and index > 0 and parts[index - 1].isdigit():
                    return int(parts[index - 1])
    return 0


def apply_patch(app_root: Path, patch_path: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["patch", "-p0", "-i", str(patch_path.resolve())],
        cwd=app_root,
        text=True,
        capture_output=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def defect_patch(defect: dict) -> str:
    return defect.get("oracle_patch") or defect["solution_patch"]


def apply_oracle_patches(app_root: Path, manifest: dict) -> list[str]:
    problems = []
    for defect in defects(manifest):
        patch_path = app_root / defect_patch(defect)
        proc = apply_patch(app_root, patch_path)
        if proc.returncode != 0:
            problems.append(f"{defect['id']}: patch failed: {(proc.stdout + proc.stderr).strip()}")
    return problems


def validate_seeded_red(app_root: Path, manifest: dict) -> tuple[bool, list[TestRun]]:
    expected = expected_failures(manifest)
    runs = [run_pytest(app_root), run_pytest(app_root)]
    ok = all(run.failed == expected and run.passed_count == 37 for run in runs)
    return ok, runs


def validate_oracle_green(manifest: dict, source: Path = APP_ROOT) -> tuple[bool, TestRun, list[str]]:
    with tempfile.TemporaryDirectory(prefix="total_tdd_oracle_") as tmp:
        app = copy_app(Path(tmp) / "app", source)
        patch_problems = apply_oracle_patches(app, manifest)
        if patch_problems:
            return False, TestRun(1, set(), 0, "\n".join(patch_problems)), patch_problems
        run = run_pytest(app)
        return run.returncode == 0 and not run.failed, run, []


def defect_table(manifest: dict, seeded_runs: list[TestRun], oracle_run: TestRun) -> str:
    lines = ["id   category              fail_to_pass  seeded  oracle"]
    seeded_failed = seeded_runs[0].failed if seeded_runs else set()
    for defect in defects(manifest):
        tests = set(defect["fail_to_pass"])
        seeded = "red" if tests <= seeded_failed else "miss"
        oracle = "green" if not (tests & oracle_run.failed) and oracle_run.returncode == 0 else "fail"
        lines.append(f"{defect['id']:<4} {defect['category']:<21} {len(tests):<12} {seeded:<7} {oracle}")
    return "\n".join(lines)


def validate(app_root: Path = APP_ROOT, manifest_path: Path | None = None) -> tuple[int, str]:
    manifest_path = manifest_path or (app_root / "defects.json")
    manifest = load_manifest(manifest_path)
    problems = []
    if len(defects(manifest)) != 8:
        problems.append(f"manifest has {len(defects(manifest))} defects, expected 8")
    problems.extend(f"hash {problem}" for problem in check_manifest_hashes(app_root, manifest))
    seeded_ok, seeded_runs = validate_seeded_red(app_root, manifest)
    if not seeded_ok:
        expected = sorted(expected_failures(manifest))
        actual = [sorted(run.failed) for run in seeded_runs]
        problems.append(f"seeded red mismatch: expected {expected}, got {actual}")
    oracle_ok, oracle_run, patch_problems = validate_oracle_green(manifest, app_root)
    problems.extend(patch_problems)
    if not oracle_ok:
        problems.append("oracle suite did not go green")
    table = defect_table(manifest, seeded_runs, oracle_run)
    status = "VALID" if not problems else "INVALID"
    details = [status, table]
    if seeded_runs:
        details.append(f"seeded pass counts: {', '.join(str(run.passed_count) for run in seeded_runs)}")
    details.append(f"oracle returncode: {oracle_run.returncode}")
    if problems:
        details.append("problems:")
        details.extend(f"- {problem}" for problem in problems)
    return (0 if not problems else 1), "\n".join(details)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=APP_ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    code, output = validate(args.app_root, args.manifest)
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
