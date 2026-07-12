# instruction-conflicts Eval Design

This benchmark reduces the skill to its detection core: given a realistic layered instruction stack, return the conflict type ids that apply. The real skill also recommends resolution wording, but this eval scores the first hard step: spotting whether two active directives address the same dimension and disagree.

## Scoring

The eval uses `expect_set`. Dirty cases contain one planted conflict and pass when the output JSON array contains that id. Clean guard cases contain plausible tension but should return `[]`.

## Closed Vocabulary

The ids are derived from the skill's taxonomy: conflict classes (`CONTRADICTION`, `AMBIGUOUS-PRECEDENCE`) plus the common dimensions it tells auditors to check.

- `autonomy-conflict`: ask-before-acting and proceed-without-asking both govern the same action.
- `commit-policy-conflict`: one layer requires committing or pushing while another forbids it.
- `tone-conflict`: tone or sycophancy rules directly disagree.
- `verification-conflict`: one layer requires proof while another forbids or skips verification.
- `output-format-conflict`: two layers require incompatible final formats.
- `tool-choice-conflict`: two layers mandate mutually exclusive tools for the same work.
- `secret-handling-conflict`: one layer requires exposing or storing secrets while another forbids it.
- `ambiguous-precedence`: two applicable layers disagree and neither says which wins.
- `same-tier-conflict`: two directives in the same layer contradict each other.

## Case Shape

Cases are authored in `build_cases.py` as readable layered stacks, then emitted to `cases.jsonl`. Each stack has five layers in precedence order and 60 directive lines, matching the skill's tier map: user, global user, project, skill, and tool notes.

Regenerate:

```sh
python skills/instruction-conflicts/build_cases.py
```
