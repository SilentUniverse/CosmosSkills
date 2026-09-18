# Managed batch proof, budget and close

Loaded at durable-proof export or migration, budget exhaustion, terminal gc, or managed batch
close. Execution and admission live in [BATCH-FORMAT.md](BATCH-FORMAT.md); review and delivery in
[BATCH-REVIEW.md](BATCH-REVIEW.md).

## Durable proof and owned temporary files

Schema 3 publishes `.scratch/FEATURE/receipts/managed/PROOF.json` and its hash-addressed object closure.
It includes the contract text, requirement/manual bodies, actual jobs, receipt/logs and consumed
proof/decision evidence. It can be copied with the feature's history and verified without batch
runtime directories. It is historical proof, not a way to resume an active batch in another clone.
`batch-proof-export` explicitly publishes portable copies of retained managed proofs; missing or
corrupt evidence prevents migration. Retain the originals until the copy verifies.

Temporary files created for an issue belong under its owned feature scratch directory. Register
`{path, owner, purpose, lifecycle: temporary|asset|evidence|delivery, references: []}` through
`artifact-register ROOT FEATURE --record FILE`; release the finished producer with
`artifact-release ROOT FEATURE --owner OWNER`. A shared consumer releases only its own `--consumer`.
Managed terminal check scratch, including private restored dependencies, is registered automatically.
Shared developer dependency directories, tracked tests, issue history and durable receipts are not
transient GC. Unknown root-level files require explicit classification, never age-based deletion.

`gc ROOT FEATURE --apply` rechecks consumers, process state and file identity under the workflow
lock, persists unlink intents before deletion and reports actual removed bytes plus retained reasons.
Stage/close cleanup does not run product tests or models. Completed portable-proof batches allow
obsolete feature wave/preflight caches to be collected. Exported releases and proof objects have
conservative durable retention: approval never makes a possibly running application disposable.
Direct human launches need no process scan or lease to remain protected.

## Budget continuation

`batch-budget --interactive --limits FILE --reason TEXT` permits an actual operator to raise limits
without discarding the goal or prior consumption. FILE contains `dispatches`, `runs`, `seconds`.
A pinned host may instead supply a signed `--event` with batch_id, plan_digest, action=extend_budget,
limits, reason, decision_id and expected_revision. The retained event binds all increases; replay
is idempotent, changed payloads/lowered limits/stale revisions fail, and holds remain in force.

## Managed completion record (protocol 2)

An assigned schema-2/3 batch uses `check-local` for development feedback, then yields the complete
execution to the controller. Local green or worker exit never marks an issue done. The controller
runs the accepted checks on the frozen candidate and writes this completion form only after their
executed receipts cover the issue AC and current contract:

```markdown
### 完成 — YYYY-MM-DD

- managed-proof: <proof_sha256>
```

The proof object binds the issue reference, behavior/profile digests, candidate, named verifiers,
AC union, run IDs and immutable receipt/log hashes. `validate_v3_completion` resolves this shape
through `workflow_members.validate_proof`; editing the line cannot create evidence. It is an
alternative to the legacy v3 receipt-reference form in
[COMPLETION-RECORD.md](COMPLETION-RECORD.md), not an additional receipt to invent. Final
combined checks and required operator observations remain batch obligations after issue completion.
Only active-batch failed-verification recovery may reopen its completed members. Follow
[BATCH-FORMAT.md](BATCH-FORMAT.md) for the controller commands and retained evidence.

Schema 3 also publishes a portable proof pointer under
`.scratch/<feature>/receipts/managed/<proof_sha256>.json` with a complete local object closure.
It retains actual contract and requirement text, manual steps, jobs, results/logs, upstream proof
and decision events. Copy that directory with the issue history before dropping execution caches.
External completed dependencies retain their original contracts and validated completion payloads;
available managed proof closures are copied too. A legacy done declaration without machine proof
remains a historical premise, not an upgraded verification claim.
Proof verification checks bytes and AC coverage; it does not assert the same outcome on changed
source. An absent or damaged closure keeps the original evidence retained and reports the gap.
