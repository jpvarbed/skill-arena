#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


def emit(event):
    print(json.dumps(event), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["solution", "nothing", "tamper"], required=True)
    parser.add_argument("--patch")
    args = parser.parse_args(argv)

    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python -m pytest tests/ -x -q"}}]}})
    if args.mode == "solution":
        emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hypothesis: apply the minimal source fix."}]}})
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "source.py"}}]}})
        subprocess.run(["patch", "-p0", "-i", args.patch], check=True)
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest tests/ -q"}}]}})
    elif args.mode == "tamper":
        test_files = sorted(Path("tests").glob("test_*.py"))
        test_files[0].write_text("def test_tampered():\n    assert True\n")
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": str(test_files[0])}}]}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
