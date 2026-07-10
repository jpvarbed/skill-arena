#!/usr/bin/env python3
import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backends import call_backend, is_error_sentinel
from scorers import score_case


ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
OUT_DIR = ROOT / "out"
DEFAULT_BACKENDS = ["codex"]
SKILL_ALIASES = {"ai-writing-tell": "highsignal"}

TELLS = {
    "throat-clear": "soft setup that delays the point (\"One thing that helps:\")",
    "claimed-emotion": "claims a feeling instead of showing it (\"what surprised me\")",
    "manufactured-drama": "a tease dressed as a hook (\"refuses to\")",
    "manufactured-quotability": "a clever closer built to sound deep, earning nothing",
    "parataxis": "short clauses stacked with no conjunction, implying an unstated link",
    "not-just-x": "\"it's not just X, it's Y\" fake elevation",
    "filler": "a sentence that carries no information; delete it and lose nothing",
    "abstract-over-number": "vague framing where a concrete number would hit harder",
    "business-speak": "lever, unlock, leverage, move the needle, step-change",
    "label-colon": "a colon faking a beat before a short payoff (\"My hardest problem: sales\")",
    "em-dash": "em dashes overused in any medium (more than ~1 per 100 words)",
    "real-actual": "real/actual as an empty intensifier",
}

def build_prompt(draft, context="social"):
    lines = "\n".join(f"- {k}: {v}" for k, v in TELLS.items())
    return (
        "You are running the 'highsignal' writing skill in DETECT mode.\n"
        "Given the DRAFT, decide which of these AI-writing tells it contains.\n"
        "Only use ids from this exact list:\n" + lines + "\n\n"
        f"The draft is a {context} piece. 'em-dash' counts in any medium when the density "
        "is high (more than ~1 per 100 words); a single em dash in long-form prose is fine. "
        "A colon introducing a genuine list is NOT 'label-colon'. Judge accordingly.\n\n"
        "Output ONLY a JSON array of the matching ids (e.g. [\"filler\",\"em-dash\"]), "
        "or [] if the draft is clean. No prose, no explanation, just the array.\n\n"
        f"DRAFT:\n{draft}\n"
    )


@dataclass(frozen=True)
class Skill:
    name: str
    directory: Path
    config: dict


def load_skill(name):
    actual_name = SKILL_ALIASES.get(name, name)
    directory = SKILLS_DIR / actual_name
    config_path = directory / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"skill config not found: {config_path}")
    return Skill(name=name, directory=directory, config=json.loads(config_path.read_text()))


def load_cases(skill):
    path = resolve_cases_path(skill)
    cases = []
    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
    return cases


def resolve_cases_path(skill):
    configured = skill.config.get("cases_path", "cases.jsonl")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = skill.directory / path
    return path


def list_skills():
    return sorted(path.name for path in SKILLS_DIR.iterdir() if (path / "config.json").exists())


def run(skills, backend_names, out_dir=OUT_DIR, dry_run=False):
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "skills": {},
    }
    for skill_name in skills:
        skill = load_skill(skill_name)
        cases = load_cases(skill)
        cells = []
        for variant in skill.config.get("prompt_variants", []):
            for backend in backend_names:
                cells.append(run_cell(skill, cases, variant, backend, dry_run=dry_run))
        results["skills"][skill.name] = {
            "cases_path": skill.config.get("cases_path", "cases.jsonl"),
            "scorer": skill.config.get("scorer", {}),
            "case_count": len(cases),
            "cells": cells,
        }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2) + "\n")

    from report import print_comparison, write_leaderboard

    print_comparison(results)
    write_leaderboard(results, out_dir / "leaderboard.html")
    print(f"\nwrote {results_path}")
    print(f"wrote {out_dir / 'leaderboard.html'}")
    return results


