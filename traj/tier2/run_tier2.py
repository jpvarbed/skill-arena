#!/usr/bin/env python3
import argparse
import concurrent.futures
import inspect
import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

try:
    from traj.run_benchmark import append_result, parse_csv
    from traj.scorers import score_transcript
except ImportError:
    from run_benchmark import append_result, parse_csv
    from scorers import score_transcript

try:
    from . import exebox
    from .swebench_adapter import grade_patch_with_swebench
except ImportError:
    import exebox
    from swebench_adapter import grade_patch_with_swebench


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = ROOT.parent / "out" / "tier2"
DEFAULT_ARMS = ["baseline", "skill"]
TIMEOUT_S = 1800


class BaseCommitMismatch(RuntimeError):
    pass


def load_manifest(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return {"instances": data}
    return data


def run_checked(client, box_name, command, timeout=None):
    proc = client.ssh(box_name, command, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(redact_secrets(proc.stderr or proc.stdout or f"command failed: {command}"))
    return proc


def prepare_workdir(client, box_name, image):
    run_checked(client, box_name, f"docker pull {shlex.quote(image)}", timeout=1800)
    run_checked(client, box_name, "rm -rf /home/exedev/work/repo && mkdir -p /home/exedev/work", timeout=120)
    container = run_checked(client, box_name, f"docker create {shlex.quote(image)}", timeout=120).stdout.strip()
    try:
        run_checked(client, box_name, f"docker cp {shlex.quote(container)}:/testbed /home/exedev/work/repo", timeout=600)
    finally:
        run_checked(client, box_name, f"docker rm {shlex.quote(container)}", timeout=120)


def assert_base_commit(client, box_name, base_commit):
    proc = client.ssh(box_name, "git -C /home/exedev/work/repo rev-parse HEAD", timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(redact_secrets(proc.stderr))
    actual = proc.stdout.strip()
    if actual != base_commit:
        raise BaseCommitMismatch(f"HEAD {actual} != base_commit {base_commit}")
    return True


def extract_patch(client, box_name, base_commit):
    # intent-to-add so files the agent CREATED appear in the diff (council [H]: new-file fixes must grade)
    run_checked(client, box_name, "git -C /home/exedev/work/repo add -N .", timeout=60)
    proc = client.ssh(box_name, f"git -C /home/exedev/work/repo diff {shlex.quote(base_commit)}", timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(redact_secrets(proc.stderr))
    return proc.stdout


def build_remote_agent_command(
    problem_statement,
    arm,
    skill_file,
    agent_cmd,
    trace_remote,
    stderr_remote,
    timeout_s=TIMEOUT_S,
):
    skill_text = Path(skill_file).read_text() if arm == "skill" and skill_file else ""
    if agent_cmd:
        command = agent_cmd.format(
            prompt=shlex.quote(problem_statement),
            instruction=shlex.quote(problem_statement),
            skill_prompt=shlex.quote(skill_text),
            skill_file=shlex.quote(str(skill_file or "")),
            cwd=shlex.quote("/home/exedev/work/repo"),
            trace_remote=shlex.quote(trace_remote),
            stderr_remote=shlex.quote(stderr_remote),
            timeout=str(timeout_s),
        )
    else:
        parts = [
            "CLAUDE_CODE_SIMPLE=1",
            'ANTHROPIC_API_KEY="$AGENT_API_KEY"',
            "timeout",
            str(timeout_s),
            "claude",
            "-p",
            shlex.quote(problem_statement),
            "--model",
            "sonnet",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if arm == "skill":
            parts.extend(["--append-system-prompt", shlex.quote(skill_text)])
        command = " ".join(parts)
    return (
        f"mkdir -p {shlex.quote(str(Path(trace_remote).parent))} && "
        f"cd /home/exedev/work/repo && ({command}) > {shlex.quote(trace_remote)} 2> {shlex.quote(stderr_remote)}"
    )


def run_trial(client, box_name, instance, arm, trial, skill_file, out_dir, agent_cmd, grader):
    started = time.monotonic()
    trace_remote = f"/home/exedev/work/traces/{instance['instance_id']}_{arm}_{trial}.jsonl"
    stderr_remote = f"/home/exedev/work/traces/{instance['instance_id']}_{arm}_{trial}.stderr"
    trace_path = Path(out_dir) / "traces" / f"{instance['instance_id']}_{arm}_{trial}.jsonl"
    stderr_path = Path(out_dir) / "traces" / f"{instance['instance_id']}_{arm}_{trial}.stderr"
    timeout = False
    patch = ""
    grade = {"resolved": False, "fail_to_pass_passed": 0, "pass_to_pass_regressions": 0}
    error = ""

    try:
        prepare_workdir(client, box_name, instance["image"])
        assert_base_commit(client, box_name, instance["base_commit"])
        command = build_remote_agent_command(
            instance["problem_statement"],
            arm=arm,
            skill_file=skill_file,
            agent_cmd=agent_cmd,
            trace_remote=trace_remote,
            stderr_remote=stderr_remote,
        )
        proc = client.ssh(box_name, command, timeout=TIMEOUT_S + 60)
        timeout = proc.returncode == 124
        if proc.returncode not in (0, 124):
            error = redact_secrets(proc.stderr or proc.stdout)
        patch = extract_patch(client, box_name, instance["base_commit"])
        patch_path = Path(out_dir) / "patches" / f"{instance['instance_id']}_{arm}_{trial}.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(redact_secrets(patch))
        if not timeout and not error:
            grade = _grade_patch(grader, instance, patch, Path(out_dir) / "grading", client, box_name)
    except Exception as exc:
        error = redact_secrets(str(exc))
    finally:
        _copy_remote_artifact(client, box_name, trace_remote, trace_path)
        _copy_remote_artifact(client, box_name, stderr_remote, stderr_path)
        for artifact in (trace_path, stderr_path):
            if artifact.exists():
                artifact.write_text(redact_secrets(artifact.read_text()))

    metrics = score_transcript(trace_path) if trace_path.exists() else {}
    if timeout:
        status = "timeout"
    elif error:
        status = "infra_error"
    elif bool(grade["resolved"]):
        status = "resolved"
    else:
        status = "unresolved"
    row = {
        "instance_id": instance["instance_id"],
        "arm": arm,
        "trial": trial,
        "status": status,
        "resolved": status == "resolved",
        "fail_to_pass_passed": int(grade["fail_to_pass_passed"]),
        "pass_to_pass_regressions": int(grade["pass_to_pass_regressions"]),
        "timeout": timeout,
        "duration_s": round(time.monotonic() - started, 3),
        "metrics": metrics,
        "trace_path": str(trace_path),
        "trace_bytes": trace_path.stat().st_size if trace_path.exists() else 0,
        "box_name": box_name,
    }
    if error:
        row["error"] = error
    return row


def run_instance(instance, arms, trials, skill_file, out_dir, agent_cmd, client_factory, grader, results_path, lock):
    box_name = exebox.box_name_for_instance(instance["instance_id"])
    client = client_factory()
    rows = []
    try:
        client.create(box_name)
        client.wait_ready(box_name)
        for arm in arms:
            for trial in range(1, trials + 1):
                row = run_trial(client, box_name, instance, arm, trial, skill_file, out_dir, agent_cmd, grader)
                append_result(results_path, row, lock)
                rows.append(row)
                print(
                    f"{row['instance_id']} {row['arm']} trial={row['trial']} "
                    f"resolved={row['resolved']} timeout={row['timeout']}"
                )
    finally:
        client.remove(box_name)
    return rows


def run_matrix(
    manifest_path,
    arms,
    trials,
    skill_file,
    out_dir=DEFAULT_OUT_DIR,
    agent_cmd=None,
    client_factory=exebox.ExeBoxClient,
    grader=grade_patch_with_swebench,
    parallel_boxes=1,
):
    manifest = load_manifest(manifest_path)
    instances = manifest.get("instances", [])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"
    lock = threading.Lock()
    rows = []
    max_workers = min(max(1, parallel_boxes), 3, len(instances) or 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                run_instance,
                instance,
                arms,
                trials,
                skill_file,
                out_dir,
                agent_cmd,
                client_factory,
                grader,
                results_path,
                lock,
            )
            for instance in instances
        ]
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    return rows


def redact_secrets(text):
    if not text:
        return text
    redacted = str(text)
    for key in ("AGENT_API_KEY", "ANTHROPIC_API_KEY", "EXE_DEV_KEY", exebox.KEY_ENV):
        value = os.environ.get(key)
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _grade_patch(grader, instance, patch, work_dir, client, box_name):
    signature = inspect.signature(grader)
    accepts_kwargs = any(param.kind == param.VAR_KEYWORD for param in signature.parameters.values())
    if accepts_kwargs or {"client", "box_name"} <= set(signature.parameters):
        return grader(instance, patch, work_dir, client=client, box_name=box_name)
    return grader(instance, patch, work_dir)


def _copy_remote_artifact(client, box_name, remote, local):
    try:
        result = client.scp_from(box_name, remote, local)
        if getattr(result, "returncode", 0) != 0:
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            Path(local).write_text("")
        elif Path(local).exists():
            Path(local).write_text(redact_secrets(Path(local).read_text(errors="replace")))
    except Exception:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text("")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--arms")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--skill-file")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--agent-cmd")
    parser.add_argument("--parallel-boxes", type=int, default=1)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("cleanup")
    args = parser.parse_args(argv)

    if args.command == "cleanup":
        print(json.dumps({"removed": exebox.ExeBoxClient().cleanup()}, indent=2))
        return 0

    arms = parse_csv(args.arms, DEFAULT_ARMS)
    unknown = set(arms) - {"baseline", "skill"}
    if unknown:
        raise SystemExit(f"unknown arms: {', '.join(sorted(unknown))}")
    if "skill" in arms and not args.skill_file:
        raise SystemExit("--skill-file is required when the skill arm is selected")
    if args.skill_file and not Path(args.skill_file).exists():
        raise SystemExit(f"skill file not found: {args.skill_file}")
    manifest = load_manifest(args.manifest)
    if args.smoke:
        manifest = dict(manifest, instances=manifest.get("instances", [])[:1])
        arms = arms[:1]
        args.trials = 1
        smoke_manifest = Path(args.out_dir) / "smoke-manifest.json"
        smoke_manifest.parent.mkdir(parents=True, exist_ok=True)
        smoke_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        args.manifest = str(smoke_manifest)
    run_matrix(
        manifest_path=args.manifest,
        arms=arms,
        trials=max(1, args.trials),
        skill_file=args.skill_file,
        out_dir=args.out_dir,
        agent_cmd=args.agent_cmd,
        parallel_boxes=args.parallel_boxes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
