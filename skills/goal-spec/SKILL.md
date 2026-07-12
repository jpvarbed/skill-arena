---
name: goal-spec
description: Turn a rough task into a launch-ready /goal brief — a verifiable spec with context-access, a verification plan, and a binary rubric — so a dispatched agent runs to completion unattended. Use when prepping a task for "/goal", or when the user says "spec this for goal", "write the rubric", "make this verifiable", "prep a dispatch", or any turn whose real job is assembling the spec+rubric for a later /goal launch. NOT for doing the task yourself (just do it) and NOT for scoring a finished skill (use "linting-and-scoring"). Pairs with "adversarial-review" and "grilling" (stress-test the brief); distinct from "writing-plans"/"to-prd", which produce implementation plans, not verifiable dispatch briefs.
---

# goal-spec — compile a verifiable /goal brief

**Verifiability is the #1 determinant of whether a dispatched agent finishes.** A `/goal`
launch only goes as well as the spec + rubric you hand it. This skill turns a rough ask into
a launch-ready brief so the agent can run to completion unattended — and so you stop
hand-assembling context every time.

> Working model: every turn that *isn't* a `/goal` should be building the brief for the next
> one. This skill is that build. The output is a paste-ready brief, not the work itself.

## Step 1 — Pass the verifiability gate (do this first)
State the done-condition as a **binary check** a human or script could evaluate with no
judgment call.
- Can't state it cleanly → the unit is too big or too fuzzy. **Decompose** until each unit
  has a binary done-check, then spec each unit separately.
- "Looks good / is better / handles edge cases" are not checks. "Beats the 90% holdout
  baseline", "exit 0 + artifact at PATH", "all N rows reconcile" are.

## Step 1b — Blindspot pass (map vs territory)
The brief is a **map**; the agent works in the **territory** (real codebase, live constraints,
the human's actual intent). The gap between them is unknowns — where a dispatched agent guesses.
Surface all three non-obvious quadrants BEFORE emitting the brief, one move each:
- **Known unknowns** → turn into interview questions, one at a time, prioritizing the ones whose
  answer would change the architecture; write the answers INTO the brief (references over prose).
- **Unknown knowns** (obvious-to-the-human but unstated) → show 3–4 candidate directions to react
  to (`grilling` / a throwaway `prototype`) instead of asking in the abstract.
- **Unknown unknowns** → a dedicated blindspot list: "what would make this run wrong that neither
  of us has said out loud" — likely edge cases, adjacent systems, unstated invariants.
More work per run ⇒ more unknowns ⇒ more places to guess wrong: a long blindspot list is a
decomposition signal (back to Step 1). Also tell the dispatched agent to keep a **deviations
log** — an unknown hit mid-build may mean the problem should be solved a different way; route
it back to the plan, don't bury it.

## Step 2 — Context access (give the keys, not the data)
List what the agent must reach AND the tool to reach it. Prefer live access over pasted dumps.
1. Reference material: markdown of prior experiments/decisions/numbers; the relevant docs.
2. Tools/CLIs it will drive, each with its auth source (e.g. training CLI, `langsmith-cli`
   for traces, `linear`/`gh`/`bws`).
3. Output location (repo / branch / dir) and any fixtures (the train + holdout sets).

Bad: paste three logs. Good: "traces live in LangSmith — read with `langsmith-cli runs …`".

## Step 3 — Verification plan (how it knows it's *working*, not just *done*)
1. **Primary signal** — the metric that moves ("number go up") and how to measure it.
2. **Hill-climb set** — the pre-split train + holdout it iterates against (never tune on holdout).
3. **Number to beat** — an explicit baseline (e.g. "break 90%, the GLM-5.2 baseline").
4. **Reading intermediate signal** — how to inspect rollouts/traces to choose the next move.
5. **Human hints** — known good moves + failure modes (length penalty if turns balloon,
   prompt-eng first, and what reward-hacking looks like for *this* task).

## Step 4 — Binary rubric (the done-checklist the agent self-checks before returning)
Every item PASS/FAIL, no vibes. Cover three axes: **outcome**, **integrity**, **reproducibility**.
Example (fine-tuning run):
- [ ] Beat the 90% holdout baseline.
- [ ] Checked traces for reward hacking, and reported what was found.
- [ ] Experiment logged in LangSmith; reproducible with a single command + a write-up.

## Step 5 — Adversarial pre-launch pass (don't skip)
Red-team the brief with `adversarial-review` before dispatch:
- **Can the agent pass the rubric without doing the work?** (reward-hacking the checks) → tighten,
  or add an integrity check it can't spoof.
- Is every rubric item binary AND verifiable with the context you provided?
- Is anything in the verification plan unmeasurable with the tools listed? → add the tool or cut the check.

## Step 6 — Emit the brief
Output one paste-ready block, then hand it to `/goal`:
```
GOAL: <one verifiable outcome>
CONTEXT: <access list — tools (+auth) + refs + output location + fixtures>
EFFORT: <high | medium | low — high for design/interface/data-model or irreversible calls; low for
  mechanical/verified-downstream work. Set the dispatched agent's reasoning tier by leverage, not
  size. Orchestrators launch high (Fable xhigh). See docs/effort-policy.md.>
VERIFY: <primary signal · hill-climb set · number-to-beat · how to read signal · hints>
RESOLVED (do not reopen): <decisions already settled — tech choices, scope cuts. A reviewer/agent
  that reopens one is out of scope. Pass this to `review-council --resolved` so gates don't re-argue it.>
RUBRIC (binary):
  - [ ] <outcome check>
  - [ ] <integrity check>
  - [ ] <reproducibility check>
DONE = all rubric checks PASS.
```

## Errors / failure modes
| Issue | Fix |
|---|---|
| Done-condition isn't binary | Decompose until each unit has a script/metric-checkable done-check. |
| No baseline to beat | Establish one first (measure current / the holdout) — a number-to-beat is required, not optional. |
| Rubric is game-able (reward-hackable) | Add an integrity check (inspect traces/artifacts) or make the metric harder to spoof. |
| Context pasted, not accessible | Replace dumps with the tool + location the agent can query live. |
| Verification tool/CLI missing or unauthed | Provide it (or its `bws` key) before launch — if the agent can't verify, don't dispatch. |
| Task too large for one /goal | Split into units, each its own brief; sequence or dispatch in parallel. |
