#!/usr/bin/env python3
"""Precision diagnostic + eligibility gate for expect_set forge results.

The subset-pass scorer (any expected/got overlap passes a dirty case) leaves
over-labeling invisible outside clean cases. This tool recomputes, from the raw
per-trial outputs stored in a forge results.json, the precision picture for each
contestant on one backend — and applies a release gate to the declared winner:

  eligible iff, vs the "original" contestant on the same backend:
    (a) subset-pass score is strictly higher            (the forge's own lift), and
    (b) mean extra labels per dirty case is not higher  (no over-labeling regression), and
    (c) clean-case passes are not lower                 (no false-positive regression).

Usage:
  python precision.py --results out/forge-X/results.json --backend <backend>
Writes precision.json + precision.md next to the results file and prints one
verdict line. Generic over any expect_set skill; no skill names hardcoded.
"""
import argparse
import json
import statistics
from pathlib import Path

from arena import load_cases, load_skill
from scorers import parse_array


def case_expect_map(skill_name):
    skill = load_skill(skill_name)
    return {case["id"]: case for case in load_cases(skill)}


def contestant_metrics(cell, cases_by_id, trials_expected=None):
    """Per-contestant precision metrics.

    clean_passes uses the runner's own k-majority verdict per case — the same
    standard as the headline score, and the one the release gate is registered
    against. clean_all_trials (every trial clean) is the stricter diagnostic.
    exact_set_rate is case-level (exact on every parseable trial); extras are
    the mean over cases of each case's mean-across-trials.

    Coverage is tracked, not silently absorbed: unknown case ids, missing
    outputs, and unparseable trials are counted, and the release gate refuses
    a verdict for contestants with incomplete coverage (fail closed).
    """
    exact_hits = 0
    scored = 0
    clean_passes = 0
    clean_all_trials = 0
    clean_total = 0
    extras_per_dirty_case = []
    unknown_case_ids = 0
    unparseable_trials = 0
    for row in cell.get("cases", []):
        case = cases_by_id.get(row.get("id"))
        if case is None:
            unknown_case_ids += 1
            continue
        outputs = row.get("trial_outputs") or [row.get("output")]
        outputs = [o for o in outputs if o is not None]
        gots_raw = [parse_array(o) for o in outputs]
        unparseable_trials += sum(1 for g in gots_raw if g is None)
        if trials_expected is not None and len(outputs) < trials_expected:
            unparseable_trials += trials_expected - len(outputs)
        gots = [g for g in gots_raw if g is not None]
        if not gots:
            continue
        scored += 1
        if case["kind"] == "dirty":
            exp = set(case["expect"]) if isinstance(case["expect"], list) else {case["expect"]}
            extras = [len(g - exp) for g in gots]
            extras_per_dirty_case.append(statistics.mean(extras))
            if all(g == exp for g in gots):
                exact_hits += 1
        else:
            clean_total += 1
            if bool(row.get("pass")):
                clean_passes += 1
            if all(len(g) == 0 for g in gots):
                exact_hits += 1
                clean_all_trials += 1
    passes = cell.get("passes")
    n = cell.get("n")
    return {
        "contestant": cell.get("contestant"),
        "backend": cell.get("backend"),
        "subset_score": (passes / n) if passes is not None and n else None,
        "passes": passes,
        "n": n,
        "errors": cell.get("errors"),
        "exact_set_rate": round(exact_hits / scored, 4) if scored else None,
        "mean_extra_labels_dirty": (
            round(statistics.mean(extras_per_dirty_case), 4) if extras_per_dirty_case else None
        ),
        "clean_passes": clean_passes,
        "clean_all_trials": clean_all_trials,
        "clean_total": clean_total,
        "cases_scored": scored,
        "unknown_case_ids": unknown_case_ids,
        "unparseable_trials": unparseable_trials,
    }


def full_coverage(metrics, case_count):
    """A gated contestant must cover every case with every trial parseable."""
    return (
        metrics["cases_scored"] == case_count
        and metrics["unknown_case_ids"] == 0
        and metrics["unparseable_trials"] == 0
    )


