# writing-hooks Eval Design

This benchmark follows the highsignal detection recipe: one post, one planted tell, closed vocabulary, and clean guards that should return no ids. It evaluates the specific hook gotchas in `SKILL.md`, not general writing taste.

## Scoring

The eval uses `expect_set`. Dirty cases pass when the output JSON array contains the planted tell id. Clean guard cases pass only on `[]`.

## Closed Vocabulary

The ids are derived from the `Gotchas (kill these in hooks)` section:

- `throat-clear`
- `business-speak`
- `claimed-emotion`
- `manufactured-drama`
- `markdown-in-tweets`
- `em-dash`
- `real-actual`
- `manufactured-quotability`
- `parataxis`
- `not-just-x`
- `filler`
- `abstract-over-number`

Regenerate:

```sh
python skills/writing-hooks/build_cases.py
```
