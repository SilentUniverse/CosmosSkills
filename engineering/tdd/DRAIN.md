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

`-p` farms the ready issues out to **subagents** instead of running them inline. The point is
context isolation: each issue's verbose red-green output stays in its own window and never floods
the main session, and independent slices finish in parallel. Same DAG, same per-issue gate — `-p`
only adds two per-issue judgements: **hand this issue to a subagent, and does it need its own
worktree?**

Loop until the ready set is empty:

1. **Compute the wave.** From the remaining `ready-for-agent` issues, take every one whose blockers
   are all `done`. These have no ordering constraint between them.
2. **Fan out — one subagent per issue, dispatched in a single turn.** Each `general-purpose` subagent
   runs the full autonomous red-green loop for its issue. Where it edits depends on coupling:
   - **Decoupled (the common case) → edit in place.** Slices that touch disjoint files can't collide,
     so their subagents edit the **shared working tree directly** — no worktree, no branch, nothing to
     merge afterwards.
   - **Would collide → isolate in a worktree.** Only when two in-flight issues genuinely touch the
     same files, give those a git worktree / branch (`tdd/<NN>-<slug>`) so their edits don't stomp
     each other; the main session merges them back in dependency order (`/resolving-merge-conflicts`
     for any conflict).

   The brief must be self-contained (it can't see this conversation):
   - **Invoke `/tdd <issue-path>`** — this loads the full workflow (status guard, existing-test scan,
     red-green-refactor discipline, Murphy check, completion record). The issue is `ready-for-agent`
     → autonomous mode: skip all "confirm with user" prompts.
   - Its `## 上级` PRD/parent, the project's scoped-test + build commands from `docs/agents/domain.md`,
     and the domain glossary pointer.
   - Report back **only** by outcome —
     - **Green** → one line: which tests it added (files + case counts) + scoped pass tally. The
       subagent writes the completion record and sets `status: done` itself.
     - **Red / blocked** → failing case names + a trimmed traceback (not thousands of raw lines) and
       what it tried. Leave `status: ready-for-agent`.

   The verbose test output stays in the subagent — it does not flow back into the main context.
3. **Collect the wave.** Each green subagent has already written its completion record and set
   `status: done`; verify by re-running the scoped tests on the tree (for the worktree exception,
   after its branch lands cleanly and still passes on the merged tree). If they fail — e.g. a
   concurrent edit conflicted — revert to `ready-for-agent` and note why. A red issue stays
   `ready-for-agent` — and anything that was `blocked_by` it stays blocked, so it simply never
   enters a later wave (report it deferred).
4. **Recompute** the ready set (newly-`done` issues may unblock the next wave) and repeat.

## Shared: close the batch

After the last issue takes the active set to empty, run the **full suite + build once** as the
batch's closing check (**[FULL-SUITE.md](FULL-SUITE.md)**) — in a subagent, forking green (one-line
tally) vs red (failing names + trimmed traceback). Report shipped, failed, deferred, and the
full-suite result; explain
each shipped issue's changed code flow in the chat window. Suggest `/code-review` for an independent
Spec recheck (batch is uncommitted: fixed point HEAD, working-tree diff). If a feature's `done`
count crossed ~8, suggest `/tidy`.
