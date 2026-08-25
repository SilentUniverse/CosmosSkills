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
   after its blockers. Skip (don't fail) any issue still blocked by an unfinished issue; report
   it as deferred at the end.

## Shared: blocked 纪律

Issues have no `blocked` state; blocked is a **report classification**. A report may call an
issue blocked only when all three hold:

1. **Specific condition** — the exact command, the exact error, what exactly is missing
   (environment, dependency, access).
2. **Survived one approach switch** — the same condition persisted after a *different* angle was
   tried (CLAUDE.md §5 anti-thrash), not after one identical retry.
3. **Everything outside the blocked path is green** — hard, slow, or partly unclear is red with a
   note, not blocked.

## Serial path (default: bare `/tdd`, `/tdd <feat>`)

Run each issue, **one at a time**, through the autonomous-mode loop (SKILL.md §Workflow), all in
the current session so you can watch each one. No worktrees, no parallel subagents. This is
deliberately the dumb-but-legible path.

Per-issue gate: mark `status: done` only if build + the touched module's **scoped** tests pass
(not the whole suite). Before each issue, record its baseline (`git status --porcelain` output).
On failure, restore to that baseline: tracked files clean at baseline and modified now →
`git checkout -- <file>`; files added since → delete; files already dirty at baseline →
untouched. Never revert `.scratch/**`. Leave the issue `ready`, note why in `## Comments`, and
**continue** to the next. Dependents were already deferred at enumeration.

## Parallel path (`/tdd -p [<feat>]`)

`-p` farms the ready issues out to **subagents** instead of running them inline. The point is
context isolation: each issue's verbose red-green output stays in its own window and never floods
the main session, and independent slices finish in parallel. The workspace is the memory. Cards,
manifests, and wave baselines live under `.scratch/`; the orchestrator session is disposable.
Same DAG, same per-issue gate. `-p` only adds per-issue judgements: **hand this issue to a
subagent, and does it need its own worktree?**

Loop until the ready set is empty:

1. **Compute the wave — by script, never by hand.** Run this skill's
   `scripts/drain-wave.py next <repo-root> [<feat>]`. The script reads only the frontmatter
   declarations (status / blocked_by / touches / test_paths) and prints the wave
   (parallel, collision-free), the serialized remainder, `solo:` issues (missing a declaration;
   one per wave), and `deferred:` lines (feed the close report's
   Frontier). Exit 3 = zombies — a dispatched issue that neither closed nor flipped done
   ([EDGE-CASES.md](EDGE-CASES.md)); resolve by adopt-or-revert and `collect` before any new
   wave. Exit 4 = nothing ready, batch complete. Shared surfaces (workspace manifest,
   lockfile, any repo-root file a slice edits) are declared in `touches:` verbatim. The
   script serializes on any overlap. More than half the batch undeclared → suggest the
   serial path instead: `-p` on undeclared cards is serial-with-extra-steps.
2. **Fan out — one subagent per issue, at most 4 in flight.** Record the dispatch intent
   first: `drain-wave.py dispatch <repo-root> <slug>...` writes the wave number, the issue
   list, and the wave baseline (`git status --porcelain`) to
   `.scratch/<feat>/wave-ledger.json` **before any subagent starts**. A crashed run
   resumes from the ledger, not from reverse-engineering the tree. The dispatch call
   enforces the barrier (blockers all done), the ≤4 cap, and collision serialization.
   A refusal is a scheduling error to fix, not a suggestion to override. A wave over 4
   issues dispatches in batches of ≤4; collect each batch, then dispatch the rest.
   Concurrent test suites thrash one machine into flaky reds. Each `general-purpose`
   subagent
   runs the full autonomous red-green loop for its issue. `--log` drain: one issue per wave.
   Coupling came from the declarations in step 1:
   - **Disjoint → edit in place.** Subagents edit the shared tree directly.
   - **Overlapping → serialize into successive waves.** Worktree (`tdd/<NN>-<slug>`) only on
     the user's explicit request, to parallelize an overlapping pair; merge back in dependency order
     (`/merge-conflicts` for any conflict). Inside a worktree, nothing writes shared state
     (no stash, no shared tmp paths).

   The brief must be self-contained (it can't see this conversation):
   - **Invoke `/tdd <issue-path>`** (add `--log` when the drain was started with `--log`).
     This loads the full workflow (status guard, existing-test scan, red-green-refactor
     discipline, Murphy check, completion record). The issue is `ready` → autonomous mode:
     skip all "confirm with user" prompts. Run this slice yourself. No spawning further
     subagents; no entering drain mode.
   - The issue is self-contained; no PRD attach. Paste the scoped-test and build command
     lines from `docs/agents/domain.md` into the brief; the brief's lines stand in for the
     existing-test scan's domain.md lookup.
   - The **tests-so-far manifest** (earlier waves' 新增测试): don't write tests it already covers;
     report duplicates instead.
   - Report back **only** by outcome, in this fixed shape. A free-form reply is not a result;
     red/blocked reports stay under 400 words:
     - **`result: green`** → which tests it added (files + case counts) + files changed
       (production and tests) + scoped pass tally. The
       subagent writes the completion record (syncing `test_paths:` per its template) and sets
       `status: done` itself.
     - **`result: red` / `result: blocked`** → failing case names + a trimmed traceback (error
       head + last frames + omitted-line count; never file contents) + what it tried + what it
       had already confirmed + one suggested next action.
       Revert **this issue's** edits first (not the whole wave). Leave `status: ready`.

   The verbose test output stays in the subagent; it does not flow back into the main context.
3. **Collect the wave.** Close the ledger first: `drain-wave.py collect <repo-root>
   <slug>=<result>[,...]` (green|red|blocked|aborted). A done-on-disk issue reported
   non-green refuses until reconciled, and a green report for an issue not yet `done` on
   disk refuses too; flip the completion record + frontmatter first. Each green subagent
   has already written its completion
   record and set
   `status: done`. An imperfectly shaped report trusts the disk over the note: check the issue's
   `### 完成` record and rerun that module's scoped tests. Record valid + green → accept with the
   deviation noted; record broken → treat as red (revert this issue, leave `ready`). Verify
   **once per wave, after all subagents land**: run the
   union of the touched modules' scoped tests in one pass, narrowed by the domain.md
   impact-probe test command when one exists, and reconcile the write set: compare
   `git status --porcelain` against the wave baseline (exclude `.scratch/**`), attributing each
   changed file via the wave's reported files. Two issues reporting the same file, or a changed
   file nobody reported → wave-fatal (recovery below). An issue's undeclared test file with green
   tests → sync its `test_paths:` (the sanctioned frontmatter edit); an undeclared production
   file → note it in its `### 完成` 备注. Files no declaration covers (repo root, config) can
   still collide; the closing suite is the net. For the worktree exception, verify
   after its branch lands and passes on the merged tree. **Wave-fatal ≠ per-issue red**: a defect
   in the wave itself stops the whole wave and surfaces immediately. Wave-fatal defects: the
   brief named a nonexistent issue, the tests-so-far manifest contradicts the tree, the base
   build is broken. Wave-fatal
   recovery against the step-2 baseline: code files clean in the baseline and modified now →
   `git checkout -- <file>`; files the wave added → delete; files already modified in the
   baseline → report, don't restore. Never touch `.scratch/**`; completion records and revert
   notes live there. Map the defect to its issues via each `### 完成` 新增测试
   list, set those issues back to `ready`, append the note, report the mapping. A red issue
   stays `ready`. Anything `blocked_by` it never enters a later wave; report it
   deferred. Merge each green issue's 新增测试 into the **tests-so-far manifest** and carry it
   into every later wave's brief.
4. **Recompute** the ready set (newly-`done` issues may unblock the next wave) and repeat.
   After collecting a wave, persist its state: update `.scratch/<feat>/handoff.md` in rolling
   mode with the wave number and the tests-so-far manifest. The wave baseline lives in the
   ledger, so the handoff points at it instead of duplicating it. A crashed
   overnight run resumes from the handoff instead of reverse-engineering a mixed tree (a
   cross-feature drain rolls `.scratch/handoff.md` instead). In a
   runner-driven drain (the skills repo's `scripts/overnight.py`) the runner owns wave
   scheduling: it runs `next` and `dispatch`es the wave itself **before launching the
   session**. Every dispatch timestamp provably precedes the session's work, so the ledger
   can never be written after the fact. The session receives the dispatched wave, runs the
   subagents, `collect`s, writes §5 as 读 handoff → 续跑下一波, and stops; a zombie report
   (next exit 3) gets a session that only adopt-or-reverts and `collect`s; the close-out
   runs as its own fresh session. No wave is ever scheduled from a rotting context.
   Interactive `-p` sessions never rotate and call `next`/`dispatch` themselves.

## Shared: close the batch

After the last issue takes the active set to empty, run
`drain-wave.py audit <repo-root> [<feat>]`. Every test-pattern file under
`touches:` must be claimed by some issue's `test_paths:`; the pattern list is the script's,
and vendored/build trees are skipped. Assign each unowned file (sanctioned append) or
open a cleanup issue before the review, so no unreviewed test rides the batch. Then run
the **full suite + build once** as the
batch's closing check (**[FULL-SUITE.md](FULL-SUITE.md)**), in a subagent, forking green (one-line
tally) vs red (failing names + trimmed traceback). `--log` drain: rerun each shipped issue's log
command (from 新增测试); do not run FULL-SUITE.md. **If the closing suite is red**: map each
failing case to its issue via that issue's `### 完成` 新增测试 list; revert matched issues to
`ready` with a note; `done` does not survive a red close. Report unmapped failures as
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
   in PRD-less issues' `### 完成`), each with its exact runnable command inline when one exists,
   copy-paste ready; subjective checks marked 人工. Left pending for the user, never as issue state.
5. 详文: per-issue `### 完成` records; anything the one screen can't hold goes into the final
   rolling handoff as pointers, consumed and deleted by the morning `/resume`.

The final rolling `/handoff` refresh at close is the morning briefing. Its §5 开机动作序列 points
at the close report's 等你验证 / 待裁决 items; the morning `/resume` consumes it and deletes the
file. A fully green close with nothing pending for the human deletes the rolling handoff instead.

If a feature's `done` count crossed ~8, run `/tidy` in drain-caller mode and report: execute the
previewed plan with no confirm; skip its full suite unless it moved tests.
