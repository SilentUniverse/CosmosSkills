# Drain mode

Reached from bare `/tdd`, `/tdd <feat>`, or `/tdd -p [<feat>]`. Runs a whole
batch of `ready` issues to completion in dependency order. Two paths — serial
(default, legible) and parallel (fast). Pick by the flag; the enumeration and the batch
close are shared.

## Shared: enumerate the batch

1. Enumerate candidates: bare / `-p` scans `.scratch/*/issues/*.md` (top level, never
   `archive/`); a `<feat>` argument scans only `.scratch/<feat>/issues/*.md`. Read each one's
   `status:` and `blocked_by:` in one `rg '^(status|blocked_by):' -A2 <files>` pass;
   `yq --front-matter=extract` only as fallback for lists longer than `-A2`.
2. Keep only `status: ready`. Topologically sort on `blocked_by` so every issue runs
   after its blockers. Skip (don't fail) any issue still blocked by an unfinished issue — report
   it as deferred at the end.

## Shared: blocked 纪律

Issues have no `blocked` state — blocked is a **report classification**. A report may call an
issue blocked only when all three hold:

1. **Specific condition** — the exact command, the exact error, what exactly is missing
   (environment, dependency, access).
2. **Survived one approach switch** — the same condition persisted after a *different* angle was
   tried (CLAUDE.md §5 anti-thrash), not after one identical retry.
3. **Everything outside the blocked path is green** — hard, slow, or partly unclear is red with a
   note, not blocked.

## Serial path (default: bare `/tdd`, `/tdd <feat>`)

Run each issue, **one at a time**, through the autonomous-mode loop (SKILL.md §Workflow), all in
the current session so you can watch each one. No worktrees, no parallel subagents — deliberately
the dumb-but-legible path.

Per-issue gate: mark `status: done` only if build + the touched module's **scoped** tests pass
(not the whole suite); on failure leave it `ready`, note why in `## Comments`, and
**continue** to the next (a red issue doesn't abort the drain unless others depend on it).

## Parallel path (`/tdd -p [<feat>]`)

`-p` farms the ready issues out to **subagents** instead of running them inline. The point is
context isolation: each issue's verbose red-green output stays in its own window and never floods
the main session, and independent slices finish in parallel. Same DAG, same per-issue gate — `-p`
only adds two per-issue judgements: **hand this issue to a subagent, and does it need its own
worktree?**

Loop until the ready set is empty:

1. **Compute the wave.** From the remaining `ready` issues, take every one whose blockers
   are all `done`. These have no ordering constraint between them.
2. **Fan out — one subagent per issue, dispatched in a single turn.** Before dispatch, record the
   wave baseline (`git status --porcelain` output). Each `general-purpose` subagent
   runs the full autonomous red-green loop for its issue. `--log` drain: one issue per wave.
   Other coupling comes from `touches:` overlap
   (absent → judge from 做什么/AC):
   - **Disjoint → edit in place.** Subagents edit the shared tree directly.
   - **Overlapping → serialize into successive waves.** Worktree (`tdd/<NN>-<slug>`) only to
     deliberately parallelize overlapping slices; merge back in dependency order
     (`/merge-conflicts` for any conflict).

   The brief must be self-contained (it can't see this conversation):
   - **Invoke `/tdd <issue-path>`** (add `--log` when the drain was started with `--log`) —
     this loads the full workflow (status guard, existing-test scan, red-green-refactor
     discipline, Murphy check, completion record). The issue is `ready` → autonomous mode:
     skip all "confirm with user" prompts.
   - The issue is self-contained — no PRD attach — plus scoped-test + build commands from
     `docs/agents/domain.md` and the domain glossary pointer.
   - The **tests-so-far manifest** (earlier waves' 新增测试): don't write tests it already covers —
     report duplicates instead.
   - Report back **only** by outcome, in this fixed shape — a free-form reply is not a result:
     - **`result: green`** → which tests it added (files + case counts) + scoped pass tally. The
       subagent writes the completion record and sets `status: done` itself.
     - **`result: red` / `result: blocked`** → failing case names + a trimmed traceback (not
       thousands of raw lines) + what it tried + what it had already confirmed before failing.
       Leave `status: ready`.

   The verbose test output stays in the subagent — it does not flow back into the main context.
3. **Collect the wave.** Each green subagent has already written its completion record and set
   `status: done`. Near-miss green report (fields present, shape imperfect): extract the fields,
   note the deviation, don't re-dispatch. Verify **once per wave, after all subagents land**: run
   the union of the touched modules' scoped tests in one pass. For the worktree exception, verify
   after its branch lands and passes on the merged tree. **Wave-fatal ≠ per-issue red**: a defect
   in the wave itself — the brief named a nonexistent issue, the tests-so-far manifest contradicts
   the tree, the base build is broken — stops the whole wave and surfaces immediately. Wave-fatal
   recovery against the step-2 baseline: files clean in the baseline and modified now →
   `git checkout -- <file>`; files the wave added → `rm`; files already modified in the baseline
   → report, don't restore. On failure: map failing tests to issues via each `### 完成` 新增测试
   list, revert matched issues to `ready` with a note, report the mapping. A red issue
   stays `ready` — anything `blocked_by` it never enters a later wave (report it
   deferred). Merge each green issue's 新增测试 into the **tests-so-far manifest** and carry it
   into every later wave's brief.
4. **Recompute** the ready set (newly-`done` issues may unblock the next wave) and repeat.

## Shared: close the batch

After the last issue takes the active set to empty, run the **full suite + build once** as the
batch's closing check (**[FULL-SUITE.md](FULL-SUITE.md)**) — in a subagent, forking green (one-line
tally) vs red (failing names + trimmed traceback). `--log` drain: rerun each shipped issue's log
command (from 新增测试); do not run FULL-SUITE.md. **If the closing suite is red**: map each
failing case to its issue via that issue's `### 完成` 新增测试 list; revert matched issues to
`ready` with a note — `done` does not survive a red close; report unmapped failures as
unowned regressions. Closing assertions: every dispatched issue accounted for (shipped / failed /
deferred); no worktree left unmerged; no subagent still running. For each drained feature, run
its PRD's 端到端验证 unless absent or `（无）`; hands-on items the agent cannot run are reported
as the **等你验证** block (sources: each feature's PRD 端到端验证, plus 手动验证 lines in
`### 完成` blocks of PRD-less issues) — left pending for the user, never as issue state; on
failure, report
it against that feature's batch result. Report shipped, failed, deferred, and the full-suite
result; explain the
batch's changed flow in one consolidated write-up. Batches of ≥2 issues **run the Spec axis by
default**, dispatched in parallel with the closing suite — one read-only subagent: `git diff
HEAD` + the shipped issue paths, reports per issue under-build / over-build /
wrong-implementation. Under-build findings auto-revert: map the missing AC to its issue, set it
back to `ready` with a note (the red-close mechanism), and let the drain pick it up.
Over-build and wrong-implementation findings go to the user for adjudication — never auto-fixed.
Standards axis
runs alongside it: dispatch the `/code-review` Standards sub-agent in the same turn as the closing
suite, via the caller-ran-Spec entry in `/code-review`; read-only, findings to the user, never
auto-fixed. If a feature's `done` count crossed ~8, run `/tidy` (executes with staged deletions)
and report.
