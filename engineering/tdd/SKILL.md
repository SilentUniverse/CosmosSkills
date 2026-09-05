---
name: tdd
description: Test-driven development with red-green-refactor loop. Runs one issue path, or drains ready issues (serial, or `-p` parallel waves). Use when the user names an issue/feature to implement test-first, or says "red-green-refactor" / `--log`. A small settled requirement can run inline; substantial planning routes through `/spec` in the same task. A failure without a known cause is `/diagnose`, not this skill.
argument-hint: "Issue path, feature slug, -p, --full, --log, or nothing to drain all ready issues"
---

# Test-Driven Development

## Invocation

- `/tdd <issue-path>` — run that one issue. Read its frontmatter `status:` first (per [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd)) and obey the guard. One slice, fully visible. For a minimal projection instead of the full card, run `python <skills-root>/workflow-state.py packet <repo-root> <feat> <slug>` (`python3` only when `python` is absent); it prints status, `blocked_by`, `test_paths`, the `## 相关面` context pointers, contract digest, and the source path without writing anything.
- `/tdd` (bare) — **drain (serial)**: every `ready` issue across `.scratch/`, one at a time, dependency order, to completion. The dumb-but-legible batch path: no worktrees; watch each one in this session.
- `/tdd <feat>` — drain scoped to one feature's `issues/` directory.
- `/tdd -p [<feat>]` — **drain (parallel)**: ready issues fan out to subagents (one per issue, ≤4 in flight); each issue's verbose output stays isolated, independent slices finish in parallel. Wave rules: declared collisions serialize, undeclared issues run alone. Worktree only on explicit request, and runner-driven session rotation: [DRAIN.md](DRAIN.md).
- `/tdd --full` — run build + the whole suite now (§5); combines with any form above.
- `/tdd --log` — the verdict is a command's log file, not test runs: [LOG.md](LOG.md). Same mode when the user says this run drives a device and the result lands in a log file. Combines with any form above.
- No issue path: for one settled local behavior, keep outcome, constraints, and evidence inline
  and execute this loop without issue artifacts. Multi-slice or unresolved product work uses `/spec`
  first, then resumes here within the original request. Unknown failures use `/diagnose`.

### Drain mode

Enumerate `ready` issues, topologically sort on `blocked_by`, run the batch through the autonomous loop (§Workflow), close with one full suite + build. Two paths: **serial** (default: legible, one at a time) and **parallel** (`-p`: subagent waves). Batches keep a bounded context per issue — the accumulated conversation never becomes the context carrier ([DRAIN.md](DRAIN.md) context budget). Full algorithm, subagent brief, edit-in-place-vs-worktree call: **[DRAIN.md](DRAIN.md)**.

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

**What to run each cycle.** RED/GREEN runs execute only the test just written (`pytest path/test_x.py::test_y`). The touched module's tests run once per slice, at GREEN completion before refactor. The full suite stays batch-level (§5). Cache scoped-test / module-test / build commands in `CODEBASE.md`'s `## Verifier commands` zone, created lazily per the ARTIFACT-FORMAT stub when absent.

**Receipt conflict.** TDD never weakens aligned behavior or required proof to make a failure pass. Clear contract
invalidation appends the exact evidence, keeps the card `ready`, stops production-code writes, and
routes to `/spec` within this task; the caller resumes after repair or the required decision. An ambiguous main-agent case loads the blind
[classifier](../atk/RECEIPT-CONFLICT.md). A drain executor starts no nested review; any possible
receipt conflict takes the batch barrier in [DRAIN.md](DRAIN.md). A contract-preserving artifact fix returns directly to RED/GREEN without user realignment.

### 4. Refactor

After all tests pass: [refactoring.md](refactoring.md). Unexpected red exposing an `rg`-invisible invariant (hidden constraint/coupling) → persist it to the area's `CODEBASE.md` block (two-axis test per `/map`); no `CODEBASE.md` yet → note in `### 完成`. Run tests after each refactor step. **Never refactor while RED.**

### 5. Full-suite check

Scoped per-cycle tests (§3) can't see cross-module regressions. The full suite + build runs **automatically once per batch** (drain's last issue to `done`) and **manually** (`/tdd --full`). Run each command inline through the timeout/log supervisor; load only its compact result into context. Full procedure: **[FULL-SUITE.md](FULL-SUITE.md)**.
