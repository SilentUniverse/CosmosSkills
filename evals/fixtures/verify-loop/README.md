# Task notebook

Python 3 standard library only. Run tests with `python3 -m unittest -v`.
The public CLI is `python3 tasks.py --state <owned-state-file> <command>`.
Use `--help` to discover commands. Each invocation exits; there is no server.
`TASKS_AUDIT` optionally records CLI invocations to a JSONL file.

Business contract: adding a task preserves its title and starts it incomplete. Completing it
persists `done: true`; a later list must show exactly that task completed. Unknown IDs fail.
State belonging to another run must be preserved.

Verification assets belong in `tools/verify-tasks/`, discovered through `AGENTS.md`.
The build consumer needs `python3 tools/verify-tasks/replay.py --evidence <directory>` to verify
the add, complete and list sequence. It must drive `tasks.py` as a subprocess, return nonzero on
a business assertion failure, keep raw observations in the given directory, and remove its own
temporary state after both success and failure. It must work from this repository's root.
Keep requirements here and link them from operating instructions.
