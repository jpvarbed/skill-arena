#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    from .common import DEFAULT_TEST_COMMAND, REPO_ROOT, ROOT, copy_repo, load_task, path_is_under, repo_tree_hash, run_test_command, task_dirs
    from .scorers import score_transcript
except ImportError:
    from common import DEFAULT_TEST_COMMAND, REPO_ROOT, ROOT, copy_repo, load_task, path_is_under, repo_tree_hash, run_test_command, task_dirs
    from scorers import score_transcript


DEFAULT_ARMS = ["baseline", "skill"]
TIMEOUT_S = 600
MAX_WORKERS = 3


def assert_safe_run_cwd(cwd, repo_root=REPO_ROOT):
    cwd = Path(cwd).resolve()
    repo_root = Path(repo_root).resolve()
    if path_is_under(cwd, repo_root):
        raise ValueError(f"refusing to run agent inside repository: {cwd}")
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"run cwd does not exist: {cwd}")
    return cwd


def run_one(task_dir, arm, trial, skill_file, out_dir, agent_cmd=None):
    task_dir = Path(task_dir)
    out_dir = Path(out_dir)
    task = load_task(task_dir)
    instruction = (task_dir / "instruction.md").read_text()
    trace_path = out_dir / "traces" / f"{task_dir.name}_{arm}_{trial}.jsonl"
    stderr_path = out_dir / "traces" / f"{task_dir.name}_{arm}_{trial}.stderr"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    tests_pass = False
    timeout = False
    reason = "failed-tests"
    test_output = ""
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix=f"traj_{task_dir.name}_{arm}_{trial}_") as tmp:
        cwd = copy_repo(task_dir, Path(tmp) / "repo")
        assert_safe_run_cwd(cwd)
        pristine_tests_hash = repo_tree_hash(cwd / "tests")
        command = build_agent_command(
            instruction=instruction,
            arm=arm,
            skill_file=skill_file,
            task_dir=task_dir,
            cwd=cwd,
            trial=trial,
            agent_cmd=agent_cmd,
        )
        with trace_path.open("w") as stdout, stderr_path.open("w") as stderr:
            proc = subprocess.Popen(
                command["args"],
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                text=True,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                shell=command["shell"],
            )
            try:
                proc.wait(timeout=TIMEOUT_S)
            except subprocess.TimeoutExpired:
                timeout = True
                reason = "timeout"
                _kill_process_group(proc)
                proc.wait(timeout=10)

        if not timeout:
            tests = run_test_command(task.get("test_command", DEFAULT_TEST_COMMAND), cwd)
            test_output = tests.stdout + "\n" + tests.stderr
            tests_pass = tests.returncode == 0
            reason = "passed" if tests_pass else "failed-tests"
            if repo_tree_hash(cwd / "tests") != pristine_tests_hash:
                tests_pass = False
                reason = "test-tamper"

        temp_path = str(cwd.resolve())

    metrics = score_transcript(trace_path)
    return {
        "task": task_dir.name,
        "arm": arm,
        "trial": trial,
        "tests_pass": tests_pass,
        "timeout": timeout,
        "reason": reason,
        "duration_s": round(time.monotonic() - started, 3),
        "metrics": metrics,
        "transcript_path": str(trace_path),
        "temp_path": temp_path,
        "test_output": _compact_output(test_output),
    }


def build_agent_command(instruction, arm, skill_file, task_dir, cwd, trial, agent_cmd=None):
    skill_text = Path(skill_file).read_text() if arm == "skill" and skill_file else ""
    if agent_cmd:
        values = {
            "prompt": shlex.quote(instruction),
            "instruction": shlex.quote(instruction),
            "skill_prompt": shlex.quote(skill_text),
            "skill_file": shlex.quote(str(skill_file or "")),
            "task_dir": shlex.quote(str(Path(task_dir).resolve())),
            "solution_patch": shlex.quote(str((Path(task_dir) / "solution" / "fix.patch").resolve())),
            "cwd": shlex.quote(str(Path(cwd).resolve())),
            "task": shlex.quote(Path(task_dir).name),
            "arm": shlex.quote(arm),
            "trial": str(trial),
            "python": shlex.quote(sys.executable),
        }
        return {"args": agent_cmd.format(**values), "shell": True}

    args = [
        "claude",
        "-p",
        instruction,
        "--model",
        "sonnet",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    if arm == "skill":
        args.extend(["--append-system-prompt", skill_text])
    return {"args": args, "shell": False}


def run_matrix(tasks, arms, trials, skill_file, out_dir, agent_cmd=None):
    out_dir = Path(out_dir)
    results_path = out_dir / "results.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    jobs = [(task, arm, trial) for task in tasks for arm in arms for trial in range(1, trials + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(jobs) or 1)) as pool:
        futures = [
            pool.submit(run_one, task, arm, trial, skill_file, out_dir, agent_cmd)
            for task, arm, trial in jobs
        ]
        try:
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                append_result(results_path, row, lock)
                print(f"{row['task']} {row['arm']} trial={row['trial']} pass={row['tests_pass']} reason={row['reason']}")
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(130)


def append_result(path, row, lock):
    path = Path(path)
    with lock:
        rows = []
        if path.exists() and path.read_text().strip():
            rows = json.loads(path.read_text())
            if not isinstance(rows, list):
                raise ValueError(f"results file must contain a JSON array: {path}")
        rows.append(row)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)


def parse_csv(value, default):
    if value is None:
        return list(default)
    return [part.strip() for part in value.split(",") if part.strip()]


def _kill_process_group(proc):
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


def _compact_output(text):
    return "\n".join(text.splitlines()[-40:])[-4000:]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--tasks")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--arms")
    parser.add_argument("--skill-file")
    parser.add_argument("--out-dir", default=str(ROOT / "out"))
    parser.add_argument("--agent-cmd")
    args = parser.parse_args(argv)

    arms = parse_csv(args.arms, DEFAULT_ARMS)
    unknown_arms = set(arms) - {"baseline", "skill"}
    if unknown_arms:
        raise SystemExit(f"unknown arms: {', '.join(sorted(unknown_arms))}")
    if "skill" in arms and not args.skill_file:
        raise SystemExit("--skill-file is required when the skill arm is selected")
    if args.skill_file and not Path(args.skill_file).exists():
        raise SystemExit(f"skill file not found: {args.skill_file}")

    selected = parse_csv(args.tasks, [])
    tasks = task_dirs(ROOT / "tasks", selected or None)
    trials = max(1, args.trials)
    if args.smoke:
        tasks = tasks[:1]
        arms = ["baseline", "skill"]
        trials = 1
        if not args.skill_file:
            raise SystemExit("--skill-file is required for --smoke")
    run_matrix(tasks, arms, trials, args.skill_file, Path(args.out_dir), args.agent_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
