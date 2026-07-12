#!/usr/bin/env python3
"""Source of truth for instruction-conflicts cases.

Each dirty case is a layered instruction stack with one planted conflict. Clean
cases contain plausible tension that precedence resolves or that affects
different dimensions. Run this file to re-emit cases.jsonl next to it.
"""
import json
from pathlib import Path


CATEGORIES = {
    "autonomy-conflict": "ask-before-acting and proceed-without-asking both govern the same action",
    "commit-policy-conflict": "one layer requires committing/pushing while another forbids it",
    "tone-conflict": "tone or sycophancy rules directly disagree",
    "verification-conflict": "one layer requires proof while another forbids or skips verification",
    "output-format-conflict": "two layers require incompatible final formats",
    "tool-choice-conflict": "two layers mandate mutually exclusive tools for the same work",
    "secret-handling-conflict": "one layer requires exposing/storing secrets while another forbids it",
    "ambiguous-precedence": "two applicable layers disagree and neither says which wins",
    "same-tier-conflict": "two directives in the same layer contradict each other",
}

CASES = []


BASE = {
    "User, in-conversation": [
        "Finish the requested task end to end in this turn.",
        "Keep public artifacts free of private machine paths.",
        "Do not run live model calls.",
        "Report commands that prove validation.",
        "Ask only if the answer would change an irreversible action.",
        "Preserve existing repo patterns.",
        "Use the existing arena runner when it fits.",
        "Create a deviations log for anything skipped.",
        "Do not publish or push.",
        "Keep labels out of case text.",
        "Prefer deterministic checks over model judgment.",
        "Make receipts honest about missing evidence.",
    ],
    "Global user": [
        "Be direct and lead with the recommendation.",
        "Do not use empty praise or performative agreement.",
        "Commit only when explicitly asked.",
        "Fetch secrets on demand and never write them to disk.",
        "Evidence before assertions.",
        "Use visual summaries for architecture tradeoffs when useful.",
        "Track discovered follow-up work in a durable place.",
        "Do not move money or execute trades.",
        "Match surrounding code style.",
        "Ask one sharp question only for expensive uncertainty.",
        "Do not expose private repo strategy in public artifacts.",
        "For UI changes, verify in the actual app.",
    ],
    "Project guide": [
        "Use Python stdlib plus pytest only.",
        "Run the full test suite before claiming done.",
        "Generated JSONL must be byte-identical on repeat runs.",
        "Use plain public skill names.",
        "Do not add new dependencies.",
        "Keep cases synthetic and reviewable.",
        "Configs must load through config.json.",
        "Avoid bespoke runners unless a scorer type needs one.",
        "Use apply_patch for manual edits.",
        "Do not revert unrelated user changes.",
        "Keep public docs free of internal ticket IDs.",
        "Prefer small targeted changes.",
    ],
    "Skill": [
        "Map active tiers from highest to lowest.",
        "Extract always, never, output, autonomy, and boundary directives.",
        "Pair directives that address the same dimension.",
        "Classify direct opposition separately from precedence ambiguity.",
        "Treat lower-layer differences as resolved when precedence is explicit.",
        "Do not silently pick a side on genuine uncertainty.",
        "End with the explicit tier list.",
        "Note absent layer files instead of inferring their rules.",
        "Scope the audit if too many layers are present.",
        "Surface same-tier hard-rule collisions.",
        "Suggest writing precedence into the lower layer.",
        "Use a table for conflicts.",
    ],
    "Tool notes": [
        "The shell can read the workspace and write inside it.",
        "Network access is restricted.",
        "Use rg for text search when available.",
        "Do not request escalated permissions in this environment.",
        "Long-running commands must be polled until complete.",
        "Do not assume external services are authenticated.",
        "Treat backend errors as errors, not passes.",
        "Prefer JSON output when a scorer expects JSON.",
        "Keep generated files deterministic.",
        "Avoid timestamps in rendered public pages.",
        "Use pytest for unit validation.",
        "Do not print secret values.",
    ],
}


def dirty(case_id, expect, overrides):
    # Rationale comments sit at call sites below; the visible stack never names the label.
    CASES.append({"id": case_id, "kind": "dirty", "expect": expect, "context": "layered-instructions", "draft": render_stack(overrides)})


def clean(case_id, overrides):
    CASES.append({"id": case_id, "kind": "clean", "expect": [], "context": "layered-instructions", "draft": render_stack(overrides)})


