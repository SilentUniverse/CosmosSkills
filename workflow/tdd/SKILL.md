---
name: tdd
description: >-
  Use when implementing a named issue or feature test-first, running red-green-refactor, draining ready issues, or recording TDD evidence. Owns implementation and validation; substantial unresolved requirements route through spec, while unknown failures route through diagnose.
argument-hint: "Issue path, feature slug, -p, -all, -log, or nothing to drain all ready issues"
---

# Test-Driven Development

## Invocation

- `/tdd <issue-path>` — run only that issue. Read frontmatter `status:` and obey the guard below.
  Use a caller-supplied packet directly. Otherwise obtain the compact contract with
  `python <skills-root>/workflow-state.py packet <repo-root> <feat> <slug>`; use `python3` when
  `python` is absent. It includes required inputs and the newest retry, omitting prior Comments.
  If source/status/hash is observed stale, pause writes and return one attention event.
- Explicit bare `/tdd` — **drain (serial)**: every `ready` issue across `.scratch/`, one at a time,
  in dependency order. A caller or natural-language implementation request inherits only its named
  task; absence of an issue path does not authorize a repository-wide drain.
- `/tdd <feat>` — drain scoped to one feature's `issues/` directory.
- `/tdd -p [<feat>]` — **drain (parallel)**: up to four concurrent issues including the main agent's. The main agent normally owns the highest-priority issue, delegates the rest, and supervises the wave. Delegated output stays isolated while the critical slice remains visible. Declared collisions serialize; undeclared issues run alone. Worktree only on explicit request, and runner-driven session rotation: [DRAIN.md](DRAIN.md) plus [DRAIN-PARALLEL.md](DRAIN-PARALLEL.md).
- `/tdd -all` — run build + the whole suite now (§5); combines with any form above.
- `/tdd -log` — the verdict is a command's log file, not test runs: [LOG.md](LOG.md). Same mode when the user says this run drives a device and the result lands in a log file. Combines with any form above.
- Task-scoped entry without an issue: for one settled local behavior, keep outcome, constraints, and evidence inline
  and execute this loop without issue artifacts. Multi-slice or unresolved product work uses `/spec`
  first, then resumes here within the original request. Unknown failures use `/diagnose`.

### Drain mode

Load [DRAIN.md](DRAIN.md) only for an explicit batch; `-p` additionally loads
[DRAIN-PARALLEL.md](DRAIN-PARALLEL.md). Its driver owns enumeration, dependency order,
wave packets, receipts, recovery, and batch close. Serial is the default; `-p` enables independent
worker waves. Keep conversation summaries out of subsequent issue briefs.

### Status guard (issue-driven invocation)

| Status | Action |
| --- | --- |
| `ready` | **Autonomous mode** — skip "confirm with user" prompts; run unattended. |
| `done` | Verify/report existing completion. A requested behavior change routes to `/spec` for a redo; do not ask the user to edit status. Active-batch recovery follows DRAIN. |
| anything else | Inspect the invalid state; repair an unambiguous schema typo, otherwise report the exact ambiguity. Do not guess approval from status. |

Edge cases — prior `### 完成` on a `ready` issue, or `category: redo`/`fix` (parent-test fate): [EDGE-CASES.md](EDGE-CASES.md).

## Completion record

**Issue-based runs only.** When all AC pass, review this issue's owned diff against its AC, preserve other work, write the completion record, then close to `done`: **[COMPLETION-RECORD.md](COMPLETION-RECORD.md)**.

Submit through `/commit` only when the user requested it; then continue there after validation.

## Test philosophy

Tests verify behavior through public interfaces, not implementation details; expected values come from an independent spec/example — [tests.md](tests.md), [mocking.md](mocking.md). One test at a time (vertical slices), never batch all tests then all implementation.

## Workflow

### 1. Planning

Start from first principles about the approach. Use the project's domain glossary so test names and interface vocabulary match the project's language; respect ADRs in the area touched.

Use settled requirements as the contract; infer routine interface and test mechanics from the repo.
Ask only a new consequential decision. Shape a new seam with `/codebase-design` when needed.
Existing coverage first: [tests.md](tests.md) §Existing coverage. Inline runs use their stated
behavior/evidence contract; issue runs use 做什么/AC/验证设计 and the parent extract.

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

Write ONE test confirming ONE thing about the system: RED (test fails on the asserted behavior) → GREEN (minimal code passes). Proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior: RED (write next test, watch it fail) → GREEN (minimal code passes).

- One test at a time; an import/collection error is not RED
- Only enough code to pass the current test; don't anticipate future tests
- Keep tests focused on observable behavior

**What to run each cycle.** RED/GREEN runs execute only the test just written (`pytest path/test_x.py::test_y`).
Run the touched module's tests at slice completion; relevant refactors invalidate that evidence.
The full suite stays batch-level (§5). Reuse project commands. Cache only reusable adapters that
cannot be cheaply recovered from project configuration in `CODEBASE.md`'s `## Verifier commands`.

**Receipt conflict.** TDD never weakens aligned behavior or required proof to make a failure pass. Clear contract
invalidation appends the exact evidence, keeps the card `ready`, stops production-code writes, and
routes to `/spec` within this task; the caller resumes after repair or the required decision. An ambiguous main-agent case loads the blind
[classifier](../atk/RECEIPT-CONFLICT.md). A drain executor starts no nested review; any possible
receipt conflict takes the batch barrier in [DRAIN.md](DRAIN.md). A contract-preserving artifact fix returns directly to RED/GREEN without user realignment.

### 4. Refactor

After all tests pass: [refactoring.md](refactoring.md). Unexpected red exposing an `rg`-invisible invariant (hidden constraint/coupling) → persist it to the area's `CODEBASE.md` block (two-axis test per `/map`); no `CODEBASE.md` yet → note in `### 完成`. Run tests after each refactor step. **Never refactor while RED.**

### 5. Full-suite check

Scoped per-cycle tests (§3) can't see cross-module regressions. The full suite + build runs **automatically once per batch** (drain's last issue to `done`) and **manually** (`/tdd -all`). Run each command inline through the timeout/log supervisor; load only its compact result into context. Full procedure: **[FULL-SUITE.md](FULL-SUITE.md)**.
