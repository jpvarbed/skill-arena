import json
from types import SimpleNamespace

from traj.tier2 import validate_instances


def _candidate(instance_id):
    return {
        "instance_id": instance_id,
        "repo": "repo/name",
        "base_commit": "a" * 40,
        "image": f"image/{instance_id}:latest",
        "FAIL_TO_PASS": ["fail_test"],
        "PASS_TO_PASS": ["pass_test"],
        "problem_statement": "fix it",
    }


def test_manifest_freezes_first_passing_instances_and_records_skips(tmp_path):
    candidates = [_candidate(f"repo__case-{index}") for index in range(1, 5)]
    outcomes = {
        "repo__case-1": validate_instances.ValidationOutcome(True, True, "sha256:one", "ok"),
        "repo__case-2": validate_instances.ValidationOutcome(False, True, "sha256:two", "gold patch did not pass"),
        "repo__case-3": validate_instances.ValidationOutcome(True, True, "sha256:three", "ok"),
        "repo__case-4": validate_instances.ValidationOutcome(True, True, "sha256:four", "ok"),
    }

    manifest = validate_instances.build_manifest(
        {"criteria": {"source": "fixture"}, "candidates": candidates},
        validator=lambda candidate: outcomes[candidate["instance_id"]],
        target_count=2,
    )

    assert [row["instance_id"] for row in manifest["instances"]] == ["repo__case-1", "repo__case-3"]
    assert manifest["instances"][0]["image_digest"] == "sha256:one"
    assert manifest["skipped"] == [
        {"instance_id": "repo__case-2", "reason": "gold patch did not pass"},
        {"instance_id": "repo__case-4", "reason": "not-needed-after-target-count"},
    ]


def test_manifest_write_exits_with_too_few_validated_instances(tmp_path):
    candidates = [_candidate("repo__case-1")]
    manifest_path = tmp_path / "manifest.json"

    try:
        validate_instances.write_manifest(
            {"candidates": candidates},
            manifest_path,
            validator=lambda candidate: validate_instances.ValidationOutcome(False, False, "sha256:none", "no-op unexpectedly passed"),
            target_count=1,
        )
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    data = json.loads(manifest_path.read_text())
    assert data["instances"] == []
    assert data["skipped"][0]["reason"] == "no-op unexpectedly passed"


def test_live_validator_grades_on_created_box_and_tears_down():
    calls = []
    removed = []
    candidate = _candidate("repo__case-1")

    class FakeClient:
        def create(self, name):
            calls.append(("create", name))
            return {"ssh_dest": f"{name}.exe.xyz"}

        def wait_ready(self, name):
            calls.append(("wait_ready", name))

        def remove(self, name):
            removed.append(name)

        def ssh(self, name, command, timeout=None):
            calls.append(("ssh", command))
            if command.startswith("docker image inspect"):
                return SimpleNamespace(returncode=0, stdout="repo@sha256:abc\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

    graded = []

    def grader(instance, patch, work_dir, client, box_name):
        graded.append((patch, box_name, client.__class__.__name__))
        return {
            "resolved": bool(patch),
            "fail_to_pass_passed": 1 if patch else 0,
            "pass_to_pass_regressions": 0,
        }

    validator = validate_instances.LiveValidator(
        client_factory=FakeClient,
        dataset_rows=[{"instance_id": candidate["instance_id"], "patch": "gold patch"}],
        grader=grader,
    )

    outcome = validator(candidate)

    assert outcome.gold_passed is True
    assert outcome.noop_failed is True
    assert outcome.image_digest == "repo@sha256:abc"
    assert graded == [
        ("gold patch", "t2-repo-case-1", "FakeClient"),
        ("", "t2-repo-case-1", "FakeClient"),
    ]
    assert removed == ["t2-repo-case-1"]
    assert ("ssh", "docker pull image/repo__case-1:latest") in calls
