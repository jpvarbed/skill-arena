#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_json(path, default):
    path = Path(path)
    if not path.exists() or not path.read_text().strip():
        return default
    return json.loads(path.read_text())


def write_receipt(results_path=None, manifest_path=None, out_path=None):
    results_path = Path(results_path or ROOT.parent / "out" / "tier2" / "results.json")
    manifest_path = Path(manifest_path or ROOT / "manifest.json")
    out_path = Path(out_path or ROOT.parent / "out" / "tier2" / "receipt.md")
    rows = load_json(results_path, [])
    manifest = load_json(manifest_path, {"instances": [], "skipped": []})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_receipt(rows, manifest))
    return out_path


def render_receipt(rows, manifest):
    lines = ["# Tier 2 Trajectory Benchmark Receipt", ""]
    lines.extend(render_conclusion(rows))
    lines.extend(render_arm_summary(rows))
    lines.extend(render_instance_table(rows))
    lines.extend(render_manifest_echo(manifest))
    lines.extend(render_caveats())
    lines.extend(render_metrics_definitions())
    return "\n".join(lines)


def render_conclusion(rows):
    rate = _overall_resolved_rate(rows)
    verdict = _difficulty_verdict(rate)
    return [
        "## Conclusion",
        "",
        f"Resolved rate: {_pct(sum(bool(row.get('resolved')) for row in rows), len(rows))}. {verdict}",
        "",
    ]


def render_arm_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["arm"]].append(row)
    lines = ["## Per-Arm Summary", ""]
    lines.append("| arm | resolved | resolved rate | regressions |")
    lines.append("| --- | ---: | ---: | ---: |")
    for arm in sorted(grouped):
        items = grouped[arm]
        resolved = sum(bool(row.get("resolved")) for row in items)
        regressions = sum(int(row.get("pass_to_pass_regressions", 0)) for row in items)
        lines.append(f"| {arm} | {resolved}/{len(items)} | {_pct(resolved, len(items))} | {regressions} |")
    if not grouped:
        lines.append("| n/a | 0/0 | n/a | 0 |")
    lines.append("")
    return lines


def render_instance_table(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["instance_id"], row["arm"])].append(row)
    lines = ["## Per-Instance Results", ""]
    lines.append("| instance | arm | trials | fail-to-pass passed | regressions | avg duration |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for (instance_id, arm), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda row: row["trial"])
        marks = "".join("R" if row.get("resolved") else "F" for row in ordered)
        f2p = sum(int(row.get("fail_to_pass_passed", 0)) for row in ordered)
        regressions = sum(int(row.get("pass_to_pass_regressions", 0)) for row in ordered)
        duration = sum(float(row.get("duration_s", 0)) for row in ordered) / len(ordered)
        lines.append(f"| {instance_id} | {arm} | {marks} | {f2p} | {regressions} | {duration:.1f}s |")
    if not grouped:
        lines.append("| n/a | n/a | n/a | 0 | 0 | 0.0s |")
    lines.append("")
    return lines


def render_manifest_echo(manifest):
    lines = ["## Frozen Manifest", ""]
    lines.append("| instance | repo | base commit | image digest |")
    lines.append("| --- | --- | --- | --- |")
    for item in manifest.get("instances", []):
        lines.append(
            f"| {item['instance_id']} | {item.get('repo', '')} | `{item.get('base_commit', '')[:12]}` | `{item.get('image_digest', '')}` |"
        )
    if not manifest.get("instances"):
        lines.append("| n/a | n/a | n/a | n/a |")
    lines.append("")
    lines.append(f"Skipped candidates recorded during validation: {len(manifest.get('skipped', []))}.")
    lines.append("")
    return lines


def render_caveats():
    return [
        "## Caveats",
        "",
        "- k is small by design: the frozen tier-2 manifest targets 12 instances plus overflow validation records.",
        "- Cost tier is materially higher than tier 1 because each instance uses a disposable exe.dev box and Docker image pulls.",
        "- The skill arm uses `--append-system-prompt`; that is a prompt-injection knob, not native skill activation.",
        "- Trajectory metrics reuse `traj/scorers.py` and inherit the same stream-json parser limits.",
        "",
    ]


def render_metrics_definitions():
    return [
        "## Metrics Definitions",
        "",
        "- resolved: all FAIL_TO_PASS tests passed under the SWE-bench grading report.",
        "- fail_to_pass_passed: count of FAIL_TO_PASS tests reported successful.",
        "- pass_to_pass_regressions: count of PASS_TO_PASS tests reported failing after the patch.",
        "- trajectory metrics: transcript-derived behavior metrics from `traj/scorers.py`.",
        "",
    ]


def _graded(rows):
    return [row for row in rows if row.get("status", "resolved" if row.get("resolved") else "unresolved") in ("resolved", "unresolved")]


def _overall_resolved_rate(rows):
    if not rows:
        return None
    graded = _graded(rows)
    if not graded:
        return 0.0
    return sum(bool(row.get("resolved")) for row in graded) / len(graded)


def _difficulty_verdict(rate):
    if rate is None:
        return "No runs were present, so the baseline difficulty band cannot be judged."
    if 0.2 <= rate <= 0.8:
        return "This is inside the target difficulty band [20%, 80%]."
    return "This is outside the target difficulty band [20%, 80%]; treat comparisons as less diagnostic."


def _pct(numerator, denominator):
    if not denominator:
        return "n/a"
    return f"{100 * numerator / denominator:.1f}%"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(ROOT.parent / "out" / "tier2" / "results.json"))
    parser.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    parser.add_argument("--out", default=str(ROOT.parent / "out" / "tier2" / "receipt.md"))
    args = parser.parse_args(argv)
    path = write_receipt(args.results, args.manifest, args.out)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
