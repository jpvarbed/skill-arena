import json

from arena import Skill


def fixed_results(success=True):
    target_original = 1 if success else 2
    target_v1 = 2
    return {
        "schema_version": 1,
        "skill": "ai-writing-tell",
        "target": "haiku",
        "contestants": [
            {"id": "baseline", "kind": "baseline", "text": ""},
            {"id": "original", "kind": "original", "text": "old skill\n"},
            {"id": "v1", "kind": "variant", "text": "old skill\nnew rule\n"},
            {"id": "v2", "kind": "variant", "text": "old skill\nbetter rule\n"},
        ],
        "models": [
            {"backend": "haiku", "model_id": "claude-haiku-4-5-20251001"},
            {"backend": "openai", "model_id": "gpt-5.5"},
        ],
        "cells": [
            cell("baseline", "haiku", 1, [False, True, False]),
            cell("baseline", "openai", 1, [True, False, False]),
            cell("original", "haiku", target_original, [False, True, bool(target_original > 1)]),
            cell("original", "openai", 2, [True, True, False]),
            cell("v1", "haiku", target_v1, [True, True, False]),
            cell("v1", "openai", 2, [True, True, False]),
            cell("v2", "haiku", 2, [True, True, False]),
            cell("v2", "openai", 2, [True, False, True]),
        ],
    }


def cell(contestant, backend, passes, outcomes):
    cases = [
        {"id": "dirty-1", "kind": "dirty", "pass": outcomes[0], "detail": "", "error": False, "output": "[]", "input": "dirty one"},
        {"id": "dirty-2", "kind": "dirty", "pass": outcomes[1], "detail": "", "error": False, "output": "[]", "input": "dirty two"},
        {"id": "clean-1", "kind": "clean", "pass": outcomes[2], "detail": "", "error": False, "output": "[]", "input": "clean one"},
    ]
    return {
        "contestant": contestant,
        "backend": backend,
        "model_id": "model",
        "score": passes / 3,
        "passes": passes,
        "n": 3,
        "errors": 0,
        "cases": cases,
    }


def test_lift_math_success_and_deterministic_winner_tiebreak():
    from forge import summarize_results

    summary = summarize_results(fixed_results(success=True))

    assert summary["success"] is True
    assert summary["target_lift"] == 1 / 3
    assert summary["winner"] == "v2"
    assert summary["models"][0] == {
        "backend": "haiku",
        "original_score": 1 / 3,
        "best_variant": "v1",
        "best_variant_score": 2 / 3,
        "lift": 1 / 3,
        "winner_score": 2 / 3,
        "winner_lift": 1 / 3,
    }


def test_target_tie_or_regression_is_no_improvement():
    from forge import summarize_results

    summary = summarize_results(fixed_results(success=False))

    assert summary["success"] is False
    assert summary["target_lift"] == 0.0
    assert summary["status"] == "failed-hero"


def test_generator_is_blind_to_cases_and_writes_variants(tmp_path):
    import forge

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text("Original skill text with throat-clear as a tell.\n")
    loaded_skill = Skill(
        name="ai-writing-tell",
        directory=skill_dir,
        config={
            "skill_path": str(skill_path),
            "scorer": {"type": "expect_set"},
            "models": {"google": "gemini-2.5-flash"},
        },
    )
    secret_case = {
        "id": "SECRET_CASE",
        "kind": "dirty",
        "context": "social",
        "expect": "SECRET_LABEL",
        "draft": "SECRET_DRAFT",
    }
    calls = []

    def generator_call(prompt, model):
        calls.append(prompt)
        assert "SECRET_CASE" not in prompt
        assert "SECRET_LABEL" not in prompt
        assert "SECRET_DRAFT" not in prompt
        # one plain SKILL.md per call (per-variant generation)
        return f"improved skill variant {len(calls)}"

    def model_call(backend, prompt, model):
        return '["SECRET_LABEL"]'

    def load_cases_after_variants(skill):
        variant_paths = sorted((tmp_path / "out" / "forge-variants" / "ai-writing-tell").glob("v*.md"))
        assert [path.name for path in variant_paths] == ["v1.md", "v2.md", "v3.md", "v4.md"]
        return [secret_case]

    forge.run_forge(
        "ai-writing-tell",
        ["google"],
        out_dir=tmp_path / "out",
        attempts=1,
        skill_loader=lambda name: loaded_skill,
        load_cases_fn=load_cases_after_variants,
        generator_call=generator_call,
        model_call=model_call,
    )

    assert calls
    variant_paths = sorted((tmp_path / "out" / "forge-variants" / "ai-writing-tell").glob("v*.md"))
    assert [path.name for path in variant_paths] == ["v1.md", "v2.md", "v3.md", "v4.md"]


def test_replay_recomputes_the_same_summary_without_model_calls(tmp_path):
    from forge import format_lift_table, replay_results, summarize_results

    path = tmp_path / "forge-results.json"
    path.write_text(json.dumps(fixed_results(success=True)))

    replayed = replay_results(path)
    expected = summarize_results(fixed_results(success=True))

    assert replayed["summary"] == expected
    assert format_lift_table(replayed["summary"]) == format_lift_table(expected)


def test_receipt_renders_hero_and_honest_negative_branches():
    from report import render_forge_receipt

    hero = render_forge_receipt(fixed_results(success=True))
    negative = render_forge_receipt(fixed_results(success=False))

    assert "A generated variant beat the original on the target model." in hero
    assert "Before / after" in hero
    assert "Winning SKILL.md diff" in hero
    assert "Cases the winner fixed" in hero
    assert "dirty one" in hero

    assert "No improvement found." in negative
    assert "Before / after" in negative
    assert "Winning SKILL.md diff" in negative
