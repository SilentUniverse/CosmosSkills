import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Local task notebook")
    parser.add_argument("--state", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add").add_argument("title")
    commands.add_parser("list")
    commands.add_parser("complete").add_argument("id", type=int)
    args = parser.parse_args()
    if os.environ.get("TASKS_AUDIT"):
        with open(os.environ["TASKS_AUDIT"], "a", encoding="utf-8") as audit:
            audit.write(json.dumps({"command": args.command, "state": str(args.state)}) + "\n")
    tasks = json.loads(args.state.read_text()) if args.state.exists() else []
    if args.command == "add":
        task = {"id": len(tasks) + 1, "title": args.title, "done": False}
        tasks.append(task)
        result = task
    elif args.command == "complete":
        task = next((item for item in tasks if item["id"] == args.id), None)
        if task is None:
            parser.error("unknown task")
        task["done"] = True
        result = task
    else:
        result = tasks
    if args.command != "list":
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(tasks), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
