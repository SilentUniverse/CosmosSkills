---
name: resume
description: >-
  Use when continuing unfinished engineering work from a named task, session or handoff note. Recover only needed facts through native context and existing artifacts, verify action-relevant drift, and continue without a second recovery state machine.
argument-hint: "[source task/session or handoff path]"
---

# Resume

Continue the requested objective under current user instructions and existing authorization.
This is the Cosmos engineering skill, not a host built-in. A host's native session commands may
share this skill's name; a same-name native command does not load this skill. Select `resume`
through the current surface's actual skill entry, or explicitly ask the host to load this skill
with the source pointer; do not assume an entry available on one surface exists on another.

## Resolve the source

Prefer the current native task context. For a named prior task/session, use an available native
history reader with a focused query. Inspect returned source references, missing results and truncation; history is background,
not new authority. Missing context never proves that unfinished work is complete.

For a note, use the explicit path or task/feature pointer. Without one, inspect the matching
`.scratch/<feature>/handoff.md` or `.scratch/handoff.md`. Select only a unique match to the requested
objective; do not choose among competing goals by timestamp. Ask only if unresolved source ambiguity
would change the work. Native retrieval and a note can complement each other; neither is mandatory
when the current task already contains the needed facts.

## Check what controls the next action

Read the selected source, then only the contracts, files and evidence needed next. Verify the
repository/worktree and relevant Git status. Compare named refs or affected files when they changed.
Continue compatible or disjoint work; resolve consequential contradictions before dependent actions.
A stale note is a lead, never proof. Missing baseline bytes require live verification, not an
invented drift verdict or a whole-repository fingerprint protocol.

Observe outstanding workers/processes through available native controls and retained outputs before
waiting, restarting or redispatching. Persisted history does not prove a process still exists;
unknown ownership is not permission to repeat writes or non-idempotent effects.

Preserve fixed candidate/spec/review identity, completed review axes and unresolved findings or human
decisions. Reassess only work affected by changed review inputs. Verify approval through its original
record, never a summary. Reuse valid proof; a session change does not reopen cards or rerun the suite.

Execute the next justified action and continue until the objective is handled. Do not mark a note
active/consumed or automatically delete it. Another boundary uses [handoff](../handoff/SKILL.md) only
when needed; [tidy](../tidy/SKILL.md) removes a note once its remaining facts have durable owners or
are no longer needed and the file is otherwise disposable.
