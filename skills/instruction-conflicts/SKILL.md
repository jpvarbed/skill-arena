---
name: instruction-conflicts
description: Audit the layered instruction stack (in-conversation user → soul.md/global → project guide → skill → tool/system) for conflicting or ambiguous directives, and surface which layer should win. Use when the user says "check for instruction conflicts", "do my layers contradict", "audit soul.md vs project/skill", "why is the agent ignoring X", or before relying on a deep skill stack. NOT for scoring one skill's quality (use linting-and-scoring) or auditing whether a skill obeys itself (use the adherence audit). Built from ManyIH (arXiv:2604.09443) via apply-paper.
---

# Instruction-conflict audit

Map the active layers, compare directives that govern the same decision, and make precedence explicit. Report genuine conflicts without inflating harmless differences into contradictions.

## 1. Map active tiers

Enumerate only the layers actually in force, highest precedence first:

1. **User, in conversation** — explicit current instructions.
2. **Global user** — global preference or policy files.
3. **Project** — repository guidance.
4. **Skill** — active skill instructions.
5. **Tool / harness / system** — tool defaults, hooks, or harness behavior.

For each tier, record its source. If a source is unavailable, mark the layer absent; do not infer its directives.

More-specific instructions may override more-general ones within their scope. Treat explicitly pinned hard rules—such as security, money, secrets, or commit boundaries—as non-overridable by lower tiers.

## 2. Extract directives

Collect actionable imperatives from each layer:

- Always, never, must, and do-not rules
- Output and formatting contracts
- Ask-versus-act autonomy rules
- Verification requirements
- Commit, push, publishing, and secret-handling boundaries
- Tone and interaction rules
- Required or prohibited tools

Record each directive with its tier, source, scope, conditions, and strength.

## 3. Compare directives

Compare two directives only when they govern the same dimension, scope, condition, and decision point. Different scopes, compatible requirements, or sequential actions are not conflicts.

Classify each relevant pair:

### CONTRADICTION

Both directives apply simultaneously and require mutually exclusive behavior.

- **Example:** Project says “always commit completed changes”; global says “never commit unless asked.”
- **Near-miss:** Project says “commit when the user requests delivery”; global says “commit only when asked.” These agree.

### AMBIGUOUS-PRECEDENCE

Both directives plausibly apply and differ, but their scope, strength, or override relationship does not establish which governs.

- **Example:** One active skill requires JSON-only output; another active skill requires a Markdown table, with no rule for combining or prioritizing them.
- **Near-miss:** The user requests JSON-only output while a skill defaults to Markdown. The higher-tier, task-specific instruction resolves the difference.

### OVERRIDE-OK

The directives differ, but the stated tier order, scope, or explicit exception cleanly determines which one applies.

- **Example:** A skill says “ask before editing by default”; the current user explicitly says “edit the file now.” The user instruction wins for this task.
- **Near-miss:** A project guide says “push after every change” while a pinned global rule says “never push without confirmation.” This is a contradiction to fix, not a harmless override.

Do not report stylistic variation, added strictness, or compatible sequencing as conflict unless compliance with one directive prevents compliance with the other.

## 4. Resolve or surface

For each finding:

- **CONTRADICTION:** Identify the governing tier if precedence is explicit, but still surface the contradictory wording and recommend reconciling the lower layer.
- **AMBIGUOUS-PRECEDENCE:** Do not guess. Present both directives, ask which should govern, and recommend encoding that decision in the appropriate layer.
- **OVERRIDE-OK:** State the winning directive briefly. No corrective action is required.

If two directives conflict within the same tier, precedence cannot resolve the tie; flag a self-conflict for the user.

Prefer fixes that make scope or precedence explicit, such as: “Defer to global policy for commit behavior” or “This format applies unless the current user specifies another.”

## 5. Output

Use this table:

| Dimension | Layer A (directive) | Layer B (directive) | Type | Resolution / fix |
|---|---|---|---|---|

Include genuine findings and any materially relevant `OVERRIDE-OK` cases. If none exist, say so plainly.

End with the explicit active tier list, including each source and any pinned rules.

## Failure handling

| Issue | Required handling |
|---|---|
| Layer source is unreadable or missing | Mark it absent and continue; do not infer its rules. |
| Same-tier directives conflict | Flag a self-conflict for user resolution. |
| Precedence is genuinely unclear | Do not auto-resolve; request a decision and propose durable wording. |
| Full audit is too large | Audit the dimensions relevant to the current task and list what was skipped. |
| Directives appear different but scopes do not overlap | Record no conflict. |
