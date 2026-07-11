# highsignal - cross-model eval results

Both models run through [`eval.py`](./eval.py) on [`cases.jsonl`](./cases.jsonl) (14 cases:
11 dirty, 3 clean), detect mode, single run each. June 2026.

## Scores

| Model | Pass | Rate | False positives (clean) |
|---|---|---|---|
| `codex exec` (codex-cli 0.142.4, default model) | 13/14 | 93% | 0 |
| Claude `sonnet-4-6` (Anthropic API) | 12/14 | 86% | 0 |

Zero false positives for both - neither over-flags clean writing.
