#!/usr/bin/env python3
import argparse
import tempfile
from pathlib import Path

try:
    from .common import apply_solution_patch, copy_repo, first_failure_line, load_task, repo_tree_hash, run_test_command, task_dirs
except ImportError:
    from common import apply_solution_patch, copy_repo, first_failure_line, load_task, repo_tree_hash, run_test_command, task_dirs


def validate_task(task_dir):
    task_dir = Path(task_dir)
    task = load_task(task_dir)
    command = task["test_command"]
    repo_hash = repo_tree_hash(task_dir / "repo")

    with tempfile.TemporaryDirectory(prefix=f"traj_validate_red_{task_dir.name}_") as tmp:
        cwd = copy_repo(task_dir, Path(tmp) / "repo")
        red = run_test_command(command, cwd)
        starts_red = red.returncode != 0
        failure = first_failure_line(red.stdout + "\n" + red.stderr) if starts_red else "tests unexpectedly passed"

    with tempfile.TemporaryDirectory(prefix=f"traj_validate_green_{task_dir.name}_") as tmp:
        cwd = copy_repo(task_dir, Path(tmp) / "repo")
        patch = apply_solution_patch(task_dir, cwd)
        first = run_test_command(command, cwd)
        second = run_test_command(command, cwd)
        patch_applied = patch.returncode == 0
        green_once = first.returncode == 0
        green_twice = second.returncode == 0

    ok = starts_red and patch_applied and green_once and green_twice
    return {
        "task": task_dir.name,
        "hash": repo_hash,
        "starts_red": starts_red,
        "patch_applied": patch_applied,
        "green_once": green_once,
        "green_twice": green_twice,
        "failure": failure,
        "ok": ok,
    }


def print_table(rows):
    print("task                         repo_sha256                                                       red  patch  green1  green2  first_failure")
    print("-" * 150)
    for row in rows:
        print(
            f"{row['task']:<28} {row['hash']}  "
            f"{_mark(row['starts_red']):<3}  {_mark(row['patch_applied']):<5}  "
            f"{_mark(row['green_once']):<6}  {_mark(row['green_twice']):<6}  {row['failure']}"
        )


def _mark(value):
    return "yes" if value else "no"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", help="comma-separated task ids")
    parser.add_argument("--tasks-dir", default=None)
    args = parser.parse_args(argv)
    task_ids = [part.strip() for part in args.tasks.split(",") if part.strip()] if args.tasks else None
    tasks_dir = args.tasks_dir or Path(__file__).resolve().parent / "tasks"
    rows = [validate_task(path) for path in task_dirs(tasks_dir, task_ids)]
    print_table(rows)
    failed = [row["task"] for row in rows if not row["ok"]]
    if failed:
        print(f"\nfailed: {', '.join(failed)}")
        return 1
    print(f"\nvalidated {len(rows)}/{len(rows)} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
