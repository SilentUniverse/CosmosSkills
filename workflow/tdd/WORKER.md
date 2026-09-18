# Worker entry (`-p` delegated issues)

You are one delegated worker inside a parallel drain wave. This file is your complete execution
entry; the caller's brief supplied your packet, execution ID, and any `receipt-hit:<key>` token.
Wave driving, supervision, collect and recovery belong to the orchestrator in
[DRAIN.md](DRAIN.md); you do not own them. Do not invoke `/tdd`, start drain mode, or load that
file for execution rules. No nested agents.
Use `python` for workflow scripts; `python3` only when `python` is absent.

An assigned schema-2/3 batch branches here, before execution: development feedback runs through
`check-local` and the controller's continuation protocol in [BATCH-FORMAT.md](BATCH-FORMAT.md),
not this file's pytest loop; local green never closes the card. Every other packet continues
below.

## Pre-issue statement

- Use the caller-supplied packet and execution ID directly; never run
  `workflow-state.py start` and do not regenerate the packet.
- Before the first edit, recompute the recorded environment fingerprint and replay the issue's
  referenced P#; reuse a just-observed identical check when its action, cwd, and fingerprint are
  unchanged. An orchestrator-supplied `receipt-hit:<key>` whose tuple, fingerprint, and profile
  match replaces the replay. Drift or a failed replay leaves the card `ready` with expected/observed
  evidence: pause production writes and return one attention event; never silently refresh the
  contract or substitute weaker proof.
- State in 2–3 lines what this slice requires, the interface you will shape, the behaviors you will
  test first, how the issue says to prove them, and the biggest assumption. Do not wait for a reply.
- The packet's `retry_summary` counts prior red/blocked attempts on this card. The next remedy
  must differ materially from those attempts; a repeated identical failure is an attention
  event, not another try.

## RED/GREEN loop

- Complete the behavior evidence, not a test count: locate existing coverage for each behavior
  first. An already-failing case is this slice's RED; run it as-is; coverage that pins the
  behavior verifies without an equivalent case; extend an existing scenario or its parameters
  before adding an independent one.
- One case at a time: RED (fails on the asserted behavior) → GREEN (minimal code passes); an
  import/collection error is not RED. Run only the case driving each cycle, written or reused
  (`pytest path/test_x.py::test_y`), and the touched module's tests at slice completion. The full
  suite and build are batch-level obligations owned by the orchestrator; never launch them.
- Test quality: [tests.md](tests.md); load [mocking.md](mocking.md) only when a test needs mocks.
  An inherited `-log` replaces the test loop with the recorded control action and log predicate per
  [LOG.md](LOG.md).
- Never weaken aligned behavior or required proof to make a failure pass. A clear contract
  invalidation stops production-code writes and returns `conflict`; start no nested review; the
  batch barrier in [DRAIN.md](DRAIN.md) owns classification. A contract-preserving artifact fix
  returns directly to RED/GREEN.

## Completion and return

- When all AC pass: review this issue's owned diff against its AC (preserve user changes and other
  workers' hunks), append new test files within admitted `touches` to `test_paths`, then write the
  completion record and close with your execution ID per
  [COMPLETION-RECORD.md](COMPLETION-RECORD.md):
  `python <skills-root>/workflow-state.py close <repo-root> <feat> <slug> --execution <id>`.
  An assigned schema-2/3 batch does not close the card itself; its controller writes the
  managed-proof completion ([BATCH-PROOF.md](BATCH-PROOF.md)).
- Return one terminal outcome, then stop; no polling, status prose, or follow-up writes. The
  four values and their evidence shapes are owned by DRAIN.md's worker result table; in brief:
  `green` ≤8 compact lines (P#/fingerprint verdict, completion/receipt pointers, only unexpected
  changed paths, new test ownership, non-derivable caveats; card is `done`); `red` failing cases,
  trimmed error, attempted remedy, confirmed facts, next action (retain `ready`); `blocked` the
  exact unavailable condition or needed decision, attempted safe alternatives where useful,
  completed independent work (retain `ready`); `conflict` the failing command/output plus the
  precise contract clause it invalidates; append evidence (retain `ready`, return to `/spec`).
- Only a new consequential choice returns to the caller as an attention event; ask nothing the
  packet, repository, or recorded decisions can answer.
