# Trajectory Benchmark

This benchmark measures whether loading a debugging skill changes both the outcome and the path a coding agent takes when fixing failing Python tests.

It has two tiers:

- Tier 1: small authored Python tasks in `traj/tasks/`. These saturate by design on strong models and are mainly useful for measuring method adoption: test-first behavior, verification after edits, file churn, and similar trajectory signals.
- Tier 2: frozen SWE-bench Verified instances in `traj/tier2/`. These are real issues run on disposable exe.dev cloud boxes with Docker and measure effectiveness: resolved issues, FAIL_TO_PASS progress, and PASS_TO_PASS regressions.

The task corpus lives in `traj/tasks/`. Each task starts with one realistic bug and a pytest suite where at least one test fails. The benchmark runs fresh copies of each task across two arms:

- `baseline`: no skill prompt
- `skill`: the same prompt plus `--append-system-prompt` with `--skill-file`

## Commands

Validate the corpus:

```bash
python traj/validate_tasks.py
```

Run a smoke benchmark:

```bash
python traj/run_benchmark.py --smoke --skill-file path/to/debugging-skill.md
```

The full runner defaults to all tasks, both arms, and three trials:

```bash
python traj/run_benchmark.py --skill-file path/to/debugging-skill.md
```

Generate a receipt:

```bash
python traj/report.py
```

## Tier 2 Commands

Tier 2 uses optional live dependencies. Do not add them to the core project dependencies; install them into the repo venv when running the live pipeline:

```bash
uv pip install swebench datasets
```

Select deterministic overflow candidates from SWE-bench Verified:

```bash
python -m traj.tier2.select_instances
```

Validate candidates on real exe.dev boxes and freeze the first 12 that pass the gold/no-op checks:

```bash
python -m traj.tier2.validate_instances
```

Run the tier-2 matrix:

```bash
python -m traj.tier2.run_tier2 --skill-file path/to/debugging-skill.md
```

Run one smoke cell:

```bash
python -m traj.tier2.run_tier2 --smoke --arms baseline
```

Generate the tier-2 receipt:

```bash
python -m traj.tier2.report_tier2
```

Clean up leftover runner-created boxes:

```bash
python -m traj.tier2.run_tier2 cleanup
```

Required live environment variables:

- `exe_dev_skill_arena_forever_ssh_key`: bearer token for exe.dev lifecycle calls.
- `AGENT_API_KEY`: agent key made available to the remote box command as `ANTHROPIC_API_KEY="$AGENT_API_KEY"`.

Tier 2 is the expensive tier. Each instance creates a disposable exe.dev box, pulls the prebuilt SWE-bench image, copies `/testbed` out of a fresh container, runs the agent over ssh, copies the stream-json trace back before teardown, and grades the patch through the SWE-bench helpers. Keep `--parallel-boxes` at or below `3`.

## Runner Flags

- `--smoke`: first task, both arms, one trial
- `--tasks`: comma-separated task ids
- `--trials`: trials per task and arm, default `3`
- `--arms`: comma-separated arms, `baseline` and/or `skill`
- `--skill-file PATH`: required when the `skill` arm is selected
- `--out-dir`: output directory, default `traj/out`
- `--agent-cmd`: shell command template for tests and dry harnesses

`--agent-cmd` templates can use `{python}`, `{task_dir}`, `{solution_patch}`, `{cwd}`, `{task}`, `{arm}`, `{trial}`, `{prompt}`, and `{skill_prompt}`.

## Output Schema

`traj/out/results.json` is a JSON array. Each row has:

```json
{
  "task": "task-id",
  "arm": "baseline",
  "trial": 1,
  "tests_pass": true,
  "timeout": false,
  "reason": "passed",
  "duration_s": 1.23,
  "metrics": {
    "ran_test_before_edit": true,
    "verified_after_last_edit": true,
    "files_edited": 1,
    "test_runs": 2,
    "flail_index": 3,
    "stated_hypothesis": true,
    "parse_errors": 0
  },
  "transcript_path": "traj/out/traces/task_baseline_1.jsonl",
  "temp_path": "/tmp/traj_task_baseline_1_x/repo"
}
```

`traj/out/receipt.md` summarizes raw trial fix rates, majority-of-k task fix rates, per-task trajectory metrics, timeout or tamper incidents, and a frozen task manifest with repo tree hashes.

Tier-2 rows live at `traj/out/tier2/results.json` by default:

```json
{
  "instance_id": "repo__project-123",
  "arm": "baseline",
  "trial": 1,
  "resolved": false,
  "fail_to_pass_passed": 2,
  "pass_to_pass_regressions": 0,
  "timeout": false,
  "duration_s": 123.4,
  "metrics": {
    "ran_test_before_edit": true,
    "verified_after_last_edit": true,
    "files_edited": 2,
    "test_runs": 3,
    "flail_index": 5,
    "stated_hypothesis": true,
    "parse_errors": 0
  },
  "trace_path": "traj/out/tier2/traces/repo__project-123_baseline_1.jsonl",
  "box_name": "t2-repo-project-1"
}
```

## Caveats

This is a small benchmark. It uses one agent command and model setting unless configured otherwise. The skill arm injects prompt text with `--append-system-prompt`, which is not the same as native skill activation. Trajectory metrics are parsed from stream-json transcripts and may miss unexpected event shapes.
