---
name: tdd
description: >-
  Use when implementing a named issue or feature test-first, running red-green-refactor, draining ready issues, or recording TDD evidence. Owns implementation and validation; substantial unresolved requirements route through spec, while unknown failures route through diagnose.
argument-hint: "Issue path, feature slug, -s, -p, -all, -log, or nothing to continue the current goal"
---

# Test-Driven Development

## Invocation

- `/tdd <issue-path>` — run that issue after the status/review guard.
  Use a caller-supplied packet and execution ID directly. Otherwise, after the status/review guard,
  run `python <skills-root>/workflow-state.py start <repo-root> <feat> <slug>` (`python3` when
  `python` is absent). This admits the card and returns its packet, execution ID and baseline
  digest. `packet` remains a read-only inspection command. If source/status/hash is observed
  stale, pause writes and return one attention event; never redispatch or refresh a worker's input silently.
- Bare `/tdd` continues the current accepted goal. Without a unique current scope, show the compact
  candidate scopes before dispatch. Repository-wide drain requires an explicit whole-repository
  request; missing parameters never enlarge authorization.
- `/tdd <feat>` — drain scoped to one feature's `issues/` directory, parallel permission by default.
- `/tdd -p [<feat>]` — compatibility alias for the default parallel drain.
- `/tdd -s [<feat>]` — **force serial**: one issue at a time, no worker waves.
- Parallel is a permission, not an obligation. With one eligible task the main agent runs it
  directly; with several independent declared tasks it dispatches native-subagent waves of at most
  four concurrent issues including the main agent's. The main agent normally owns the
  highest-priority issue and supervises delegated work. Declared collisions serialize; undeclared
  issues run alone; workers never nest a workflow. Rules: [DRAIN.md](DRAIN.md) plus
  [DRAIN-PARALLEL.md](DRAIN-PARALLEL.md).
- `/tdd -all` — run build + the whole suite now (§5); combines with any form above. During an
  open `-p` wave it defers to the wave collect and never launches a live-tree suite against
  open workers.
- `/tdd -log` — the verdict is a command's log file, not test runs: [LOG.md](LOG.md). Also applies to device runs judged by a log; combines with other forms.
- Task-scoped entry without an issue: keep a settled outcome, constraints, authorization, and proof
  inline when no queue, delegation, dependency, or contract-history consumer needs a card. File count
  does not decide this; `/spec`'s routing conditions do — a settled small task lands here directly,
  a new public contract or measurement-semantics change routes to `/spec` first. A requested plan or consequential unresolved choice uses `/spec`, then resumes
  within the existing authorization; only unresolved material choices hold dependent work. Unknown failures use `/diagnose`.
  Before editing, inspect relevant ready work and open assignments through `workflow-state.py survey`;
  use the existing card when it owns the work, and coordinate any active execution before touching its scope.

### Drain mode

Load [DRAIN.md](DRAIN.md) only for an explicit batch; wave dispatch additionally loads
[DRAIN-PARALLEL.md](DRAIN-PARALLEL.md) (`-s` stays serial). Its driver owns enumeration, dependency order,
wave packets, receipts, recovery, and batch close. Parallel permission is the default: several
independent ready cards may run as a worker wave, while a single eligible card or `-s` keeps the
main agent on the serial path. Keep conversation summaries out of subsequent issue briefs.
When changing an external runner or provider adapter, load [SESSION-REUSE.md](SESSION-REUSE.md).

### Status guard (issue-driven invocation)

Honor the request's accepted scope and any explicit pending plan review. A user-issued `/tdd`
accepts its targeted plan; an automatic handoff carries the user's implementation authorization.
`ready` records engineering readiness, not human product acceptance.

| Status | Action |
| --- | --- |
| `ready` | Once the review checkpoint is satisfied, run autonomously without repeated confirmation. |
| `done` | Verify/report existing completion. A requested behavior change routes to `/spec` for a redo; do not ask the user to edit status. Active-batch recovery follows DRAIN. |
| pending | Resolve the recorded engineering readiness gap; keep human decision dependencies separate. |

Unknown statuses are invalid; repair an unambiguous schema typo or report the ambiguity.

Edge cases — prior `### 完成` on a `ready` issue, or `category: redo`/`fix` (parent-test fate): [EDGE-CASES.md](EDGE-CASES.md).

## Completion record

Managed batches load [BATCH-FORMAT.md](BATCH-FORMAT.md) for dispatch and background checks;
review boundaries load [BATCH-REVIEW.md](BATCH-REVIEW.md) and managed close loads
[BATCH-PROOF.md](BATCH-PROOF.md). Follow its projected action at safe boundaries; independent work
can continue during human review.

**Issue-based runs only.** When all AC pass, review this issue's owned diff against its AC, preserve other work, write the completion record, then close to `done`: **[COMPLETION-RECORD.md](COMPLETION-RECORD.md)**.

Use TIDY at delivery boundaries for released temporary files; preserve tests and useful experience.
Submit through `/pr` only when requested; continue there after validation.

