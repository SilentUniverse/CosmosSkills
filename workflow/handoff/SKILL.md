---
name: handoff
description: >-
  Use when unfinished work must cross a session boundary, before clearing context, or at an unattended batch checkpoint. Writes one compact, integrity-stamped continuation bridge and excludes completed work.
argument-hint: "What must the next session continue?"
---

# Handoff

For an active protocol-2 batch, retain its batch ID, frozen runtime entry and unresolved action as pointers; do not copy its proof history. Resume through [BATCH-FORMAT.md](../tdd/BATCH-FORMAT.md).

Write the smallest state packet from which a cold session can execute the next action. This is not a
conversation summary. Preserve decisions and exact replay strings; discard exploration and narration.

## When and where

- Feature work → `.scratch/<feat>/handoff.md`.
- Cross-feature work → `.scratch/handoff.md`.
- Write when requested or when unfinished state must cross a real session boundary, including an
  unattended runner that cannot continue its native session.
- Finished work gets no handoff. Never use an OS temp directory.

## Input budget

Use session context to preserve the objective, authorization, and unresolved work. Read current
`git status --short`, the active issue/plan, and artifacts required by the next action. Reopen
earlier context only to recover a missing decision; reference supporting logs and diffs by path.
Without an issue, retain the remaining goal, acceptance checks, current authority, minimal code
relationships, and validation pointers here. Transfer verified reusable knowledge to its existing
retrieval surface before consuming the handoff; completed exploration has no place in the bridge.

For creation, run
`python scripts/handoff-state.py new <repo-root> <draft-path> --feature <slug> [--capsule <type>]`
once (`python3` only when `python` is absent). It writes the draft skeleton below with the current
`git_base` and `worktree_digest` already stamped and reports the `target` and the version to pass as
`--expected`; fill the body only and never hand-copy hashes. For a rolling update, snapshot both
baselines before editing the draft. The digest tracks product drift only:
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
- PRD: `<governing PRD path + its R/D/S anchors when present>`
- active: `<the one active issue/plan file>`
- remaining: `<slices/issues still owed>`
<one line on the objective still owed, only if the pointers cannot say it>

## Decisions
- <decision, authorization, or invariant> — <scope and constraint a future agent must preserve>

## Avoid
- <failed or rejected path> — <evidence>; omit this section when empty
```

`Continue` is machine-facing execution input: terse, ordered, exact. `State` is the anchor block —
one pointer line each for the governing PRD, the active issue, and the remaining work; narrative
history stays out. `Decisions` carries only decisions not yet recorded in a PRD, issue, or ADR;
once a decision lands in its authoritative artifact, the next rolling update drops it. `Avoid`
names the failed path and its evidence pointer, nothing else. Never duplicate PRDs,
issues, ADRs, completion records, receipts, logs, commits, or diffs; reference them by path.
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

Update only fields that moved: snapshot both baselines, replace `Continue`, advance the one-line
`State`, and add only new non-derivable decisions or failed paths. Drop a decision line once its
PRD/issue/ADR records it. Do not append history. Read the
current version and baselines with
`python scripts/handoff-state.py snapshot <repo-root> --path <handoff-path>`.
Write the draft under `.scratch/tmp/`, then publish it through the version check:

```text
python scripts/handoff-state.py publish <repo-root> <handoff-path> --expected <version> --source <draft-path>
```

The helper verifies the draft baseline, stamps a new generation, and atomically replaces only the
observed handoff version. A changed version or baseline requires reconciliation; never retry by
blindly copying the new hash. Remove the consumed draft. Do not overwrite the target directly.

## Safety and done

Preserve paths, commands, errors, identifiers, and signatures byte-for-byte. Remove secrets and PII.
Before returning, confirm `Continue` has a READ/RUN/CONFIRM chain. `publish` already stamped the
baseline into the frontmatter, so do not re-verify it by hand. Report only path, `git_base`, and the
first action.
