#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path

try:
    from .common import ROOT, repo_tree_hash, task_dirs
except ImportError:
    from common import ROOT, repo_tree_hash, task_dirs


def load_results(path):
    path = Path(path)
    if not path.exists() or not path.read_text().strip():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("results.json must contain a JSON array")
    return data


def write_receipt(results_path=ROOT / "out" / "results.json", out_path=ROOT / "out" / "receipt.md", tasks_dir=ROOT / "tasks"):
    rows = load_results(results_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_receipt(rows, tasks_dir))
    return out_path


def render_receipt(rows, tasks_dir):
    lines = ["# Trajectory Benchmark Receipt", ""]
    lines.extend(render_fix_rates(rows))
    lines.extend(render_task_table(rows))
    lines.extend(render_incident_log(rows))
    lines.extend(render_manifest(rows, tasks_dir))
    lines.extend([
        "## Caveats",
        "",
        "- This is a small benchmark; task-level majority rates should be treated as directional.",
        "- Results cover one agent command and model setting unless the runner is configured otherwise.",
        "- The skill arm injects prompt text with `--append-system-prompt`; it is not a native skill activation path.",
        "- Trajectory metrics are extracted from stream-json transcripts and may miss tool calls emitted in unexpected shapes.",
        "",
    ])
    return "\n".join(lines)


def render_fix_rates(rows):
    by_arm = defaultdict(list)
    by_task_arm = defaultdict(list)
    for row in rows:
        by_arm[row["arm"]].append(bool(row["tests_pass"]))
        by_task_arm[(row["task"], row["arm"])].append(bool(row["tests_pass"]))

    lines = ["## Fix Rates", ""]
    lines.append("| arm | raw trials | raw pass rate | majority tasks |")
    lines.append("| --- | ---: | ---: | ---: |")
    for arm in sorted(by_arm):
        values = by_arm[arm]
        raw = sum(values)
        task_majorities = [
            sum(values) > (len(values) / 2)
            for (task, task_arm), values in by_task_arm.items()
            if task_arm == arm
        ]
        majority = sum(task_majorities)
        lines.append(f"| {arm} | {raw}/{len(values)} | {_pct(raw, len(values))} | {majority}/{len(task_majorities)} |")
    lines.append("")
    return lines


def render_task_table(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["arm"])].append(row)
    lines = ["## Per-Task Results", ""]
    lines.append("| task | arm | trials | pass | avg tests | avg files | avg flail | hypothesis |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for (task, arm), items in sorted(grouped.items()):
        trial_marks = "".join("P" if item["tests_pass"] else "F" for item in sorted(items, key=lambda r: r["trial"]))
        metrics = [item.get("metrics", {}) for item in items]
        lines.append(
            f"| {task} | {arm} | {trial_marks} | {sum(item['tests_pass'] for item in items)}/{len(items)} | "
            f"{_avg(metrics, 'test_runs'):.1f} | {_avg(metrics, 'files_edited'):.1f} | "
            f"{_avg(metrics, 'flail_index'):.1f} | {sum(bool(m.get('stated_hypothesis')) for m in metrics)}/{len(metrics)} |"
        )
    lines.append("")
    return lines


def render_incident_log(rows):
    incidents = [row for row in rows if row.get("timeout") or row.get("reason") == "test-tamper"]
    lines = ["## Timeout And Tamper Log", ""]
    if not incidents:
        lines.extend(["No timeouts or test tampering detected.", ""])
        return lines
    lines.append("| task | arm | trial | reason | temp path |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for row in incidents:
        lines.append(f"| {row['task']} | {row['arm']} | {row['trial']} | {row['reason']} | `{row.get('temp_path', '')}` |")
    lines.append("")
    return lines


def render_manifest(rows, tasks_dir):
    outcomes = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for row in rows:
        cell = outcomes[row["task"]][row["arm"]]
        cell[0] += 1 if row["tests_pass"] else 0
        cell[1] += 1
    lines = ["## Frozen Task Manifest", ""]
    lines.append("| task | repo sha256 | pilot outcomes |")
    lines.append("| --- | --- | --- |")
    for task_dir in task_dirs(tasks_dir):
        task_outcomes = outcomes.get(task_dir.name, {})
        pilot = ", ".join(f"{arm} {passes}/{total}" for arm, (passes, total) in sorted(task_outcomes.items())) or "not run"
        lines.append(f"| {task_dir.name} | `{repo_tree_hash(task_dir / 'repo')}` | {pilot} |")
    lines.append("")
    return lines


def _pct(numerator, denominator):
    if not denominator:
        return "n/a"
    return f"{(100 * numerator / denominator):.1f}%"


def _avg(metrics, key):
    if not metrics:
        return 0.0
    return sum(float(item.get(key, 0)) for item in metrics) / len(metrics)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(ROOT / "out" / "results.json"))
    parser.add_argument("--out", default=str(ROOT / "out" / "receipt.md"))
    args = parser.parse_args(argv)
    path = write_receipt(args.results, args.out)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
