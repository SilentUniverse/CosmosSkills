---
name: correct
description: >-
  Use only when the user invokes /correct, or a correction repeats a mistake agents already made in this project. Groups repeated agent mistakes into classes and makes each impossible at the highest level that works: architecture, types, a lint or check whose error names the fix, a test, and prose last.
argument-hint: "[mistake or area] (optional; no args = mine recent history)"
disable-model-invocation: true
---

# Correct

Change the project so the next agent cannot repeat the mistake. Assume every contributor is an
agent that sees only the files it opened, copies the nearest example, and takes the shortest path
that compiles. A change that looks right from one file must be right for the whole repository.

## 1. Find mistake classes

With a named mistake, start from it. Otherwise read recent commits and reverts, review comments,
the project's agent instruction files, user corrections in this session, and comments that justify
a workaround (timers, sleeps, retries, suppressions). For a review of delegated or unattended work,
also read `.scratch/acceptance-log.md`, each `.scratch/*/DECISIONS.md` (reverts, stops, overturned
`待确认`) and `ACCEPTANCE.md` (未通过 rows, disagreements with the independent review), and classify
every 返工 or 回滚 cause.

Group mistakes into classes. A first occurrence gets an in-place fix and one line in
`.scratch/acceptance-log.md`: `<date> | <task> | 返工 | <class> | <pointer>`. It creates no rule.
The line records a mistake class, not a conversation turn, so it does not conflict with `CLAUDE.md`
§5 "never log a turn". When the log shows a class a second time, move it up: architecture → types →
check → test → a rule line in the project's `AGENTS.md`.

## 2. Fix each class at the highest level that works

1. **Architecture.** One owner per piece of state, one supported way per task. Hide internals so
   the wrong import fails; replace hand-synced lists with one source of truth; delete the old way
   and dead code an agent would copy.
2. **Types.** Make the bad state unrepresentable.
3. **A check whose error names the fix.** A lint, dependency rule or script that names the file,
   type or function to use instead. Where the pattern is already common, fail only on new
   occurrences, then migrate the old ones.
4. **A behavior test.** Fix or delete tests that pass when the behavior breaks or fail when only
   internals change ([test quality](../tdd/tests.md)).
5. **Prose last** (a rule line in `AGENTS.md`), only for judgment calls nothing can check. Nothing
   fails when an agent skips it.

Use the project's existing linters, type checker and test runner; add a tool only when none covers
the class (`CLAUDE.md` §3 ladder). An exception lives on the offending line with a reason and an
owner.

## 3. Prove and record

- Prove each new check fails on a real past instance of the mistake (the reverted commit, the
  reviewed diff, or a minimal reproduction), then passes on the fixed code. A check never seen to
  fail is not evidence.
- Run the check through the same command locally and, where the project has CI, in CI.
- Keep a rule table in the project's agent instruction file (`AGENTS.md` or its equivalent): each
  rule and what enforces it. A repeat of a rule that is listed but unenforced moves up a level in
  the same change. Drop a rule once its mistake can no longer happen; when the acceptance
  record shows its class stopped recurring, propose demoting it and let the user decide.

An audit-only request returns the classes and proposed levels without edits. Otherwise each class
is its own reviewable change; submission follows `/pr` when requested.

End with each class, its evidence, the level chosen and why a higher level did not work, the proof
that the check fails on the past mistake, and classes left at prose.
