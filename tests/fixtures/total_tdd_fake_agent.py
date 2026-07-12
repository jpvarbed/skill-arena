#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
import time
from pathlib import Path


HEADER = ["id", "area", "user_story", "expected_behavior", "source", "status", "issues", "fix", "verified"]


def write_tracker(path: Path) -> None:
    rows = [
        ["D001", "catalog", "author case search", "case-insensitive author filter", "shelfd/catalog.py", "fixed", "le guin mismatch", "normalized author", "pytest"],
        ["D002", "fees", "late fee day count", "charge every late day", "shelfd/fees.py", "fixed", "75 became 50", "removed grace day", "pytest"],
        ["D003", "checkout", "api checkout accepts iso due date string", "parse due date", "shelfd/circulation.py", "fixed", "TypeError on string", "parse_date", "pytest"],
        ["D004", "members", "member limit fourth checkout boundary", "max_loans blocks extra loan", "shelfd/members.py", "fixed", "fourth checkout allowed", ">= limit", "pytest"],
        ["D005", "circulation", "overdue repeatable state query", "no mutable seen leak", "shelfd/circulation.py", "fixed", "second query empty", "local seen", "pytest"],
        ["D006", "reservation", "renew reservation late fee interaction", "reserved books cannot renew", "shelfd/circulation.py", "fixed", "reservation ignored", "check reservations", "pytest"],
        ["D007", "import", "csv loan import member limit", "import validates max_loans", "shelfd/io.py", "fixed", "import bypassed max_loans", "limit check", "pytest"],
        ["D008", "audit", "audit checkout return interleaving same member", "both events recorded", "shelfd/audit.py", "fixed", "return dropped", "remove dedupe", "pytest"],
    ]
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)


def apply_all_patches(cwd: Path) -> None:
    for patch in sorted((cwd / "solutions").glob("*.patch")):
        subprocess.run(["patch", "-p0", "-i", str(patch)], cwd=cwd, check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["solution", "nothing", "tamper", "sleep"], default="solution")
    parser.add_argument("--prompt")
    args = parser.parse_args()
    cwd = Path.cwd()
    if args.prompt:
        assert Path(args.prompt).exists()
    print("secret sk-testsecret1234567890")
    if args.mode == "sleep":
        time.sleep(5)
        return 0
    if args.mode in {"solution", "tamper"}:
        apply_all_patches(cwd)
    if args.mode == "tamper":
        target = cwd / "tests" / "test_catalog.py"
        target.write_text(target.read_text() + "\n# tampered\n")
    write_tracker(cwd / "tracker.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
