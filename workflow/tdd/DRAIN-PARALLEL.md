# Parallel waves (`-p`)

Loaded only for a `-p` drain; a serial batch never loads this file. It extends
[DRAIN.md](DRAIN.md): driver, preflight receipts, the worker brief contract, collect, and batch
close stay there and stay loaded. The caller owns the whole batch exactly as in serial mode.

## Collision-free waves

For `-p`, use the driver's computed collision-free wave. Overlapping `touches`, `test_paths`, or
exact `exclusive_resources` IDs serialize, and missing path declarations run alone. Declare shared
root/config paths explicitly. SPEC names exclusive devices, databases, build outputs, and constrained
runners on every card that uses them; do not rely on a prose warning the driver cannot enforce.

## Generate wave inputs

After dispatch, generate briefs in one read-only call per feature:

```text
python <skills-root>/workflow-state.py briefs <repo-root> <feat> --compact
```

This validates outstanding assignments and the dispatch binding, includes their packets, and emits
one shared manifest with per-worker references. It persists nothing. `packets` remains available for
packet-only inspection; do not call it before `briefs`. Assemble each worker's necessary inputs once
using DRAIN's brief contract; a JSON pointer alone does not give a separate agent the referenced text.

## Assign, launch, and supervise

Assign the first (highest-priority) issue to the orchestrator by default. Launch every remaining
worker concurrently in one host operation, then immediately begin the orchestrator issue; the
four-issue cap includes the orchestrator. Retain each worker's host identifier beside its ledger
binding; later corrections and stops address that worker only through this handle. If the
orchestrator's next RED/GREEN action would itself occupy the turn past one bounded host wait
(a long verifier run or a wait on a host event) with no local safe work to fill the interval,
delegate that issue too and keep the orchestrator on supervision, evidence review, and
reconciliation. The orchestrator's issue follows the same ownership and evidence contract.

Until every worker closes, repeat a bounded supervision loop:

1. Keep one cursor per worker. Prefer host completion/attention events and bounded host waits:
   consume a completion notification when it re-invokes the turn, keep the blocking wait
   cursor-aware and time-bounded, and use a non-terminal status read for mid-run review. Mid-run
   review between events is opportunistic: one compact snapshot during the main turn's own safe
   work, never a cadence owed on every interval. Only a host without native events falls back to
   the snapshot cadence: one compact snapshot at the first meaningful RED/GREEN boundary after at
   least about 30 seconds, operationally after the first bounded host wait without an event,
   since the previous status call; if no boundary arrives, check by about one minute (every
   bounded wait thereafter). Consume an explicit attention/final event immediately without an extra
   status call.
   Check events against the packet, declared paths, first test, and verifier; silence alone is not
   drift.
2. Between checks, fill the bounded interval with one RED/GREEN action, evidence/ownership review
   for returned work, reconciliation preparation for this wave, or immutable-candidate verification/delivery preparation for a managed batch.
   Do not spend a remote call before every short local action.
3. If no safe work remains, use one cursor-aware host blocking wait of up to about one minute;
   a bare sleep observes nothing. Do not busy-poll, reread full worker history, or request
   periodic prose status.
4. When user feedback arrives mid-wave, locate the affected assignment first. Resolve
   repo-observable context gaps for the worker and send only the missing packet field, pointer,
   command, or evidence through the host's native worker message to the retained identifier.
   Sending does not imply consumption or that old actions stopped; judge the effect at that
   worker's next return or terminal state. Correct concrete scope/path/test drift promptly;
   interrupt, stop, and rebrief only when continuing would contaminate ownership. A new
   consequential choice returns to the caller.
5. Consume final results immediately and retain their compact outcomes in the current wave context,
   but do not partially collect the ledger. Do not redo the worker's task; once every worker is
   terminal, verify the combined evidence and ownership before the one wave commit.

The turn may end while the wave is open only when the host keeps dispatched workers running across
turns and redelivers their completion to this session. Reply with one mid-wave lead line
(`范围 tdd drain wave N（k issue）· 进行中 · 已回 x/y`) that the wave is still running;
ending the turn releases no file or resource ownership. A wave must close within one
supervising session's lifetime: worker host handles are session-local, so a session boundary
over an open wave forces adopt-or-revert reconciliation in [EDGE-CASES.md](EDGE-CASES.md).
Plan wave size and session pressure accordingly. Without a confirmed background path, keep
supervising in the foreground or stop every worker safely before ending the turn. A turn
re-invoked by a completion notification first consumes that terminal result per step 5, retaining
its compact outcome without partially collecting the ledger; only the one collect after every
worker is terminal closes the wave. The session itself never closes over an open wave: leave it
only after that collect, or after an escalated attention stop that first interrupts or stops
every worker, or through a handoff that records the open execution.

## Orchestrator write scope and the open-wave barrier

While workers remain, the orchestrator may write only its assigned issue's declared paths and its
own workflow artifacts. Shared state changes go through the owning script; `.scratch` is not an
unrestricted shared write area. Outside that scope, only read-only inspection or managed checks in
an already captured isolated candidate are allowed. Do not launch a live-tree batch suite or
shared-cache preflight; unassigned activity drifts fingerprints and blurs path ownership. The
[wave barrier](DRAIN.md#wave-barrier) owns why no next-wave input materialization, refill dispatch,
or managed capture can join an open wave. After reconciliation rerun `step` and generate the next
wave's inputs once, and dispatch the next wave as soon as the ledger closes.


For incremental batches, service `batch-run --background` and pending notification events at safe
boundaries. Deliveries and checks already bound to an immutable candidate can progress while the
main agent's implementation task remains unfinished. Request safe return before a new capture;
never claim the shared working tree is fixed while a wave is still writing.
