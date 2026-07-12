#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

try:
    from . import validate_app
except ImportError:
    import validate_app


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DEFAULT_RESULTS = REPO_ROOT / "out" / "total-tdd" / "results.csv"
DEFAULT_REPORT = REPO_ROOT / "out" / "total-tdd-report.md"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def bool_cell(row: dict, key: str) -> bool:
    return str(row.get(key, "")).casefold() == "true"


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(rows: list[dict], manifest: dict) -> dict:
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row["arm"]].append(row)
    summary = {}
    for arm, arm_rows in by_arm.items():
        discovered = {
            defect["id"]: sum(1 for row in arm_rows if bool_cell(row, f"{defect['id']}_discovered"))
            for defect in manifest["defects"]
        }
        fixed = {
            defect["id"]: sum(1 for row in arm_rows if bool_cell(row, f"{defect['id']}_fixed"))
            for defect in manifest["defects"]
        }
        discovery_rate = sum(discovered.values()) / (len(arm_rows) * len(manifest["defects"])) if arm_rows else 0.0
        summary[arm] = {
            "trials": len(arm_rows),
            "discovered": discovered,
            "fixed": fixed,
            "discovery_rate": discovery_rate,
            "regressions": sum(int(row.get("regressions") or 0) for row in arm_rows),
            "conformance": sum(1 for row in arm_rows if bool_cell(row, "conformance_ok")),
            "resolved": sum(1 for row in arm_rows if row.get("status") == "resolved"),
            "duration_s": avg([float(row.get("duration_s") or 0) for row in arm_rows]),
        }
    return summary


def rule_text(defect: dict) -> str:
    chunks = []
    for rule in defect.get("match_rules", []):
        parts = []
        if rule.get("all"):
            parts.append("all(" + ", ".join(rule["all"]) + ")")
        if rule.get("any"):
            parts.append("any(" + ", ".join(rule["any"]) + ")")
        if rule.get("keywords"):
            parts.append("keywords(" + ", ".join(rule["keywords"]) + ")")
        if rule.get("files"):
            parts.append("files(" + ", ".join(rule["files"]) + ")")
        chunks.append(" + ".join(parts))
    return " OR ".join(chunks)


def render_report(rows: list[dict], manifest: dict) -> str:
    summary = summarize(rows, manifest)
    baseline = summary.get("baseline")
    tripped = bool(baseline and baseline["discovery_rate"] > 0.80)
    verdict = "TRIPPED" if tripped else "not tripped"
    lines = [
        "# total-tdd Wave B Receipt",
        "",
        f"Conclusion: baseline discovery band verdict is **{verdict}**. The band trips when baseline discovery above 80%.",
        "Resolved threshold: a trial is `resolved` only when at least 6 of 8 defects are fixed with zero regressions.",
        "",
        "## Summary",
        "",
        "| arm | trials | resolved | discovery | conformance | regressions | avg duration s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm in sorted(summary):
        item = summary[arm]
        lines.append(
            f"| {arm} | {item['trials']} | {item['resolved']} | {item['discovery_rate']:.1%} | "
            f"{item['conformance']}/{item['trials']} | {item['regressions']} | {item['duration_s']:.1f} |"
        )
    lines.extend(["", "## Per-Defect Discovery/Fix", ""])
    for arm in sorted(summary):
        item = summary[arm]
        lines.extend([f"### {arm}", "", "| defect | discovered | fixed |", "| --- | ---: | ---: |"])
        for defect in manifest["defects"]:
            defect_id = defect["id"]
            lines.append(f"| {defect_id} | {item['discovered'][defect_id]}/{item['trials']} | {item['fixed'][defect_id]}/{item['trials']} |")
        lines.append("")
    caveats = []
    if not rows:
        caveats.append("No trials were present in the results CSV.")
    if "skill" not in summary:
        caveats.append("Skill arm was not present in this result set.")
    if "baseline" not in summary:
        caveats.append("Baseline arm was not present in this result set.")
    if not caveats:
        caveats.append("No live-agent claims are implied by fake-agent unit tests; this receipt only summarizes the provided results CSV.")
    lines.extend(["## Caveats", ""])
    lines.extend(f"- {item}" for item in caveats)
    lines.extend([
        "",
        "## Metrics Definitions",
        "",
        "- Discovery: a defect is discovered when any tracker.csv row matches one of its manifest rules.",
        "- Fix: every FAIL_TO_PASS test for the defect passes after the run and the relevant test file was not modified.",
        "- Regression: any originally passing seeded-app test fails after the run.",
        "- Conformance: tracker.csv parses with the total-tdd 9-column schema and status enum.",
        "- Integrity: if a defect's FAIL_TO_PASS test file changed, that defect's fix is not counted.",
        "",
    ])
    for defect in manifest["defects"]:
        lines.append(f"- `{defect['id']}` discovery match: {rule_text(defect)}")
    lines.extend([
        "",
        "| defect | category | match rules | fail_to_pass |",
        "| --- | --- | --- | --- |",
    ])
    for defect in manifest["defects"]:
        lines.append(
            f"| {defect['id']} | {defect['category']} | {rule_text(defect)} | "
            f"{'<br>'.join(defect['fail_to_pass'])} |"
        )
    return "\n".join(lines) + "\n"


def build_report(results_path: Path, app_root: Path | None = None) -> str:
    manifest = validate_app.load_manifest(app_root or validate_app.MANIFEST)
    if not results_path.exists():
        return render_report([], manifest)
    if results_path.suffix == ".json":
        json_rows = json.loads(results_path.read_text())
        rows = []
        for item in json_rows:
            row = {
                "arm": item.get("arm", ""),
                "trial": str(item.get("trial", "")),
                "status": item.get("status", ""),
                "duration_s": str(item.get("duration_s", "")),
                "conformance_ok": str(bool(item.get("conformance"))).lower(),
                "regressions": str(item.get("regressions", 0)),
            }
            for defect in manifest["defects"]:
                values = item.get("defects", {}).get(defect["id"], {})
                row[f"{defect['id']}_discovered"] = str(bool(values.get("discovered"))).lower()
                row[f"{defect['id']}_fixed"] = str(bool(values.get("fixed"))).lower()
                row[f"{defect['id']}_integrity_ok"] = str(not bool(values.get("integrity_blocked"))).lower()
            rows.append(row)
        return render_report(rows, manifest)
    return render_report(read_rows(results_path), manifest)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    manifest = validate_app.load_manifest()
    rows = read_rows(args.results)
    report = render_report(rows, manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
