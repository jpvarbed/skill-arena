# Inference canary example

This suite freezes three workflow contracts:

- preserve an exact instruction while editing
- keep private source context out of public output
- find behavior and authorization risk in a code review

See the [2026-07-10 seven-lane receipt](RECEIPT-2026-07-10.md).

Run a first baseline:

```sh
uv run arena canary \
  --config examples/inference-canary/config.json \
  --backends codex,cursor \
  --runs-dir out/canary
```

Run the same command later. The latest compatible suite becomes the baseline automatically. A changed prompt, expectation, scorer, or injected skill starts a new baseline instead of producing a false drift label.

`results.json` keeps raw outputs for local diagnosis. `summary.md` contains only lane status, counts, and changed check IDs, so it is the safer receipt to share after review.

`json_fields` requires strict JSON with the named fields and permits additional fields. Use the legacy `json` assertion when the entire object must match exactly.
