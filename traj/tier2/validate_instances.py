#!/usr/bin/env python3
import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ValidationOutcome:
    gold_passed: bool
    noop_failed: bool
    image_digest: str
    reason: str
    details: dict | None = None


def load_candidates(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return {"criteria": {}, "candidates": data}
    return data


def build_manifest(candidate_data, validator, target_count=12):
    candidates = list(candidate_data.get("candidates", []))
    manifest = {
        "criteria": candidate_data.get("criteria", {}),
        "target_count": target_count,
        "instances": [],
        "skipped": [],
    }
    for index, candidate in enumerate(candidates):
        if len(manifest["instances"]) >= target_count:
            for remaining in candidates[index:]:
                manifest["skipped"].append(
                    {"instance_id": remaining["instance_id"], "reason": "not-needed-after-target-count"}
                )
            break
        outcome = validator(candidate)
        if outcome.gold_passed and outcome.noop_failed:
            frozen = dict(candidate)
            frozen["image_digest"] = outcome.image_digest
            frozen["validation"] = {
                "gold_patch_passed": outcome.gold_passed,
                "noop_fail_to_pass_failed": outcome.noop_failed,
                "details": outcome.details or {},
            }
            manifest["instances"].append(frozen)
        else:
            manifest["skipped"].append({"instance_id": candidate["instance_id"], "reason": outcome.reason})
    return manifest


def write_manifest(candidate_data, path, validator, target_count=12):
    manifest = build_manifest(candidate_data, validator=validator, target_count=target_count)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if len(manifest["instances"]) < target_count:
        raise SystemExit(1)
    return path


class LiveValidator:
    def __init__(self, client_factory=None, dataset_rows=None, grader=None):
        try:
            from .exebox import ExeBoxClient
            from .swebench_adapter import grade_patch_with_swebench
        except ImportError:
            from exebox import ExeBoxClient
            from swebench_adapter import grade_patch_with_swebench

        self.client_factory = client_factory or ExeBoxClient
        self.dataset_rows = dataset_rows
        self.grader = grader or grade_patch_with_swebench

    def __call__(self, candidate):
        try:
            from . import exebox
            from .run_tier2 import run_checked
        except ImportError:
            import exebox
            from run_tier2 import run_checked

        dataset_row = self._dataset_by_id().get(candidate["instance_id"], {})
        gold_patch = dataset_row.get("patch") or dataset_row.get("gold_patch") or dataset_row.get("test_patch")
        if not gold_patch:
            return ValidationOutcome(False, False, "", "missing gold patch in dataset row")

        box_name = exebox.box_name_for_instance(candidate["instance_id"])
        client = self.client_factory()
        created = False
        try:
            client.create(box_name)
            created = True
            client.wait_ready(box_name)
            run_checked(client, box_name, f"docker pull {candidate['image']}", timeout=1800)
            digest = _image_digest(client, box_name, candidate["image"])
            gold = self.grader(candidate, gold_patch, ROOT / "validation", client=client, box_name=box_name)
            noop = self.grader(candidate, "", ROOT / "validation", client=client, box_name=box_name)
            gold_passed = bool(gold["resolved"]) and gold["pass_to_pass_regressions"] == 0
            noop_failed = not bool(noop["resolved"])
            reason = "ok" if gold_passed and noop_failed else _validation_reason(gold_passed, noop_failed)
            return ValidationOutcome(gold_passed, noop_failed, digest, reason, {"gold": gold, "noop": noop})
        finally:
            if created:
                client.remove(box_name)

    def _dataset_by_id(self):
        if self.dataset_rows is None:
            try:
                from .select_instances import load_verified_dataset
            except ImportError:
                from select_instances import load_verified_dataset

            self.dataset_rows = load_verified_dataset()
        return {row["instance_id"]: row for row in self.dataset_rows}


def _image_digest(client, box_name, image):
    proc = client.ssh(
        box_name,
        f"docker image inspect --format='{{{{index .RepoDigests 0}}}}' {shlex.quote(image)}",
        timeout=120,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _validation_reason(gold_passed, noop_failed):
    if not gold_passed:
        return "gold patch did not pass"
    if not noop_failed:
        return "no-op unexpectedly passed"
    return "validation failed"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default=str(ROOT / "candidates.json"))
    parser.add_argument("--out", default=str(ROOT / "manifest.json"))
    parser.add_argument("--target-count", type=int, default=12)
    args = parser.parse_args(argv)
    path = write_manifest(load_candidates(args.candidates), args.out, LiveValidator(), target_count=args.target_count)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
