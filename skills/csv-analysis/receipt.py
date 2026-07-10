#!/usr/bin/env python3
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_tiers(cases_path):
    tiers = {}
    with Path(cases_path).open() as f:
        for line in f:
            case = json.loads(line)
            tiers[case["id"]] = case["meta"]["tier"]
    return tiers


def pct(value):
    return f"{value * 100:.1f}%"


def build_receipt(results_path=ROOT / "out" / "results.json", cases_path=Path(__file__).with_name("cases.jsonl")):
    results = json.loads(Path(results_path).read_text())
    cells = results["skills"]["csv-analysis"]["cells"]
    tiers = load_tiers(cases_path)
    lines = ["# CSV Analysis Receipt", ""]
    for backend in sorted({cell["backend"] for cell in cells}):
        baseline = next(cell for cell in cells if cell["backend"] == backend and cell["prompt_variant"] == "baseline")
        with_skill = next(cell for cell in cells if cell["backend"] == backend and cell["prompt_variant"] == "with-skill")
        lines += [
            f"## {backend}",
            "",
            f"- baseline: {pct(baseline['pass_rate'])}",
            f"- with-skill: {pct(with_skill['pass_rate'])}",
            f"- delta: {pct(with_skill['pass_rate'] - baseline['pass_rate'])}",
            "",
            "| tier | baseline | with-skill | delta |",
            "| --- | ---: | ---: | ---: |",
        ]
        for tier in ["easy", "medium", "hard"]:
            base_cases = [case for case in baseline["cases"] if tiers[case["id"]] == tier]
            skill_cases = [case for case in with_skill["cases"] if tiers[case["id"]] == tier]
            base_rate = sum(case["pass"] for case in base_cases) / len(base_cases)
            skill_rate = sum(case["pass"] for case in skill_cases) / len(skill_cases)
            lines.append(f"| {tier} | {pct(base_rate)} | {pct(skill_rate)} | {pct(skill_rate - base_rate)} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    argv = argv or sys.argv[1:]
    results_path = Path(argv[0]) if argv else ROOT / "out" / "results.json"
    text = build_receipt(results_path)
    out = ROOT / "out" / "csv-receipt.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
