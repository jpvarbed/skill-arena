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


def test_render_forge_prompt_defaults_to_tells_mode():
    from forge import render_forge_prompt

    prompt = render_forge_prompt("SKILLBODY", {"draft": "DRAFTBODY", "kind": "dirty"}, None)

    assert "tell ids" in prompt
    assert "DRAFTBODY" in prompt
    assert "SKILLBODY" in prompt


def test_render_forge_prompt_code_review_mode_uses_diff_spec_and_vocab():
    from forge import render_forge_prompt

    config = {"forge": {"mode": "code-review", "categories": {"feature-envy": "reaches into another object"}}}
    case = {"id": "x", "kind": "dirty", "expect": "spec-missing", "draft": "DIFFBODY", "spec": "SPECBODY", "context": "typescript"}

    prompt = render_forge_prompt("SKILLBODY", case, config)

    assert "DIFFBODY" in prompt          # the diff under review
    assert "SPECBODY" in prompt          # the spec, included because present
    assert "feature-envy" in prompt      # the closed vocabulary
    assert "SKILLBODY" in prompt         # the skill under test
    assert "JSON array" in prompt
    assert "tell ids" not in prompt      # not the highsignal wording


def test_render_forge_prompt_code_review_omits_spec_when_absent():
    from forge import render_forge_prompt

    config = {"forge": {"mode": "code-review", "categories": {"mysterious-name": "unclear name"}}}
    case = {"id": "y", "kind": "dirty", "expect": "mysterious-name", "draft": "DIFFONLY", "context": "typescript"}

    prompt = render_forge_prompt("SKILL", case, config)

    assert "DIFFONLY" in prompt
    assert "SPEC (" not in prompt        # no spec block when the case has no spec


def test_build_mutation_prompt_uses_config_task_and_angles_and_stays_blind():
    from forge import build_mutation_prompt

    config = {"forge": {"mutation_task": "REVIEW TASK", "mutation_angles": ["ANGLE-A", "ANGLE-B"]}}

    p0 = build_mutation_prompt("ORIGINAL", 1, 0, config=config)
    p1 = build_mutation_prompt("ORIGINAL", 1, 1, config=config)

    assert "REVIEW TASK" in p0 and "ANGLE-A" in p0
    assert "ANGLE-B" in p1
    assert "ORIGINAL" in p0
    # default (no config) preserves the highsignal framing byte-for-byte
    assert "AI-writing tells" in build_mutation_prompt("ORIG", 1, 0)


def test_score_contestant_majority_vote_denoises_trials():
    from forge import score_contestant

    skill = Skill(name="t", directory=None, config={"scorer": {"type": "expect_set"}})
    cases = [{"id": "d1", "kind": "dirty", "expect": "x", "draft": "..."}]
    # a flaky case: passes 2 of 3 trials -> majority pass, pass_rate 2/3
    outputs = iter(['["x"]', '["x"]', '[]'])

    def model_call(backend, prompt, model):
        return next(outputs)

    cell = score_contestant(skill, cases, {"id": "c", "text": "S"}, "openai", "m", model_call, trials=3)

    assert cell["cases"][0]["pass_rate"] == 2 / 3
    assert cell["cases"][0]["pass"] is True
    assert cell["cases"][0]["trials"] == 3


def test_score_contestant_even_trials_tie_fails():
    # Council finding on the k-trial diff: `pass_count * 2 >= trials` let an even-k tie count as a
    # pass (trials=2, 1/2 -> pass), inflating denoised scores. STRICT majority: tie = fail.
    from forge import score_contestant

    skill = Skill(name="t", directory=None, config={"scorer": {"type": "expect_set"}})
    cases = [{"id": "d1", "kind": "dirty", "expect": "x", "draft": "..."}]
    outputs = iter(['["x"]', "[]"])  # 1 pass, 1 fail -> tie

    def model_call(backend, prompt, model):
        return next(outputs)

    cell = score_contestant(skill, cases, {"id": "c", "text": "S"}, "openai", "m", model_call, trials=2)

    assert cell["cases"][0]["pass_rate"] == 1 / 2
    assert cell["cases"][0]["pass"] is False  # a tie is not evidence of a pass


