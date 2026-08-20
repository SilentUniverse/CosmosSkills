---
name: resume
description: Resume work from the most recent handoff. Finds the active handoff under .scratch/ by frontmatter, verifies the git baseline still matches, then executes its 开机动作序列. Use at the start of a new session to continue a multi-session task without hunting for the handoff file. Self-invoke when a session starts with an active handoff present and the first message (or orchestrating prompt) is a continuation cue; never when the user signals a fresh start.
argument-hint: "Feature slug (optional; omit to use the latest active handoff)"
---

# Resume

The inverse of `/handoff` — locate the active handoff, verify its baseline, continue from its 开机动作序列.
Handoffs live under `.scratch/` (feature-scoped `.scratch/<feat>/handoff.md` or cross-feature
`.scratch/handoff.md`); frontmatter per `ARTIFACT-FORMAT.md` (installed: `~/.claude/skills/ARTIFACT-FORMAT.md`; repo: `engineering/ARTIFACT-FORMAT.md`).

## Invocation

- `/resume` — locate the most recent `status: active` handoff and continue from it.
- `/resume <feat>` — continue from `.scratch/<feat>/handoff.md`.

## Process

### 0. Orientation is already loaded — don't re-own it

CLAUDE.md §6 loads the orientation layer at session start, before `/resume` runs. So `/resume` only
*layers a handoff on top* — don't re-load or re-explore what orientation already gave you.

### 1. Locate the handoff

- `/resume <feat>` → read `.scratch/<feat>/handoff.md`.
- `/resume` (no arg) → scan `.scratch/**/handoff.md` for `status: active` and pick the newest by
  `date` (tie-break on file mtime). If none is `active`, tell the user there's nothing to resume and
  stop — a stray non-`active` handoff is legacy; confirm explicitly before touching it. (Step 0 has
  already run, so even with no handoff the session is oriented — say so.)

### 2. Verify the baseline

Compare the handoff's `git_base` against current `git rev-parse --short HEAD`.

- **Match** — clean continuation; proceed.
- **Diverged** — commits landed since the handoff was written. Warn the user and show
  `git log --oneline <git_base>..HEAD` so they can see what changed, then ask whether to proceed.
  The handoff's "关键口径清单" may be stale relative to those commits.
- **Unknown revision** — `git_base` no longer resolves (rebase / force-push / branch switch). Show
  `git reflog -15`, ask the user which commit to anchor to, offer to rewrite `git_base` before
  continuing.

Also check working-tree cleanliness; if dirty, surface `git status` briefly before acting.

### 3. Execute the 开机动作序列

Read the handoff's six sections. Section 5 (开机动作序列) is the script: read the listed files, run
the listed commands, confirm the stated first decision. Section 4 (关键口径清单) is the load-bearing
context — treat those decisions and invariants as binding. Don't re-explore what the handoff already
decided. Confirm any claim you're about to act on (a test passes, a file exists, a command works)
against the workspace first — the handoff is a bounded handoff, not truth.

If the handoff names a feature, also glance at its live working set:
`rg '^status: ready' -g '*.md' -g '!**/archive/**' .scratch/<feat>/issues`.

### 4. Delete the handoff when the work is finished

Once the work reaches a natural stopping point (issue `done`, or the user starts something else),
**delete the handoff file** — one handoff, one consume. If the session runs long and needs a fresh
handoff, write a new one via `/handoff`; one live handoff per feature at any time.