def run_cell(skill, cases, variant, backend, dry_run=False):
    case_results = []
    total_latency = 0.0
    for case in cases:
        prompt = render_prompt(skill, case, variant)
        model = skill.config.get("models", {}).get(backend)
        started = time.monotonic()
        if dry_run:
            output = dry_run_output(skill, case)
        else:
            output = call_backend(backend, prompt, model)
        latency = time.monotonic() - started
        total_latency += latency
        error = is_error_sentinel(output)
        try:
            verdict = score_case(case, output, skill.config.get("scorer", {}))
            error = error or bool(verdict.get("error"))
        except Exception as exc:
            error = True
            verdict = {"pass": False, "detail": f"scorer error: {exc}"}
        case_results.append({
            "id": case.get("id"),
            "pass": bool(verdict["pass"]),
            "detail": verdict["detail"],
            "error": error,
            "latency_s": round(latency, 3),
        })
    n = len(case_results)
    passed = sum(1 for result in case_results if result["pass"])
    errors = sum(1 for result in case_results if result["error"])
    return {
        "backend": backend,
        "prompt_variant": variant.get("name", "default"),
        "pass_rate": passed / n if n else None,
        "n": n,
        "passes": passed,
        "cost_est": 0.0,
        "latency_s": round(total_latency, 3),
        "errors": errors,
        "cases": case_results,
    }


def render_prompt(skill, case, variant):
    builder = variant.get("builder")
    if builder == "highsignal.build_prompt":
        return build_prompt(case["draft"], case.get("context", "social"))
    template = variant.get("template")
    if template:
        values = {
            **case,
            "input": case.get("input") or case.get("draft") or "",
            "draft": case.get("draft") or case.get("input") or "",
        }
        prompt = template.format(**values)
    else:
        prompt = case.get("input") or case.get("draft") or ""
    if variant.get("inject_skill"):
        skill_path = Path(skill.config["skill_path"]).expanduser()
        if not skill_path.is_absolute():
            skill_path = skill.directory / skill_path
        skill_text = skill_path.read_text()
        if skill_text.startswith("---\n"):
            _, sep, rest = skill_text.partition("\n---\n")
            if sep:
                skill_text = rest
        return skill_text.strip() + "\n\n" + prompt
    return prompt


def dry_run_output(skill, case):
    scorer_type = skill.config.get("scorer", {}).get("type")
    if scorer_type == "expect_set":
        if case.get("kind") == "dirty":
            expect = case.get("expect")
            return json.dumps(expect if isinstance(expect, list) else [expect])
        return "[]"
    if scorer_type == "deterministic":
        expect = case.get("expect")
        if isinstance(expect, dict) and "json" in expect:
            return json.dumps(expect["json"])
        if isinstance(expect, dict) and "exact" in expect:
            return str(expect["exact"])
        if isinstance(expect, dict) and "keyword" in expect:
            return str(expect["keyword"])
    return "{}"


def parse_backends(value):
    if not value:
        return DEFAULT_BACKENDS
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser():
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run")
    target = run_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--skill")
    target.add_argument("--all", action="store_true")
    run_parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS))
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--out-dir", default=str(OUT_DIR))

    report_parser = sub.add_parser("report")
    report_parser.add_argument("--results", default=str(OUT_DIR / "results.json"))
    report_parser.add_argument("--html", default=str(OUT_DIR / "leaderboard.html"))

    forge_parser = sub.add_parser("forge")
    forge_parser.add_argument("--skill")
    forge_parser.add_argument("--backends")
    forge_parser.add_argument("--full", action="store_true")
    forge_parser.add_argument("--replay", action="store_true")
    forge_parser.add_argument("--target", default="openai")
    forge_parser.add_argument("--attempts", type=int, default=2)
    forge_parser.add_argument(
        "--trials", type=int, default=1,
        help="Score each case k times and take the MAJORITY verdict (denoises LLM nondeterminism). Default 1.",
    )
    forge_parser.add_argument(
        "--generator", default="codex", choices=["codex", "opus", "openai", "google"],
        help="Model that GENERATES variants (the leverage step). Default codex = GPT-5.5 on subscription.",
    )
    forge_parser.add_argument("--results", default=str(OUT_DIR / "forge-results.json"))
    forge_parser.add_argument("--out-dir", default=str(OUT_DIR))
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        skills = list_skills() if args.all else [args.skill]
        run(skills, parse_backends(args.backends), out_dir=Path(args.out_dir), dry_run=args.dry_run)
        return 0
    if args.command == "report":
        from report import main as report_main

        return report_main(["--results", args.results, "--html", args.html])
    if args.command == "forge":
        from forge import cli as forge_cli

        return forge_cli(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
