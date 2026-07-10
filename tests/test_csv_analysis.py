import copy
import importlib.util
import json
import sys
from pathlib import Path

import arena


ROOT = Path(__file__).resolve().parents[1]
CSV_SKILL_DIR = ROOT / "skills" / "csv-analysis"


def load_module(name, path):
    sys.path.insert(0, str(CSV_SKILL_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_cases = load_module("csv_analysis_build_cases", CSV_SKILL_DIR / "build_cases.py")
verify_gold = load_module("csv_analysis_verify_gold", CSV_SKILL_DIR / "verify_gold.py")
receipt = load_module("csv_analysis_receipt", CSV_SKILL_DIR / "receipt.py")


def test_build_cases_is_byte_identical(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    build_cases.write_cases(first)
    build_cases.write_cases(second)
    assert first.read_bytes() == second.read_bytes()


def test_executor_matches_hand_computed_golden_answers():
    rows = [
        {"region": "West", "rep": "Ari", "product": "Alpha", "date": "2026-01-05", "units": "10", "revenue": "100", "cost": "40", "satisfaction": "80"},
        {"region": "East", "rep": "Blair", "product": "Beta", "date": "2026-01-20", "units": "6", "revenue": "90", "cost": "30", "satisfaction": "70"},
        {"region": "West", "rep": "Ari", "product": "Beta", "date": "2026-02-10", "units": "14", "revenue": "210", "cost": "84", "satisfaction": "90"},
        {"region": "East", "rep": "Chen", "product": "Alpha", "date": "2026-02-12", "units": "8", "revenue": "160", "cost": "64", "satisfaction": "60"},
    ]
    cases = [
        ({"op": "aggregate", "agg": "sum", "column": "units"}, {"exact": "38"}),
        ({"op": "predicate_count", "filters": [{"column": "region", "op": "eq", "value": "West"}]}, {"exact": "2"}),
        ({"op": "filtered_aggregate", "agg": "mean", "column": "revenue", "filters": [{"column": "region", "op": "eq", "value": "East"}], "round": 2}, {"exact": "125.00"}),
        ({"op": "groupby_argmax", "group_by": "region", "metric": "revenue"}, {"exact": "West"}),
        ({"op": "nth_largest", "column": "revenue", "n": 2}, {"exact": "160"}),
        ({"op": "groupby_dict", "group_by": "product", "metric": "units"}, {"json": {"Alpha": 18, "Beta": 20}}),
        ({"op": "multi_filter_aggregate", "agg": "sum", "column": "units", "filters": [{"column": "region", "op": "eq", "value": "West"}, {"column": "units", "op": "gte", "value": "12"}]}, {"exact": "14"}),
        ({"op": "ratio_percent", "numerator": "cost", "denominator": "revenue", "round": 2}, {"exact": "38.93"}),
        ({"op": "date_bucket_count", "date_column": "date"}, {"json": {"2026-01": 2, "2026-02": 2}}),
        ({"op": "multi_step", "group_by": "rep", "metric": "satisfaction"}, {"exact": "Ari"}),
    ]
    for query, expected in cases:
        assert build_cases.execute_query(rows, query) == expected


def test_verify_gold_returns_nonzero_for_wrong_gold():
    case = build_cases.build_cases()[0]
    bad = copy.deepcopy(case)
    bad["expect"] = {"exact": "wrong"}
    assert verify_gold.main_for_test([bad]) == 1


def test_verify_gold_returns_nonzero_for_tie():
    query = {"op": "groupby_argmax", "group_by": "region", "metric": "revenue"}
    rows = [
        {"region": "West", "rep": "Ari", "product": "Alpha", "date": "2026-01-05", "units": "1", "revenue": "100", "cost": "40", "satisfaction": "80"},
        {"region": "East", "rep": "Blair", "product": "Beta", "date": "2026-01-20", "units": "1", "revenue": "100", "cost": "30", "satisfaction": "70"},
    ]
    expect = build_cases.execute_query(rows, query)
    case = {
        "id": "tie",
        "input": build_cases.render_input(rows, build_cases.question_for(query), expect),
        "expect": expect,
        "meta": {"columns": build_cases.COLUMNS, "rows": rows, "query": query},
    }
    assert verify_gold.main_for_test([case]) == 1


def test_render_prompt_injects_frontmatter_stripped_skill_only_for_with_skill(tmp_path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\nBody instructions.\n")
    skill = arena.Skill("demo", skill_dir, {"skill_path": "SKILL.md"})
    case = {"input": "CSV prompt"}
    baseline = arena.render_prompt(skill, case, {"name": "baseline", "template": "{input}"})
    injected = arena.render_prompt(skill, case, {"name": "with-skill", "inject_skill": True, "template": "{input}"})
    assert baseline == "CSV prompt"
    assert injected == "Body instructions.\n\nCSV prompt"
    assert "---" not in injected


def test_receipt_computes_delta_from_minimal_results(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        "\n".join(
            json.dumps({"id": f"{tier}-1", "meta": {"tier": tier}})
            for tier in ["easy", "medium", "hard"]
        )
        + "\n"
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps({
        "skills": {
            "csv-analysis": {
                "cells": [
                    {"backend": "codex", "prompt_variant": "baseline", "pass_rate": 1 / 3, "cases": [
                        {"id": "easy-1", "pass": True}, {"id": "medium-1", "pass": False}, {"id": "hard-1", "pass": False}
                    ]},
                    {"backend": "codex", "prompt_variant": "with-skill", "pass_rate": 2 / 3, "cases": [
                        {"id": "easy-1", "pass": True}, {"id": "medium-1", "pass": True}, {"id": "hard-1", "pass": False}
                    ]},
                ]
            }
        }
    }))
    text = receipt.build_receipt(results_path, cases_path)
    assert "- delta: 33.3%" in text
    assert "| medium | 0.0% | 100.0% | 100.0% |" in text
