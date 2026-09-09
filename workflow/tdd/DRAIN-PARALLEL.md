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
python3 <skills-root>/workflow-state.py briefs <repo-root> <feat> --compact
```

This validates outstanding assignments and the dispatch binding, includes their packets, and emits
one shared manifest with per-worker references. It persists nothing. `packets` remains available for
packet-only inspection; do not call it before `briefs`. Assemble each worker's necessary inputs once
using DRAIN's brief contract; a JSON pointer alone does not give a separate agent the referenced text.

## Assign, launch, and supervise

Assign the first (highest-priority) issue to the orchestrator by default. Launch every remaining
worker concurrently in one host operation, then immediately begin the orchestrator issue; the
four-issue cap includes the orchestrator. If its next action cannot yield within the supervision
interval, delegate that issue too and keep the orchestrator on supervision, evidence review, and
reconciliation. The orchestrator's issue follows the same ownership and evidence contract.

Until every worker closes, repeat a bounded supervision loop:

1. Keep one cursor per worker. Use host completion/attention events when available. Otherwise consume
   one compact event snapshot at the first meaningful RED/GREEN
   boundary after at least about 30 seconds since the previous status call; if no boundary arrives,
   check by about one minute. Consume an explicit attention/final event immediately without an
   extra status call. Check events against the packet, declared paths, first test, and verifier;
   silence alone is not drift.
2. Between checks, fill the bounded interval with one RED/GREEN action, evidence/ownership review
   for returned work, reconciliation preparation for this wave, or other read-only close-out work.
   Do not spend a remote call before every short local action.
3. If no safe work remains, use one cursor-aware wait of up to about one minute. Do not busy-poll,
   reread full worker history, or request periodic prose status.
4. Resolve repo-observable context gaps for the worker and send only the missing packet field,
   pointer, command, or evidence. Correct concrete scope/path/test drift promptly; interrupt and
   rebrief only when continuing would contaminate ownership. A new consequential choice returns to
   the caller.
5. Consume final results immediately and retain their compact outcomes in the current wave context,
   but do not partially collect the ledger. Do not redo the worker's task; once every worker is
   terminal, verify the combined evidence and ownership before the one wave commit.

## Orchestrator write scope and the open-wave barrier

While workers remain, the orchestrator may write only its assigned issue's declared paths and its
own workflow artifacts. Shared state changes go through the owning script; `.scratch` is not an
unrestricted shared write area. Outside that scope, only read-only inspection is allowed. Do not launch the batch suite
or shared-cache preflight. Unassigned activity drifts fingerprints and blurs path ownership. Do not
materialize next-wave packets, briefs, or manifests while the wave is open; they would be stale by
construction. After reconciliation rerun `step` and generate the next wave's inputs once. Do not
dispatch a refill either: one open wave across all features is the reconciliation contract because
every worker diffs against the same recorded baseline. Dispatch
the next wave as soon as the ledger closes. This fixed shared-tree barrier may leave a short-lived
free slot, but prevents a refill from inheriting moving sibling edits and turning ownership review
into an ambiguous multi-baseline merge.
