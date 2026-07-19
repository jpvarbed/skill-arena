# skill-workshop Eval Design

This suite tests whether an agent can distinguish evidence-gated skill
authoring from plausible shortcuts. It scores policy decisions, not prose
quality or live adapters.

## Scoring

`expect_set` cases return only violation ids. Dirty cases plant one primary
violation; clean guards combine valid obligations and expect `[]`. The same
cases and model run without and with the skill.

## Closed vocabulary

- `spec-after-build` — behavior is implemented before its contract is fixed.
- `patchwork` — a wall is hidden behind a flag, shim, or parallel path.
- `tier-downgrade` — the selected tier omits a higher-risk dependency.
- `hybrid-tests` — an integration that bundles code omits inherited tests.
- `dry-run-as-proof` — wiring/static output is claimed as behavioral proof.
- `answer-leak` — forward-test agents receive expected answers or prior output.
- `secret-persist` — credentials are committed or written to device config.
- `smoke-as-live` — benign smoke is treated as representative qualification.
- `hidden-integration` — failed live setup or recovery is concealed.
- `runtime-substitution` — a declared provider/model is silently replaced.
- `single-family-completion` — completion lacks another model family.
- `implicit-effort` — review effort and latency tradeoff are undeclared.
- `premature-ship` — required artifacts or receipts are missing at ship time.

## Coverage

Dirty cases cover every vocabulary item. Clean guards cover a lean method skill,
a code-free integration, a hybrid integration with explicit effort, and a
fully evidenced handoff. The first suite version mislabeled an integration that
omitted requested/effective effort as clean; v2 retains it as a dirty guard and
adds the valid counterpart. Blind agent execution and live adapter qualification remain separate
receipts because classifier prompts cannot prove either.
