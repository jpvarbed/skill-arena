import json
import re
from dataclasses import dataclass, field
from pathlib import Path


BEGIN = "<!-- arena-publish:begin -->"
END = "<!-- arena-publish:end -->"

PUBLISHERS = [
    {
        "skill": "highsignal",
        "category": "writing",
        "canonical_repo": "https://github.com/jpvarbed/highsignal",
        "sources": {
            "skill_file": "~/dev/highsignal/SKILL.md",
            "results": "~/dev/highsignal/tests/RESULTS.md",
            "cases": "~/dev/highsignal/tests/cases.jsonl",
            "forge": "~/dev/skill-arena/out/forge-results.json",
        },
    }
]


@dataclass(frozen=True, order=True)
class SkillRef:
    category: str
    name: str

    @property
    def rel_dir(self):
        return f"{self.category}/{self.name}"


@dataclass
class PublishSurface:
    skill: SkillRef
    status: str
    headline: str
    evidence_link: str
    perf_text: str
    skill_text: str | None = None
    results_text: str | None = None
    data: dict | None = None
    notes: list[str] = field(default_factory=list)


class PublishError(Exception):
    pass


def run_publish(skills_repo, publishers=None, dry_run=False, stream=None):
    stream = stream or _Stdout()
    skills_repo = Path(skills_repo)
    publishers = publishers or PUBLISHERS
    try:
        readme_path = skills_repo / "README.md"
        readme_text = readme_path.read_text() if readme_path.exists() else "# Skills\n"
        validate_readme_markers(readme_text)
        surfaces = build_surfaces(skills_repo, publishers)
        writes = plan_writes(skills_repo, surfaces, readme_text)
        if dry_run:
            for path in sorted(writes):
                stream.write(f"would write {path}\n")
            return 0
        apply_writes(skills_repo, writes)
        hygiene_hits = scan_hygiene(skills_repo)
        if hygiene_hits:
            for hit in hygiene_hits:
                stream.write(f"hygiene violation: {hit}\n")
            return 1
        return 0
    except PublishError as exc:
        stream.write(f"publish error: {exc}\n")
        return 1


def run_verify(skills_repo, publishers=None, stream=None, report_path=None):
    stream = stream or _Stdout()
    skills_repo = Path(skills_repo)
    try:
        readme_path = skills_repo / "README.md"
        readme_text = readme_path.read_text()
        validate_readme_markers(readme_text)
        surfaces = build_surfaces_from_rendered(skills_repo)
        expected_writes = plan_writes(skills_repo, surfaces, readme_text)
        mismatches = []
        for rel_path, expected in expected_writes.items():
            actual_path = skills_repo / rel_path
            if not actual_path.exists():
                mismatches.append(f"{rel_path}: missing")
                continue
            if actual_path.read_text() != expected:
                mismatches.append(f"{rel_path}: does not match evidence")
        hygiene_hits = scan_hygiene(skills_repo)
        mismatches.extend(f"hygiene: {hit}" for hit in hygiene_hits)
        if mismatches:
            for mismatch in mismatches:
                stream.write(f"verify error: {mismatch}\n")
            return 1
        if report_path:
            _write_verification_report(Path(report_path), skills_repo, surfaces, expected_writes)
        return 0
    except (PublishError, OSError, json.JSONDecodeError) as exc:
        stream.write(f"verify error: {exc}\n")
        return 1


def cli(args):
    if getattr(args, "verify", False):
        return run_verify(args.skills_repo, report_path=getattr(args, "report", None))
    return run_publish(args.skills_repo, dry_run=getattr(args, "dry_run", False))


def discover_skills(skills_repo):
    skills = []
    for category in sorted(path for path in Path(skills_repo).iterdir() if path.is_dir() and not path.name.startswith(".")):
        for skill_dir in sorted(path for path in category.iterdir() if path.is_dir() and not path.name.startswith(".")):
            if (skill_dir / "SKILL.md").exists():
                skills.append(SkillRef(category.name, skill_dir.name))
    return skills


