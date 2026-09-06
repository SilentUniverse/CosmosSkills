# tdd — -log mode

Loaded on demand by [`/tdd`](SKILL.md) when invoked with `-log`, or when the user says this run
drives a device and the result lands in a log file.

Keep the status guard, declared scope, fingerprint/P# replay, contract-conflict recovery, and
completion record. Replace the test-writing RED/GREEN loop with the recorded control action and
log predicate. A successful launcher exit alone does not prove the required behavior.

Run bounded commands through `scripts/test-supervisor.py` in this skill, preserving the exact
command, exit, log, and acceptance predicate. The final verifier must assert the predicate and fail
when it is false; capture-only commands cannot close a card. Retain the shortest decisive excerpt.
A long-lived device stream uses a bounded capture and explicit stop
condition. 车机 / `adb`: read `~/.claude/references/android-adb.md` first.

- Drain `-p`: one issue per wave.
- `-all` and drain close: replay each shipped issue's action and predicate against the final state.
- A v3 issue still requires a bound final receipt; use the same completion procedure as test mode.
- Combines with any invocation form.
