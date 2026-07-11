import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from arena import load_cases, render_prompt, run_loaded_skills


def suite_fingerprint(skill, cases):
    ids = [case.get("id") for case in cases]
    if any(not case_id for case_id in ids):
        raise ValueError("canary cases require a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("canary case ids must be unique")
    variants = sorted(skill.config.get("prompt_variants", []), key=lambda item: item.get("name", "default"))
    payload = {
        "name": skill.name,
        "config": {
            key: value for key, value in skill.config.items()
            if key not in {"models", "cases_path"}
        },
        "cases": sorted(cases, key=lambda item: item["id"]),
        "rendered_prompts": [
            {
                "case_id": case["id"],
                "variant": variant.get("name", "default"),
                "prompt": render_prompt(skill, case, variant),
            }
            for case in sorted(cases, key=lambda item: item["id"])
            for variant in variants
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def lane_key(skill_name, cell):
    return (
        skill_name,
        cell["backend"],
        cell.get("model"),
        cell["prompt_variant"],
    )


def result_lanes(results):
    lanes = {}
    for skill_name, skill_result in results["skills"].items():
        for cell in skill_result["cells"]:
            lanes[lane_key(skill_name, cell)] = (skill_name, cell)
    return lanes


def case_state(case):
    if case.get("error"):
        return "error"
    return "pass" if case.get("pass") else "fail"


def lane_safe(cell):
    return bool(cell["cases"]) and all(case_state(case) == "pass" for case in cell["cases"])


def current_failures(cell):
    failures = []
    for case in cell["cases"]:
        if case_state(case) == "error":
            failures.append(f"{case['id']}: error")
            continue
        failed_checks = [check["id"] for check in case.get("checks", []) if not check.get("pass")]
        if failed_checks:
            failures.extend(f"{case['id']}/{check_id}: fail" for check_id in failed_checks)
        elif case_state(case) == "fail":
            failures.append(f"{case['id']}: fail")
    return failures


def compare_results(current, baseline=None):
    if baseline and baseline.get("suite_fingerprint") != current.get("suite_fingerprint"):
        raise ValueError("baseline suite fingerprint does not match current suite")
    previous = result_lanes(baseline) if baseline else {}
    compared = []
    for key, (skill_name, cell) in sorted(result_lanes(current).items()):
        prior = previous.get(key)
        current_safe = lane_safe(cell)
        if not baseline:
            status = "baseline"
        elif not prior:
            status = "new"
        else:
            previous_safe = lane_safe(prior[1])
            if previous_safe and current_safe:
                status = "still safe"
            elif previous_safe and not current_safe:
                status = "drifted"
            elif not previous_safe and current_safe:
                status = "recovered"
            else:
                status = "still failing"

        changes = []
        if prior:
            previous_cases = {case["id"]: case for case in prior[1]["cases"]}
            for case in cell["cases"]:
                previous_case = previous_cases.get(case["id"])
                if not previous_case:
                    continue
                check_changes = []
                previous_checks = {check["id"]: check for check in previous_case.get("checks", [])}
                for check in case.get("checks", []):
                    previous_check = previous_checks.get(check["id"])
                    if previous_check and previous_check.get("pass") != check.get("pass"):
                        before = "pass" if previous_check.get("pass") else "fail"
                        after = "pass" if check.get("pass") else "fail"
                        check_changes.append(f"{case['id']}/{check['id']}: {before} -> {after}")
                if check_changes:
                    changes.extend(check_changes)
                elif case_state(previous_case) != case_state(case):
                    changes.append(f"{case['id']}: {case_state(previous_case)} -> {case_state(case)}")
        if not changes and not current_safe and status in {"baseline", "new", "still failing"}:
            changes = current_failures(cell)
        compared.append({
            "skill": skill_name,
            "backend": cell["backend"],
            "model": cell.get("model"),
            "prompt_variant": cell["prompt_variant"],
            "status": status,
            "passed": sum(1 for case in cell["cases"] if case_state(case) == "pass"),
            "failed": sum(1 for case in cell["cases"] if case_state(case) != "pass"),
            "changes": changes,
        })
    return compared


def markdown_cell(value):
    return (
        " ".join(str(value).split())
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
    )


def write_summary(run_dir, results, baseline_results=None, baseline_label=None):
    lines = [
        "# Inference canary run",
        "",
        f"- run: `{run_dir.name}`",
        f"- baseline: `{baseline_label}`" if baseline_label else "- baseline: none",
        f"- suite: `{results['suite_fingerprint']}`",
        "",
        "| Skill | Backend | Model | Variant | Status | Passed | Failed/Error | Changed cases |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for lane in compare_results(results, baseline_results):
        lines.append(
            f"| {markdown_cell(lane['skill'])} | {markdown_cell(lane['backend'])} | "
            f"{markdown_cell(lane['model'] or 'default')} | {markdown_cell(lane['prompt_variant'])} | "
            f"{markdown_cell(lane['status'])} | {lane['passed']} | {lane['failed']} | "
            f"{markdown_cell('; '.join(lane['changes']) or '-')} |"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")


def normalize_results_path(path):
    path = Path(path)
    return path / "results.json" if path.is_dir() else path


def load_compatible_baseline(path, fingerprint):
    results_path = normalize_results_path(path)
    results = json.loads(results_path.read_text())
    if results.get("suite_fingerprint") != fingerprint:
        raise ValueError("baseline suite fingerprint does not match current suite")
    return results_path, results


def latest_compatible_baseline(runs_dir, fingerprint):
    candidates = []
    if Path(runs_dir).exists():
        for results_path in Path(runs_dir).glob("*/results.json"):
            try:
                results = json.loads(results_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if results.get("suite_fingerprint") == fingerprint:
                candidates.append((results.get("generated_at", ""), results_path, results))
    if not candidates:
        return None, None
    _, results_path, results = max(candidates, key=lambda item: (item[0], str(item[1])))
    return results_path, results


def run_canary(skill, backends, runs_dir, run_id="", baseline=None, dry_run=False):
    cases = load_cases(skill)
    fingerprint = suite_fingerprint(skill, cases)
    missing_models = [backend for backend in backends if not skill.config.get("models", {}).get(backend)]
    if missing_models:
        raise ValueError(f"canary requires an explicit model for: {', '.join(missing_models)}")
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"canary run already exists: {run_dir}")
    if baseline:
        baseline_path, baseline_results = load_compatible_baseline(baseline, fingerprint)
    else:
        baseline_path, baseline_results = latest_compatible_baseline(runs_dir, fingerprint)
    run_dir.mkdir(parents=True, exist_ok=False)
    results = run_loaded_skills(
        [skill],
        backends,
        out_dir=run_dir,
        dry_run=dry_run,
        metadata={"suite_fingerprint": fingerprint},
        include_outputs=True,
    )
    write_summary(
        run_dir,
        results,
        baseline_results=baseline_results,
        baseline_label=baseline_path.parent.name if baseline_path else None,
    )
    print(f"wrote {run_dir / 'summary.md'}")
    return results
