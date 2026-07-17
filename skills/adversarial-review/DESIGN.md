# adversarial-review Eval Design

This benchmark scores the behavioral core of the council skill: given a
proposed implementation decision, identify which hard contract it violates.
The benchmark does not call real reviewer seats; live adapter verification is a
separate integration receipt in the source skill.

## Scoring

`expect_set` cases require a JSON array of ids. Dirty cases plant one primary
violation. Clean guards combine several valid behaviors and must return `[]`.

## Closed vocabulary

- `assumed-auth` — missing config or auth facts are guessed instead of asked.
- `unsupported-adapter` — a custom or unknown executable is accepted as a seat
  instead of requiring one of the four direct built-in adapters.
- `implicit-custom-discovery` — generic executables or default models are
  discovered without an explicit user-supplied contract.
- `setup-available-hidden` — a newly installed known built-in is absent from
  config but is not surfaced for one-time setup.
- `gemini-seat` — Gemini enters through any adapter, gateway, or alias.
- `missing-persona` — the stable four-persona roster is reduced.
- `cross-persona-leak` — one persona receives another persona's output.
- `loose-output` — malformed output is normalized, repaired, or accepted.
- `runtime-reassignment` — a failed persona is moved to another seat mid-run.
- `degraded-pass` — fewer than four valid persona outputs can produce PASS.
- `hidden-recovery` — failed-seat setup and recovery are not surfaced.
- `stale-seat-skip` — a previously failed configured seat is not probed again.
- `smoke-overwrites-review` — a benign smoke result overwrites representative
  review health or is treated as proof that a real review will complete.
- `raw-verdict-authority` — dropped findings still control the council verdict.
- `shell-command-config` — invocation is stored or evaluated as a shell string.
- `embedded-secret` — credential values are persisted in device config.
- `single-family-when-diverse` — a profile uses only one derived model family
  even though the device has at least two review-qualified families available.
- `unbounded-effort` — review effort is left to model defaults or omitted from
  receipts, hiding the direct quality/latency tradeoff between profiles.

## Coverage

The cases cover first-use questions, built-in-only seats, newly available seat
detection, Gemini rejection, persona completeness and isolation, strict output
validation, planned single-engine profiles only on one-family devices,
cross-family defaults when the device has a choice, runtime failure semantics,
operation-specific recovery visibility, smoke/review health separation,
returning seats, structured argv, secret hygiene, verdict recomputation after
semantic triage, and explicit effort/latency policy.
