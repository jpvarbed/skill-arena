from pathlib import Path

from traj.validate_tasks import validate_task


def _write_fixture_task(root, fixed=False, broken_patch=False):
    task = root / ("green" if fixed else "red")
    repo = task / "repo"
    tests = repo / "tests"
    solution = task / "solution"
    tests.mkdir(parents=True)
    solution.mkdir()
    task.joinpath("task.toml").write_text(
        'id = "fixture"\n'
        'category = "fixture"\n'
        'difficulty = "small fixture"\n'
        'test_command = "python -m pytest tests/ -x -q"\n'
    )
    task.joinpath("instruction.md").write_text("The tests fail. Find and fix the bug.\n")
    repo.joinpath("calc.py").write_text("def add(a, b):\n    return a - b\n")
    tests.joinpath("test_calc.py").write_text(
        "from calc import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )
    patch = (
        "--- calc.py\n"
        "+++ calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    if broken_patch:
        patch = patch.replace("return a + b", "return a * b")
    solution.joinpath("fix.patch").write_text(patch)
    return task


def test_validate_task_accepts_known_good_fixture(tmp_path):
    row = validate_task(_write_fixture_task(tmp_path))
    assert row["ok"] is True
    assert row["starts_red"] is True
    assert row["green_twice"] is True


def test_validate_task_rejects_broken_solution_fixture(tmp_path):
    row = validate_task(_write_fixture_task(tmp_path, broken_patch=True))
    assert row["ok"] is False
    assert row["starts_red"] is True
    assert row["green_once"] is False
