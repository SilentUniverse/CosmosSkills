---
name: merge-conflicts
description: Resolve an in-progress git merge or rebase conflict by understanding each side's original intent, then preserving both where possible. Use when a merge/rebase is mid-conflict, or when the user asks to resolve conflicts.
---

# Resolving Merge Conflicts

Resolve conflicts by understanding each side's intent. Report the reconciled behavior, verification,
and remaining conflicts in the user's language.

1. **See the current state** of the merge/rebase — `git status`, `git log --oneline --graph -20`, and the conflicting files (`git diff --name-only --diff-filter=U`). Know which two commits/branches are meeting and what the merge is *for*.

2. **Find the primary sources** for each conflicting hunk — the intent behind each change. Read the commit messages and, since this repo tracks work locally, the originating issue under `.scratch/<feat>/issues/NN-*.md` (its `## 验收标准` and `### 完成` record) and any `docs/adr/` decision the hunk touches.

3. **Resolve each hunk.** Preserve both intents where possible. Resolve incompatible changes against the stated goal and prior decisions; if neither settles a consequential conflict, ask with the concrete alternatives and continue other hunks. Never silently drop a side. Use `CONTEXT.md` vocabulary when present.

4. **Run automated checks.** Discover commands from `CODEBASE.md`, a legacy command cache, or project configuration; no confirmation or map bootstrap for routine local checks. Run relevant typecheck/tests/format/build and fix merge regressions. Run inline with bounded logs; widen checks for affected contracts or unresolved risk. Missing tooling warrants available static checks and a precise unverified gap.

5. **Finish the requested operation.** Stage only resolved paths. Inspect the final index against the initial operation state; never include unrelated user changes. When the request authorizes completing the merge/rebase, continue it through all replayed commits after checks pass. If unrelated staged work would be swept in, leave it intact and ask how to separate it. A resolve-only request leaves verified resolutions for the caller's submission step.

## Preserve unresolved work

Resolve within existing authority whether attended or unattended. If a decision blocks completion,
preserve the operation and report the exact conflict after completing independent work. Abort only
when the user or an explicit automation rollback contract calls for it.