def eligibility(winner_m, original_m):
    checks = {
        "subset_score_strictly_higher": (
            winner_m["subset_score"] is not None
            and original_m["subset_score"] is not None
            and winner_m["subset_score"] > original_m["subset_score"]
        ),
        "extra_labels_not_worse": (
            winner_m["mean_extra_labels_dirty"] is not None
            and original_m["mean_extra_labels_dirty"] is not None
            and winner_m["mean_extra_labels_dirty"] <= original_m["mean_extra_labels_dirty"]
        ),
        "clean_passes_not_worse": winner_m["clean_passes"] >= original_m["clean_passes"],
    }
    return {"eligible": all(checks.values()), "checks": checks}


def render_md(report):
    lines = [
        "## Precision diagnostic (secondary; headline metric is subset-pass)",
        "",
        "The headline scorer passes a dirty case on ANY overlap with the expected set, so",
        "over-labeling is invisible outside clean cases. This table re-parses raw outputs.",
        "",
        "| contestant | subset score | exact-set rate | mean extra labels (dirty) | clean passes (k-majority) | clean all-trials |",
        "|---|---|---|---|---|---|",
    ]
    for m in report["contestants"]:
        lines.append(
            f"| {m['contestant']} | {m['passes']}/{m['n']} | {m['exact_set_rate']} "
            f"| {m['mean_extra_labels_dirty']} | {m['clean_passes']}/{m['clean_total']} "
            f"| {m['clean_all_trials']}/{m['clean_total']} |"
        )
    gate = report.get("gate")
    if gate:
        if gate.get("coverage_failure"):
            lines += ["", "**Winner eligibility gate: NO VERDICT (coverage failure)**", "",
                      f"- incomplete evidence for: {', '.join(gate['coverage_failure'])} "
                      "(every case and every trial must be present and parseable)"]
        else:
            lines += ["", f"**Winner eligibility gate: {'PASS' if gate['eligible'] else 'FAIL'}**", ""]
            for name, ok in gate["checks"].items():
                lines.append(f"- {name}: {'ok' if ok else 'FAIL'}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--backend", required=True)
    args = ap.parse_args()

    results_path = Path(args.results)
    results = json.loads(results_path.read_text())
    trials = int(results.get("trials") or 1)
    cases_by_id = case_expect_map(results["skill"])
    cells = [c for c in results["cells"] if c.get("backend") == args.backend]
    metrics = [contestant_metrics(c, cases_by_id, trials_expected=trials) for c in cells]
    by_id = {m["contestant"]: m for m in metrics}

    report = {"skill": results["skill"], "backend": args.backend, "trials": trials,
              "contestants": metrics}
    winner = (results.get("summary") or {}).get("winner")
    if winner and winner in by_id and "original" in by_id:
        report["winner"] = winner
        # fail closed: no verdict at all unless BOTH gated contestants cover every
        # case with every trial parseable — partial evidence must not turn ELIGIBLE
        bad = [cid for cid in (winner, "original")
               if not full_coverage(by_id[cid], len(cases_by_id))]
        if bad:
            report["gate"] = {"eligible": False, "coverage_failure": bad, "checks": {}}
        else:
            report["gate"] = eligibility(by_id[winner], by_id["original"])

    (results_path.parent / "precision.json").write_text(json.dumps(report, indent=2) + "\n")
    (results_path.parent / "precision.md").write_text(render_md(report))
    gate = report.get("gate")
    if not gate:
        print("precision gate: no-winner  (wrote precision.json / precision.md)")
        return 2
    if gate.get("coverage_failure"):
        print(f"precision gate: COVERAGE-FAILURE {gate['coverage_failure']}  "
              "(wrote precision.json / precision.md)")
        return 2
    verdict = "ELIGIBLE" if gate["eligible"] else "INELIGIBLE"
    print(f"precision gate: {verdict}  (wrote precision.json / precision.md)")
    return 0 if gate["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
