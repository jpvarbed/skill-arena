#!/usr/bin/env python3
"""Merge N independent k=1 `arena run` results into a per-case majority verdict.

Used to confirm/deny an apparent ceiling before a forge no-go: one k=1 pass at
17-18/18 is inside single-case noise; three passes merged by strict per-case
majority are the decision-grade number.

Usage:
  python majority.py --skill S --backend B run1/results.json run2/results.json run3/results.json
Prints per-case majority table + merged score. Strict majority; ties fail closed.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_case_passes(path, skill, backend):
    data = json.loads(Path(path).read_text())
    skill_block = data["skills"][skill]
    cell = next(c for c in skill_block["cells"] if c["backend"] == backend)
    return {row["id"]: bool(row["pass"]) for row in cell["cases"]}, cell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("results", nargs="+")
    args = ap.parse_args()

    votes = defaultdict(list)
    for path in args.results:
        passes, _ = load_case_passes(path, args.skill, args.backend)
        for case_id, ok in passes.items():
            votes[case_id].append(ok)

    k = len(args.results)
    majority_passes = 0
    for case_id in sorted(votes):
        vs = votes[case_id]
        if len(vs) != k:
            raise SystemExit(f"case {case_id} present in {len(vs)}/{k} runs — refusing to merge")
        ok = sum(vs) * 2 > k  # strict majority; even-k tie fails closed
        majority_passes += ok
        print(f"{'PASS' if ok else 'FAIL'}  {case_id}  votes={sum(vs)}/{k}")
    print(f"majority score: {majority_passes}/{len(votes)}  (k={k}, backend={args.backend})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
