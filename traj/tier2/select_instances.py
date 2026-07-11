#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


DATASET_ID = "princeton-nlp/SWE-bench_Verified"
ORDERING_DESCRIPTION = (
    "eligible rows sorted by problem statement length, repo size hint, repo, and instance id; "
    "the first target set is repo-diversified before overflow is appended"
)
FILTER_CRITERIA = {
    "dataset": DATASET_ID,
    "python_repos": "SWE-bench Verified is a Python benchmark; reject rows whose language field is present and not python",
    "requires_x86_64_image": True,
    "requires_fail_to_pass": True,
    "requires_pass_to_pass": True,
    "target_count": 12,
    "overflow_count": 6,
    "minimum_distinct_repos_in_target": 4,
    "ordering": ORDERING_DESCRIPTION,
}


def load_verified_dataset():
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("install tier2 extras with: uv pip install swebench datasets") from exc
    return list(load_dataset(DATASET_ID, split="test"))


def default_image_ref(row):
    try:
        try:
            from swebench.harness.test_spec.test_spec import make_test_spec  # swebench >= 4.0
        except ImportError:
            from swebench.harness.test_spec import make_test_spec  # swebench < 4.0
    except ImportError as exc:
        raise RuntimeError("install tier2 extras with: uv pip install swebench datasets") from exc
    spec = make_test_spec(dict(row), namespace="swebench")
    for attr in ("instance_image_key", "instance_image_name", "image_name"):
        value = getattr(spec, attr, None)
        if value:
            return value
    raise RuntimeError("SWE-bench test spec did not expose an instance image name")


def select_candidates(rows, count=18, target_count=12, image_namer=default_image_ref):
    eligible = []
    for row in rows:
        normalized = normalize_row(row, image_namer=image_namer)
        if normalized is not None:
            eligible.append(normalized)
    eligible.sort(key=_sort_key)

    selected = _repo_diverse_prefix(eligible, target_count=target_count)
    selected_ids = {row["instance_id"] for row in selected}
    for row in eligible:
        if row["instance_id"] not in selected_ids:
            selected.append(row)
            selected_ids.add(row["instance_id"])
        if len(selected) >= count:
            break
    return selected[:count]


def normalize_row(row, image_namer=default_image_ref):
    row = dict(row)
    if str(row.get("language", "python")).lower() != "python":
        return None
    fail_to_pass = parse_test_list(row.get("FAIL_TO_PASS"))
    pass_to_pass = parse_test_list(row.get("PASS_TO_PASS"))
    required = ("instance_id", "repo", "base_commit", "problem_statement")
    if any(not row.get(key) for key in required) or not fail_to_pass or not pass_to_pass:
        return None
    try:
        image = image_namer(row)
    except RuntimeError:
        raise  # environment/setup error — never silently filter the whole dataset
    except Exception:
        return None
    if not image:
        return None
    return {
        "instance_id": str(row["instance_id"]),
        "repo": str(row["repo"]),
        "base_commit": str(row["base_commit"]),
        "image": str(image),
        "FAIL_TO_PASS": fail_to_pass,
        "PASS_TO_PASS": pass_to_pass,
        "problem_statement": str(row["problem_statement"]),
        "filter_criteria": {
            "python_repo": True,
            "x86_64_image": True,
            "requires_fail_to_pass": True,
            "requires_pass_to_pass": True,
        },
        "_repo_size_mb": float(row.get("repo_size_mb") or row.get("repo_size") or 0),
    }


def parse_test_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [line.strip() for line in stripped.splitlines() if line.strip()]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item)]
    return []


def write_candidates(rows, path, count=18, target_count=12, image_namer=default_image_ref):
    candidates = select_candidates(rows, count=count, target_count=target_count, image_namer=image_namer)
    data = {
        "criteria": dict(FILTER_CRITERIA, target_count=target_count, overflow_count=max(0, count - target_count)),
        "candidates": [_public_candidate(row) for row in candidates],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if len(candidates) < count:
        raise SystemExit(
            f"selected only {len(candidates)}/{count} candidates — filters or dataset access are broken; refusing to proceed"
        )
    return path


def _repo_diverse_prefix(rows, target_count):
    selected = []
    selected_ids = set()
    repos = []
    for row in rows:
        if row["repo"] not in repos:
            repos.append(row["repo"])
        if len(repos) == FILTER_CRITERIA["minimum_distinct_repos_in_target"]:
            break
    for repo in repos:
        for row in rows:
            if row["repo"] == repo and row["instance_id"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["instance_id"])
                break
    for row in rows:
        if len(selected) >= target_count:
            break
        if row["instance_id"] not in selected_ids:
            selected.append(row)
            selected_ids.add(row["instance_id"])
    return selected


def _sort_key(row):
    return (
        len(row["problem_statement"]),
        row.get("_repo_size_mb", 0),
        row["repo"],
        row["instance_id"],
    )


def _public_candidate(row):
    return {key: value for key, value in row.items() if not key.startswith("_")}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).with_name("candidates.json")))
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--target-count", type=int, default=12)
    args = parser.parse_args(argv)
    path = write_candidates(load_verified_dataset(), args.out, count=args.count, target_count=args.target_count)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
