#!/usr/bin/env python3
import hashlib
import shutil
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
TASKS_DIR = ROOT / "tasks"
DEFAULT_TEST_COMMAND = "python -m pytest tests/ -x -q"


def task_dirs(tasks_dir=TASKS_DIR, task_ids=None):
    wanted = set(task_ids or [])
    dirs = [path for path in Path(tasks_dir).iterdir() if (path / "task.toml").exists()]
    selected = [path for path in sorted(dirs, key=lambda p: p.name) if not wanted or path.name in wanted]
    missing = wanted - {path.name for path in selected}
    if missing:
        raise ValueError(f"unknown task ids: {', '.join(sorted(missing))}")
    return selected


def load_task(task_dir):
    with (Path(task_dir) / "task.toml").open("rb") as fh:
        data = tomllib.load(fh)
    data.setdefault("test_command", DEFAULT_TEST_COMMAND)
    return data


def repo_tree_hash(repo_dir):
    repo_dir = Path(repo_dir)
    digest = hashlib.sha256()
    for path in sorted(p for p in repo_dir.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts or path.name.endswith(".pyc"):
            continue
        rel = path.relative_to(repo_dir).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def copy_repo(task_dir, destination):
    source = Path(task_dir) / "repo"
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def run_test_command(command, cwd, timeout=60):
    args = shlex.split(command)
    if args and args[0] == "python":
        args[0] = sys.executable
    return subprocess.run(
        args,
        cwd=Path(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def apply_solution_patch(task_dir, cwd):
    patch_path = Path(task_dir) / "solution" / "fix.patch"
    return subprocess.run(
        ["patch", "-p0", "-i", str(patch_path)],
        cwd=Path(cwd),
        capture_output=True,
        text=True,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )


def first_failure_line(output):
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED ") or stripped.startswith("E "):
            return stripped[:160]
    return "failed"


def path_is_under(path, parent):
    path = Path(path).resolve()
    parent = Path(parent).resolve()
    return path == parent or parent in path.parents
