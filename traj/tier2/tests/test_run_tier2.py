import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from traj.tier2 import run_tier2


def test_wrong_image_refuses_before_agent_runs():
    calls = []

    class FakeClient:
        def ssh(self, name, command, timeout=None):
            calls.append(command)
            if "rev-parse HEAD" in command:
                return SimpleNamespace(returncode=0, stdout="imagehead\n", stderr="")
            return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a valid object")

    with pytest.raises(run_tier2.BaseCommitMismatch):
        run_tier2.assert_base_commit(FakeClient(), "t2-case", "expected")

    assert calls[0] == "git -C /home/exedev/work/repo rev-parse HEAD"
    assert "cat-file -t expected" in calls[1]


def test_head_ahead_of_base_is_allowed_and_returned():
    class FakeClient:
        def ssh(self, name, command, timeout=None):
            if "rev-parse HEAD" in command:
                return SimpleNamespace(returncode=0, stdout="imagehead\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="commit\n", stderr="")

    assert run_tier2.assert_base_commit(FakeClient(), "t2-case", "expected") == "imagehead"


def test_extract_patch_uses_pinned_base_commit():
    commands = []

    class FakeClient:
        def ssh(self, name, command, timeout=None):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="diff --git a/x b/x\n", stderr="")

    assert run_tier2.extract_patch(FakeClient(), "t2-case", "abc123") == "diff --git a/x b/x\n"
    assert commands == [
        "git -C /home/exedev/work/repo add -N .",
        "git -C /home/exedev/work/repo diff abc123",
    ]


def test_default_agent_command_uses_remote_key_reference_and_no_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "sk-ant-secret-value")
    skill = tmp_path / "skill.md"
    skill.write_text("Use tests first.")

    command = run_tier2.build_remote_agent_command(
        problem_statement="Fix the bug",
        arm="skill",
        skill_file=skill,
        agent_cmd=None,
        trace_remote="/home/exedev/work/traces/t.jsonl",
        stderr_remote="/home/exedev/work/traces/t.stderr",
        timeout_s=1800,
    )

    assert 'ANTHROPIC_API_KEY="$AGENT_API_KEY"' in command
    assert "sk-ant-secret-value" not in command
    assert "ANTHROPIC_BASE_URL" not in command
    assert "--append-system-prompt" in command


def test_fake_run_persists_trace_and_redacts_secrets_before_teardown(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "sk-ant-secret-value")

    manifest = {
        "instances": [
            {
                "instance_id": "repo__case-1",
                "repo": "repo/name",
                "base_commit": "abc123",
                "image": "image:latest",
                "FAIL_TO_PASS": ["fail_test"],
                "PASS_TO_PASS": ["pass_test"],
                "problem_statement": "fix it",
            }
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    removed = []
    prompt_writes = {}

    class FakeClient:
        def create(self, name):
            return {"ssh_dest": f"{name}.exe.xyz"}

        def wait_ready(self, name):
            return None

        def remove(self, name):
            removed.append(name)

        def ssh(self, name, command, timeout=None):
            if command.startswith("docker pull"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command.startswith("rm -rf /home/exedev/work/repo"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command.startswith("docker create"):
                return SimpleNamespace(returncode=0, stdout="ctr\n", stderr="")
            if command.startswith("docker cp"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command.startswith("docker rm"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command == "git -C /home/exedev/work/repo rev-parse HEAD":
                return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
            if command.startswith("git -C /home/exedev/work/repo cat-file -t"):
                return SimpleNamespace(returncode=0, stdout="commit\n", stderr="")
            if command.startswith("mkdir -p /home/exedev/work/traces"):
                return SimpleNamespace(returncode=0, stdout="", stderr="secret sk-ant-secret-value")
            if command == "git -C /home/exedev/work/repo add -N .":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command == "git -C /home/exedev/work/repo diff abc123":
                return SimpleNamespace(returncode=0, stdout="diff --git a/a.py b/a.py\n", stderr="")
            raise AssertionError(command)

        def write_text(self, name, path, text):
            prompt_writes[path] = text

        def scp_from(self, name, remote, local):
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            Path(local).write_text('{"type":"text","text":"because the fix is small sk-ant-secret-value"}\n')

    rows = run_tier2.run_matrix(
        manifest_path=manifest_path,
        arms=["baseline"],
        trials=1,
        skill_file=None,
        out_dir=tmp_path / "out",
        client_factory=lambda: FakeClient(),
        grader=lambda instance, patch, work_dir: {
            "resolved": True,
            "fail_to_pass_passed": 1,
            "pass_to_pass_regressions": 0,
        },
        parallel_boxes=1,
    )

    assert rows[0]["resolved"] is True
    assert run_tier2.REMOTE_PROMPT_FILE in prompt_writes and prompt_writes[run_tier2.REMOTE_PROMPT_FILE]
    assert rows[0]["metrics"]["stated_hypothesis"] is True
    assert removed == [rows[0]["box_name"]]
    artifact_text = "\n".join(path.read_text(errors="replace") for path in (tmp_path / "out").rglob("*") if path.is_file())
    assert "sk-ant-secret-value" not in artifact_text


def test_box_aware_grader_receives_client_and_box_name(tmp_path):
    seen = {}

    def grader(instance, patch, work_dir, client=None, box_name=None):
        seen["client"] = client
        seen["box_name"] = box_name
        return {
            "resolved": False,
            "fail_to_pass_passed": 0,
            "pass_to_pass_regressions": 0,
        }

    result = run_tier2._grade_patch(
        grader,
        {"instance_id": "repo__case-1"},
        "patch",
        tmp_path,
        client="client-object",
        box_name="t2-case",
    )

    assert result["resolved"] is False
    assert seen == {"client": "client-object", "box_name": "t2-case"}


def test_prompt_with_skill_combines_for_single_arg_agents(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("Debug systematically.")
    cmd = run_tier2.build_remote_agent_command(
        "Fix the bug.",
        arm="skill",
        skill_file=str(skill),
        agent_cmd="codex exec {prompt_with_skill}",
        trace_remote="/home/exedev/work/traces/t.jsonl",
        stderr_remote="/home/exedev/work/traces/t.stderr",
    )
    assert "Debug systematically." in cmd and "Fix the bug." in cmd
    baseline = run_tier2.build_remote_agent_command(
        "Fix the bug.",
        arm="baseline",
        skill_file=str(skill),
        agent_cmd="codex exec {prompt_with_skill}",
        trace_remote="/home/exedev/work/traces/t.jsonl",
        stderr_remote="/home/exedev/work/traces/t.stderr",
    )
    assert "Debug systematically." not in baseline


def test_bootstrap_codex_agent_installs_and_pushes_auth(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text('{"token": "subscription"}')
    commands, writes = [], {}

    class FakeClient:
        def ssh(self, name, command, timeout=None):
            commands.append(command)
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        def write_text(self, name, path, text):
            writes[path] = text

    run_tier2.bootstrap_codex_agent(FakeClient(), "t2-box", auth_path=auth)
    assert any("npm install -g @openai/codex" in c for c in commands)
    assert writes["/home/exedev/.codex/auth.json"] == '{"token": "subscription"}'
