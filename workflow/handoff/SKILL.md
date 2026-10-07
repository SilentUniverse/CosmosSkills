---
name: handoff
description: >-
  Use when the user asks to hand off unfinished work or a session boundary would lose necessary engineering facts. Prefer native context and existing artifacts; write a compact continuation note only when needed, without managing session recovery.
argument-hint: "[task or feature] [note path]"
---

# Handoff

Keep the remaining objective executable by its next owner. Same-task compaction and reopening use
the host's native context and session recovery; neither alone requires a note or a skill transition.

## Select the bridge

Use the source task/session reference and existing engineering artifacts when the destination can
read them. When the destination host provides a native history reader, use it with a
focused query; a session reference alone does not inject its history. Verify the reader is
available in the destination.

Write a note when explicitly requested, when crossing hosts without accessible history, or when
necessary unfinished facts have no retrievable owner. Use the requested path; otherwise use
`.scratch/<feature>/handoff.md`, or `.scratch/handoff.md` for work without a feature. Concurrent
unrelated work uses distinct named paths. Inspect an existing note before updating it; preserve
another task's unfinished obligations. Completed work needs no continuation note.

## Preserve only what is needed

Read the active contract and relevant Git status. Include only populated fields:

- Source task/session and repository/worktree identity; current HEAD when useful for later comparison.
- Remaining objective, existing authorization and unresolved decisions not recorded elsewhere.
- Exact pointers to governing contracts, necessary dirty files, retained evidence and next inputs.
- Next action and its observable success condition.
- Outstanding worker/process/review obligations with existing IDs, output references and fixed
  review inputs. Record observed state as an observation, never a promise that work is still alive.

Reference owned facts instead of copying Spec, Issue bodies, transcripts or approval summaries.
For pending review, preserve candidate/spec/review identity and raw decision pointers; a note cannot
approve an object. Exclude secrets. Do not launch, stop or recreate work merely to write the note.

Update the selected note in place: no journal, snapshot, marker, lock or recovery helper. Report
the exact source/note and the first continuation action, then leave session lifecycle to the host.
A handoff-only request ends with this bridge; a caller needing a mid-work checkpoint gets no
invented pause or second owner.

Use [resume](../resume/SKILL.md) when the destination needs to reconstruct the next engineering action.
