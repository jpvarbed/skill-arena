#!/usr/bin/env python3
import concurrent.futures
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from arena import OUT_DIR, load_cases, load_skill
from backends import call_backend, is_error_sentinel
from scorers import parse_json_value, score_case


VARIANTS_PER_ATTEMPT = 4
DEFAULT_TARGET = "openai"  # writing is a high-value task -> optimize for the strong model people use; haiku is a comparison column only
DEFAULT_SMOKE_BACKENDS = ["google"]
FULL_BACKENDS = ["haiku", "openai", "google"]

# Generation is the leverage step — it sets the ceiling on variant quality — so it
# gets a STRONG model, never a cheap one (cheap models belong in the scoring matrix).
# Default = GPT-5.5 on Jason's codex SUBSCRIPTION (no per-call API cost).
DEFAULT_GENERATOR = "codex"
GENERATOR_MODELS = {
    "codex": "gpt-5.5",  # via `codex exec` (subscription)
    "opus": "claude-opus-4-8",  # Anthropic API (metered) — strongest writer
    "openai": "gpt-5.5",  # OpenAI API (metered)
    "google": "gemini-2.5-flash",  # cheap fallback only
}


def _extract_skill_md(raw):
    """Pull the SKILL.md body out of a model reply, tolerating a code fence or
    a one-line preamble. Empty -> ''."""
    text = str(raw).strip()
    if "```" in text:
        blocks = text.split("```")
        if len(blocks) >= 3:
            body = blocks[1]
            if body.lstrip().split("\n", 1)[0].strip().lower() in {"md", "markdown", "text"}:
                body = body.split("\n", 1)[1] if "\n" in body else ""
            return body.strip()
    return text


