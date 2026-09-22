---
name: tidy
description: >-
  Use when the user wants engineering status, temporary-file cleanup, or legacy-artifact normalization. Derives outstanding obligations from contracts and evidence, and removes only proven disposable outputs through their storage owner.
argument-hint: "[inspect|-old] [feature]; default to the current goal"
---

# Tidy

Contracts, proof and raw review records determine remaining obligations. The host owns runtime
status; the storage owner owns deletion. Tidy creates no summary state or task ledger.

## Inspect

- `/tidy [feature]`: inspect and clean proven disposable outputs in scope.
- `/tidy inspect [feature]`: report/preview only.
- `/tidy -old <feature|repo>`: normalize historical artifacts in explicit scope.
- No identifiable goal: survey only. Whole-repository cleanup needs that scope.

Use `workflow-state.py survey ROOT --format human` or `inspect ROOT FEATURE --format human`.
These projections cover Issue readiness and validated completion; they do not enumerate all review
or human obligations. Also read the scoped PRD/Issue manual checks and referenced review objects,
raw decisions and feedback. For a scope without an index, inspect only its candidate-review and
human-decision JSON records, validate their references, and match decisions by review digest.
Report readiness gaps, invalid/missing proof, pending fixed-object reviews, unresolved feedback
and human-only checks separately. Query native task state for active use; do not copy it into cards.
Engineering `done` is not delivery acceptance.

## Retain or delete

Keep pending reviews, accepted snapshots, delivered versions, proof dependencies, referenced logs,
regression tests/fixtures and useful tools/experience. If native storage lacks sufficient retention,
export required bytes to project evidence and verify hash/reference closure; do not copy sessions.

Delete only proven disposable output with no retention reference and no active user/producer. The
storage owner must exclude new references/use between final check and deletion and recheck path/content
identity. Without that guarantee, retain the shared object as a cleanup candidate. Age, directory name,
ignored status, card completion or idle locks are insufficient. Add no global Cosmos registry.

Use storage-native or existing project cleanup facilities. Cleanup authorization covers proven
disposable deletion. Report actual paths removed and retention/failure reasons. Do not run tests,
builds, browsers or models for cleanup. Tracked code/test retirement is normal engineering work.

## Legacy normalization

Keep original proof before changing references. Historical managed proofs need intact digests,
contracts, logs and dependency closure, read without launching old runtime. Migrate portable proof
only with verified closure. Active old writers finish under their owner or hand over explicitly at a
quiescent boundary; never automatically kill/reopen/delete them because their format is old.

Normalize only unassigned open cards to Parent pointers and controlling constraints under
[ISSUE-TEMPLATE.md](../spec/ISSUE-TEMPLATE.md). Done contracts and accepted snapshots stay immutable.
PRD anchoring/changed requirements use `/spec`; Tidy never creates approval. Continuation notes from [handoff](../handoff/SKILL.md), including older notes, may retain necessary
facts but receive no publish/consume state. Keep them until the remaining facts have owners or
are no longer needed; session recovery alone does not make a note disposable. Remove legacy SUMMARY only after
its required facts/references have real owners.

For test cost, read [TEST-POLICY.md](../TEST-POLICY.md) and existing measurements; report slow groups,
repeated candidate runs and mixed results without rerunning/deleting tests. Continue authorized work.
