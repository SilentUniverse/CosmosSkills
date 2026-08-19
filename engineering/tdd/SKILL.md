---
name: tdd
description: Test-driven development with red-green-refactor loop. Runs one issue, drains a feature's (or all) ready issues in dependency order (serially, or in parallel waves with -p), or interviews when asked without an issue. Use when user wants to build features or fix bugs using TDD, mentions "red-green-refactor", wants integration tests, or asks for test-first development.
argument-hint: "Issue path, feature slug, or nothing to drain all ready issues"
---

# Test-Driven Development

## Invocation

- `/tdd <issue-path>` — run that one issue. Read its frontmatter `status:` first (per [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd)) and obey the guard below. Fully visible, one slice.
- `/tdd` (bare) — **drain mode (serial)**: run *every* `ready` issue across `.scratch/`, one at a time, in dependency order, to completion. The dumb-but-legible batch path — no worktrees, all in the current session so you can watch each one.
- `/tdd <feat>` — drain mode scoped to one feature's `issues/` directory.
- `/tdd -p [<feat>]` — **drain mode (parallel)**: farm ready issues out to subagents (one per issue) so each issue's verbose output stays isolated and independent slices finish in parallel. Decoupled slices edit the shared tree directly; a worktree is used only when two in-flight issues would touch the same files. See [DRAIN.md](DRAIN.md).
- `/tdd --full` — run build + the whole suite now (the manual full-suite check, §5); combine with any form above.
- Natural-language ask without an issue (e.g. "write tests for the parser") — fall back to **interview mode** (jump to Workflow §1).

### Drain mode

