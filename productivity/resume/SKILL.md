---
name: resume
description: Locate and continue the newest active handoff through its minimal boot chain. Uses git and worktree digests to detect drift, reads only named inputs, and consumes the bridge when its objective finishes.
argument-hint: "Feature slug (optional)"
---

# Resume

Resume is the inverse of `/handoff`; it layers one bounded packet over session-start orientation.

## 1. Locate and classify drift

Run once:

```text
python <handoff-skill-dir>/scripts/handoff-state.py locate <repo-root> [<feature>]
```

Use `python3` only when `python` is absent. The helper checks only `.scratch/handoff.md` and
`.scratch/*/handoff.md`, selects the newest active
packet, and compares both committed and uncommitted baselines.

- `none` → report no resumable work and stop.
- `match` → proceed without rereading repository orientation.
- `worktree-diverged` or `head-diverged` → inspect compact `git status --short`, relevant diff stat,
  and overlapping named paths. Continue autonomously if changes are disjoint and decisions remain
  true; ask once only for an overlap that changes the result or contract.
- `unknown-base` → show `git reflog -15` and ask which revision anchors the work.
- `legacy-no-worktree-digest` → inspect status once, proceed cautiously, and emit schema v2 next time.

## 2. Load in execution order

Read the selected handoff once, then route by its `capsule`:

- `active-work` (default) — execute the chain below.
- `awaiting-alignment` — surface the open question and its Design Receipt to the user before
  touching anything; do not auto-execute `Continue`.
- `external-pending` — check the external task named in `State`; wait or re-check its recovery
  condition instead of running `Continue`.

For `active-work`, load in execution order:

1. `Continue` — execute its READ/RUN/CONFIRM chain.
2. `Decisions` — treat non-drifted decisions and invariants as binding.
3. `State` — follow pointers only when the current action needs them.
4. `Avoid` — consult only before trying a related approach.

Do not reopen completed issues, broad logs, or the full diff. Confirm live any claim that controls an
edit. The handoff is routing plus decisions, not proof.

For feature work, query live cards only when the next action needs dispatch:
`rg '^status: ready' -g '*.md' -g '!**/archive/**' .scratch/<feat>/issues`.

## 3. Consume

Delete the handoff only when the objective it bridges is complete or explicitly abandoned. A long
continuation needing another boundary overwrites it through `/handoff`; never keep two active packets
for one feature. Report the resumed action and current evidence, not a second summary of the packet.
