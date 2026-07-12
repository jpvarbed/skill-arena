import importlib.util
import json
from pathlib import Path

import arena


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def test_instruction_conflicts_cases_are_deterministic_and_shaped(tmp_path):
    module = load_module("instruction_conflicts_cases", ROOT / "skills" / "instruction-conflicts" / "build_cases.py")
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"

    module.write_cases(first)
    module.write_cases(second)
    cases = read_jsonl(first)

    assert first.read_bytes() == second.read_bytes()
    assert len(cases) == 18
    assert sum(case["kind"] == "dirty" for case in cases) == 14
    assert sum(case["kind"] == "clean" for case in cases) == 4
    assert set(case["expect"] for case in cases if case["kind"] == "dirty") <= set(module.CATEGORIES)
    for case in cases:
        lines = case["draft"].splitlines()
        assert 60 <= len(lines) <= 200
        if case["kind"] == "dirty":
            assert case["expect"] not in case["draft"]


def test_writing_hooks_cases_are_deterministic_and_have_clean_guards(tmp_path):
    module = load_module("writing_hooks_cases", ROOT / "skills" / "writing-hooks" / "build_cases.py")
    out = tmp_path / "cases.jsonl"

    module.write_cases(out)
    cases = read_jsonl(out)

    assert len(cases) == 18
    assert sum(case["kind"] == "dirty" for case in cases) == 14
    assert sum(case["kind"] == "clean" for case in cases) == 4
    assert set(case["expect"] for case in cases if case["kind"] == "dirty") <= set(module.CATEGORIES)
    for case in cases:
        if case["kind"] == "dirty":
            assert case["expect"] not in case["draft"]


def test_caveman_cases_have_domains_and_probe_coverage(tmp_path):
    module = load_module("caveman_cases", ROOT / "skills" / "caveman" / "build_cases.py")
    out = tmp_path / "cases.jsonl"

    module.write_cases(out)
    cases = read_jsonl(out)

    assert len(cases) == 12
    assert len({case["domain"] for case in cases}) >= 10
    for case in cases:
        word_count = len(case["input"].split())
        assert 150 <= word_count <= 400
        assert len(case["probes"]) >= 3
        assert case["reference_compression"]


def test_goal_spec_cases_are_rough_task_prompts():
    cases = read_jsonl(ROOT / "skills" / "goal-spec" / "cases.jsonl")

    assert len(cases) == 8
    assert all("input" in case for case in cases)
    assert all("expect" not in case for case in cases)


def test_arena_dry_run_wires_new_skill_configs(tmp_path):
    results = arena.run(
        ["instruction-conflicts", "writing-hooks", "caveman", "goal-spec"],
        ["codex"],
        out_dir=tmp_path,
        dry_run=True,
    )

    assert set(results["skills"]) == {"instruction-conflicts", "writing-hooks", "caveman", "goal-spec"}
    assert results["skills"]["instruction-conflicts"]["case_count"] == 18
    assert results["skills"]["writing-hooks"]["case_count"] == 18
    assert results["skills"]["caveman"]["case_count"] == 12
    assert results["skills"]["goal-spec"]["case_count"] == 8
