#!/usr/bin/env python3
"""Gold-free headroom SCREEN across skills — pick a forge target empirically.

For each skill, run it on representative inputs k times on the model people actually use,
and measure two cheap, gold-free signals:

  - instability = 5 - self-consistency: do the k runs DISAGREE in substance? (judge 1-5)
      High instability  -> the skill under-constrains the model -> RELIABILITY headroom.
  - delta = does the skill change the output vs a no-skill baseline? (judge 1-5)
      delta ~1 -> the skill is inert (nothing to improve *via the skill*).

  headroom = instability * (delta / 5)   # wobbly AND actually doing work

`highsignal` and `code-review` are ANCHORS: we've empirically PROVEN they're near-ceiling on
GPT-5.5, so a trustworthy screen MUST rank them low-headroom. If it doesn't, distrust the run.

Honest proxy limits: this rewards analytical/structured skills where "consistency" means
correctness. Purely creative skills (design) show high instability that isn't fixable headroom
— excluded here. The screen RANKS candidates; it does not replace a gold eval (the forge's job
on the winner).
"""
import json
import os
import statistics
import sys
from pathlib import Path

from backends import call_backend, is_error_sentinel
from scorers import parse_json_value

ROOT = Path(__file__).resolve().parent
K = 3
# Default to the codex SUBSCRIPTION (flat cost) — same GPT-5.5, no per-call metering.
# Slower per call than the OpenAI API, which is the right trade for a batch screen.
# Override with SCREEN_RUN_MODEL / SCREEN_JUDGE_MODEL (e.g. "openai" for speed, "haiku" for a cheap judge).
RUN_MODEL = os.environ.get("SCREEN_RUN_MODEL", "codex")
JUDGE_MODEL = os.environ.get("SCREEN_JUDGE_MODEL", "codex")

MP = "~/dev/mattpocockskills/skills"

# kind: "anchor" (known near-ceiling — sanity check) | "candidate"
SKILLS = [
    {"name": "highsignal", "kind": "anchor", "path": "~/dev/highsignal/SKILL.md", "inputs": [
        "Detect AI-writing tells in: 'One thing that really helps with agent reliability: you specify an output format.'",
        "Detect AI-writing tells in: 'What surprised me most was that a smaller model handled the routing just fine.'",
    ]},
    {"name": "code-review", "kind": "anchor", "path": f"{MP}/engineering/code-review/SKILL.md", "inputs": [
        "Review this diff:\n--- a/cart.ts\n+  calc(d: LineItem[]){ let x=0; for(const i of d) x+=i.price*i.qty; return x }",
        "Review this diff:\n--- a/geo.ts\n+  export function distanceKm(a: LatLng, b: LatLng){ return haversine(a, b) }",
    ]},
    {"name": "diagnosing-bugs", "kind": "candidate", "path": f"{MP}/engineering/diagnosing-bugs/SKILL.md", "inputs": [
        "Users report the cart total is sometimes NaN. Code: getTotal(){ return this.items.reduce((s,i)=>s+i.price*i.qty) } — diagnose the root cause.",
        "A React text input loses focus on every keystroke while typing. Diagnose the most likely root cause.",
    ]},
    {"name": "to-prd", "kind": "candidate", "path": f"{MP}/engineering/to-prd/SKILL.md", "inputs": [
        "Feature request: let users export their account data as a CSV file. Produce a concise PRD.",
        "Feature request: add a dark mode toggle to the settings page. Produce a concise PRD.",
    ]},
    {"name": "domain-modeling", "kind": "candidate", "path": f"{MP}/engineering/domain-modeling/SKILL.md", "inputs": [
        "Model the domain for a library book-lending system: concise core types and relationships.",
        "Model the domain for a food-delivery order lifecycle: concise core types and states.",
    ]},
    {"name": "grilling", "kind": "candidate", "path": f"{MP}/productivity/grilling/SKILL.md", "inputs": [
        "Plan: add real-time collaboration to our doc editor with websockets in two weeks. Grill this plan.",
        "Plan: migrate our monolith to microservices this quarter to improve scalability. Grill this plan.",
    ]},
]


def gen(prompt):
    return call_backend(RUN_MODEL, prompt, None)


def run_with_skill(skill_text, task):
    return gen(
        "Apply the SKILL.md below to the task. Follow it faithfully and be concise.\n\n"
        f"SKILL.md:\n<<<\n{skill_text}\n>>>\n\nTASK:\n{task}\n"
    )


def run_baseline(task):
    return gen(f"{task}\n\nBe concise.")


def _score(prompt):
    raw = call_backend(JUDGE_MODEL, prompt, None)
    value = parse_json_value(raw)
    if isinstance(value, dict) and "score" in value:
        try:
            return max(1, min(5, int(value["score"])))
        except (TypeError, ValueError):
            return None
    return None


def judge_consistency(runs):
    joined = "\n\n".join(f"[Response {i + 1}]\n{r}" for i, r in enumerate(runs))
    return _score(
        "These are independent responses to the SAME task. Rate how much they AGREE in substance "
        "and conclusions, 1-5 (5 = essentially the same substance/answer, 1 = wildly different). "
        'Return ONLY {"score": N}.\n\n' + joined
    )


def judge_delta(baseline, skilled):
    return _score(
        "Response A was produced with NO special instructions; Response B was produced with a SKILL "
        "applied — same task. Rate how much the skill CHANGED the substance, 1-5 (5 = transformed, "
        '1 = basically identical). Return ONLY {"score": N}.\n\n'
        f"[A: no skill]\n{baseline}\n\n[B: with skill]\n{skilled}"
    )


def screen_skill(spec):
    text = Path(spec["path"]).expanduser().read_text()
    per_input = []
    for task in spec["inputs"]:
        runs = [run_with_skill(text, task) for _ in range(K)]
        baseline = run_baseline(task)
        per_input.append({
            "task": task[:70],
            "consistency": judge_consistency(runs),
            "delta": judge_delta(baseline, runs[0]),
            "errors": sum(1 for r in runs + [baseline] if is_error_sentinel(r)),
        })
    cons = [p["consistency"] for p in per_input if p["consistency"] is not None]
    deltas = [p["delta"] for p in per_input if p["delta"] is not None]
    mean_cons = statistics.mean(cons) if cons else None
    mean_delta = statistics.mean(deltas) if deltas else None
    instability = (5 - mean_cons) if mean_cons is not None else None
    headroom = instability * (mean_delta / 5) if (instability is not None and mean_delta is not None) else None
    return {
        "name": spec["name"], "kind": spec["kind"],
        "mean_consistency": mean_cons, "instability": instability,
        "mean_delta": mean_delta, "headroom": headroom, "inputs": per_input,
    }


def main():
    results = [screen_skill(s) for s in SKILLS]
    ranked = sorted(results, key=lambda r: (r["headroom"] is not None, r["headroom"] or -1), reverse=True)
    out = ROOT / "out" / "screen-results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"k": K, "run_model": RUN_MODEL, "skills": ranked}, indent=2) + "\n")

    def fmt(x):
        return f"{x:.2f}" if x is not None else "n/a"

    print(f"{'skill':18} {'kind':10} {'instability':>11} {'delta':>6} {'headroom':>9}")
    print("-" * 58)
    for r in ranked:
        print(f"{r['name']:18} {r['kind']:10} {fmt(r['instability']):>11} {fmt(r['mean_delta']):>6} {fmt(r['headroom']):>9}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    sys.exit(main())
