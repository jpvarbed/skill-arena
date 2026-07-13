# skill-arena

Which model runs your skill best? Point this at a skill and its graded cases, and it runs every
model over them and prints one honest number per cell. A failed call scores as an error, never a
fake pass.

**Live example:** https://skill-arena.jasonv.app runs six models over two skills. On
AI-writing-tell detection, GPT-5.5 and Gemini 2.5 Pro tie at 94%, and Haiku 4.5 is the floor at 69%.

Cases live in git, so the number is reproducible and the diff is reviewable. Bring your own skill
repo and get the same table.

## Run

```sh
# no network — stubs every backend, proves the wiring
uv run arena run --all --backends anthropic,openai,google --dry-run

# the real matrix
uv run arena run --all --backends anthropic,openai,google
```

Each run writes `out/results.json`, `out/leaderboard.html`, and a table to stdout. Regenerate the
page from a saved run:

```sh
uv run arena report --results out/results.json --html out/leaderboard.html
```

## Forge a Skill

`arena forge` generates blind SKILL.md variants, scores baseline/original/variants on the same
graded cases, and writes a receipt.

```sh
# cheap smoke run, one Google backend
uv run arena forge --skill ai-writing-tell

# hero receipt run: target Haiku plus OpenAI and Google
uv run arena forge --skill ai-writing-tell --full

# offline replay from saved model outputs, no API calls
uv run arena forge --replay --results out/forge-results.json
```

Forge writes `out/forge-results.json`, `out/receipt.html`, and variant files under
`out/forge-variants/`. A hero requires strict lift over the original on the target model
(`haiku` by default); ties and regressions render an honest no-improvement receipt.

Two companion checks for `expect_set` skills, where the headline scorer passes a dirty
case on any expected/got overlap:

```sh
# precision diagnostic + winner release gate (over-labeling can't buy a lift)
uv run python precision.py --results out/forge-X/results.json --backend <backend>

# merge N independent k=1 runs into a per-case strict-majority score
uv run python majority.py --skill <name> --backend <backend> run1/results.json run2/results.json run3/results.json
```

`precision.py` recomputes exact-set rate, mean extra labels on dirty cases, and clean-case
passes from the raw per-trial outputs, then gates the declared winner against the original:
strictly higher subset score, no more extra labels, no fewer clean passes — fail any and the
"lift" is ineligible.

## Add a Skill

Create `skills/<name>/config.json`:

```json
{
  "name": "my-skill",
  "cases_path": "cases.jsonl",
  "prompt_variants": [
    {
      "name": "default",
      "template": "Answer the request.\n\nREQUEST:\n{input}\n"
    }
  ],
  "scorer": {
    "type": "deterministic"
  }
}
```

Create `skills/<name>/cases.jsonl` with one JSON object per line. The schema is a superset of
highsignal's existing cases:

```jsonl
{"id":"1","input":"Return ok.","expect":{"exact":"ok"}}
{"id":"2","input":"Return JSON.","expect":{"json":{"ok":true}}}
```

Supported scorer types:

- `expect_set`: highsignal-compatible id-set matching for `{kind, expect, draft}` cases.
- `deterministic`: `exact`, `regex`, `keyword`, `keywords`, and `json` assertions.
- `llm_judge`: local judge backend that expects a JSON verdict.
- `arize`: explicit stub; raises until the Arize evaluator adapter is wired.

## Backends and Auth

Secrets are loaded from the environment first. If a key is missing, `backends.py` sources
`~/dev/.env.local` and runs `bws secret list -o json`, parsed in Python with `strict=False`.
Secret values are never printed.

| Backend | Adapter | Auth |
| --- | --- | --- |
| `codex` | `codex exec --skip-git-repo-check` | local Codex auth |
| `claude-cli` | `claude -p` | local Claude auth |
| `anthropic` | Anthropic Messages API | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI chat completions | `OPENAI_API_KEY` |
| `google` | Gemini generateContent | `GOOGLE_API_KEY` |
| `openrouter` | OpenRouter chat completions | `OPENROUTER_API_KEY` |
| `fireworks` | Fireworks chat completions | `FIREWORKS_API_KEY` |

Backend exceptions, quota failures, auth failures, and recognizable CLI errors return an `ERROR:`
sentinel. Scorers treat that sentinel as a failing error result, never as a clean answer.

## Backend gotchas (learned running the real matrix)

- **codex CLI needs a TTY.** As a subprocess it works in the foreground but hangs (app-server
  init) when the arena is run detached/backgrounded. Prefer the API backends for unattended runs;
  use codex only in a foreground/interactive shell.
- **Reasoning models eat the token cap.** gpt-5.x and gemini-2.5-pro spend the output budget on
  hidden reasoning; a small cap returns an empty answer. gpt-5.x also use `max_completion_tokens`
  (not `max_tokens`) and reject a custom temperature. Caps are set generous (2000) for these.
- **Model judges are nondeterministic.** highsignal detection varies run-to-run (~14–15/16 per
  backend); the arena's scorer is identical to highsignal/tests/eval.py, so a differing pass count
  is model variance, not a scoring divergence.
