from __future__ import annotations

import argparse
import json
import sys

from .api import Shelfd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shelfd")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add-book")
    add.add_argument("title")
    add.add_argument("author")
    add.add_argument("--year", type=int, required=True)
    add.add_argument("--genre", action="append", default=[])
    add.add_argument("--copies", type=int, default=1)

    search = sub.add_parser("search")
    search.add_argument("--text")
    search.add_argument("--author")
    search.add_argument("--genre")
    search.add_argument("--available-only", action="store_true")

    member = sub.add_parser("register-member")
    member.add_argument("name")
    member.add_argument("email")
    member.add_argument("--max-loans", type=int, default=3)

    sub.add_parser("summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = Shelfd()
    if args.command == "add-book":
        book = app.add_book(args.title, args.author, year=args.year, genres=args.genre, copies=args.copies)
        print(json.dumps(book.to_dict(), sort_keys=True))
        return 0
    if args.command == "search":
        books = app.search(
            text=args.text,
            author=args.author,
            genre=args.genre,
            available_only=args.available_only,
        )
        print(json.dumps([book.to_dict() for book in books], sort_keys=True))
        return 0
    if args.command == "register-member":
        member = app.register_member(args.name, args.email, max_loans=args.max_loans)
        print(json.dumps(member.to_dict(), sort_keys=True))
        return 0
    if args.command == "summary":
        print(json.dumps(app.summary(), sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
