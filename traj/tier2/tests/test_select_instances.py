import json

from traj.tier2 import select_instances


def test_candidate_selection_is_deterministic_and_repo_diverse(tmp_path):
    rows = [
        {
            "instance_id": "django__django-3",
            "repo": "django/django",
            "base_commit": "a" * 40,
            "problem_statement": "short django",
            "FAIL_TO_PASS": ["tests/test_a.py::test_one"],
            "PASS_TO_PASS": ["tests/test_a.py::test_two"],
            "repo_size_mb": 200,
        },
        {
            "instance_id": "sympy__sympy-1",
            "repo": "sympy/sympy",
            "base_commit": "b" * 40,
            "problem_statement": "short sympy",
            "FAIL_TO_PASS": ["tests/test_b.py::test_one"],
            "PASS_TO_PASS": ["tests/test_b.py::test_two"],
            "repo_size_mb": 300,
        },
        {
            "instance_id": "pytest-dev__pytest-1",
            "repo": "pytest-dev/pytest",
            "base_commit": "c" * 40,
            "problem_statement": "short pytest",
            "FAIL_TO_PASS": ["tests/test_c.py::test_one"],
            "PASS_TO_PASS": ["tests/test_c.py::test_two"],
            "repo_size_mb": 100,
        },
        {
            "instance_id": "pallets__flask-1",
            "repo": "pallets/flask",
            "base_commit": "d" * 40,
            "problem_statement": "short flask",
            "FAIL_TO_PASS": "[\"tests/test_d.py::test_one\"]",
            "PASS_TO_PASS": "[\"tests/test_d.py::test_two\"]",
            "repo_size_mb": 50,
        },
        {
            "instance_id": "django__django-1",
            "repo": "django/django",
            "base_commit": "e" * 40,
            "problem_statement": "x" * 500,
            "FAIL_TO_PASS": ["tests/test_e.py::test_one"],
            "PASS_TO_PASS": ["tests/test_e.py::test_two"],
            "repo_size_mb": 20,
        },
        {
            "instance_id": "bad__missing-tests-1",
            "repo": "bad/repo",
            "base_commit": "f" * 40,
            "problem_statement": "bad",
            "FAIL_TO_PASS": [],
            "PASS_TO_PASS": [],
        },
    ]

    image_namer = lambda row: f"ghcr.io/swebench/{row['instance_id']}:x86_64"
    selected = select_instances.select_candidates(rows, count=5, target_count=4, image_namer=image_namer)
    selected_again = select_instances.select_candidates(list(reversed(rows)), count=5, target_count=4, image_namer=image_namer)

    assert [row["instance_id"] for row in selected] == [row["instance_id"] for row in selected_again]
    assert len({row["repo"] for row in selected[:4]}) == 4
    assert selected[0]["instance_id"] == "pallets__flask-1"
    assert selected[0]["image"] == "ghcr.io/swebench/pallets__flask-1:x86_64"


def test_write_candidates_echoes_filter_criteria(tmp_path):
    rows = [
        {
            "instance_id": "repo__one-1",
            "repo": "repo/one",
            "base_commit": "1" * 40,
            "problem_statement": "short",
            "FAIL_TO_PASS": ["a"],
            "PASS_TO_PASS": ["b"],
        }
    ]

    path = tmp_path / "candidates.json"
    select_instances.write_candidates(rows, path, count=1, target_count=1, image_namer=lambda row: "image:latest")
    data = json.loads(path.read_text())

    assert data["criteria"]["dataset"] == "princeton-nlp/SWE-bench_Verified"
    assert data["criteria"]["ordering"] == select_instances.ORDERING_DESCRIPTION
    assert data["candidates"][0]["filter_criteria"]["requires_fail_to_pass"] is True