## Test philosophy

Test public behavior against independent expectations; apply [test quality](tests.md) throughout
planning, implementation and review. Screenshots, agent self-reports and ad-hoc probe scripts
never substitute for required acceptance.
Load [mocking.md](mocking.md) only when a test needs mocks.
Complete one RED/GREEN slice before writing the next test. Only UI behavior loads [UI-TESTING.md](UI-TESTING.md).

## Workflow

### 1. Planning

Start from first principles about the approach. Use the project's domain glossary so test names and interface vocabulary match the project's language; respect ADRs in the area touched.

Use settled requirements as the contract; infer routine interface and test mechanics from the repo.
Ask only a new consequential decision. Shape a new seam with `/codebase-design` when needed.
Check existing coverage first. Inline runs use their stated
behavior/evidence contract; issue runs use 做什么/AC/验证设计 and the parent extract.

Update and replay affected existing drivers and scenario instructions in the same slice.
Use `/verify` only when missing or drifted run, drive or observation tools block verification.

Repeated follow-up patches landing on the same module are a design signal: stop patching and
re-derive the design from the requirements; propose the re-derivation instead of the next patch.

**Pre-issue statement (autonomous mode).** Before the first edit, recompute the recorded environment
fingerprint. Replay the issue’s referenced P#; reuse a just-observed identical check in this task if its
action, cwd, and fingerprint are unchanged. A drain run may reuse an
exact orchestrator-supplied `receipt-hit:<key>` from [DRAIN.md](DRAIN.md); a unique tuple replays
normally, while drift leaves the card ready. Subagents never write the receipt. Then state in 2–3 lines:
what this slice requires, which interface you'll shape, which behaviors you'll test first, how the
issue says to prove them, and the biggest assumption. Don't wait for a reply. A fingerprint drift or
failed P# leaves the issue `ready`: record expected/observed evidence. The caller restores declared
setup or repairs a stale environment record outside the behavior wave, replays P#, then resumes.
Ask only if that repair needs new authority or changes product/dependency choices. Keep production
writes paused until readiness passes; never silently replace the required verifier.

### 2. Tracer Bullet

Complete the behavior evidence, not a test count: locate the existing tests for the behavior
this slice changes before writing any. An already-failing case is this slice's RED; run it
as-is. Coverage that already pins the behavior needs verification only, not an equivalent case.
For a real gap, extend an existing scenario or its parameters first, then add one independent
case protecting a failure mode no current test covers. The tracer proves the path works
end-to-end.

### 3. Incremental Loop

For each remaining behavior: RED (write or extend the one test that pins it, watch it fail) →
GREEN (minimal code passes).

- One case at a time; an import/collection error is not RED
- Only enough code to pass the current test; don't anticipate future tests
- Keep tests focused on observable behavior
- No explanatory comments; place a surviving contract or reason at the interface a human reads,
  not beside implementation the code already shows

**What to run each cycle.** RED/GREEN runs execute only the case driving this cycle, written or
reused (`pytest path/test_x.py::test_y`).
Run the touched module's tests at slice completion; relevant refactors invalidate that evidence.
The full suite stays batch-level (§5). Reuse project commands. Cache only reusable adapters that
cannot be cheaply recovered from project configuration in `CODEBASE.md`'s `## Verifier commands`.

**Receipt conflict.** TDD never weakens aligned behavior or required proof to make a failure pass. Clear contract
invalidation appends the exact evidence, keeps the card `ready`, stops production-code writes, and
routes to `/spec` within this task; the caller resumes after repair or the required decision. An ambiguous main-agent case loads the blind
[classifier](../atk/RECEIPT-CONFLICT.md). A drain executor starts no nested review; any possible
receipt conflict takes the batch barrier in [DRAIN.md](DRAIN.md). A contract-preserving artifact fix returns directly to RED/GREEN without user realignment.

### 4. Refactor

After all tests pass: [refactoring.md](refactoring.md). Persist a verified, hard-to-recover invariant
to the relevant existing knowledge surface under `/map`'s two-axis test; link its code/test evidence.
Knowledge retention does not require an issue completion. If no such surface exists, establish only
the needed entry with a retrieval path; do not inventory the whole repository to retain one fact.
Keep transient hypotheses in the current task or handoff. Behavior-preserving refactors reuse
the relevant existing regressions as the before/after check; do not manufacture a RED for form.
Run affected tests after refactoring; **never refactor while RED**.

When test cost grows or shared checks need scheduling, apply [test policy](../TEST-POLICY.md).
Review changed tests against the same test quality criteria; shared checks remain parent-owned.

### 5. Full-suite check

Each delivery candidate needs its required combined checks and applicable suite/build; final evidence
must match the final candidate. Reuse valid evidence and recheck relevant changes. `/tdd -all` runs
the whole suite now. Use the timeout/log supervisor, nonblocking long execution and compact output:
**[FULL-SUITE.md](FULL-SUITE.md)**.