def build_surfaces(skills_repo, publishers):
    discovered = {skill: None for skill in discover_skills(skills_repo)}
    measured = {}
    for entry in publishers:
        surface = build_publisher_surface(entry)
        measured[surface.skill] = surface
        discovered.setdefault(surface.skill, None)

    surfaces = []
    for skill in sorted(discovered):
        surfaces.append(measured.get(skill) or build_unmeasured_surface(skill))
    return surfaces


def build_publisher_surface(entry):
    skill = SkillRef(entry["category"], entry["skill"])
    canonical = entry["canonical_repo"]
    sources = entry.get("sources", {})
    notes = []
    skill_text = read_optional(sources.get("skill_file"))
    if skill_text is None:
        notes.append("skill source missing; SKILL.md copy skipped.")
    else:
        skill_text = f"<!-- canonical: {canonical}; curated copy -->\n" + skill_text

    results_text = read_optional(sources.get("results"))
    cases_count = count_jsonl(sources.get("cases"))
    if cases_count is None:
        notes.append("cases source missing; case count skipped.")

    detection = None
    if results_text is None:
        notes.append("detection results source missing; skipped.")
    else:
        detection_scores = parse_detection_results(results_text)
        if detection_scores:
            detection = {
                "benchmark": "highsignal detect eval",
                "case_count": cases_count,
                "trials": 1,
                "scores": detection_scores,
            }
        else:
            notes.append("detection results unparseable; skipped.")

    forge = None
    forge_text = read_optional(sources.get("forge"))
    if forge_text is None:
        notes.append("forge source missing; skipped.")
    else:
        try:
            forge = parse_forge_results(json.loads(forge_text))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            notes.append("forge results unparseable; skipped.")

    data = {
        "schema_version": 1,
        "skill": skill.name,
        "category": skill.category,
        "canonical_repo": canonical,
        "evidence": ["eval/RESULTS.md", "eval/data.json"],
        "detection": detection,
        "forge": forge,
        "notes": notes,
    }
    measured = bool(detection or forge)
    perf_text = render_measured_perf(skill, data) if measured else render_unmeasured_perf(skill, notes)
    headline = render_headline(data) if measured else "evidence unavailable; see PERF.md"
    return PublishSurface(
        skill=skill,
        status="measured" if measured else "no eval yet",
        headline=headline,
        evidence_link=f"{skill.rel_dir}/PERF.md",
        perf_text=perf_text,
        skill_text=skill_text,
        results_text=results_text,
        data=data if measured else None,
        notes=notes,
    )


def build_surfaces_from_rendered(skills_repo):
    surfaces = []
    for skill in discover_skills(skills_repo):
        data_path = Path(skills_repo) / skill.rel_dir / "eval" / "data.json"
        if data_path.exists():
            data = json.loads(data_path.read_text())
            results_path = Path(skills_repo) / skill.rel_dir / "eval" / "RESULTS.md"
            if results_path.exists():
                reparsed = parse_detection_results(results_path.read_text())
                if data.get("detection") and reparsed != data["detection"].get("scores"):
                    raise PublishError(f"{skill.rel_dir}: detection data does not match eval/RESULTS.md")
            perf_text = render_measured_perf(skill, data)
            surfaces.append(
                PublishSurface(
                    skill=skill,
                    status="measured",
                    headline=render_headline(data),
                    evidence_link=f"{skill.rel_dir}/PERF.md",
                    perf_text=perf_text,
                    data=data,
                )
            )
        else:
            surfaces.append(build_unmeasured_surface(skill))
    return sorted(surfaces, key=lambda surface: surface.skill)


def build_unmeasured_surface(skill, notes=None):
    notes = notes or []
    return PublishSurface(
        skill=skill,
        status="no eval yet",
        headline="Numbers appear here when this skill gets a benchmark.",
        evidence_link=f"{skill.rel_dir}/PERF.md",
        perf_text=render_unmeasured_perf(skill, notes),
        notes=notes,
    )


