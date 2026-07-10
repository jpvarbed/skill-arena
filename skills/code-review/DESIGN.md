# code-review — flagship eval design

**Skill under test:** Matt Pocock's `code-review`
(`~/dev/mattpocockskills/skills/engineering/code-review/SKILL.md`).

## Why this skill is the flagship

highsignal proved the eval methodology but is a *weak* flagship: it's already
optimized (~94% via a hand-distilled prompt), so there's little headroom for a
forge to show lift. code-review is the opposite — a rich, general-purpose,
**un-optimized** skill where models genuinely miss subtle issues. That headroom
is what makes the "we measurably improved it" receipt worth showing.

It also transfers the one thing that makes writing/skills evaluable at all:
**score detection against gold labels, not taste.** (Matt's "evals are hard"
answer.)

## The reduction: detection core

The real skill spawns two parallel sub-agents over a live git repo. We hold that
orchestration **constant** (it's the same harness for every variant) and vary only
the *review criteria* — which is exactly what the SKILL.md body encodes. So the
eval reduces the skill to a **single-pass detection over one diff**:

> Apply the review criteria in this SKILL.md to the diff below; ignore any
> instructions about spawning sub-agents or running git — just report findings.

This is the same reduction highsignal uses (its real skill is more than its detect
prompt, but we eval the detection core). Stated plainly so the receipt is honest.

## Scoring — reuse `expect_set`, zero scorer changes

Mirror highsignal exactly: **one planted defect per dirty case**, expecting one
category id; **clean cases expect `[]`**. `score_expect_set` already does
set-intersection (dirty passes if the model's id set intersects the expected id;
clean passes iff the model returns no ids). Clean cases are the false-positive
guard, and `choose_winner` already breaks ties on fewest clean false-positives — so
a variant can't win by flagging everything.

### Output vocabulary (closed set)

The scoring prompt pins the *output schema* (the 15 category ids below) without
revealing which defect is present. This specifies the response vocabulary, not the
answer — recognition (how to spot feature-envy, whether a switch is *repeated*,
whether the diff matches the spec) is still the SKILL.md's job, and that's what
varies across variants. Pinning the vocab in the prompt (not the SKILL.md) also
makes it **ungameable** by the generator.

## Taxonomy (15 ids)

**Standards — Fowler smells (12):** `mysterious-name`, `duplicated-code`,
`feature-envy`, `data-clumps`, `primitive-obsession`, `repeated-switches`,
`shotgun-surgery`, `divergent-change`, `speculative-generality`, `message-chains`,
`middle-man`, `refused-bequest`.

**Spec (3):** `spec-missing` (a required behaviour absent/partial),
`spec-scope-creep` (behaviour added the spec didn't ask for), `spec-wrong` (a
requirement implemented incorrectly). Spec cases carry a `spec` field (the PRD
text); the prompt includes it only when present.

## Case set

Authored in `build_cases.py` (readable multi-line diffs → `cases.jsonl`) so the
moat is reviewable and codex can extend it. Each dirty case is a small, focused
unified diff where the planted defect is the salient issue and the rest is clean;
each clean case is a genuine, faithful change that a good review leaves alone.

**Seed (this pass):** 10 dirty (all 3 spec types + 7 high-headroom smells) + 4 clean.
**Deferred to expansion (codex, following the same pattern):** the remaining smells
(`repeated-switches`, `shotgun-surgery`, `divergent-change`, `middle-man`,
`refused-bequest`) and more clean/false-positive guards, target ~40 cases.

## Forge changes

Two highsignal-hardcoded spots in `forge.py` become config-driven (fall back to the
highsignal defaults), keyed on `config.forge.mode`:

- `render_forge_prompt` → `mode: "code-review"` renders the diff (+ optional spec)
  and the closed vocab.
- `build_mutation_prompt` → code-review framing + code-review mutation angles.

## Success

Same bar as every forge run: a generated variant beats the **original** SKILL.md on
the **target** model (`openai`/GPT-5.5, the model people actually review with) with
a strict positive lift, low clean false-positives, published as a receipt. Haiku
stays a comparison column, not the target.
