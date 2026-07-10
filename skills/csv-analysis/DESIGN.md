# CSV Analysis Benchmark

This benchmark measures whether a skill improves small CSV analysis tasks with deterministic grading.

The case source of truth is `meta.query`. The generator derives both the natural-language question and the stored gold answer from that query with the same executor, then renders the CSV from `meta.rows`. The `meta` block exists only for verification and is never included in the prompt.

The corpus is fixed, seeded, tiered, and synthetic. Synthetic tables keep the gold answer controllable; real CSV traces can be added later as a separate layer. Re-running `build_cases.py` emits byte-identical JSONL.

Gold is stored only in scorer-native deterministic shapes:

```json
{"exact": "42"}
{"json": {"East": 10, "West": 12}}
```

Regenerate and verify:

```sh
python skills/csv-analysis/build_cases.py
python skills/csv-analysis/verify_gold.py
uv run arena run --skill csv-analysis --dry-run
```
