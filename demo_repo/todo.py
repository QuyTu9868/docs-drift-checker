"""Tiny demo CLI."""
import argparse
import json
import os

PATH = os.environ.get("TODO_PATH", "tasks.json")


def load() -> list[dict]:
    return json.load(open(PATH)) if os.path.exists(PATH) else []


def main() -> None:
    ap = argparse.ArgumentParser(prog="todo.py", description="Tiny task tracker")
    ap.add_argument("--version", action="version", version="todo 0.2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("title")
    ls = sub.add_parser("list")
    ls.add_argument("--all", action="store_true")   
    sub.add_parser("done").add_argument("id", type=int)
    args = ap.parse_args()
    print(args)


if __name__ == "__main__":
    main()
