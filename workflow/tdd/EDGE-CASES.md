# tdd — Invocation edge cases

Loaded by [tdd](SKILL.md) for prior completion records, dispatched work, and redo/fix issues.

## Dispatched but never closed

`drain-wave.py next` exits 3 when the ledger holds dispatched work without a collected result.
First use the owning host's task/process handles to confirm workers and verifier descendants are
terminal. A timestamp, timeout, missing heartbeat, or parent-process exit alone is not proof.
Unknown owners require reconciliation at that host; preserve their work meanwhile.
Then inspect the diff and baseline before any new wave; resolve each issue by evidence:

- **Adopt** useful in-scope work: finish/verify it, write `### 完成`, set `done`, and retain a
  `green` outcome.
- **Revert** only attributable edits that cannot safely be completed, leave `ready`, append the
  reason, and retain an `aborted` outcome. Preserve user/concurrent changes and `.scratch/**`
  history.

After every outstanding issue has an outcome, run the combined scoped checks and reconcile changed
paths against the wave baseline. Then pass all remaining outcomes to one `drain-wave.py collect`
call with that dispatch's `--execution <id>`. A `done` card is still a zombie until this wave-level reconciliation is committed.
An assigned card moved to `archive/` or deleted also remains a zombie; restore it to its feature's
live issue path before explicit collection. `next` and `step` never infer an outcome or mutate the
ledger.

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
