---
name: merge-conflicts
description: Resolve an in-progress git merge or rebase conflict by understanding each side's original intent, then preserving both where possible. Use when a merge/rebase is mid-conflict, or when the user asks to resolve conflicts.
---

# Resolving Merge Conflicts

Resolve conflicts by understanding *why* each side changed the code, not by pattern-matching the `<<<<<<<` markers. Report to the user in Chinese (per `~/.claude/CLAUDE.md` §1).

1. **See the current state** of the merge/rebase — `git status`, `git log --oneline --graph -20`, and the conflicting files (`git diff --name-only --diff-filter=U`). Know which two commits/branches are meeting and what the merge is *for*.

2. **Find the primary sources** for each conflicting hunk — the intent behind each change. Read the commit messages, and — since this repo tracks work locally — the originating issue under `.scratch/<feat>/issues/NN-*.md` (its `## AC` and `### 完成` record) and any `docs/adr/` decision the hunk touches.

3. **Resolve each hunk.** Preserve both intents where possible; where they're genuinely incompatible, pick the one matching the merge's stated goal and note the trade-off (a one-liner to the user, or an ADR if it's a real decision) — never invent new behaviour or silently drop a side. Use the project's domain language (`CONTEXT.md`) for any names you introduce.

4. **Run the project's automated checks.** Discover them from `docs/agents/domain.md` (cached test/build/format commands); if absent, infer from config and confirm with the user. Run typecheck → tests → format, and fix anything the merge broke. Run the suite/build in a subagent or redirect its output to `.scratch/tmp/`; bring only the pass/fail summary and failing cases into context.

5. **Finish the merge/rebase.** Stage everything and commit (let git write the default merge message, or a short one naming what was reconciled). If rebasing, `git rebase --continue` until all commits are replayed.

## Resolve, don't abort — with one exception

The default is to **resolve**, never `git merge --abort`.

The one exception is **unattended automation**: an agent merging with no human watching should *abort* (leaving `main` clean) rather than guess and corrupt `main`. This skill is the **attended** counterpart: reach for it when a human is present to adjudicate the trade-offs.
