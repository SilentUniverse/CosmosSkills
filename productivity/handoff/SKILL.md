---
name: handoff
description: Write one compact, integrity-stamped bridge for unfinished work that must cross a session boundary. Use before /clear at the smart-zone edge or for an unattended batch checkpoint; never summarize completed work.
argument-hint: "What must the next session continue?"
---

# Handoff

Write the smallest state packet from which a cold session can execute the next action. This is not a
conversation summary. Preserve decisions and exact replay strings; discard exploration and narration.

## When and where

- Feature work → `.scratch/<feat>/handoff.md`.
- Cross-feature work → `.scratch/handoff.md`.
- Interactive work writes only on explicit `/handoff`; unattended batches may overwrite at wave close.
- Finished work gets no handoff. Never use an OS temp directory.

## Input budget

Use session context to preserve the objective, authorization, and unresolved work. Read current
`git status --short`, the active issue/plan, and artifacts required by the next action. Reopen
earlier context only to recover a missing decision; reference supporting logs and diffs by path.

Run `python <handoff-skill-dir>/scripts/handoff-state.py snapshot <repo-root>` once
(`python3` only when `python` is absent). Copy its
`git_base` and `worktree_digest` exactly into frontmatter. The digest tracks product drift only:
it excludes handoff files and workflow-internal writes (preflight cache, wave ledger, execution
receipts). Evidence integrity is the artifact gate's job, not the digest's; overwriting this
bridge or replaying a preflight does not invalidate the baseline.

## Format

```markdown
---
schema_version: 2
type: handoff
feature: <slug|null>
capsule: active-work
git_base: <short HEAD>
worktree_digest: <sha256>
status: active
date: YYYY-MM-DD
---

# Handoff: <topic>

## Continue
1. READ `<minimum exact paths>`
2. RUN `<exact bounded command>`
3. CONFIRM `<observable predicate>`; THEN `<next edit/decision>`

## State
<objective still owed + current node + pointers to authoritative artifacts/evidence>

## Decisions
- <decision, authorization, or invariant> — <scope and constraint a future agent must preserve>

## Avoid
- <failed or rejected path> — <evidence>; omit this section when empty
```

`Continue` is machine-facing execution input: terse, ordered, exact. `State` and `Decisions` are the
human review surface: plain language, only facts that affect the next choice. Never duplicate PRDs,
issues, ADRs, completion records, receipts, logs, commits, or diffs.
`CONFIRM` means observe the predicate, not request user approval. The chain is an entry to the
remaining objective; finishing its first action does not complete that objective.

`capsule` sets what resume does first:

- `active-work` (default) — mid red-green or a dirty worktree; `Continue` is the entry.
- `awaiting-alignment` — blocked on a human decision; `Decisions` carries the open question and,
  when no PRD exists yet, the latest Design Receipt (the sole body-copy exception); `Continue`
  starts by checking whether that question is still unresolved, then asks only if needed. Name
  independent work that can continue while the answer is pending.
- `external-pending` — waiting on an external task or result; `State` names it and its recovery
  condition.

## Rolling update

Update only fields that moved: restamp both baselines, replace `Continue`, advance the one-line
`State`, and add only new non-derivable decisions or failed paths. Do not append history.

## Safety and done

Preserve paths, commands, errors, identifiers, and signatures byte-for-byte. Remove secrets and PII.
Before returning, confirm `Continue` has a READ/RUN/CONFIRM chain and the snapshot values match the
written frontmatter. Report only path, `git_base`, and the first action.
