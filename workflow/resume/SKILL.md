---
name: resume
description: >-
  Use when continuing interrupted work from a Cosmos handoff. Selects the matching active bridge, checks Git and worktree drift, loads only named inputs, resumes the objective, and consumes that version after completion.
argument-hint: "Feature slug or exact handoff path (optional)"
---

# Resume

Resume is the inverse of `/handoff`; it layers one bounded packet over session-start orientation.

## 1. Locate and classify drift

Run once:

```text
python <handoff-skill-dir>/scripts/handoff-state.py locate <repo-root> [<feature>]
```

Use `python3` only when `python` is absent. The helper checks only `.scratch/handoff.md` and
`.scratch/*/handoff.md` and compares both committed and uncommitted baselines. Retain the returned
path and `version` for consumption. Use `--path <exact-handoff>` when a pointer names the bridge.

- `none` → report no active handoff; continue an objective supplied by the user from available
  context, or report that no objective can be recovered.
- `ambiguous` → choose from explicit task/feature pointers, then locate that path. If available
  context cannot distinguish the remaining objectives, ask which to resume. Dates and mtimes do not select an owner.
- `match` → proceed without rereading repository orientation.
- `worktree-diverged` or `head-diverged` → inspect compact `git status --short`, relevant diff stat,
  and overlapping named paths. Continue autonomously if changes are disjoint and decisions remain
  true. Resolve compatible overlap from live evidence; ask only if it leaves a consequential
  decision unresolved.
- `unknown-base` → inspect the named refs and `git reflog -15` to recover the anchor. Ask only
  when competing anchors change the next action and evidence cannot distinguish them.
- `legacy-no-worktree-digest` → inspect status once, proceed cautiously, and emit schema v2 next time.

## 2. Load in execution order

Read the selected handoff once, then route by its `capsule`:

- `active-work` (default) — execute the chain below.
- `awaiting-alignment` — check the open question against current instructions and evidence. If
  resolved, proceed; otherwise ask with the relevant receipt and continue independent work.
- `external-pending` — check the task and recovery condition in `State`. Resume the dependent
  chain when recovered; while pending, continue independent authorized work.

For `active-work`, load in execution order:

1. Read `Continue` to identify the action, then `Decisions` and `State` for its objective,
   authorization, and constraints. Current user instructions take precedence.
2. Consult `Avoid` before trying a related approach; follow evidence pointers only as needed.
3. Verify the claims controlling the action, then execute READ/RUN/CONFIRM. `CONFIRM` is an
   observable check, not another approval. Continue toward the remaining objective.

Do not reopen completed issues, broad logs, or the full diff. Confirm live any claim that controls an
edit. The handoff is routing plus decisions, not proof.

For feature work, query live cards only when the next action needs dispatch:
`python <skills-root>/workflow-state.py survey <repo-root> --format human`. It parses frontmatter
and separates ready from blocked; do not enumerate cards with `rg`.

## 3. Consume

Consume the selected version only when its objective is complete or explicitly abandoned:

```text
python <handoff-skill-dir>/scripts/handoff-state.py consume <repo-root> <handoff-path> --expected <version>
```

A mismatch preserves newer work; inspect and reconcile it without blind deletion or hash refresh.
Check the whole remaining user goal and transfer reusable knowledge before consumption; an empty
issue queue or a successful first Continue command does not establish completion.
A long continuation needing another boundary publishes through `/handoff`; never keep two active
packets for one feature. Report the resumed action and current evidence, not a second summary.
