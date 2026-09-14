---
name: tidy
description: >-
  Use when the user wants workflow status or temporary work files cleaned up. Shows outstanding engineering and human obligations, deletes proven disposable artifacts, and preserves tests, experience and retained releases.
argument-hint: "[inspect] [feature]; default to the current goal"
---

# Tidy

Owns current-state projection and temporary-file cleanup. Product changes, test deduplication and
requirement lineage belong to normal implementation or Spec.

## Invocation

- `/tidy [feature]`: inspect and clean the named feature or current goal's proven disposable files.
- `/tidy inspect [feature]`, or an explicit inspect-only request: show state and preview, without deletion.
- With no identifiable current goal, survey only. Whole-repository cleanup requires explicit scope.

Use `workflow-state.py survey ROOT --format human` or `inspect ROOT FEATURE --format human` for
current reality. Show pending readiness, technical/decision blockers, fixed review requests and
unresolved feedback even when related issues are done. History is available on demand; no SUMMARY
copy is generated. Completed issue cards remain available outside the compact active frontier.

## Actual cleanup

Use `workflow-state.py gc ROOT FEATURE` to inspect candidates, then `--apply` for an authorized cleanup.
The cleanup request already authorizes proven disposable files; do not ask for individual approval.
Report actual removed paths/count/bytes and concrete retention or failure reasons.

Register temporary outputs where created, using `artifact-register ROOT FEATURE --record FILE`.
The record names path, owner, purpose, lifecycle and references. Use an execution-owned feature
scratch directory for probes; managed verification records its scratch outputs automatically.
Use `artifact-release ROOT FEATURE --owner OWNER` after the producer is finished. Shared consumers
release their own references with `--consumer REF`. Never infer disposability from age, extension,
ignored/untracked status or a directory name.

Keep regression tests, fixtures, useful scripts and hard-to-recover test experience at their project
owners. Retain complete proof dependencies, unresolved feedback evidence, pending reviews and promised
historical releases. An accepted review does not release an application still being used.

Apply rechecks file identity, content, active ownership and consumers under the publication lock.
Changed, unowned, linked, tracked or still-referenced files are retained. Known temporary files are
actually deleted; only empty owned directories are removed. A damaged unrelated feature must not
block independently safe cleanup; damaged shared ownership evidence retains its affected candidates.
GC does not launch product tests, builds, browsers or model calls. Tracked code/test deletion is a
normal change with appropriate validation. TIDY never reopens issues or changes accepted behavior.

When asked about test growth/cost, use [test policy](../TEST-POLICY.md) to summarize existing receipts.
Show slow groups, repeated runs and instability/retirement candidates as engineering work; do not
run tests, classify semantic duplicates from filenames, or delete tests through GC.

## Timing and recovery

Implementation registers outputs and releases them when finished. Delivery boundaries perform local
cleanup; users need not invoke TIDY after every issue. Resume the caller's authorized work afterward.
If runtime/ownership evidence is unavailable, report retained files and missing evidence. Never report
hidden history as deleted files. Interrupted deletion resumes from its durable per-file journal.
