---
name: tidy
description: >-
  Use when the user wants engineering status, a catch-up since a commit or date, temporary-file cleanup, or legacy-artifact normalization. Derives outstanding obligations from contracts and evidence, and removes only proven disposable outputs through their storage owner.
argument-hint: "[inspect|-old|since <commit|date>] [feature]; default to the current goal"
---

# Tidy

Contracts, proof and raw review records determine remaining obligations. The host owns runtime
status; the storage owner owns deletion. Tidy creates no summary state or task ledger.

## Inspect

- `/tidy [feature]`: inspect and clean proven disposable outputs in scope.
- `/tidy inspect [feature]`: report/preview only.
- `/tidy -old <feature|repo>`: normalize historical artifacts in explicit scope.
- `/tidy since <commit|date>`: catch-up summary only; see Since.
- No identifiable goal: survey only. Whole-repository cleanup needs that scope.

Use `workflow-state.py survey ROOT [--feature FEATURE] --format human`.
It covers unit readiness and validated completion; it does not enumerate all review
or human obligations. Also read the scoped FEATURE.md 端到端验证 checks and referenced review objects,
raw decisions and feedback. For a scope without an index, inspect only its candidate-review and
human-decision JSON records, validate their references, and match decisions by review digest.
Report readiness gaps, invalid/missing proof, pending fixed-object reviews, unresolved feedback
and human-only checks separately. Query native task state for active use; do not copy it into units.
Engineering `done` is not delivery acceptance.

## Since

`/tidy since <commit|date>` is read-only: no deletion, file or state. It gathers three sources from
that point on: `git log` (each change merged, local-only or still open), `待确认` lines in
`.scratch/*/DECISIONS.md` not corrected by a later line, and pending human reviews (the survey above
plus each `ACCEPTANCE.md` 需要你看的地方). It reports three blocks:

- **改了什么**: one plain sentence per change on what it changes for the user, with its state.
  Hashes, paths and counts appear only when the user needs them to act.
- **等我决定的**: each item with the decision, a recommendation, its evidence and risk. Write 没有
  when none exist; never invent one.
- **风险与缺口**: unverified results, 未证实 safety facts, missing evidence and sources that could
  not be read.

## Retain or delete

Keep pending reviews, accepted snapshots, delivered versions, proof dependencies, referenced logs
(every `runs/` log or receipt a done unit's 完成 record names), `.scratch/acceptance-log.md`, failed
`runs/` logs and receipts while the feature has units not yet done (`close` rejects a pass that a
known failed attempt contradicts), regression tests/fixtures and useful tools/experience. Other
unreferenced `runs/` logs, `.scratch/tmp/` scratch previews/probes, legacy `.scratch/show-*.html`
files, and `*.lock` files are disposable. If native storage lacks sufficient retention,
export required bytes to project evidence and verify hash/reference closure; do not copy sessions.

Delete only proven disposable output with no retention reference and no active user/producer. The
storage owner must exclude new references/use between final check and deletion and recheck path/content
identity. Without that guarantee, retain the shared object as a cleanup candidate. Age, directory name,
ignored status, unit completion or idle locks are insufficient. Add no global Cosmos registry.

Use storage-native or existing project cleanup facilities. Cleanup authorization covers proven
disposable deletion. Report actual paths removed and retention/failure reasons. Do not run tests,
builds, browsers or models for cleanup. Tracked code/test retirement is normal engineering work.

## Legacy normalization

Active old writers finish under their owner or hand over explicitly at a quiescent boundary; never
kill, reopen or delete them because their format is old.

Legacy planning files are folded into one FEATURE.md through `/cosmos-setup`. Done contracts and
accepted snapshots stay immutable. Changed requirements use `/spec`; Tidy never creates approval. Continuation notes from [handoff](../handoff/SKILL.md), including older notes, may retain necessary
facts but receive no publish/consume state. Keep them until the remaining facts have owners or
are no longer needed; session recovery alone does not make a note disposable.

For test cost, read [TEST-POLICY.md](../TEST-POLICY.md) and existing measurements; report slow groups,
repeated candidate runs and mixed results without rerunning/deleting tests.
