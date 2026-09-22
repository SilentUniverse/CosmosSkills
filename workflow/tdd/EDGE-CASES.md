# Existing work and contract changes

## Interrupted work

Read native task/session state and engineering facts. Confirm a previous writer has stopped before
assigning its paths again. Missing heartbeat or parent exit does not establish descendant termination.
Preserve unknown ownership. Adopt useful in-scope changes and verify them; revert only attributable
unwanted edits under existing authorization. Never replay unknown non-idempotent effects.
Native recovery owns session continuation. When necessary engineering facts cross a task/host
boundary, use [handoff](../handoff/SKILL.md); a destination reconstructs the next action with
[resume](../resume/SKILL.md). Neither writes a recovery ledger or requires a context clear.

## Prior completion on an open Issue

Keep the previous record and identify the remaining obligation. Old status cannot validate stale or
damaged evidence. Preserve unchanged proof; record a distinct attempt for new checks. Session change
alone does not reopen cards or rerun the suite.

## redo / fix

Read the `refines` parent's AC and proof. Keep tests for required behavior, update affected assertions
in place, and retire tests only when their behavior is superseded or equivalent coverage preserves
distinct failure detection. Record relevant changed/deleted test paths. Investigate missing lineage;
ask only if the intended parent or behavior remains ambiguous.
