#!/usr/bin/env python3
"""Source of truth for writing-hooks tell-detection cases."""
import json
from pathlib import Path


CATEGORIES = {
    "throat-clear": "soft setup that delays the point",
    "business-speak": "lever, unlock, supercharge, move the needle, or leverage",
    "claimed-emotion": "claims surprise or fascination instead of letting the fact carry it",
    "manufactured-drama": "tease dressed as stakes instead of the actual finding",
    "markdown-in-tweets": "markdown emphasis or header syntax in post text",
    "em-dash": "em dash in post text",
    "real-actual": "real or actual used as empty intensifier",
    "manufactured-quotability": "poster-like closer that asserts a vibe",
    "parataxis": "short clauses stacked so rhythm implies an unearned link",
    "not-just-x": "not just X, it is Y fake elevation",
    "filler": "sentence carries no information",
    "abstract-over-number": "vague framing where a concrete number should lead",
}

CASES = []


def dirty(case_id, expect, draft):
    CASES.append({"id": case_id, "kind": "dirty", "expect": expect, "context": "post", "draft": draft.strip()})


def clean(case_id, draft):
    CASES.append({"id": case_id, "kind": "clean", "expect": [], "context": "post", "draft": draft.strip()})


# Opens with setup instead of the finding.
dirty("wh-throat-clear-format", "throat-clear", """
One thing that reliably helps with agent evals: making the output shape boring.

The model either returns the id or it doesn't.
""")

# Uses vague product language where a plain verb would do.
dirty("wh-business-speak-evals", "business-speak", """
The highest-leverage move in skill evals is unlocking deterministic feedback loops.

Once the loop is in place, every prompt change has a receipt.
""")

# Announces surprise instead of showing the fact.
dirty("wh-claimed-emotion-cache", "claimed-emotion", """
What surprised me: the slow part was not generation.

It was reading the artifacts closely enough to know whether the run mattered.
""")

# Creates drama around a mundane implementation detail.
dirty("wh-manufactured-drama-report", "manufactured-drama", """
The report that refused to lie was just a Markdown table.

No dashboards. No judge model. Just fixtures and pass counts.
""")

# Tweet text includes markdown that renders literally.
dirty("wh-markdown-bold", "markdown-in-tweets", """
**Skill evals work when the answer key is boring.**

The hard part is choosing what deserves an answer key.
""")

# Post text uses an em dash.
dirty("wh-em-dash-runner", "em-dash", """
The runner did the useful thing — it failed closed when the scorer could not parse output.

That one behavior saves bad receipts from becoming public numbers.
""")

# Empty intensifier.
dirty("wh-real-bottleneck", "real-actual", """
The real bottleneck is not model quality.

It is whether the task has a checkable output.
""")

# Closer tries to sound quotable instead of adding reasoning.
dirty("wh-quotable-salad", "manufactured-quotability", """
The skill got better when I stopped asking for polish and started asking for evidence.

The receipt was the product all along.
""")

# Two short lines imply a relationship without stating it.
dirty("wh-parataxis-cost", "parataxis", """
The model got cheaper.
The review got stricter.
The work moved faster.
""")

# Fake elevation pattern.
dirty("wh-not-just-planner", "not-just-x", """
It is not just a planner, it is a way to never lose the important work.

The useful part is the handoff rubric.
""")

# Dead sentence can be deleted without loss.
dirty("wh-filler-overview", "filler", """
There are a lot of interesting things happening in agent tooling right now.

The part worth measuring is whether the agent can finish without a human rescuing the run.
""")

# Vague lead hides the number.
dirty("wh-abstract-number", "abstract-over-number", """
The schedule is crowded enough that manual planning breaks down.

551 talks, 30 tracks, and every good session collides with another good session.
""")

# Another business-speak variant from the skill's exact list.
dirty("wh-business-supercharge", "business-speak", """
Structured rubrics supercharge the review process.

They make a model show the defect it found instead of producing a general critique.
""")

# Another claimed-emotion variant.
dirty("wh-claimed-fascinated", "claimed-emotion", """
I was fascinated to find that the clean cases did most of the work.

They caught prompts that learned to flag everything.
""")


clean("wh-clean-number-first", """
551 talks at AI Engineer World's Fair.

A few I am not missing: eval infrastructure, long-running agents, and failure analysis.
""")

clean("wh-clean-plain-finding", """
Specifying the output format helped less than adding clean guard cases.

The guards punished prompts that learned to call every draft broken.
""")

clean("wh-clean-colon-list", """
Three checks caught the regression: case count, byte-identical generation, and public hygiene scan.
""")

clean("wh-clean-engineer-voice", """
The useful eval target was not writing quality.

It was whether the model could name the exact tell without inventing one.
""")


def write_cases(path):
    Path(path).write_text("\n".join(json.dumps(case, sort_keys=True) for case in CASES) + "\n")


if __name__ == "__main__":
    write_cases(Path(__file__).with_name("cases.jsonl"))
