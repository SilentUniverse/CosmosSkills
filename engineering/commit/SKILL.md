---
name: commit
description: Create one git commit from the session's validated changes. Use when the user says /commit or asks to commit or submit; every other skill stops at validated changes and hands off here.
---

# Commit

The single submit entry (per `~/.claude/CLAUDE.md` §4). Ordinary coding, planning, and
review skills stop at validated changes; this skill is what submits them.

## Context

Read all four before staging anything:

- `git status`
- `git diff HEAD`
- `git branch --show-current`
- `git log --oneline -10`

## Task

Create a single git commit.

Stage and commit in one message: `git add` the files this change touched, then `git commit`.
Only `git add`, `git status`, and `git commit` run here; pushing is not part of this skill.
Match the message shape of the recent history: `type(scope): summary`, imperative, English.

Report the hash and the files staged; nothing follows the commit.