def plan_writes(skills_repo, surfaces, readme_text):
    writes = {}
    for surface in surfaces:
        writes[f"{surface.skill.rel_dir}/PERF.md"] = surface.perf_text
        if surface.skill_text is not None:
            writes[f"{surface.skill.rel_dir}/SKILL.md"] = surface.skill_text
        if surface.results_text is not None:
            writes[f"{surface.skill.rel_dir}/eval/RESULTS.md"] = surface.results_text
        if surface.data is not None:
            writes[f"{surface.skill.rel_dir}/eval/data.json"] = json.dumps(surface.data, indent=2, sort_keys=True) + "\n"
    writes["README.md"] = render_readme(readme_text, surfaces)
    writes["docs/methodology.md"] = render_methodology()
    return writes


def apply_writes(skills_repo, writes):
    for rel_path in sorted(writes):
        path = Path(skills_repo) / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(writes[rel_path])


def validate_readme_markers(text):
    begin_count = text.count(BEGIN)
    end_count = text.count(END)
    if begin_count == 0 and end_count == 0:
        return
    if begin_count != 1 or end_count != 1:
        raise PublishError("README must contain exactly one arena publish marker pair")
    if text.index(BEGIN) > text.index(END):
        raise PublishError("README arena publish markers are out of order")


def render_readme(readme_text, surfaces):
    block = render_readme_block(surfaces)
    if BEGIN in readme_text or END in readme_text:
        before, rest = readme_text.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        suffix = after.lstrip("\n")
        return before + block + ("\n" + suffix if suffix else "")
    heading = "\n## Skills"
    if heading in readme_text:
        before, after = readme_text.split(heading, 1)
        return before.rstrip() + "\n\n" + block + "\n## Skills" + after
    return readme_text.rstrip() + "\n\n" + block


def render_readme_block(surfaces):
    lines = [
        BEGIN,
        "| Skill | Category | Status | Headline | Evidence |",
        "|---|---|---|---|---|",
    ]
    for surface in sorted(surfaces, key=lambda s: (s.skill.category, s.skill.name)):
        lines.append(
            f"| {surface.skill.name} | {surface.skill.category} | "
            f"{surface.status} | {surface.headline} | [PERF.md]({surface.evidence_link}) |"
        )
    lines.append(END)
    return "\n".join(lines) + "\n"


def render_measured_perf(skill, data):
    detection = data.get("detection")
    forge = data.get("forge")
    lines = [f"# {skill.name} Performance", ""]
    lines.append("## Measured Skills")
    if detection:
        case_count = detection.get("case_count")
        n_text = f"N={case_count}" if case_count is not None else "N unavailable"
        models = ", ".join(score["model"] for score in detection["scores"])
        lines.append(f"- Detection benchmark: {detection['benchmark']} ({n_text}; k=1 single run; models: {models}).")
    if forge:
        models = ", ".join(model["backend"] for model in forge["models"])
        trials = forge.get("trials") or 1
        lines.append(f"- Forge pre/post: original skill vs best generated variant (k={trials}; models: {models}).")
    for note in data.get("notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Numbers", ""])
    if detection:
        lines.extend([
            "### Detection Eval",
            "",
            "| Model | Pass | Rate | False positives |",
            "|---|---:|---:|---:|",
        ])
        for score in detection["scores"]:
            lines.append(f"| {score['model']} | {score['passes']}/{score['total']} | {score['rate']} | {score['false_positives']} |")
        lines.append("")
    if forge:
        lines.extend([
            "### Forge Pre/Post",
            "",
            "| Model | Original | Best variant | Lift |",
            "|---|---:|---:|---:|",
        ])
        for model in forge["models"]:
            original = format_score_cell(model["original_passes"], model["n"], model["original_score"])
            best = f"{model['best_variant']} {format_score_cell(model['best_variant_passes'], model['n'], model['best_variant_score'])}"
            lines.append(f"| {model['backend']} | {original} | {best} | {format_signed_pp(model['lift_pp'])} |")
        lines.append("")
    lines.extend([
        "## Caveats",
        "",
        "- Regressions are shown explicitly; negative lift means the best variant scored below the original.",
        "- Detection scores come from the copied eval result, not from a fresh model run.",
        "- Forge pre/post compares the original skill against the best generated variant per model.",
        "",
        "## Evidence",
        "",
    ])
    if detection:
        lines.append("- [Detection eval](eval/RESULTS.md)")
    if forge:
        lines.append("- [Forge data](eval/data.json)")
    lines.extend([
        "",
        "Generated by arena publish from eval/RESULTS.md, eval/data.json. Do not hand-edit.",
        "",
    ])
    return "\n".join(lines)


