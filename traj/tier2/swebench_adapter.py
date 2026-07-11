#!/usr/bin/env python3
import hashlib
import json
import shlex
from pathlib import Path


def parse_grading_report(report_path, fail_to_pass, pass_to_pass):
    report = json.loads(Path(report_path).read_text())
    return parse_grading_report_data(report, fail_to_pass=fail_to_pass, pass_to_pass=pass_to_pass)


def parse_grading_report_data(report, fail_to_pass, pass_to_pass):
    if "tests_status" not in report and "resolved" not in report:
        # swebench get_eval_report keys the report by instance_id — unwrap one level
        inner = [v for v in report.values() if isinstance(v, dict) and ("tests_status" in v or "resolved" in v)]
        if len(inner) == 1:
            report = inner[0]
    status = report.get("tests_status", {})
    fail_status = status.get("FAIL_TO_PASS", {})
    pass_status = status.get("PASS_TO_PASS", {})
    # the report's lists are already scoped to the instance's test sets by swebench itself;
    # name formats differ per runner (e.g. sympy bare names), so never re-intersect with dataset names
    return {
        "resolved": bool(report.get("resolved")),
        "fail_to_pass_passed": len(fail_status.get("success", [])),
        "pass_to_pass_regressions": len(pass_status.get("failure", [])),
    }


REMOTE_GRADE_SCRIPT = r"""
import json
import shlex
import subprocess
import sys
from pathlib import Path

from swebench.harness.grading import get_eval_report
try:
    from swebench.harness.test_spec.test_spec import make_test_spec  # swebench >= 4.0
except ImportError:
    from swebench.harness.test_spec import make_test_spec  # swebench < 4.0


def sh(cmd, timeout=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


payload = json.loads(Path(sys.argv[1]).read_text())
instance = payload["instance"]
work_dir = Path(sys.argv[1]).parent
log_path = Path(payload["log_path"])
image = instance["image"]
cname = "grade-" + work_dir.name[:48]

prediction = {
    "instance_id": instance["instance_id"],
    "model_patch": payload["patch_text"],
    "model_name_or_path": "skill-arena-tier2",
}
test_spec = make_test_spec(dict(instance), namespace="swebench")

sh(f"docker rm -f {shlex.quote(cname)}")
run = sh(f"docker run -d --name {shlex.quote(cname)} {shlex.quote(image)} tail -f /dev/null", timeout=300)
if run.returncode != 0:
    raise SystemExit(f"container start failed: {run.stderr or run.stdout}")
try:
    apply_failed = ""
    if payload["patch_text"].strip():
        (work_dir / "model.patch").write_text(payload["patch_text"])
        sh(f"docker cp {shlex.quote(str(work_dir / 'model.patch'))} {shlex.quote(cname)}:/tmp/model.patch", timeout=120)
        applied = sh(
            f"docker exec {shlex.quote(cname)} bash -c "
            + shlex.quote("cd /testbed && (git apply -v /tmp/model.patch || patch --batch --fuzz=5 -p1 -i /tmp/model.patch)"),
            timeout=300,
        )
        if applied.returncode != 0:
            apply_failed = (applied.stderr or "") + (applied.stdout or "")
    if apply_failed:
        log_path.write_text("PATCH_APPLY_FAILED\n" + apply_failed)
    else:
        (work_dir / "eval.sh").write_text(test_spec.eval_script)
        sh(f"docker cp {shlex.quote(str(work_dir / 'eval.sh'))} {shlex.quote(cname)}:/tmp/eval.sh", timeout=120)
        try:
            ran = sh(f"docker exec {shlex.quote(cname)} bash /tmp/eval.sh", timeout=1500)
            log_path.write_text((ran.stdout or "") + "\n" + (ran.stderr or ""))
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            log_path.write_text(partial + "\nEVAL_TIMEOUT\n")
finally:
    sh(f"docker rm -f {shlex.quote(cname)}")

report = get_eval_report(
    test_spec=test_spec,
    prediction=prediction,
    test_log_path=log_path,
    include_tests_status=True,
)
Path(sys.argv[2]).write_text(json.dumps(report, sort_keys=True, default=str) + "\n")
"""


