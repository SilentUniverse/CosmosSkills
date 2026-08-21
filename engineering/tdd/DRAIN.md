# Drain mode

Reached from bare `/tdd`, `/tdd <feat>`, or `/tdd -p [<feat>]`. Runs a whole
batch of `ready` issues to completion in dependency order. Two paths — serial
(default, legible) and parallel (fast). Pick by the flag; the enumeration and the batch
close are shared.

## Shared: enumerate the batch

1. Enumerate candidates: bare / `-p` scans `.scratch/*/issues/*.md` (top level, never
   `archive/`); a `<feat>` argument scans only `.scratch/<feat>/issues/*.md`. Read each one's
   `status:`, `blocked_by:`, `touches:`, and `test_paths:` in one
   `rg '^(status|blocked_by|touches|test_paths):' -A3 <files>` pass;
   `yq --front-matter=extract` only as fallback for lists longer than `-A3`.
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
(not the whole suite). Before each issue, record its baseline (`git status --porcelain` output).
On failure, restore to that baseline: tracked files clean at baseline and modified now →
`git checkout -- <file>`; files added since → delete; files already dirty at baseline →
untouched. Never revert `.scratch/**`. Leave the issue `ready`, note why in `## Comments`, and
**continue** to the next — dependents were already deferred at enumeration.

## Parallel path (`/tdd -p [<feat>]`)

`-p` farms the ready issues out to **subagents** instead of running them inline. The point is
context isolation: each issue's verbose red-green output stays in its own window and never floods
the main session, and independent slices finish in parallel. The workspace is the memory — cards,
manifests, and wave baselines live under `.scratch/`; the orchestrator session is disposable.
Same DAG, same per-issue gate — `-p` only adds per-issue judgements: **hand this issue to a
subagent, and does it need its own worktree?**

Loop until the ready set is empty:

1. **Compute the wave.** From the remaining `ready` issues, take every one whose blockers
   are all `done`. Eligibility is mechanical — both `touches:` and `test_paths:` declared;
   an issue missing either runs alone in its own wave (serialized, still subagent-isolated).
   Two issues with overlapping `touches:` or colliding `test_paths:` serialize into successive
   waves. No prose inference at dispatch — the declarations are the only coupling signal.
   More than half the batch undeclared → suggest the serial path instead: `-p` on undeclared
   cards is serial-with-extra-steps.