def render_unmeasured_perf(skill, notes=None):
    lines = [
        f"# {skill.name} Performance",
        "",
        "No objective eval yet.",
        "",
        "Numbers appear here when this skill gets a benchmark; see the methodology page.",
    ]
    for note in notes or []:
        lines.extend(["", f"- {note}"])
    lines.extend(["", "Generated by arena publish from no objective evidence. Do not hand-edit.", ""])
    return "\n".join(lines)


def render_methodology():
    return """# Skill Performance Methodology

`arena publish` renders public skill-performance surfaces from evidence artifacts produced by
[skill-arena](https://github.com/jpvarbed/skill-arena).

Numbers come from objective evidence files, not hand-entered claims. Deterministic scorers check
gold cases directly when an output can be judged without another model. LLM judges are used only
when the task genuinely needs judgment, and benchmark cases should keep expected outcomes explicit.

Gold cases live with the benchmark. For nondeterministic model behavior, k-trial majority voting is
the preferred shape: run each case multiple times and count the majority verdict, so one flaky call
does not dominate the score.

Forge pre/post results compare the original skill with generated variants on the same cases and
models. Lift is strict: a tie is not an improvement, and negative lift is published as a regression.
The published data keeps the original score, best-variant score, and per-model lift so readers can
see where a variant helped and where it hurt.

Trajectory benchmarks use real issues or realistic task traces when a skill is supposed to improve
multi-step agent work. Those results should link back to the exact evidence snapshot used to render
the public page.
"""


def render_headline(data):
    parts = []
    detection = data.get("detection")
    if detection and detection.get("scores"):
        best = max(detection["scores"], key=lambda score: (score["passes"] / score["total"], score["model"]))
        parts.append(f"detection {best['model']} {best['passes']}/{best['total']}")
    forge = data.get("forge")
    if forge and forge.get("models"):
        ordered = sorted(forge["models"], key=lambda model: (-model["lift_pp"], model["backend"]))
        # honest spread: always show the best AND the worst lift — regressions never drop out
        picks = [ordered[0]] if len(ordered) == 1 else [ordered[0], ordered[-1]]
        lift_text = " / ".join(f"{model['backend']} {format_signed_pp(model['lift_pp'])}" for model in picks)
        parts.append(f"{lift_text} pre->post")
    return "; ".join(parts) if parts else "evidence unavailable; see PERF.md"


def parse_detection_results(text):
    scores = []
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line or "Model" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", cells[1])
        if not match:
            continue
        scores.append(
            {
                "model": cells[0],
                "passes": int(match.group(1)),
                "total": int(match.group(2)),
                "rate": cells[2],
                "false_positives": int(cells[3]),
            }
        )
    return scores


