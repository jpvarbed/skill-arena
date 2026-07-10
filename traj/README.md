# Trajectory Benchmark

This benchmark measures whether loading a debugging skill changes both the outcome and the path a coding agent takes when fixing failing Python tests.

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

## Caveats

This is a small benchmark. It uses one agent command and model setting unless configured otherwise. The skill arm injects prompt text with `--append-system-prompt`, which is not the same as native skill activation. Trajectory metrics are parsed from stream-json transcripts and may miss unexpected event shapes.