2. **Fan out — one subagent per issue, at most 4 in flight.** Before dispatch, record the
   wave baseline (`git status --porcelain` output). A wave over 4 issues dispatches in batches
   of ≤4, each batch landing before the next — concurrent test suites thrash one machine into
   flaky reds. Each `general-purpose` subagent
   runs the full autonomous red-green loop for its issue. `--log` drain: one issue per wave.
   Coupling came from the declarations in step 1:
   - **Disjoint → edit in place.** Subagents edit the shared tree directly.
   - **Overlapping → serialize into successive waves.** Worktree (`tdd/<NN>-<slug>`) only on
     the user's explicit request, to parallelize an overlapping pair; merge back in dependency order
     (`/merge-conflicts` for any conflict). Inside a worktree, nothing writes shared state
     (no stash, no shared tmp paths).

   The brief must be self-contained (it can't see this conversation):
   - **Invoke `/tdd <issue-path>`** (add `--log` when the drain was started with `--log`) —
     this loads the full workflow (status guard, existing-test scan, red-green-refactor
     discipline, Murphy check, completion record). The issue is `ready` → autonomous mode:
     skip all "confirm with user" prompts. Run this slice yourself — no spawning further
     subagents, no entering drain mode.
   - The issue is self-contained — no PRD attach. Paste the scoped-test and build command
     lines from `docs/agents/domain.md` into the brief; the brief's lines stand in for the
     existing-test scan's domain.md lookup.
   - The **tests-so-far manifest** (earlier waves' 新增测试): don't write tests it already covers —
     report duplicates instead.
   - Report back **only** by outcome, in this fixed shape — a free-form reply is not a result;
     red/blocked reports stay under 400 words:
     - **`result: green`** → which tests it added (files + case counts) + files changed
       (production and tests) + scoped pass tally. The
       subagent writes the completion record (syncing `test_paths:` per its template) and sets
       `status: done` itself.
     - **`result: red` / `result: blocked`** → failing case names + a trimmed traceback (error
       head + last frames + omitted-line count; never file contents) + what it tried + what it
       had already confirmed + one suggested next action.
       Revert **this issue's** edits first (not the whole wave). Leave `status: ready`.

   The verbose test output stays in the subagent — it does not flow back into the main context.
3. **Collect the wave.** Each green subagent has already written its completion record and set
   `status: done`. An imperfectly shaped report trusts the disk over the note: check the issue's
   `### 完成` record and rerun that module's scoped tests — record valid + green → accept with the
   deviation noted; record broken → treat as red (revert this issue, leave `ready`). Verify
   **once per wave, after all subagents land**: run the
   union of the touched modules' scoped tests in one pass — narrowed by the domain.md
   impact-probe test command when one exists — and reconcile the write set: compare
   `git status --porcelain` against the wave baseline (exclude `.scratch/**`), attributing each
   changed file via the wave's reported files. Two issues reporting the same file, or a changed
   file nobody reported → wave-fatal (recovery below). An issue's undeclared test file with green
   tests → sync its `test_paths:` (the sanctioned frontmatter edit); an undeclared production
   file → note it in its `### 完成` 备注. Files no declaration covers (repo root, config) can
   still collide — the closing suite is the net. For the worktree
   exception, verify
   after its branch lands and passes on the merged tree. **Wave-fatal ≠ per-issue red**: a defect
   in the wave itself — the brief named a nonexistent issue, the tests-so-far manifest contradicts
   the tree, the base build is broken — stops the whole wave and surfaces immediately. Wave-fatal
   recovery against the step-2 baseline: code files clean in the baseline and modified now →
   `git checkout -- <file>`; files the wave added → delete; files already modified in the
   baseline → report, don't restore. Never touch `.scratch/**` — completion records and revert
   notes live there. Map the defect to its issues via each `### 完成` 新增测试
   list, set those issues back to `ready`, append the note, report the mapping. A red issue
   stays `ready` — anything `blocked_by` it never enters a later wave (report it
   deferred). Merge each green issue's 新增测试 into the **tests-so-far manifest** and carry it
   into every later wave's brief.
4. **Recompute** the ready set (newly-`done` issues may unblock the next wave) and repeat.
   After collecting a wave, persist its state: update `.scratch/<feat>/handoff.md` in rolling
   mode with the wave number, the wave baseline, and the tests-so-far manifest — a crashed
   overnight run resumes from the handoff instead of reverse-engineering a mixed tree (a
   cross-feature drain rolls `.scratch/handoff.md` instead). In a
   runner-driven drain (repo `scripts/overnight.py`), each wave close also ends the session:
   write §5 as 读 handoff → 续跑下一波, then stop — the runner relaunches a fresh session, so no
   wave is ever scheduled from a rotting context. Interactive `-p` sessions never rotate.

## Shared: close the batch

After the last issue takes the active set to empty, run the **full suite + build once** as the
batch's closing check (**[FULL-SUITE.md](FULL-SUITE.md)**) — in a subagent, forking green (one-line
tally) vs red (failing names + trimmed traceback). `--log` drain: rerun each shipped issue's log
command (from 新增测试); do not run FULL-SUITE.md. **If the closing suite is red**: map each
failing case to its issue via that issue's `### 完成` 新增测试 list; revert matched issues to
`ready` with a note — `done` does not survive a red close; report unmapped failures as
unowned regressions. Closing assertions: every dispatched issue accounted for (shipped / failed /
deferred); no worktree left unmerged; no subagent still running. For each drained feature, run
its PRD's 端到端验证 unless absent or `（无）`; on failure, report it against that feature's
batch result.

Batches of ≥2 issues run **both review axes in parallel with the closing suite**, same turn
(briefs, single source: [../code-review/SUBAGENT-BRIEFS.md](../code-review/SUBAGENT-BRIEFS.md)):

- **Spec axis** — one read-only subagent: `git diff HEAD` + the shipped issue paths, brief §Spec
  (caller-ran-Spec mode), reports per issue under-build / over-build / wrong-implementation.
  Under-build findings auto-revert: map the missing AC to its issue, set it back to `ready` with
  a note (the red-close mechanism), let the drain pick it up.
- **Standards axis** — read-only, brief §Standards, same file.
- Over-build and wrong-implementation findings → the user for adjudication, never auto-fixed.

**Close report — one screen, five blocks:**

1. 结果: shipped / failed / deferred counts + suite verdict.
2. Frontier: one line per non-shipped issue — `NN <slug> — blocked by <NN> | deferred | failed: <cause>`.
3. 待裁决: over-build / wrong-implementation findings, each quoted to its hunk.
4. 等你验证: every hands-on check (sources: each feature's PRD 端到端验证, plus 手动验证 lines
   in PRD-less issues' `### 完成`), each with its exact runnable command inline when one exists —
   copy-paste ready; subjective checks marked 人工. Left pending for the user, never as issue state.
5. 详文: per-issue `### 完成` records; anything the one screen can't hold goes into the final
   rolling handoff as pointers, consumed and deleted by the morning `/resume`.

The final rolling `/handoff` refresh at close is the morning briefing — its §5 开机动作序列 points
at the close report's 等你验证 / 待裁决 items; the morning `/resume` consumes it and deletes the
file. A fully green close with nothing pending for the human deletes the rolling handoff instead.

If a feature's `done` count crossed ~8, run `/tidy` in drain-caller mode (execute the
previewed plan, no confirm; skip its full suite unless it moved tests) and report.
