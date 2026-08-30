---
name: tdd
description: Test-driven development with red-green-refactor loop. Runs one issue path, or drains ready issues (serial, or `-p` parallel waves). Use when the user names an issue/feature to implement test-first, or says "red-green-refactor" / `--log`. A bare requirement with no issue is `/spec`. A failure without a known cause is `/diagnose`, not this skill.
argument-hint: "Issue path, feature slug, -p, --full, --log, or nothing to drain all ready issues"
---

# Test-Driven Development

## Invocation

- `/tdd <issue-path>` — run that one issue. Read its frontmatter `status:` first (per [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd)) and obey the guard. One slice, fully visible.
- `/tdd` (bare) — **drain (serial)**: every `ready` issue across `.scratch/`, one at a time, dependency order, to completion. The dumb-but-legible batch path: no worktrees; watch each one in this session.
- `/tdd <feat>` — drain scoped to one feature's `issues/` directory.
- `/tdd -p [<feat>]` — **drain (parallel)**: ready issues fan out to subagents (one per issue, ≤4 in flight); each issue's verbose output stays isolated, independent slices finish in parallel. Wave rules: declared collisions serialize, undeclared issues run alone. Worktree only on explicit request, and runner-driven session rotation: [DRAIN.md](DRAIN.md).
- `/tdd --full` — run build + the whole suite now (§5); combines with any form above.
- `/tdd --log` — the verdict is a command's log file, not test runs: [LOG.md](LOG.md). Same mode when the user says this run drives a device and the result lands in a log file. Combines with any form above.
- Natural-language ask without an issue path — stop; tell the user to `/spec` first. Do not interview, do not write tests.

### Drain mode

Enumerate `ready` issues, topologically sort on `blocked_by`, run the batch through the autonomous loop (§Workflow), close with one full suite + build. Two paths: **serial** (default: legible, one at a time) and **parallel** (`-p`: subagent waves). Batches keep a bounded context per issue — the accumulated conversation never becomes the context carrier ([DRAIN.md](DRAIN.md) context budget). Full algorithm, subagent brief, edit-in-place-vs-worktree call: **[DRAIN.md](DRAIN.md)**.

### Status guard (issue-driven invocation)

| Status | Action |
| --- | --- |
| `ready` | **Autonomous mode** — skip "confirm with user" prompts; run unattended. |
| `done` | **Refuse.** Print: "this issue is `done`; create a redo issue or set `status:` back to `ready` first." |
| anything else | Refuse with the same guidance. |

Edge cases — prior `### 完成` on a `ready` issue, or `category: redo`/`fix` (parent-test fate): [EDGE-CASES.md](EDGE-CASES.md).

## Completion record

**Issue-based runs only.** When all AC pass, run an adversarial review, check `git diff` traces to this issue's AC, set `status: done`, append a `### 完成` block to `## Comments`. Procedure + template (incl. the Murphy failure-mode check): **[COMPLETION-RECORD.md](COMPLETION-RECORD.md)**.

Standalone `/tdd` does **not** submit; use the Submit workflow named in `CLAUDE.md`.

## Test philosophy

Tests verify behavior through public interfaces, not implementation details; expected values come from an independent spec/example — [tests.md](tests.md), [mocking.md](mocking.md). One test at a time (vertical slices), never batch all tests then all implementation.

## Workflow

### 1. Planning

Start from first principles about the approach. Use the project's domain glossary so test names and interface vocabulary match the project's language; respect ADRs in the area touched.

Before writing any code: list the behaviors to test (not implementation steps); confirm interface changes, behaviors, and plan with the user *(autonomous mode: skip confirms — the aligned issue's 做什么/AC/验证设计 plus the PRD extract in `## 上级` are the contract)*; shape deep modules and testable interfaces; `/codebase-design` only when a new seam is in play or the interface is unclear. Existing coverage first: [tests.md](tests.md) §Existing coverage.

**Pre-issue statement (autonomous mode).** Before the first edit, recompute the recorded environment
fingerprint. A standalone run replays every referenced P# without setup. A drain run may reuse an
exact orchestrator-supplied `receipt-hit:<key>` from [DRAIN.md](DRAIN.md); a unique tuple replays
normally, while drift leaves the card ready. Subagents never write the receipt. Then state in 2–3 lines:
what this slice requires, which interface you'll shape, which behaviors you'll test first, how the
issue says to prove them, and the biggest assumption. Don't wait for a reply. A fingerprint drift or
failed P# leaves the issue `ready`: append exact expected/observed evidence and report red. Never
install, upgrade, start an undeclared dependency, or substitute a verifier at execution time. If an
AC→evidence mapping cannot run, use the same red path; do not silently redesign an aligned card.

### 2. Tracer Bullet

Write ONE test confirming ONE thing about the system: RED (test fails on the asserted behavior) → GREEN (minimal code passes). Proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior: RED (write next test, watch it fail) → GREEN (minimal code passes).

- One test at a time; an import/collection error is not RED
- Only enough code to pass the current test; don't anticipate future tests
- Keep tests focused on observable behavior

**What to run each cycle.** RED/GREEN runs execute only the test just written (`pytest path/test_x.py::test_y`). The touched module's tests run once per slice, at GREEN completion before refactor. The full suite stays batch-level (§5). Cache scoped-test / module-test / build commands in `docs/agents/domain.md`.

### 4. Refactor

After all tests pass: [refactoring.md](refactoring.md). Unexpected red exposing an `rg`-invisible invariant (hidden constraint/coupling) → persist it to the area's `CODEBASE.md` block (two-axis test per `/map`); no `CODEBASE.md` yet → note in `### 完成`. Run tests after each refactor step. **Never refactor while RED.**

### 5. Full-suite check

Scoped per-cycle tests (§3) can't see cross-module regressions. The full suite + build runs **automatically once per batch** (drain's last issue to `done`) and **manually** (`/tdd --full`). Both run in a subagent that keeps verbose output out of context. Full procedure: **[FULL-SUITE.md](FULL-SUITE.md)**.
