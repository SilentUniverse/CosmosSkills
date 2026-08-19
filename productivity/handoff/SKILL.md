---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up. Use before /clear, when context is nearly full, or to checkpoint a long multi-session task. In unattended runs (drain -p, overnight batches), overwrite-in-place a rolling mini-refresh at batch close; interactive sessions never auto-invoke — the user calls /handoff at the smart-zone boundary.
argument-hint: "What will the next session be used for?"
---

Write a minimal recoverable snapshot so the next session can continue from the current node by reading this one file. This is **not** a conversation summary — extract current state, key decisions, and next actions. Discard exploration; preserve decisions.

## Fidelity rules

- **6 个固定节一个不删**：某节无内容写 `（无）`。
- **精确字符串逐字保留**：路径、命令、错误信息、标识符、签名。

## Where to save

Per `ARTIFACT-FORMAT.md` §Handoff files (installed: `~/.claude/skills/ARTIFACT-FORMAT.md`; repo: `engineering/ARTIFACT-FORMAT.md`):

- **Feature-scoped work** → `.scratch/<feat>/handoff.md` (rolling — overwrite in place each time; git keeps history).
- **Cross-feature work** → `.scratch/handoff.md` (a single rolling file at the `.scratch/` root).

Do **not** use the OS temp directory. If not inside a git repo, fall back to the working directory root.

## Rolling mode (unattended runs only)

In autonomous runs (`/tdd -p` waves, overnight batches), overwrite-in-place at each batch close with a **fixed mini-refresh touching every section that moved** (~6–8 lines, seconds):

- §1 one status line · §2 one baseline line (re-stamp `git_base` in frontmatter too) · §3 the current next fork · §5's first boot action · §4 any new decisions/invariants · §6 any newly discarded approach
- Heavy detail stays in its artifacts (completion records, issues, commits); the handoff carries pointers and deltas only (What-not-to-duplicate).
- Sufficiency bar: a **cold session crash-lands mid-task** → this file plus the artifacts it names must be enough to continue. §2 and §6 are what a delta most easily starves — never skip them.

The final `/handoff` verifies and tops up the existing file instead of recompressing the session. Interactive sessions never auto-invoke — the user sees the context level and calls `/handoff` at the smart-zone boundary.

Every handoff carries YAML frontmatter:

```yaml
---
type: handoff
feature: balance      # the feature slug, or null for cross-feature work
git_base: 3451766     # `git rev-parse --short HEAD` at write time
status: active        # active when written; /resume sets consumed when the bridged work finishes, not at pickup
date: 2026-06-18
---
```

## What not to duplicate

Content already captured elsewhere (PRDs, plans, ADRs, issues, commits, diffs) — reference by path or URL, do not copy the body.

## Redact

Remove any sensitive information: API keys, passwords, tokens, PII.

## Output structure (6 fixed sections)

```markdown
# Handoff: <topic> (<date>)

## 1. 当前状态
Where we are + key artifact paths and their status. One sentence that tells someone "how far we got".

## 2. 基线
git HEAD (commit hash), working directory cleanliness, key file list relevant to this work.
If this work changed the **shape** of a module (moved a seam, introduced/removed an invariant, altered
how things wire up), the `CODEBASE.md` block for that area is now stale — refresh it via `/zoom-out`
before handing off, or note here that it needs refreshing, so the next session's session-start load
(which compares each section's `git_base` to HEAD) hands over a map aligned with the code, not one a
commit behind. Skip this if the work touched no structure — don't run `/zoom-out` for its own sake.

## 3. 下一步分叉
Candidate options for the user / next session to decide (A / B / C) with tradeoffs. If the path is already decided, state the next concrete step.

## 4. 关键口径清单
Decisions and invariants that must survive across sessions. Each entry includes a "why".
- Decision: … | Why: …
- Invariant: … | Why: …

## 5. 开机动作序列
First ordered actions after /clear (which files to read, which command to run, what to confirm first).

## 6. 明确不写的
What was actively discarded (dead-end explorations, failed approaches) — let the user do a final scan to confirm nothing critical was dropped.

## Suggested skills
Skills appropriate for the next session (e.g. `/tdd`, `/diagnose`, `/grill`), one sentence each on why.
```

Section 4 is the core. If the user passed arguments, treat them as the focus of the next session and tailor the document accordingly.

## Done criteria

Report the saved path and `git_base`; confirm §1 and §5 are non-empty before finishing.
