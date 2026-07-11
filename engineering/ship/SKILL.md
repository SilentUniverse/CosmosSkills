---
name: ship
description: Orchestrate a feature's ready-for-agent issues to completion. Reads the dependency DAG from frontmatter, topologically sorts, dispatches independent issues to subagents running /tdd (same-module work serialized, cross-module parallelized), enforces a build+test verification gate before each commit, and collects ready-for-human issues into a hands-on checklist.
disable-model-invocation: true
argument-hint: "Feature slug (optional; omit to pick from INDEX)"
---

# Ship

The orchestration layer above `/tdd` — it decides which issues, in what order, what runs in
parallel, and how the feature wraps up. It does not write code itself; it invokes `/tdd` as the
execution unit. All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).

> **Boundary: the agent runs the deterministic tail, not the judgment.** `/ship` only touches
> `ready-for-agent` issues. `grill` / `to-prd` / `to-issues` (deciding direction) and every
> `ready-for-human` issue (architecture, UX taste, real-device checks) stay with the human.

## Invocation

- `/ship <feat>` — ship that feature.
- `/ship` — read `.scratch/INDEX.md`, list features with `ready-for-agent` issues, ask which to ship.

## Process

### 1. Build the plan

Read `.scratch/<feat>/issues/*.md` (top level, not `archive/`). Collect every `ready-for-agent`
issue with its `blocked_by` list. Read frontmatter fields deterministically with `yq` rather than
eyeballing — e.g. enumerate the DAG with:

```bash
for f in .scratch/<feat>/issues/*.md; do
  echo "$f: $(yq --front-matter=extract '.status' "$f") <- $(yq --front-matter=extract '.blocked_by | join(\",\")' "$f")"
done
```

Then:

1. **Topologically sort** on `blocked_by`. An issue is runnable only once all its blockers are
   `done`. If a blocker is itself `ready-for-agent`, it's in this run; if a blocker is
   `ready-for-human`, the dependent is **deferred** (can't auto-run past a human gate).
2. **Detect file-level conflicts (critical).** Two issues that will modify the same module can't run
   in parallel safely — concurrent `/tdd` runs would clobber each other. Infer the touched modules
   from each issue's `做什么` / `实现决策` (and `CONTEXT.md` code paths if present). Group issues that
   share a module so they run **serially**; only genuinely disjoint issues run in **parallel**.
   When in doubt, serialize — a wrong parallelization corrupts work, a wrong serialization only
   costs time.
3. Present the wave plan and ask the user to confirm before dispatching:

```
🚢 Ship 计划：balance
──────────────────────────────────────────────────────────────
Wave 1（并行，各自 worktree，模块不相交）:
  03-mobile-ui.md      (touches src/ui/)
  04-cache.md          (touches src/cache/)
  → 并行跑完后，各分支过两阶段 review，通过的串行 merge-back 回主分支
Wave 2（依赖 Wave 1，从更新后的主分支分叉）:
  05-balance-api.md    (blocked_by: 04-cache) (touches src/api/, src/cache/ → 与 04 不同 wave)
延后（卡在人工门后，不自动跑）:
  06-design-review.md  (ready-for-human)
──────────────────────────────────────────────────────────────
确认派发？
```

### 2. Dispatch each issue through /tdd

Within a wave, spawn one subagent per issue **in parallel, each in its own git worktree** so their
commits never race on a shared index. Each runs `/tdd <issue-path>` in **autonomous mode** (the
issue is `ready-for-agent`, so `/tdd` skips confirmation prompts) and commits on its own branch.
Keep the heavy work — codebase exploration, file reads, the red-green loop — inside the subagent's
own context; the main loop only collects results.

After a wave's parallel builds finish, **review each built branch with a fresh subagent** (§3b) —
only branches that pass the two-phase review proceed. Then **merge the surviving branches back to
the main branch serially** (one `git merge --no-ff` at a time). The next wave branches from that
updated main, so `blocked_by` dependencies see the prior wave's work. If a merge conflicts (the plan
mis-grouped two issues that actually share a module), abort it (`git merge --abort`, leaving main
clean) and report that issue `failed` — never force a conflicted merge in an unattended run. (To
finish such a merge deliberately afterward, attend it with the `/resolving-merge-conflicts` skill, or
re-run the issue.) After the wave's branches
are all merged, run the **full suite + build** once against the updated main to catch cross-module
regressions the scoped per-issue gates missed; report any failure. Worktree subagents must not touch
`INDEX.md`; regenerate it once after the last wave.

### 3. Verification gate (per issue)

Two layers. A built issue must clear **both** before its branch may merge to main.

**3a. Build + scoped tests (the implementer subagent, in its worktree).** A subagent may only commit
(on its worktree branch) and mark an issue `done` after build + the touched modules' tests pass
(commands cached in `docs/agents/domain.md`). The gate is **scoped** — not the whole suite; the full
suite runs once after merge-back (step 2), not N times in parallel. On failure:

- Do not commit, do not mark `done`.
- Return `failed` with a one-line reason. The issue file stays `ready-for-agent` (the worktree is
  discarded, so nothing leaks into main).
- Report the failure in the run summary; do not let a red issue block the rest of the wave unless
  others depend on it.

On success `/tdd` writes the `### 完成` record and flips `status: done` **inside the worktree**; that
state reaches main only when the branch merges back.

