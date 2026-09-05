# tdd — Invocation edge cases

Loaded by [tdd](SKILL.md) for prior completion records, dispatched work, and redo/fix issues.

## Dispatched but never closed

`drain-wave.py next` exits 3 when the ledger holds dispatched work without a collected result.
Inspect its diff and baseline before any new wave; resolve each issue by evidence:

- **Adopt** useful in-scope work: finish/verify it, write `### 完成`, set `done`, collect `green`.
- **Revert** only attributable edits that cannot safely be completed, leave `ready`, append the
  reason, and collect `aborted`. Preserve user/concurrent changes and `.scratch/**` history.

Red or partial work is not automatically disposable. If ownership is ambiguous, preserve it and
resolve the ambiguity; a clean restart is not worth losing someone else's work.

## Prior completion block on a ready issue

Inspect why it reopened, retain useful implementation, and verify the remaining AC. Prior records
are evidence, not a request to choose “iterate or start over”. Record the new result without
rewriting the earlier attempt.

## redo / fix issues

Resolve the parent through `refines:`. If absent, inspect candidate contracts; ask only if parent
identity remains ambiguous. Read its AC and completion evidence before changing tests.

Preserve tests for behavior that remains required. Update affected assertions in place; delete a
test only when its behavior is explicitly superseded or equivalent coverage replaces it. A changed
API does not justify deleting the whole parent suite. Add each changed/deleted parent test path to
this issue's `test_paths:` and record its fate in `### 完成`.

These are implementation choices under the requested redo. Ask only when the intended behavior
is unresolved; never ask the user to select a test-maintenance tactic.