def grade_patch_with_swebench(instance, patch_text, work_dir, client=None, box_name=None):
    """Grade a patch through SWE-bench's harness.

    This live-only adapter intentionally imports SWE-bench lazily so offline
    tests do not need the tier-2 extras. The exact harness API has changed
    across SWE-bench releases; unsupported versions fail loudly instead of
    falling back to local log parsing.
    """

    if client is not None and box_name is not None:
        return grade_patch_on_box(client, box_name, instance, patch_text, work_dir)

    try:
        from swebench.harness.grading import get_eval_report
        try:
            from swebench.harness.test_spec.test_spec import make_test_spec  # swebench >= 4.0
        except ImportError:
            from swebench.harness.test_spec import make_test_spec  # swebench < 4.0
    except ImportError as exc:
        raise RuntimeError("install tier2 extras with: uv pip install swebench datasets") from exc

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    prediction = {
        "instance_id": instance["instance_id"],
        "model_patch": patch_text,
        "model_name_or_path": "skill-arena-tier2",
    }
    test_spec = make_test_spec(dict(instance), namespace="swebench")
    log_path = work_dir / f"{instance['instance_id']}.log"

    try:
        report = get_eval_report(
            test_spec=test_spec,
            prediction=prediction,
            test_log_path=log_path,
            include_tests_status=True,
        )
    except TypeError as exc:
        raise RuntimeError("installed swebench exposes an unsupported grading API") from exc

    return parse_grading_report_data(
        report,
        fail_to_pass=instance["FAIL_TO_PASS"],
        pass_to_pass=instance["PASS_TO_PASS"],
    )


_FULL_ROWS = None


def _hydrate_instance(instance):
    """make_test_spec needs the full dataset row (test_patch etc.); candidates carry a trimmed dict."""
    if "test_patch" in instance:
        return dict(instance)
    global _FULL_ROWS
    if _FULL_ROWS is None:
        try:
            from .select_instances import load_verified_dataset
        except ImportError:
            from select_instances import load_verified_dataset
        _FULL_ROWS = {row["instance_id"]: dict(row) for row in load_verified_dataset()}
    full = _FULL_ROWS.get(instance["instance_id"])
    if not full:
        raise RuntimeError(f"instance {instance.get('instance_id')} not found in dataset for hydration")
    merged = dict(full)
    merged.update({k: v for k, v in instance.items() if k not in ("FAIL_TO_PASS", "PASS_TO_PASS")})
    return merged


def grade_patch_on_box(client, box_name, instance, patch_text, work_dir):
    """Run SWE-bench grading helpers on the exe.dev box that owns Docker."""

    instance = _hydrate_instance(instance)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(instance["instance_id"])
    label = hashlib.sha256(patch_text.encode()).hexdigest()[:12]
    remote_dir = f"/home/exedev/work/grading/{slug}-{label}"
    remote_payload = f"{remote_dir}/payload.json"
    remote_script = f"{remote_dir}/grade.py"
    remote_report = f"{remote_dir}/report.json"
    remote_log = f"{remote_dir}/test.log"
    local_report = work_dir / f"{slug}-{label}-report.json"

    mkdir = client.ssh(box_name, f"mkdir -p {shlex.quote(remote_dir)}", timeout=120)
    if mkdir.returncode != 0:
        raise RuntimeError(mkdir.stderr or mkdir.stdout)

    payload = {
        "instance": dict(instance),
        "patch_text": patch_text,
        "log_path": remote_log,
    }
    client.write_text(box_name, remote_payload, json.dumps(payload, sort_keys=True))
    client.write_text(box_name, remote_script, REMOTE_GRADE_SCRIPT)
    # grade.py imports swebench on the box; provision an idempotent grading venv once per box
    venv_python = "/home/exedev/gradevenv/bin/python"
    setup = client.ssh(
        box_name,
        f"test -x {venv_python} || (python3 -m venv /home/exedev/gradevenv && {venv_python} -m pip install -q swebench)",
        timeout=600,
    )
    if setup.returncode != 0:
        raise RuntimeError(setup.stderr or setup.stdout or "grading venv setup failed")
    proc = client.ssh(
        box_name,
        f"{venv_python} {shlex.quote(remote_script)} {shlex.quote(remote_payload)} {shlex.quote(remote_report)}",
        timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    copied = client.scp_from(box_name, remote_report, local_report)
    if getattr(copied, "returncode", 0) != 0:
        raise RuntimeError(getattr(copied, "stderr", "") or "failed to copy SWE-bench grading report")

    return parse_grading_report(
        local_report,
        fail_to_pass=instance["FAIL_TO_PASS"],
        pass_to_pass=instance["PASS_TO_PASS"],
    )


def _safe_slug(value):
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(value))[:80] or "instance"