def test_run_forge_plumbs_max_workers_to_scoring(tmp_path):
    # Council finding on the k-trial diff: the forge CLI path stayed serial — run_forge never
    # forwarded max_workers. Assert the plumbing end-to-end via a spying score path.
    import forge

    seen = {}
    real = forge.score_contestant

    def spy(skill, cases, contestant, backend, model_id, model_call, trials=1, max_workers=1):
        seen["max_workers"] = max_workers
        return real(skill, cases, contestant, backend, model_id, model_call, trials=trials, max_workers=max_workers)

    original = forge.score_contestants
    try:
        forge.score_contestants = lambda skill, cases, contestants, backends, model_call=None, trials=1, max_workers=1: (
            seen.__setitem__("max_workers", max_workers) or []
        )
        forge.run_forge(
            "highsignal",
            ["openai"],
            out_dir=tmp_path,
            target="openai",
            attempts=1,
            generator_call=lambda prompt, model: "SKILL",
            model_call=lambda backend, prompt, model: "[]",
            trials=2,
            max_workers=7,
        )
    finally:
        forge.score_contestants = original

    assert seen["max_workers"] == 7


def test_score_contestant_parallel_matches_serial():
    # Measure scoring is embarrassingly parallel (case x trial calls are independent).
    # max_workers>1 must give BYTE-IDENTICAL correctness results to serial and PRESERVE case order
    # (downstream measure.py pairs baseline vs candidate by position — a reorder would mis-pair).
    import threading

    from forge import score_contestant

    skill = Skill(name="t", directory=None, config={"scorer": {"type": "expect_set"}})
    cases = [
        {"id": "d1", "kind": "dirty", "expect": "x", "draft": "aa"},
        {"id": "d2", "kind": "dirty", "expect": "y", "draft": "bb"},
        {"id": "c1", "kind": "clean", "expect": "", "draft": "cc"},
        {"id": "d3", "kind": "dirty", "expect": "z", "draft": "dd"},
    ]
    calls = {"n": 0}
    lock = threading.Lock()

    def model_call(backend, prompt, model):
        # deterministic + ORDER-INDEPENDENT: output keyed on the case (embedded in the prompt),
        # exactly how a real backend behaves (a pure function of its args, not of call order).
        with lock:
            calls["n"] += 1
        if "aa" in prompt:
            return '["x"]'          # d1 catches its tell -> pass
        if "bb" in prompt:
            return '["q"]'          # d2 flags the wrong tell -> miss
        if "cc" in prompt:
            return "[]"             # c1 clean -> correct on a clean case
        return '["z"]'              # d3 catches its tell -> pass

    args = (skill, cases, {"id": "c", "text": "S"}, "openai", "m", model_call)
    serial = score_contestant(*args, trials=3, max_workers=1)
    parallel = score_contestant(*args, trials=3, max_workers=8)

    def shape(cell):
        return [(c["id"], c["pass"], c["pass_rate"], c["trials"]) for c in cell["cases"]]

    assert shape(parallel) == shape(serial)                       # identical verdicts...
    assert [c["id"] for c in parallel["cases"]] == ["d1", "d2", "c1", "d3"]  # ...in INPUT order
    assert parallel["score"] == serial["score"]
    assert calls["n"] == 2 * len(cases) * 3                       # every case x trial ran, both runs


def test_prompt_template_mode_matches_arena_run_prompts():
    # The original contestant must be scored on byte-identical prompts to
    # `arena run`'s — otherwise the forge silently measures a different task
    # (that exact bug cost a full 540-call run on 2026-07-12).
    from arena import load_cases, load_skill, render_prompt
    from forge import read_original_skill_text, render_forge_prompt

    skill = load_skill("instruction-conflicts")
    assert skill.config["forge"]["mode"] == "prompt-template"
    variant = skill.config["prompt_variants"][0]
    original = read_original_skill_text(skill)
    for case in load_cases(skill)[:3]:
        assert render_forge_prompt(original, case, skill.config) == render_prompt(skill, case, variant)


def test_prompt_template_mode_baseline_is_bare_template():
    from arena import load_cases, load_skill
    from forge import render_forge_prompt

    skill = load_skill("instruction-conflicts")
    case = load_cases(skill)[0]
    prompt = render_forge_prompt("", case, skill.config)
    assert prompt.startswith("Audit the layered instruction stack")
    assert "No additional skill instructions." not in prompt
