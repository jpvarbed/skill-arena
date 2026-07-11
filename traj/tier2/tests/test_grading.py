import json
from types import SimpleNamespace

from traj.tier2 import swebench_adapter


def test_parse_recorded_swebench_report_shape(tmp_path):
    report = {
        "resolved": False,
        "tests_status": {
            "FAIL_TO_PASS": {"success": ["test_a"], "failure": ["test_b"]},
            "PASS_TO_PASS": {"success": ["test_c"], "failure": ["test_d"]},
        },
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))

    parsed = swebench_adapter.parse_grading_report(path, fail_to_pass=["test_a", "test_b"], pass_to_pass=["test_c", "test_d"])

    assert parsed == {
        "resolved": False,
        "fail_to_pass_passed": 1,
        "pass_to_pass_regressions": 1,
    }


def test_remote_grading_uses_box_and_parses_copied_report(tmp_path):
    writes = {}
    ssh_commands = []

    class FakeClient:
        def ssh(self, name, command, timeout=None):
            ssh_commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        def write_text(self, name, remote_path, text):
            writes[remote_path] = text

        def scp_from(self, name, remote_path, local_path):
            report = {
                "resolved": True,
                "tests_status": {
                    "FAIL_TO_PASS": {"success": ["test_fail"], "failure": []},
                    "PASS_TO_PASS": {"success": ["test_pass"], "failure": []},
                },
            }
            local_path.write_text(json.dumps(report))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

    instance = {
        "instance_id": "repo__case-1",
        "FAIL_TO_PASS": ["test_fail"],
        "PASS_TO_PASS": ["test_pass"],
        "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n",
    }

    parsed = swebench_adapter.grade_patch_with_swebench(
        instance,
        "diff --git a/a.py b/a.py\n",
        tmp_path,
        client=FakeClient(),
        box_name="t2-case",
    )

    assert parsed["resolved"] is True
    assert parsed["fail_to_pass_passed"] == 1
    assert any(command.startswith("/home/exedev/gradevenv/bin/python /home/exedev/work/grading/") for command in ssh_commands)
    payload = json.loads(next(text for path, text in writes.items() if path.endswith("/payload.json")))
    assert payload["instance"]["instance_id"] == "repo__case-1"
    assert payload["patch_text"].startswith("diff --git")
