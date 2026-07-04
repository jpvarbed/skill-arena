# PLAN — skill-arena

GOAL: One command runs a matrix of (skill × model-backend × prompt-variant) against a skill's
git-tracked case set, scores each cell with the scorer that skill declares, and emits a
comparison table + a self-contained leaderboard artifact page. Proven on ≥2 real skills across
≥3 backends, and it reproduces highsignal's existing eval EXACTLY (same cases, same per-case
result) via the arena's expect_set path.

**Baseline source of truth (record before building):** run
`python3 ~/dev/highsignal/tests/eval.py --backend codex` and capture the exact result — currently
**16 cases, 15 pass** (case 7 `filler` the sole miss, plus case 8 documented-flaky). The arena's
highsignal row must match this case-for-case on the same backend, not a threshold.

CONTEXT:
- Home: ~/dev/skill-arena (new repo; python, uv — mirror highsignal's zero-build test style).
- Seed to GENERALIZE (do not rewrite from scratch): ~/dev/highsignal/tests/eval.py — already has
  the backends (codex / anthropic / openrouter / fireworks / claude-cli), a case schema
  (cases.jsonl: {id, kind, context, expect, draft}), and a scorer. Lift its backend adapters
  verbatim into a shared `backends.py`; generalize its per-skill bits into a config.
- Backends + auth (all via bws; source ~/dev/.env.local, parse strict=False, never jq/print):
  anthropic=ANTHROPIC_API_KEY (opus-4-8, etc.), openai=OPENAI_API_KEY (gpt-5.5), google=GOOGLE_API_KEY,
  openrouter=OPENROUTER_API_KEY (has 0 credits — skip unless funded), codex=`codex exec` (no key).
- Arize is ONE scorer backend, not the system: reuse the live `task-completion` evaluator pattern
  via the arize-evaluator skill when a skill's cases want LLM-judge-in-Arize; but default scorers
  are local (deterministic assert + local LLM-judge). Don't lock the arena into Arize.
- Leaderboard: self-contained artifact page via the share-artifact skill (<slug>.jasonv.app).
- First 2 skills to prove it: (1) highsignal (its cases.jsonl, detect-mode, expect-set scoring —
  must reproduce 14/14 on its best backend); (2) a second skill with a DIFFERENT scorer type
  (candidate: a deterministic-scored skill, or the task-completion judge as an LLM-judge case set)
  so the pluggable-scorer claim is actually exercised, not just asserted.

RESOLVED (do not reopen):
- Hybrid architecture: cases live as `arena/<skill>/cases.jsonl` in git; a local runner drives the
  matrix; scoring is PLUGGABLE per skill (deterministic | llm-judge | arize-evaluator); leaderboard
  is an artifact page. NOT Arize-native (cases stay in git), NOT a from-scratch standalone (reuse
  highsignal's eval.py backends).
- Case schema is a superset of highsignal's, back-compatible: {id, input/draft, expect (id | [ids]
  | rubric), scorer, context?}. highsignal's existing cases.jsonl must load unmodified.
- Per-skill config declares: the prompt template(s)/variants, the scorer type, and the pass rule.

DESIGN (seams):
1. `backends.py` — FIRST lift highsignal's EXACT adapters unchanged (call_codex, call_anthropic,
   call_claude_cli, call_openrouter, call_fireworks) so the highsignal path reproduces byte-for-byte;
   only AFTER R1+R3 pass, add call_openai (gpt-5.5) and call_google as separate additions. Each →
   (prompt, model) -> raw text. bws-fed keys. Quota/error → ERROR sentinel, never a silent pass.
2. `scorers.py` — pluggable: `deterministic` (regex/exact/asserts), `expect_set` (highsignal's
   id-set match), `llm_judge` (a judge model + rubric → pass/fail), `arize` (optional). Each:
   (case, model_output) -> {pass: bool, detail}.
3. `arena.py` — load a skill config + its cases.jsonl; run skill × backend × prompt-variant;
   collect per-cell pass-rate + cost + latency; write results.json.
4. `report.py` — results.json → comparison table (stdout) + a self-contained HTML leaderboard
   (skills as sections, backends as columns, pass-rate cells, per-cell drill-down).
5. `skills/<name>/config.json` + `cases.jsonl` — highsignal wired first (points at its real cases).

VERIFY:
- Primary: `uv run arena run --skill highsignal --backends codex,anthropic` prints a table and the
  highsignal row reproduces its known pass rate (≥14/16 on its best backend, matching tonight's eval).
- Second skill with a non-expect_set scorer runs green, proving pluggability (not just present in code).
- Leaderboard artifact renders at a real URL with ≥2 skills × ≥3 backend columns.
- Cost/latency per cell recorded so "cheapest backend that holds the skill" is answerable.
- Reward-hack guard: a backend that errors or hits quota must score as ERROR, never silently as a
  pass or a 0 (the codex-quota lesson — fail loud).

RUBRIC (binary):
- [ ] R1: `uv run arena run --skill highsignal --backends codex` reproduces
      `highsignal/tests/eval.py --backend codex` EXACTLY (same 16 cases, same per-case pass/fail =
      15/16, case 7 the miss); highsignal's cases.jsonl loads unmodified (not copied/forked).
- [ ] R2: A 2nd skill with a DIFFERENT scorer type runs, and its offline tests include BOTH a passing
      fixture AND an intentionally-failing fixture (proves the scorer catches failure, not just runs).
- [ ] R3: One command runs ≥2 skills × ≥3 backends and emits a comparison table (stdout).
- [ ] R4: `arena report --share` deploys a self-contained leaderboard to a real <slug>.jasonv.app URL
      (≥2 skills) via share-artifact; a pre-publish check confirms slug + no secrets in the HTML;
      publish failure is a hard ERROR, and local out/leaderboard.html is always written regardless.
- [ ] R5: Per-cell cost + latency recorded; quota/errors surface as ERROR, never a fake pass or 0.
- [ ] R6: bws-only secrets, none printed; README with the single command + how to add a skill;
      offline unit tests for scorers + case loader.

DONE = all rubric PASS. Deviations logged; unreachable rubric item → stop and report.
