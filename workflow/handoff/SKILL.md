---
name: handoff
description: >-
  Use when the context window is filling up or the user ends a session with work unfinished, so a fresh session can continue. Checkpoints progress into Git and existing artifacts first; writes a short continuation note only for facts that have no other owner.
argument-hint: "[task or feature] [note path]"
---

# Handoff

Long work spans many sessions because context is finite. A fresh session must be able to take the
next correct action from durable state alone, without the old transcript. Hand off at a natural
boundary (a unit closed, a decision made) before the window is nearly exhausted, not mid-edit.

## 1. Checkpoint into owners that already exist

- **Feature route.** Close every finished unit and commit it locally. FEATURE.md (unit status,
  completion records, 变更记录) plus `git log` is the progress record; nothing else is needed.
- **Inline route.** Leave work in the working tree; commit only with existing authorization
  (`/pr`). Never stash or rewrite it. Record in the note which changes are verified.
- **Decisions.** A decision the user confirmed in this session belongs in its owner (FEATURE.md
  anchor, ADR, `CONTEXT.md`) when a later step depends on it; otherwise it goes in the note.

Feature-unit commits are local checkpoints; push only when requested.

## 2. Write the note only for the remainder

Write `.scratch/<feat>/handoff.md`, or `.scratch/handoff.md` without a feature (a requested path
wins; parallel unrelated work uses distinct names). Overwrite the previous note for the same work;
it is a pointer card, not a journal. Include only populated lines:

```markdown
# Handoff — <goal in one line>
- 目标：<remaining outcome and constraints the user stated in this session>
- 状态：<HEAD sha; feature + next ready unit, or the dirty files that matter>
- 下一步：<the single next action and how to tell it succeeded>
- 已定：<confirmed decisions not yet recorded elsewhere>
- 待定：<open questions for the user>
- 注意：<findings that would otherwise be rediscovered: dead ends, failing commands, traps>
```

Point to files, units, commits and logs instead of copying them. Exclude secrets. Skip the note
entirely when Git and FEATURE.md already say everything above. Report the note path (or "no note
needed") and the first command the next session should run; do not end or restart the session.

The next session continues through [resume](../resume/SKILL.md).
