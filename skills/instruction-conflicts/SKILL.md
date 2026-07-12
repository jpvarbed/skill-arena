---
name: instruction-conflicts
description: Audit the layered instruction stack (in-conversation user → soul.md/global → project guide → skill → tool/system) for conflicting or ambiguous directives, and surface which layer should win. Use when the user says "check for instruction conflicts", "do my layers contradict", "audit soul.md vs project/skill", "why is the agent ignoring X", or before relying on a deep skill stack. NOT for scoring one skill's quality (use linting-and-scoring) or auditing whether a skill obeys itself (use the adherence audit). Built from ManyIH (arXiv:2604.09443) via apply-paper.
---

# instruction-conflicts — audit the instruction hierarchy

LLM agents resolve conflicting instructions from many sources poorly: with assumed (not explicit)
precedence, frontier models drop to ~40% accuracy once tiers exceed a handful (ManyIH,
arXiv:2604.09443). The fix is to make the tiers **explicit** and remove genuine contradictions.
This audit does both: map the active layers, find conflicts, and state who wins.

## Step 1 — Map the active tiers (highest precedence first)
Enumerate what's actually in force for this context. Default precedence:
1. **User, in-conversation** — explicit current instructions (highest).
2. **Global user** — `soul.md` / `~/.claude/CLAUDE.md`.
3. **Project** — repo `CLAUDE.md` / `AGENTS.md` / `.cursorrules`.
4. **Skill** — the active `SKILL.md`(s).
5. **Tool / harness / system** — plugin hooks, system prompt defaults (lowest).

List each layer present + its source file. Note: more-specific *may* override more-general for
scoped concerns, but **global hard rules** (security, money/secrets boundaries, "commit only when
asked") are not overridable by a lower tier — call those out as pinned.

## Step 2 — Extract directives
From each layer pull the imperatives: "always/never", "do NOT", output/format contracts, autonomy
rules (when to ask vs act), tone rules, commit/secret/boundary rules. Tag each with its layer.

## Step 3 — Find conflicts
Pair directives that address the **same dimension** and disagree. Classify:
- **CONTRADICTION** — directly opposed (layer A says do X, layer B says never X).
- **AMBIGUOUS-PRECEDENCE** — both could apply and the wording doesn't say which wins.
- **OVERRIDE-OK** — they differ but precedence cleanly resolves it (lower yields to higher); no action.
Common dimensions to check: autonomy (ask vs proceed), commit/push policy, tone/sycophancy,
verification strictness, output format, tool choice, secret handling.

## Step 4 — Output
A table: `| Dimension | Layer A (directive) | Layer B (directive) | Type | Resolution / fix |`.
- For CONTRADICTION/AMBIGUOUS: the fix is to **make precedence explicit** in the lower layer
  ("defer to soul.md on tone") or reconcile the wording. Don't silently pick a side on a genuine
  contradiction — surface it for the user.
- End with the **explicit tier list** (Step 1) so the resolved precedence is written down, not assumed.

## Errors

| Issue | Fix |
|---|---|
| A layer file isn't readable / not found | Skip it, note it as "layer absent" — don't infer its rules. |
| Two global hard rules conflict (e.g. two soul.md lines) | Flag as a soul.md self-conflict for the user to resolve; precedence can't break a same-tier tie. |
| Conflict is real and precedence is genuinely unclear | Do NOT auto-resolve — present both directives + ask the user which wins, then suggest writing it into the lower layer. |
| Too many layers to audit fully | Scope to the dimensions that matter for the current task; say what you skipped (no silent truncation). |
