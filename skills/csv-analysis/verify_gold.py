#!/usr/bin/env python3
import csv
import io
import json
import sys
from pathlib import Path

from build_cases import COLUMNS, execute_query, has_unique_answer


def parse_input_csv(text):
    if not text.startswith("CSV:\n"):
        raise AssertionError("input must start with CSV block")
    csv_text = text.split("\n\nQuestion:", 1)[0].removeprefix("CSV:\n")
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_cases(path):
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_cases(cases):
    for case in cases:
        meta = case["meta"]
        parsed = parse_input_csv(case["input"])
        if parsed != meta["rows"]:
            raise AssertionError(f"{case['id']}: CSV rows do not match meta.rows")
        if list(parsed[0].keys()) != meta["columns"] or meta["columns"] != COLUMNS:
            raise AssertionError(f"{case['id']}: CSV columns do not match meta.columns")
        if not has_unique_answer(meta["rows"], meta["query"]):
            raise AssertionError(f"{case['id']}: query answer is ambiguous")
        expected = execute_query(meta["rows"], meta["query"])
        if case["expect"] != expected:
            raise AssertionError(f"{case['id']}: stored expect {case['expect']!r} != executor {expected!r}")


def main_for_test(cases):
    try:
        verify_cases(cases)
    except Exception:
        return 1
    return 0


def main(argv=None):
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else Path(__file__).with_name("cases.jsonl")
    try:
        verify_cases(load_cases(path))
    except Exception as exc:
        print(f"verify_gold failed: {exc}", file=sys.stderr)
        return 1
    print(f"verified {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