Enumerate `ready` issues, topologically sort on `blocked_by`, run the batch through the
autonomous loop (§Workflow), then close with one full suite + build. Two paths: **serial** (default —
legible, one issue at a time) and **parallel** (`-p` — ready issues fan out to
subagents; decoupled slices edit in place, worktree only when they'd collide). Full algorithm,
subagent brief, and the edit-in-place-vs-worktree call: **[DRAIN.md](DRAIN.md)**.

### Status guard (issue-driven invocation)

| Status            | Action                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| `ready` | **Autonomous mode** — skip "confirm with user" prompts. Run the loop unattended.                    |
| `done`            | **Refuse.** Print: "this issue is `done`; create a redo issue or set `status:` back to `ready` first." Stop. |
| anything else     | Refuse with the same guidance.                                                                      |

Edge case — `status: ready` AND `## Comments` already contains a `### 完成` block from a prior run: pause and ask the user "(a) iterate on existing code, or (b) start over?" before proceeding. *(autonomous mode: (a), recorded in `### 完成`)*

Edge case — issue `category` is `redo` / `fix` (or filename matches `*-redo-*` / `*-fix-*`): the parent slice is named by the `refines:` frontmatter field (fall back to stripping the prefix, e.g. `05-redo-balance-api.md` → `02-balance-api.md`). Read the parent's `### 完成` block and list the test files it added. Show the user:

> "This redoes `02-balance-api.md`. That issue added these tests:
> - `tests/test_balance_rest.py` (4 cases)
>
> The new spec changes the API shape. These tests will likely break. Want me to (a) update them in place / (b) delete them and write fresh / (c) leave them and let red signals guide you?"

Wait for the user's choice before starting the red-green loop. This avoids leaving zombie tests after a redo. *(autonomous mode: (a) refines, (b) replaces; record the choice in `### 完成`)*

### Existing-test scan (before writing any new test)

Identify the project's test convention from `docs/agents/domain.md`. If not specified there, infer from project config files (`pytest.ini` / `pyproject.toml`, `package.json` test script, `build.gradle` `testOptions`, etc.) and ask the user to confirm — then suggest writing it into `domain.md` so future runs skip this step. *(autonomous mode: adopt the inferred convention, note it in `### 完成`)*

For each AC in the issue, find existing coverage. Drain `-p`: the brief carries the **tests-so-far manifest** — check AC against it, scan the filesystem only for what it can't show. Serial drain: earlier issues' `### 完成` blocks are already in context — check against them. Interactive: scan directly. Report covered vs uncovered briefly in chat; record covered ACs in the `### 完成` block's 跳过的 AC field.

## Completion record

**Issue-based runs only.** When all AC pass, run an adversarial review, check `git diff` traces to this issue's AC, set `status: done`, and append a `### 完成` block to `## Comments`. Full procedure + template: **[COMPLETION-RECORD.md](COMPLETION-RECORD.md)**.

Interview mode (no issue) writes none — run `/spec` afterward and mark the issue `done`. Standalone `/tdd` does **not** submit; use the Submit workflow named in `CLAUDE.md`.

## Test philosophy

Tests verify behavior through public interfaces, not implementation details; expected values come from an independent spec/example — see [tests.md](tests.md)
and [mocking.md](mocking.md). Write one test at a time (vertical slices), never batch all tests then
all implementation.

**Murphy before done.** Green only proves the cases you wrote tests for. Before marking done,
cover each chosen behavior's failure modes too — null/empty input, boundary values, error paths,
and where relevant concurrency/timeouts. Occam trims during dev (no speculative features, per the
cycle checklist); Murphy expands during verification — an untested failure path ships as a bug.

## Workflow

### 1. Planning

Start from first principles about the approach.

When exploring the codebase, use the project's domain glossary so that test names and interface vocabulary match the project's language, and respect ADRs in the area you're touching.

Before writing any code:

- [ ] Confirm with user what interface changes are needed *(autonomous mode: skip — the spec is the issue's 做什么/AC plus the PRD extract in `## 上级`)*
- [ ] Confirm with user which behaviors to test *(autonomous mode: skip — AC are the priority)*
- [ ] Shape deep modules + testable interfaces — run the `/codebase-design` skill for the deep-vs-shallow vocabulary and testability patterns
- [ ] List the behaviors to test (not implementation steps)
- [ ] Get user approval on the plan *(autonomous mode: skip)*

**Pre-issue statement (autonomous mode).** Before writing the first test, state in 2–3 lines: what this slice requires, which interface you'll shape, which behaviors you'll test first, and the biggest assumption it rests on. Don't wait for a reply — keep going. This is the user's cheapest point to catch a wrong understanding, before any code exists.

Ask: "What should the public interface look like? Which behaviors are most important to test?"

**You can't test everything.** Confirm with the user exactly which behaviors matter most. Focus testing effort on critical paths and complex logic, not every possible edge case.

### 2. Tracer Bullet

Write ONE test that confirms ONE thing about the system:

```
RED:   Write test for first behavior → test fails
GREEN: Write minimal code to pass → test passes
```

This is your tracer bullet - proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior:

```
RED:   Write next test → fails
GREEN: Minimal code to pass → passes
```

Rules:

- One test at a time
- Run the new test and watch it fail on the asserted behavior before writing implementation — an import/collection error is not RED
- Only enough code to pass current test
- Don't anticipate future tests
- Keep tests focused on observable behavior

**What to run each cycle.** RED/GREEN runs execute only the test you just wrote (`pytest path/test_x.py::test_y`). The touched module's tests run once per slice, at GREEN completion before refactor. The full suite stays batch-level (§5). Cache scoped-test / module-test / build commands in `docs/agents/domain.md`.

### 4. Refactor

After all tests pass, look for [refactor candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules (move complexity behind simple interfaces)
- [ ] Apply SOLID principles where natural
- [ ] Consider what new code reveals about existing code
- [ ] Unexpected red exposed a `rg`-invisible invariant (hidden constraint/coupling)? Persist it to the area's `CODEBASE.md` block (two-axis test per `/zoom-out`) and report; no `CODEBASE.md` yet → note in `### 完成` instead
- [ ] Run tests after each refactor step

**Never refactor while RED.** Get to GREEN first.

### 5. Full-suite check

Scoped per-cycle tests (§3) can't see cross-module regressions. The full suite + build runs
**automatically once per batch** (when drain takes its last issue to `done`) and **manually**
(`/tdd --full`). Both run in a subagent that keeps verbose output out of context. Full procedure:
**[FULL-SUITE.md](FULL-SUITE.md)**.

## Checklist Per Cycle

```
[ ] Test describes behavior, not implementation
[ ] Test uses public interface only
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```