**3b. Two-phase review (a fresh subagent, before merge-back).** Build-green is necessary, not
sufficient — passing tests don't prove the diff matches the spec or reads cleanly. After a branch
clears 3a, run the `/code-review` skill against the branch diff (`git diff HEAD...<branch>`) with the
issue as the spec source. `/code-review` spawns its own **fresh** reviewer sub-agents (a reviewer
that didn't write the code isn't anchored to the implementer's assumptions) and returns verdicts on
its **two axes — both must pass**:

- **Spec** — every acceptance criterion is met, with **no over-build** (features, abstractions, or
  config beyond the AC — scope creep is a fail) and **no under-build** (a missing AC).
- **Standards** — matches existing style and accepted ADRs, no leftover debug/commented-out code,
  clears the Fowler smell baseline, and the new tests verify behavior through public interfaces (not
  implementation details, not tautologies).

If both pass, the branch proceeds to merge-back. If either reports a blocking finding, the branch is
**not merged**: the issue is reported `failed` with `/code-review`'s concrete findings and left
`ready-for-agent` (its branch stays in git, unmerged, so the work is inspectable). A review failure
behaves exactly like a 3a failure for scheduling — it doesn't abort the wave unless a dependent
needs it. `/code-review` is read-only; only this orchestrator merges or aborts.

`INDEX.md` is regenerated once after the final wave (or by `/tidy`), not per issue.

### 4. Auto-tidy when done piles up

After the run, check the feature's `done` count in `INDEX.md`. If it crosses ~8, offer to run
`/tidy <feat>` (archive done issues, regenerate `SUMMARY.md`, audit tests). Don't force it —
ask, since test deletion wants a human nod.

### 5. Context guard

A wave boundary is the natural checkpoint: the wave's branches are merged, `status: done` and
`INDEX.md` are on disk, so a clean break loses nothing. **Don't wait to "feel" context running low**
— a model judges its own remaining context poorly, and an in-session `/ship` accumulates every
wave's exploration and red-green output in the main loop, so a multi-wave feature can exhaust it
before the signal ever fires. Instead, decide structurally at each wave boundary: if more than a
wave or two of work remains, write a `/handoff` for the feature (it records which waves completed,
which issues remain, and the `git_base`) and stop; the next session continues with `/resume`. If
you find yourself reaching this guard repeatedly for one feature, that feature was too big for
in-session `/ship` — rerun it as `/ship-wf` (runtime B), which keeps the heavy work out of the main
context entirely.

### 6. Report

Summarize: issues shipped (with commit hashes), issues that failed the gate (with reasons),
`ready-for-human` issues deferred (the hands-on checklist for the user), and whether a `/tidy` pass
is recommended.

## Two ways to run ship

Same contract (frontmatter DAG → verification gate → INDEX/SUMMARY), two runtimes. Pick by how
long the work is and how much you want to watch it.

### A. In-session (this skill) — watch it, interrupt it

`/ship <feat>` runs the Process above in the current conversation. You see every wave, can stop or
redirect at any point. **Use it only for a handful of issues (roughly one or two waves) you want to
supervise** — it runs in the main context, so every wave's exploration and red-green output
accumulates there. Beyond that, don't lean on the step-5 guard to save you mid-run; reach for
`/ship-wf` (B) from the start, which keeps the heavy work out of the main context.

### B. `/ship-wf` — fan-out orchestration in one background run

For a feature with many issues, run the bundled Workflow script. A `*.js` file under
`.claude/workflows/` (or `~/.claude/workflows/`) is auto-registered by Claude Code as a **dynamic
slash command named after its `meta.name`** — so this workflow is invoked directly as `/ship-wf`
(not `/workflow ship-wf`; there is no such parameterized command). It does the same plan → build →
tidy loop but in a background orchestration with its own structured agents, so the heavy work never
touches your main context:

```
/ship-wf
```

Pass the feature slug as the workflow arg (the runtime prompts for `args`, or you state it: "run
ship-wf for feature balance"). Browse live/finished runs with `/workflows` (plural). The script
lives at `.claude/workflows/ship-wf.js` (source of record:
`engineering/ship/ship-wf.workflow.js`). Named `ship-wf` to avoid colliding with the `/ship` skill.
What it does, faithfully to this skill:

- **Plan** — one structured agent lists active issues (`fd … -d 1`, never `archive/`), reads
  `status` / `blocked_by` with `yq --front-matter=extract`, infers touched modules, and returns
  dependency-ordered **waves** (issues in one wave touch disjoint modules) plus a `deferred` list
  (anything gated behind a `ready-for-human` blocker).
- **Build** — within each wave, one TDD subagent per `ready-for-agent` issue runs **in parallel,
  each in its own git worktree** (`isolation: 'worktree'`) so there are no git-index races. Each is
  bound by the hard verification gate: it commits on its own branch + sets `status: done` only if
  build + tests pass, otherwise returns `failed`. After a wave's parallel builds finish, each
built branch is **reviewed via `/code-review`** (two axes: Spec + Standards, both must pass — see
    §3b) in parallel; only branches that pass review proceed. The orchestrator then
  **merges the surviving branches back to main serially** (one `git merge --no-ff` at a time);
  the next wave branches from that updated main so `blocked_by` holds. Worktree agents never touch
  `INDEX.md` — the orchestrator regenerates it once at the end.
- **Tidy** — if the post-run `done` count ≥ 8, it invokes `/tidy` to archive, regenerate
  `SUMMARY.md`, and audit tests; otherwise it just refreshes `INDEX.md`.

It returns a structured report (shipped + commits, failed + reasons, deferred, merged branches,
whether it tidied). Watch live progress with `/workflows`. Iterate by editing
`.claude/workflows/ship-wf.js` and re-running.

**Which to use:**

| Situation | Use |
|---|---|
| A few issues, want to supervise | A — `/ship <feat>` |
| Many issues, one unattended background run | B — `/ship-wf` |

Both honor the same boundary: they only touch `ready-for-agent` issues. Direction (`grill` /
`to-prd` / `to-issues`) and every `ready-for-human` gate stay with you.