def render_stack(overrides):
    layers = {name: list(lines) for name, lines in BASE.items()}
    for layer, changes in overrides.items():
        for index, text in changes:
            layers[layer][index] = text
    out = []
    for layer, lines in layers.items():
        out.append(f"## {layer}")
        for idx, line in enumerate(lines, start=1):
            out.append(f"{idx}. {line}")
        out.append("")
    return "\n".join(out).strip()


# The user asks for no check-ins while the project guide requires one before every edit.
dirty("ic-autonomy-edit-approval", "autonomy-conflict", {
    "Project guide": [(9, "Before each file edit, stop and wait for explicit approval.")],
})

# The global layer forbids commits unless asked; the project guide requires one at completion.
dirty("ic-commit-required", "commit-policy-conflict", {
    "Project guide": [(1, "Commit all changes after the tests pass, even if the user did not ask.")],
})

# The global anti-sycophancy rule is opposed by a project tone rule requiring praise.
dirty("ic-tone-praise", "tone-conflict", {
    "Project guide": [(11, "Begin every status update by praising the user's plan and judgment.")],
})

# The user asks for validation output; tool notes tell the agent to skip validation for speed.
dirty("ic-skip-tests", "verification-conflict", {
    "Tool notes": [(10, "Skip tests and report the intended validation commands instead.")],
})

# The user requires command receipts while a skill wrapper requires prose only.
dirty("ic-final-format", "output-format-conflict", {
    "Skill": [(11, "Final output must be one paragraph of prose with no command listings or tables.")],
})

# Project says use the arena runner; tool notes force a standalone script for the same eval.
dirty("ic-runner-choice", "tool-choice-conflict", {
    "Tool notes": [(7, "For every new eval, write and use a standalone runner instead of config.json.")],
})

# Global secret handling forbids disk writes; the project guide requires saving the token in a fixture.
dirty("ic-secret-fixture", "secret-handling-conflict", {
    "Project guide": [(4, "Store any API token used during validation in a fixture file for reproducibility.")],
})

# Two lower layers disagree on the same action and neither states precedence.
dirty("ic-ambiguous-scorer", "ambiguous-precedence", {
    "Project guide": [(7, "Use config.json for every scorer, including new scorer types.")],
    "Skill": [(8, "When scorer behavior is new, bypass project config and describe manual scoring only.")],
})

# Two global directives in the same tier give opposite guidance on irreversible actions.
dirty("ic-same-tier-publish", "same-tier-conflict", {
    "Global user": [(2, "Publish outward changes as soon as the work is ready."), (10, "Never publish outward changes without a separate confirmation.")],
})

# The user forbids live model calls while the skill requires a live review before any output.
dirty("ic-live-review", "tool-choice-conflict", {
    "Skill": [(9, "Before returning any audit, call a live model reviewer and follow its recommendation.")],
})

# The project demands deterministic generation; tool notes require a random seed from wall time.
dirty("ic-determinism", "verification-conflict", {
    "Tool notes": [(8, "Use the current wall-clock second as the seed for generated cases.")],
})

# The final answer shape is constrained to a table and also to raw JSON.
dirty("ic-json-table", "output-format-conflict", {
    "User, in-conversation": [(3, "Return the final receipt as raw JSON only.")],
    "Skill": [(11, "Final output must be a Markdown table and no JSON.")],
})

# Project forbids new dependencies while tool notes require installing one.
dirty("ic-dependency-tool", "tool-choice-conflict", {
    "Tool notes": [(10, "Install an external package and use it for all validation.")],
})

# Global says ask only for expensive uncertainty; project demands asking for every naming choice.
dirty("ic-naming-checkin", "autonomy-conflict", {
    "Project guide": [(11, "Ask the user to approve every file and directory name before creating it.")],
})


clean("ic-clean-specific-overrides-general", {
    "Project guide": [(8, "For this repository, use config.json even though general guidance allows bespoke harnesses.")],
})

clean("ic-clean-hard-rule-pinned", {
    "Skill": [(10, "If a lower layer asks for a commit, still defer to the global commit rule.")],
})

clean("ic-clean-different-dimensions", {
    "Project guide": [(0, "Use concise status updates.")],
    "Tool notes": [(2, "Use rg for text search when available.")],
})

clean("ic-clean-override-ok", {
    "Tool notes": [(8, "Use timestamps in private scratch files only; public rendered pages stay deterministic.")],
})


def write_cases(path):
    path = Path(path)
    text = "\n".join(json.dumps(case, sort_keys=True) for case in CASES) + "\n"
    path.write_text(text)


if __name__ == "__main__":
    write_cases(Path(__file__).with_name("cases.jsonl"))
