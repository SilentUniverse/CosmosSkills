---
name: resume
description: >-
  Use when starting a fresh session to continue unfinished work from a handoff note, a feature, or the previous session. Rebuilds the next action from Git, FEATURE.md and the note, verifies drift, and continues.
argument-hint: "[handoff path or feature]"
---

# Resume

This is the Cosmos skill; a host's native session command of the same name does not load it.
The note and history are leads; the repository is the truth.

1. **Locate.** Use the given path or feature; otherwise the single matching
   `.scratch/<feat>/handoff.md` or `.scratch/handoff.md`. Ask only when several notes compete for
   the requested goal. No note is fine: Git and FEATURE.md may already be enough.
2. **Re-ground.** Read the note, then `git status`, `git log --oneline -10`, and for a feature
   `python ../workflow-state.py survey <root> --feature <feat>`. Compare the note's HEAD and dirty
   files with reality; trust the repository where they differ and say what changed.
3. **Check before writing.** `survey` already re-validates done units and their pinned logs. Rerun a
   check only when the working tree differs from the note or last checkpoint commit, or the note
   names a check as unverified. A failure is the first thing to fix.
4. **Continue** with the note's next action, or the next ready unit. Prior approvals are valid only
   through their original record or the user's words, never a summary.

Delete the note once its remaining facts have owners or are done; another boundary writes a fresh
one through [handoff](../handoff/SKILL.md).
