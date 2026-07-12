# goal-spec Eval Design

This benchmark checks whether a rough task becomes a launch-ready `/goal` brief with the required structural guarantees.

## Scoring

`brief_lint` is a deterministic linter. It checks:

- single-line `GOAL:`
- `CONTEXT:` with an access list
- single-line `EFFORT:` set to `high`, `medium`, or `low`
- `VERIFY:` containing an explicit number-to-beat
- `RUBRIC` items are all binary checkboxes
- `RESOLVED` section is present

The arena score is conformance rate: each arm output either passes the linter or fails with named missing checks. Unit fixtures cover 5 conforming and 5 non-conforming briefs, and the linter must match those labels exactly.

Regenerate:

```sh
python skills/goal-spec/build_cases.py
```
