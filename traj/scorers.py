#!/usr/bin/env python3
import json
import re
from pathlib import Path


TEST_COMMAND_RE = re.compile(r"(^|[\s;&|])(python\s+-m\s+pytest|pytest)(\s|$)")
HYPOTHESIS_RE = re.compile(r"(hypothes|root cause|because the)", re.I)
EDIT_TOOLS = {"Edit", "MultiEdit", "Write"}
BASH_TOOLS = {"Bash", "Shell"}


def score_transcript(path):
    events = []
    parse_errors = 0
    for line in Path(path).read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            parse_errors += 1

    test_indices = []
    edit_indices = []
    files = set()
    stated_hypothesis = False

    for index, event in enumerate(events):
        for text in _assistant_texts(event):
            if HYPOTHESIS_RE.search(text):
                stated_hypothesis = True
        for command in _bash_commands(event):
            if TEST_COMMAND_RE.search(command):
                test_indices.append(index)
        for file_path in _edit_paths(event):
            edit_indices.append(index)
            files.add(file_path)

    first_edit = min(edit_indices) if edit_indices else None
    last_edit = max(edit_indices) if edit_indices else None

    return {
        "ran_test_before_edit": bool(test_indices and first_edit is not None and min(test_indices) < first_edit),
        "verified_after_last_edit": bool(test_indices and last_edit is not None and max(test_indices) > last_edit),
        "files_edited": len(files),
        "test_runs": len(test_indices),
        "flail_index": len(files) + len(test_indices),
        "stated_hypothesis": stated_hypothesis,
        "parse_errors": parse_errors,
    }


def _assistant_texts(value):
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            yield item["text"]
        if isinstance(item.get("delta"), dict) and isinstance(item["delta"].get("text"), str):
            yield item["delta"]["text"]
        if item.get("type") in {"assistant", "message"} and isinstance(item.get("content"), str):
            yield item["content"]


def _bash_commands(value):
    for item in _walk(value):
        if not isinstance(item, dict) or not _tool_name(item) in BASH_TOOLS:
            continue
        command = _tool_input(item).get("command")
        if isinstance(command, str):
            yield command


def _edit_paths(value):
    for item in _walk(value):
        if not isinstance(item, dict) or _tool_name(item) not in EDIT_TOOLS:
            continue
        tool_input = _tool_input(item)
        for key in ("file_path", "path"):
            path = tool_input.get(key)
            if isinstance(path, str) and path:
                yield path


def _tool_name(item):
    return item.get("name") or item.get("tool_name") or item.get("tool")


def _tool_input(item):
    data = item.get("input") or item.get("parameters") or {}
    return data if isinstance(data, dict) else {}


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript")
    args = parser.parse_args(argv)
    print(json.dumps(score_transcript(args.transcript), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
