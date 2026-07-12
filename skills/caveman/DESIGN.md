# caveman Eval Design

This benchmark measures whether the skill compresses prose while preserving factual content. It avoids subjective style scoring by storing factual probes per case.

## Scoring

`compression_fidelity` uses a deterministic tokenizer:

```text
[A-Za-z0-9_]+|[^\sA-Za-z0-9_]
```

That means word-like runs count as one token and punctuation counts as separate tokens. Compression is:

```text
1 - output_tokens / input_tokens
```

Fidelity is the fraction of `answer_pattern` regex probes that still match the compressed output. A case fails if fidelity is below `0.8`, regardless of compression. When fidelity passes, the case score is the compression percentage.

## Case Shape

Each case contains 150-400 words of prose from a different domain, at least three factual probes, and a reference compression used only for dry-run wiring.

Regenerate:

```sh
python skills/caveman/build_cases.py
```
