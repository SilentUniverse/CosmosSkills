# Drain mode

Reached from bare `/tdd`, `/tdd <feat>`, or `/tdd -p [<feat>]`. Runs a whole
batch of `ready-for-agent` issues to completion in dependency order. Two paths — serial
(default, legible) and parallel (fast). Pick by the flag; the enumeration and the batch
close are shared.

## Shared: enumerate the batch

1. Enumerate candidates: bare / `-p` scans `.scratch/*/issues/*.md` (top level, never
   `archive/`); a `<feat>` argument scans only `.scratch/<feat>/issues/*.md`. Read each one's
   `status:` and `blocked_by:` with `yq --front-matter=extract`.
2. Keep only `status: ready-for-agent`. Topologically sort on `blocked_by` so every issue runs
   after its blockers. Skip (don't fail) any issue still blocked by a `ready-for-human` or
   unfinished issue — report it as deferred at the end.

## Serial path (default: bare `/tdd`, `/tdd <feat>`)

Run each issue, **one at a time**, through the autonomous-mode loop (SKILL.md §Workflow), all in
the current session so you can watch each one. No worktrees, no parallel subagents — deliberately
the dumb-but-legible path.

Per-issue gate: mark `status: done` only if build + the touched module's **scoped** tests pass
(not the whole suite); on failure leave it `ready-for-agent`, note why in `## Comments`, and
**continue** to the next (a red issue doesn't abort the drain unless others depend on it).

## Parallel path (`/tdd -p [<feat>]`)

Same DAG, but instead of walking it one node at a time, run every **ready wave** concurrently. A
wave is the set of `ready-for-agent` issues whose `blocked_by` are all already `done`. This
collapses the wall-clock of N independent slices toward the time of a single slice — the largest
speedup available when a feature's slices don't all chain.

Loop until the ready set is empty:

1. **Compute the wave.** From the remaining `ready-for-agent` issues, take every one whose blockers
   are all `done`. These have no ordering constraint between them.
2. **Fan out — one subagent per issue, dispatched in a single turn.** Give each a `general-purpose`
   subagent working on its **own git worktree / branch** (`tdd/<NN>-<slug>`), so their edits never
   collide. The subagent brief must be self-contained (it can't see this conversation): the issue
   file path, its `## 上级` PRD/parent, the project's scoped-test + build commands from
   `docs/agents/domain.md`, the domain glossary pointer, and the instruction to run the full
   autonomous red-green loop and report back **only** by outcome —
   - **Green** → one line: which tests it added (files + case counts) + scoped pass tally. Leave the
     branch for the main session to integrate.
   - **Red / blocked** → failing case names + a trimmed traceback (not thousands of raw lines) and
     what it tried. Leave `status: ready-for-agent`.
   The verbose test output stays in the subagent — it does not flow back into the main context.
3. **Collect + integrate the wave.** For each green subagent, fast-forward / merge its branch into
   the working branch in dependency order; resolve any conflict with `/resolving-merge-conflicts`.
   Set each integrated issue's `status: done` only after its branch lands cleanly and its scoped
   tests still pass on the merged tree. A red issue stays `ready-for-agent` — and anything that was
   `blocked_by` it stays blocked, so it simply never enters a later wave (report it deferred).
4. **Recompute** the ready set (newly-`done` issues may unblock the next wave) and repeat.

**Mode fit — recommend, don't switch.** The widest wave's size (from the §Shared sort) is the
whole signal: a pure chain (every wave size 1) gets no speedup from `-p`, only worktree overhead,
while several **independent** slices (wide waves) are where `-p` collapses wall-clock toward one
slice. If the invoked mode doesn't fit, say so in one line, then proceed as invoked — serial is
the safe default when unsure.

## Shared: close the batch

After the last issue takes the active set to empty, run the **full suite + build once** as the
batch's closing check (SKILL.md §5) — in a subagent, forking green (one-line tally) vs red (failing
names + trimmed traceback). Report shipped, failed, deferred, and the full-suite result; explain
each shipped issue's changed code flow in the chat window. Suggest `/code-review` for an independent
Spec recheck (batch is uncommitted: fixed point HEAD, working-tree diff). If a feature's `done`
count crossed ~8, suggest `/tidy`.