def _codex_generate(prompt, model):
    """One strong-model completion via the codex subscription. `--output-last-message`
    gives the clean final message (no agent banner/scaffolding)."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as tf:
        out_path = tf.name
    try:
        subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-C", tempfile.gettempdir(),
             "-m", model or "gpt-5.5", "--output-last-message", out_path, prompt],
            capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
        )
        return Path(out_path).read_text()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _anthropic_generate(prompt, model):
    key = os.environ.get("claude_skill_arena_api_key") or os.environ["ANTHROPIC_API_KEY"]
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": model or "claude-opus-4-8", "max_tokens": 8192,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.load(resp)
    return "".join(b.get("text", "") for b in payload.get("content", []))


def _make_generator_call(generator):
    if generator == "codex":
        return _codex_generate
    if generator == "opus":
        return _anthropic_generate
    return lambda prompt, model: call_backend(generator, prompt, model)


def run_forge(
    skill_name,
    backend_names=None,
    out_dir=OUT_DIR,
    target=DEFAULT_TARGET,
    attempts=2,
    skill_loader=load_skill,
    load_cases_fn=load_cases,
    generator_call=None,
    generator=DEFAULT_GENERATOR,
    model_call=None,
    trials=1,
):
    out_dir = Path(out_dir)
    skill = skill_loader(skill_name)
    target = normalize_target(target)
    backends = normalize_backends(backend_names or DEFAULT_SMOKE_BACKENDS)
    attempts = max(1, int(attempts))
    max_attempts = attempts if target in backends else 1

    original_text = read_original_skill_text(skill)
    contestants = [
        {"id": "baseline", "kind": "baseline", "text": ""},
        {"id": "original", "kind": "original", "text": original_text},
    ]
    cells = []
    generation = []

    for attempt in range(1, max_attempts + 1):
        variants, generation_record = generate_variants(
            original_text,
            VARIANTS_PER_ATTEMPT,
            attempt,
            generator_call=generator_call,
            generator=generator,
            config=skill.config,
        )
        write_variant_files(variants, out_dir, skill.name)
        generation.append(generation_record)
        contestants.extend(variants)

    cases = load_cases_fn(skill)
    cells.extend(score_contestants(skill, cases, contestants, backends, model_call=model_call, trials=trials))

    results = build_results(skill, target, backends, contestants, cells, generation, attempts)
    results["trials"] = trials
    results["summary"] = summarize_results(results)
    path = write_results(results, out_dir / "forge-results.json")

    from report import write_forge_receipt

    receipt_path = write_forge_receipt(results, out_dir / "receipt.html")
    print(format_lift_table(results["summary"]))
    print(f"winner={results['summary']['winner'] or 'none'}")
    print(f"status={results['summary']['status']}")
    print(f"wrote {path}")
    print(f"wrote {receipt_path}")
    return results


def replay_results(path):
    results = json.loads(Path(path).read_text())
    summary = summarize_results(results)
    results = dict(results)
    results["summary"] = summary
    return {"results": results, "summary": summary}


def cli(args, stream=None):
    stream = stream or sys.stdout
    if args.replay:
        replayed = replay_results(args.results)
        from report import write_forge_receipt

        receipt_path = write_forge_receipt(replayed["results"], Path(args.out_dir) / "receipt.html")
        print(format_lift_table(replayed["summary"]), file=stream)
        print(f"winner={replayed['summary']['winner'] or 'none'}", file=stream)
        print(f"status={replayed['summary']['status']}", file=stream)
        print(f"wrote {receipt_path}", file=stream)
        return 0

    if not args.skill:
        raise SystemExit("arena forge requires --skill unless --replay is set")
    backends = forge_backends(args.backends, args.full, args.target)
    run_forge(
        args.skill,
        backends,
        out_dir=Path(args.out_dir),
        target=args.target,
        attempts=args.attempts,
        generator=getattr(args, "generator", DEFAULT_GENERATOR),
        trials=getattr(args, "trials", 1),
    )
    return 0


def forge_backends(backends_arg, full, target):
    if full:
        return unique([normalize_target(target)] + FULL_BACKENDS + normalize_backends(backends_arg or []))
    return normalize_backends(backends_arg or DEFAULT_SMOKE_BACKENDS)


def build_results(skill, target, backends, contestants, cells, generation, attempts):
    return {
        "schema_version": 1,
        "generated_at": now_utc(),
        "skill": skill.name,
        "target": target,
        "attempts_requested": attempts,
        "variants_per_attempt": VARIANTS_PER_ATTEMPT,
        "cases_path": skill.config.get("cases_path", "cases.jsonl"),
        "contestants": contestants,
        "models": [{"backend": backend, "model_id": resolve_model_id(skill, backend)} for backend in backends],
        "generation": generation,
        "cells": cells,
    }


def generate_variants(original_text, count, attempt, generator_call=None, generator=DEFAULT_GENERATOR, config=None):
    # ONE strong-model call per variant (plain SKILL.md text). Per-variant angles
    # keep them meaningfully different without a fragile "N-at-once" JSON payload
    # that truncates. The generator sees only the original + the angle — never cases.
    generator_call = generator_call or _make_generator_call(generator)
    model = GENERATOR_MODELS.get(generator)
    first = ((attempt - 1) * count) + 1
    generated_at = now_utc()
    variants = []
    raws = []
    for offset in range(count):
        prompt = build_mutation_prompt(original_text, attempt, offset, config=config)
        raw = generator_call(prompt, model)
        text = _extract_skill_md(raw)
        if not text.strip():
            raise ValueError(f"generator returned an empty variant (attempt {attempt}, index {offset})")
        raws.append(raw)
        variants.append({
            "id": f"v{first + offset}",
            "kind": "variant",
            "attempt": attempt,
            "text": text.strip() + "\n",
            "generated_at": generated_at,
        })
    return variants, {
        "attempt": attempt,
        "generator": generator,
        "model_id": model,
        "generated_at": generated_at,
        "variant_ids": [variant["id"] for variant in variants],
        "raw_output": raws,
    }


_MUTATION_ANGLES = [
    "Tighten each tell's definition and add one crisp positive+negative example per tell.",
    "Add a short decision procedure the model follows per sentence, and sharpen the edge cases.",
    "Reduce false positives: state explicitly what each tell is NOT, with counter-examples.",
    "Reorder for salience and add a compact checklist the model applies before answering.",
]


_DEFAULT_MUTATION_TASK = "You are improving a SKILL.md used to DETECT AI-writing tells in text."


def build_mutation_prompt(original_text, attempt, index, config=None):
    forge_cfg = config.get("forge", {}) if isinstance(config, dict) else {}
    angles = forge_cfg.get("mutation_angles") or _MUTATION_ANGLES
    task = forge_cfg.get("mutation_task") or _DEFAULT_MUTATION_TASK
    angle = angles[index % len(angles)]
    return (
        f"{task}\n"
        "Rewrite it into a single, better SKILL.md. Improvement angle for this variant: "
        f"{angle}\n"
        "Use ONLY the SKILL.md text below. Do NOT ask for or refer to any test cases or benchmark.\n"
        "Keep it generic, concise, and directly usable. Return ONLY the improved SKILL.md — no preamble,\n"
        "no explanation, no code fence.\n\n"
        "SKILL.md:\n<<<SKILL\n"
        f"{original_text}\n"
        "SKILL\n"
    )


def write_variant_files(variants, out_dir, skill_name):
    variant_dir = Path(out_dir) / "forge-variants" / skill_name
    variant_dir.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        path = variant_dir / f"{variant['id']}.md"
        path.write_text(variant["text"])
        variant["path"] = str(path)


def score_contestants(skill, cases, contestants, backends, model_call=None, trials=1):
    model_call = model_call or call_backend
    cells = []
    for contestant in contestants:
        for backend in backends:
            model_id = resolve_model_id(skill, backend)
            cells.append(score_contestant(skill, cases, contestant, backend, model_id, model_call, trials=trials))
    return cells


def score_contestant(skill, cases, contestant, backend, model_id, model_call, trials=1, max_workers=1):
    # trials > 1 scores each case k times and takes the MAJORITY verdict. LLM scoring
    # is nondeterministic (a strong model's false-positive rate swings case-to-case
    # between runs); on a small case set one flaky case = several points, which drowns
    # a real 1-2 case improvement. Majority-of-k denoises it. (Same lesson as the
    # gemini visual-critic variance: vote, don't trust a single run.)
    #
    # max_workers > 1 fans the (case x trial) model_call's out through a bounded thread
    # pool. Every call is independent and subprocess/HTTP-bound (e.g. `codex exec`), so
    # threads give real parallelism; outputs are collected BY INDEX so the per-case scoring
    # below is byte-identical to the serial order regardless of completion order. Default 1
    # keeps the exact original sequential behavior — callers that want speed (measure) opt in.
    trials = max(1, int(trials))
    max_workers = max(1, int(max_workers))
    scorer_cfg = skill.config.get("scorer", {})
    prompts = [render_forge_prompt(contestant["text"], case, skill.config) for case in cases]
    n_cases = len(cases)
    outputs = [[None] * trials for _ in range(n_cases)]     # outputs[case_idx][trial_idx]
    timing = [[(0.0, None)] * trials for _ in range(n_cases)]  # (latency_s, called_at) per call

    def _call(ci, tj):
        called_at = now_utc()
        started = time.monotonic()
        try:
            out = model_call(backend, prompts[ci], model_id)
        except Exception as exc:            # a raised backend error fails THIS trial, not the pool
            out = f"ERROR: scoring call raised: {exc}"
        return ci, tj, out, time.monotonic() - started, called_at

    work = [(ci, tj) for ci in range(n_cases) for tj in range(trials)]
    if max_workers == 1 or len(work) <= 1:
        collected = (_call(ci, tj) for ci, tj in work)
    else:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = [pool.submit(_call, ci, tj) for ci, tj in work]
            collected = [f.result() for f in concurrent.futures.as_completed(futures)]
        finally:
            pool.shutdown(wait=True)
    for ci, tj, out, dur, called_at in collected:
        outputs[ci][tj] = out
        timing[ci][tj] = (dur, called_at)

    case_results = []
    total_latency = 0.0
    for ci, case in enumerate(cases):
        trial_outputs = outputs[ci]
        called_at = timing[ci][0][1]                         # first trial's timestamp
        latency = sum(dur for dur, _ in timing[ci])          # total model time for this case
        total_latency += latency
        trial_passes = []
        error = False
        last_detail = ""
        for output in trial_outputs:
            err = is_error_sentinel(output)
            try:
                verdict = score_case(case, output, scorer_cfg)
                err = err or bool(verdict.get("error"))
                passed = bool(verdict["pass"])
                last_detail = verdict["detail"]
            except Exception as exc:
                err = True
                passed = False
                last_detail = f"scorer error: {exc}"
            trial_passes.append(passed)
            error = error or err
        pass_count = sum(1 for passed in trial_passes if passed)
        case_pass = pass_count * 2 >= trials  # majority; ties -> pass
        detail = f"{pass_count}/{trials} trials pass; {last_detail}" if trials > 1 else last_detail
        case_results.append({
            "id": case.get("id"),
            "kind": case.get("kind"),
            "input": case.get("draft") or case.get("input") or "",
            "pass": case_pass,
            "pass_rate": pass_count / trials,
            "trials": trials,
            "detail": detail,
            "error": error,
            "called_at": called_at,
            "latency_s": round(latency, 3),
            "output": trial_outputs[0],
            "trial_outputs": trial_outputs if trials > 1 else None,
        })
    n = len(case_results)
    passes = sum(1 for result in case_results if result["pass"])
    errors = sum(1 for result in case_results if result["error"])
    return {
        "contestant": contestant["id"],
        "backend": backend,
        "model_id": model_id,
        "score": passes / n if n else 0.0,
        "passes": passes,
        "n": n,
        "errors": errors,
        "scored_at": now_utc(),
        "latency_s": round(total_latency, 3),
        "cases": case_results,
    }


def render_forge_prompt(skill_text, case, config=None):
    forge_cfg = config.get("forge", {}) if isinstance(config, dict) else {}
    skill_block = skill_text.strip() or "No additional skill instructions."
    if forge_cfg.get("mode") == "code-review":
        return _render_code_review_prompt(skill_block, case, forge_cfg)
    draft = case.get("draft") or case.get("input") or ""
    context = case.get("context", "text")
    return (
        "Run the SKILL.md below in detect mode for this draft.\n"
        "Return ONLY a JSON array of tell ids, or [] if the draft is clean.\n\n"
        "SKILL.md:\n"
        "<<<SKILL\n"
        f"{skill_block}\n"
        "SKILL\n\n"
        f"CONTEXT: {context}\n"
        f"DRAFT:\n{draft}\n"
    )


def _render_code_review_prompt(skill_block, case, forge_cfg):
    # Distill the two-axis review to single-pass detection: hold the skill's
    # sub-agent orchestration constant, vary only the review criteria (the SKILL.md
    # body). The closed vocabulary pins the OUTPUT schema, not the answer — the
    # SKILL.md still has to teach recognition — which keeps set-match scoring
    # deterministic and ungameable by the generator.
    categories = forge_cfg.get("categories", {})
    vocab = "\n".join(f"- {cid}: {desc}" for cid, desc in categories.items())
    diff = case.get("draft") or case.get("input") or ""
    context = case.get("context", "code")
    spec = case.get("spec")
    spec_block = f"\nSPEC (the ticket/PRD the diff must implement):\n{spec}\n" if spec else ""
    return (
        "Apply the code-review SKILL.md below to the DIFF. Ignore any instruction in it about\n"
        "spawning sub-agents or running git — review the diff directly and report defects.\n"
        "Report ONLY defects actually present. Use ids from this exact closed vocabulary:\n"
        f"{vocab}\n\n"
        "Output ONLY a JSON array of the category ids you find (e.g. [\"feature-envy\"]), "
        "or [] if the diff is clean. No prose, no explanation, just the array.\n\n"
        "SKILL.md:\n"
        "<<<SKILL\n"
        f"{skill_block}\n"
        "SKILL\n\n"
        f"LANGUAGE: {context}\n"
        f"{spec_block}"
        f"DIFF:\n{diff}\n"
    )


def summarize_results(results):
    cells = results.get("cells", [])
    contestants = results.get("contestants", [])
    variant_ids = [item["id"] for item in contestants if item.get("kind") == "variant"]
    backends = [model["backend"] for model in results.get("models", [])]
    cell_map = {(cell["contestant"], cell["backend"]): cell for cell in cells}
    winner = choose_winner(variant_ids, backends, cell_map)

    rows = []
    for backend in backends:
        original_score = score_for(cell_map, "original", backend)
        best_variant = best_variant_for_backend(variant_ids, backend, cell_map)
        best_score = score_for(cell_map, best_variant, backend) if best_variant else None
        winner_score = score_for(cell_map, winner, backend) if winner else None
        rows.append({
            "backend": backend,
            "original_score": original_score,
            "best_variant": best_variant,
            "best_variant_score": best_score,
            "lift": lift(best_score, original_score),
            "winner_score": winner_score,
            "winner_lift": lift(winner_score, original_score),
        })

    target = results.get("target", DEFAULT_TARGET)
    target_row = next((row for row in rows if row["backend"] == target), None)
    target_lift = target_row["lift"] if target_row else None
    success = target_lift is not None and target_lift > 0
    return {
        "status": "hero" if success else "failed-hero",
        "success": success,
        "target": target,
        "target_lift": target_lift,
        "winner": winner,
        "winner_mean_score": mean_score(winner, backends, cell_map) if winner else None,
        "baseline_mean_score": mean_score("baseline", backends, cell_map),
        "original_mean_score": mean_score("original", backends, cell_map),
        "models": rows,
    }


def choose_winner(variant_ids, backends, cell_map):
    if not variant_ids:
        return None
    ranked = sorted(
        variant_ids,
        key=lambda variant_id: (
            -mean_score(variant_id, backends, cell_map),
            clean_false_positives(variant_id, backends, cell_map),
            variant_id,
        ),
    )
    return ranked[0]


def best_variant_for_backend(variant_ids, backend, cell_map):
    present = [variant_id for variant_id in variant_ids if (variant_id, backend) in cell_map]
    if not present:
        return None
    return sorted(present, key=lambda variant_id: (-score_for(cell_map, variant_id, backend), variant_id))[0]


def mean_score(contestant, backends, cell_map):
    if contestant is None:
        return 0.0
    scores = [score_for(cell_map, contestant, backend) for backend in backends if (contestant, backend) in cell_map]
    return sum(scores) / len(scores) if scores else 0.0


def score_for(cell_map, contestant, backend):
    cell = cell_map.get((contestant, backend))
    return float(cell.get("score", 0.0)) if cell else None


def lift(after, before):
    if after is None or before is None:
        return None
    return after - before


def clean_false_positives(contestant, backends, cell_map):
    count = 0
    for backend in backends:
        cell = cell_map.get((contestant, backend))
        if not cell:
            continue
        count += sum(1 for case in cell.get("cases", []) if case.get("kind") == "clean" and not case.get("pass"))
    return count


def fixed_cases(results, contestant, target=None):
    target = target or results.get("target", DEFAULT_TARGET)
    original = cell_lookup(results).get(("original", target))
    winner = cell_lookup(results).get((contestant, target))
    if not original or not winner:
        return []
    by_id = {case.get("id"): case for case in winner.get("cases", [])}
    fixed = []
    for original_case in original.get("cases", []):
        winner_case = by_id.get(original_case.get("id"))
        if original_case.get("pass") or not winner_case or not winner_case.get("pass"):
            continue
        fixed.append({
            "id": original_case.get("id"),
            "input": original_case.get("input", ""),
            "original_detail": original_case.get("detail", ""),
            "winner_detail": winner_case.get("detail", ""),
        })
    return fixed


def contestant_text(results, contestant_id):
    for contestant in results.get("contestants", []):
        if contestant.get("id") == contestant_id:
            return contestant.get("text", "")
    return ""


def original_text(results):
    return contestant_text(results, "original")


def cell_lookup(results):
    return {(cell["contestant"], cell["backend"]): cell for cell in results.get("cells", [])}


def format_lift_table(summary):
    headers = ["model", "original", "best", "lift", "winner"]
    rows = []
    for row in summary.get("models", []):
        rows.append([
            row["backend"],
            format_pct(row["original_score"]),
            f"{row['best_variant'] or '-'} {format_pct(row['best_variant_score'])}",
            format_pp(row["lift"]),
            f"{summary.get('winner') or '-'} {format_pct(row['winner_score'])}",
        ])
    return text_table("Forge lift", headers, rows)


def text_table(title, headers, rows):
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(str(value))) for width, value in zip(widths, row)]
    lines = [title, "  ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))
    return "\n".join(lines)


def format_pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def format_pp(value):
    return "n/a" if value is None else f"{value * 100:+.1f}pp"


def normalize_backends(names):
    if isinstance(names, str):
        names = [part.strip() for part in names.split(",") if part.strip()]
    return unique(normalize_backend(name) for name in names if name)


def normalize_backend(name):
    value = str(name).strip().lower()
    if value in {"anthropic", "anthropic:haiku", "anthropic:claude-haiku-4-5"}:
        return "haiku"
    if value.startswith("anthropic:") and "haiku" in value:
        return "haiku"
    if value.startswith("openai:"):
        return "openai"
    if value.startswith("google:"):
        return "google"
    return value


def normalize_target(value):
    return normalize_backend(value or DEFAULT_TARGET)


def unique(values):
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def resolve_model_id(skill, backend):
    models = skill.config.get("models", {})
    if backend == "google":
        return models.get("google") or models.get("gemini-flash") or GENERATOR_MODELS["google"]
    if backend == "haiku":
        return models.get("haiku") or "claude-haiku-4-5-20251001"
    if backend == "openai":
        return models.get("openai") or "gpt-5.5"
    return models.get(backend)


def read_original_skill_text(skill):
    path = resolve_skill_path(skill)
    return path.read_text()


def resolve_skill_path(skill):
    configured = skill.config.get("skill_path") or skill.config.get("skill_md_path")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = skill.directory / path
        return path
    local = skill.directory / "SKILL.md"
    if local.exists():
        return local
    if skill.name in {"highsignal", "ai-writing-tell"}:
        return Path("~/dev/highsignal/SKILL.md").expanduser()
    raise FileNotFoundError(f"skill_path not configured and no SKILL.md found for {skill.name}")


def write_results(results, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2) + "\n")
    return path


def now_utc():
    return datetime.now(timezone.utc).isoformat()