def parse_forge_results(results):
    model_ids = {model["backend"]: model.get("model_id", "") for model in results.get("models", [])}
    cells = results["cells"]
    backends = sorted({cell["backend"] for cell in cells})
    models = []
    for backend in backends:
        original = find_cell(cells, "original", backend)
        variants = [cell for cell in cells if cell["backend"] == backend and cell["contestant"] not in {"baseline", "original"}]
        if not variants:
            continue
        best = sorted(variants, key=lambda cell: (-cell["score"], cell["contestant"]))[0]
        lift_pp = round((best["score"] - original["score"]) * 100, 1)
        models.append(
            {
                "backend": backend,
                "model_id": model_ids.get(backend, original.get("model_id", "")),
                "original_score": original["score"],
                "original_passes": original["passes"],
                "best_variant": best["contestant"],
                "best_variant_score": best["score"],
                "best_variant_passes": best["passes"],
                "n": original["n"],
                "lift_pp": lift_pp,
            }
        )
    return {
        "source_schema_version": results.get("schema_version"),
        "target": results.get("target"),
        "trials": results.get("trials") or 1,
        "models": models,
    }


def find_cell(cells, contestant, backend):
    for cell in cells:
        if cell["contestant"] == contestant and cell["backend"] == backend:
            return cell
    raise ValueError(f"missing {contestant}/{backend}")


def read_optional(path_value):
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.exists():
        return None
    return path.read_text()


def count_jsonl(path_value):
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.exists():
        return None
    count = 0
    with path.open() as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def format_score_cell(passes, total, score):
    return f"{passes}/{total} ({score * 100:.1f}%)"


def format_signed_pp(value):
    return f"{value:+.1f}pp"


def scan_hygiene(root):
    patterns = [
        ("local user path", re.compile(r"/Users/")),
        ("local dev path", re.compile(r"~/dev")),
        ("private notes path", re.compile(r"dev" + r"/notes")),
        # generic public conventions and model names are not tracker tickets
        ("ticket id", re.compile(r"\b(?!(?:ADR|RFC|ISO|UTF|SHA|GPT|GLM|CVE|P[0-9])\b)[A-Z]{2,8}-[0-9]+\b")),
        # only literal credential-length values; env plumbing ("$(...)"), placeholders (<key>, ...)
        # and docs mentioning VAR= are legitimate in a public skills repo
        ("secret assignment", re.compile(r"\b[A-Za-z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN)[A-Za-z0-9_]*\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE)),
        ("key-like token", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b")),
        ("github token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{16,}\b")),
    ]
    hits = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        for label, pattern in patterns:
            match = pattern.search(text)
            if match:
                hits.append(f"{rel}: {label}")
    return hits


def _write_verification_report(report_path, skills_repo, surfaces, expected_writes):
    import hashlib
    import subprocess
    def _git(*args):
        try:
            return subprocess.run(["git", "-C", str(skills_repo), *args], capture_output=True, text=True).stdout.strip()
        except OSError:
            return "unknown"
    lines = [
        "# Publish verification record",
        "",
        "Every rendered file below was re-derived from its evidence sources and matched byte-for-byte.",
        f"Repo state at verification: branch `{_git('branch', '--show-current') or 'unknown'}`, "
        f"commit `{_git('rev-parse', '--short', 'HEAD') or 'unknown'}` (uncommitted changes may follow this record).",
        "",
        "| Rendered file | Matches evidence | sha256 (12) |",
        "|---|---|---|",
    ]
    for rel_path in sorted(expected_writes):
        digest = hashlib.sha256(expected_writes[rel_path].encode()).hexdigest()[:12]
        lines.append(f"| {rel_path} | yes | `{digest}` |")
    lines += ["", "## Evidence sources per measured skill", ""]
    for surface in surfaces:
        if surface.status == "measured":
            ref = surface.skill
            lines.append(f"- **{ref.name}**: evidence committed under `{ref.category}/{ref.name}/eval/` "
                         f"(see the PERF.md generation stamp for exact files).")
    lines += ["", "Hygiene scan: clean (local paths, tracker-id shapes, credential-length literals).",
              "Generated by `arena publish --verify --report`; regenerate rather than hand-edit.", ""]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


class _Stdout:
    def write(self, text):
        print(text, end="")
