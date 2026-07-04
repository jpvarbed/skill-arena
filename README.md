# skill-arena

Local matrix runner for evaluating skills across model backends and prompt variants.

## Run

Dry-run the full local matrix without network calls:

```sh
UV_CACHE_DIR=/private/tmp/skill-arena-uv-cache uv run arena run --all --backends codex,anthropic,openai --dry-run
```

Run the real matrix:

```sh
uv run arena run --all --backends codex,anthropic,openai
```

Outputs:

- `out/results.json`
- `out/leaderboard.html`
- a comparison table on stdout

Generate the report again from an existing result file:

```sh
uv run arena report --results out/results.json --html out/leaderboard.html
```

Deploy/share is intentionally out of scope here. The orchestrator should publish `out/leaderboard.html`.

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
