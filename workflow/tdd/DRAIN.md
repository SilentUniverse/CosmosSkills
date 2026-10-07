# Complete an authorized ready scope

Load for `/tdd <feature>` or an explicit request to complete several Issues. The ordinary host
session executes the work; Cosmos selects engineering work without a runtime queue or ledger.

Use `workflow-state.py survey ROOT --format human`, then `packet` or read-only `start`. Restrict
selection to authorized scope, `blocked_by`, accepted Spec anchors and concrete readiness gaps.
`ready` is not a running status. Resolve failures at their root cause; create a Repair Issue only
for an independent durable engineering gap.

## Native execution

Do bounded work inline by default. Independent work may use native tasks: pass the
`workflow-state.py start` packet plus any controlling constraint it does not already carry
directly as the worker's input; do not re-transcribe it into a separate dispatch brief.
The worker does not re-read the full issue, shared verifier or PRD unless it must resolve an
ambiguity, a newly discovered dependency, or a changed contract. A delegated worker validates
readiness evidence without silently changing the contract, coordinates scope expansion before
writing another task's files, returns exact command/result, proof paths, changed paths and
remaining gaps, and writes completion only when assigned. The host owns task waiting,
cancellation, retries, notification and resume.

- Overlapping writes in one checkout serialize; an actor or Promise does not isolate files.
- Independent checkouts use a native entry that actually supports their cwd.
- Shared devices/databases/ports use the project's fixture, resource service or CI. Verify exclusion
  and health after abnormal termination; an idle lock does not prove recovery.
- Missing isolation restricts the affected operation; do not create a Cosmos resource registry.

Use [TEST-POLICY.md](../TEST-POLICY.md), read matching evidence first, and keep check inputs stable.
A shared check may prove several cards. Fix the delivery candidate before combined checks/review;
Issue completion, session restart and approval do not automatically launch a full suite.

## Integrate

Inspect returned proof and owned diffs, resolve shared-file conflicts, and check the resulting
changed inputs. Complete cards through `close --evidence/--candidate`
([COMPLETION-RECORD.md](COMPLETION-RECORD.md)): the worker returns proof references and the explicit
AC mapping; the tool generates the record. Native task
completion is an observation, not acceptance; unknown outcomes remain unknown.

Continue independent authorized work while a fixed candidate awaits human review. Report remaining
engineering and human obligations separately. Preserve old proof, use Spec lineage for changed
contracts, then Tidy and any requested submission flow. Write no drain-specific recovery state.
