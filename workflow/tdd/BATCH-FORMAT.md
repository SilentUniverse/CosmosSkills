# Managed batches — `.scratch/batches/<batch_id>/`

Execution core for an active managed batch: plan semantics, dispatch, checks, admission and
job execution. Human review, revisions, delivery and manual observations load
[BATCH-REVIEW.md](BATCH-REVIEW.md) at their boundary; durable proof, budget and managed close load
[BATCH-PROOF.md](BATCH-PROOF.md).

## Incremental collaboration

Test trigger, quality, performance and retirement rules live in [test policy](../TEST-POLICY.md).
Jobs may declare `measurement_context` for comparable cost reports.

Open a managed batch for rolling plans, independent implementation during human review, versioned decisions,
and portable proof. This is the internal execution protocol for Spec/TDD/TIDY, not a fourth user entry.
A simple settled task may stay inline; open a batch when its coordination or retention is needed.

`pending` means an explicit readiness gap, recorded as `pending_reason`; it is never dispatchable.
`ready` means the engineering contract and verifier are prepared. Engineering dependencies, decision
dependencies, authorization and resources may still block dispatch. `done` means executed engineering
proof, separate from human acceptance. Pending cards retain their goal and dependencies even before
verifier preparation; restoring them takes priority when otherwise-ready consumers cannot run.

In addition to the common fields, a plan declares:

- `requirements`: `{id, body, checks}`. Bodies are retained, not only PRD links. Empty checks keep an
  uncovered requirement visible and prevent closure. A point may select requirement IDs through
  `requirements`; omitted means all requirement bodies form its contract. Each member receives
  its points' requirements as well as requirements mapped through its own checks. A combined
  integration check without issue refs cannot hide the point's requirements from its workers.
- Milestones: `version` defaults to 1; `scenarios` defaults to the point ID. Each scene has one review
  owner, and each point can combine several requirements and issues. The final point stays last.
- `decisions`: `{ID: {kind: choice|acceptance, version, instruction, point?}}`; acceptance references
  a review point. `member_decisions`: `{FEATURE/SLUG: [{id, version, equals}]}` expresses real
  consumption dependencies. Engineering and decision edges form one acyclic graph.
- `notification`: `{mode: parent_turn}` by default. An actual host adapter may use
  `{mode: host, argv: [...], deduplicates_event_id: true}`. The adapter reads one event as JSON on
  stdin, renders it with stable-ID deduplication, and returns `{acknowledged_event_id: ID}` on stdout.
  This acknowledgement records delivery, not reading or approval. The adapter is an explicitly
  configured external integration; a universal host/browser notification adapter is not bundled.
  Adapter mechanics and a sample live in [BATCH-REVIEW.md](BATCH-REVIEW.md).
- Optional `allow_inherit: true` plus complete `review_inputs` allows retaining a scene conclusion
  across source changes only when those inputs, the actual artifact, launch contract and tested
  environment match. Changed artifacts require review. If final uses another package producer,
  `final_checks: {SCENE_CHECK: FINAL_CHECK}` maps **every** required scene check to an executed final
  check; producer and artifact consumers must map to the actual final artifact. Missing mappings
  project `final_scene_checks_unmapped`; they cannot generate a green review.

The scheduler prioritizes preparing a ready delivery and completing checks for a captured candidate
before new implementation. A capture still needs the shared working tree's entire current wave to
return ([wave barrier](DRAIN.md#wave-barrier)). Once captured, its checks and delivery use immutable
inputs; independent workers can run in the original repository. There is no compulsory separate
coordinator agent.

`batch-run --background` admits a check, starts its frozen runner with a retained log and returns
without waiting for the check; a normal interactive harness calls `batch-run` and consumes the
returned actions at safe boundaries. `scripts/overnight.py` services mechanical progress and host
delivery while its implementation subprocess is busy; its lifecycle contract is
[DRAIN.md](DRAIN.md)'s External runner section, and its managed-batch diagnosis control lives in
the External runner integration section below.

Dispatch binds the assigned contract, applicable requirement bodies, upstream proofs and decision
events. `start`, an assigned `packet`, and `briefs` deliver those bindings in `execution_context`,
including decision instructions and values from the retained dispatch plan. The harness must pass
this packet to its worker; the ledger alone does not establish that an agent read it. Stale packets
are rejected. Run admission independently binds its checked inputs.
An in-flight decision change invalidates transitive consumers. A stale worker return goes back to
implementation for reconciliation; a stale run cannot supply proof. A binding-only invalidation can
be rechecked on unchanged source, but a real behavior failure remains a failure. New batches or
retries never refund the original goal's consumption.

## Executed checks and local candidates

Schemas 2 and 3 execute `jobs`, retain explicit untracked `inputs`, and enforce run/time budgets. A job declares `argv`, `timeout`, and a `result` adapter (`unittest`, `pytest`, `junit`,
`predicate`, `artifacts`, or `ui`). Every check has one job; no command is inferred from a check ID.
`batch-run` advances mechanical actions until completion or an implementation, repair, resource,
or human decision requires the harness. It does not start a model or claim a worker finished.

Both issue batches and verification-only batches (`members: []`) freeze inputs, execute checks in
isolated restorations, seal exact proof sets and close only on complete passing final proof.
Jobs bind `issue_refs` and `ac_map`; v3 cards also retain `verifier_names`, exact accepted argv/cwd,
AC mapping and actual preflight receipts. Readiness is required before admission; pending members with concrete readiness gaps are retained. A status
field alone does not establish completion or replace an executed proof.

Dispatch only the returned eligible members with the existing `start`/`dispatch` ownership path.
During implementation, `check-local --execution ID --member FEATURE/SLUG --request-id ID --job FILE`
executes a bounded local diagnostic job (`argv`, `timeout`, `result`) within that assignment. Each
RED/GREEN action consumes the original run/time budget. These receipts never enter final proof.
Local diagnostics cannot acquire shared resources or publish artifacts; those use planned jobs.
Use a fresh request ID for a new attempt; replaying an ID returns the original result.

Once the entire wave is terminal, `batch-yield --execution ID --continuations FILE` records
`{"source":{"kind":"inline|harness","reference":"actual terminal observation"},
"members":{"feature/slug":{"lane":"implement|verify","reason":"remaining work"}}}`.
Harness source also requires `execution: ID` and `terminal: {FEATURE/SLUG: {worker_id: ID,
status: completed|stopped}}` for every distinct worker. Old-execution and partial terminal results
are rejected. These are host observations; the CLI cannot authenticate arbitrary agent provider state.
Inline applies only to a direct single-card execution. Harness callers must actually await their
workers; a model-written terminal statement is not host process evidence. Yield never writes done.
Passing current-candidate checks covering an issue's AC generate its completion proof and unlock
dependents. A later integration check does not prevent earlier local AC proof; all required final
checks still run on the combined candidate. Failed final checks reopen their owners within the
same batch. Diagnosis must locate the affected members; an unmapped combined failure cannot implicitly reopen every issue.

Source snapshots include tracked actual bytes, deletion tombstones and declared untracked inputs.
They preserve the Git index and HEAD. Parent links, external links, unresolved Git state, incomplete
LFS inputs and nonportable aliases fail explicitly. No snapshot promises consistency under an
uncooperative same-account writer that changes and restores bytes between observations.

### Reuse and admission

Default reuse is disabled; missing closure means rerun.
Jobs may opt into `reuse: true` only for isolated checks without external state, real-time or
random-dependent results. UI, resource and application lifecycle jobs cannot use this cache.
`reuse_environment: {"paths": [...], "external_state": "none"}` explicitly declares the complete
materialized runtime/dependency closure. Paths may be absolute or relative to the repository.
The runtime hashes the actual command executable and all declared dependency files/directories,
including resolved symlink targets; it does not substitute a lockfile for installed package bytes.
`reuse_inputs` optionally binds additional regular repository files. Source/config/lock/test inputs
still belong in the frozen candidate. Omit reuse when network, clock, randomness, undeclared package
loads or other mutable influences prevent a closed environment. This is a caller contract, not an
automatic proof of hermeticity. No closure, unresolved tool, missing input or directory cycle means
no completed reuse. Hashing a large closure has a cost: opt in only when that cost is justified by
saved runs. Ordinary checks do not scan dependency trees or probe/install browser tooling.

Cache identity includes check name, candidate, job, verification epoch, artifact inputs, member requirement/
proof/decision bindings, process environment, executable bytes and the declared materialized dependency closure. Failed evidence never
enters the cache. Running identical immutable requests share a run ID; the returned `shared: true`
means observe that run. Aliases do not reserve another budget. Different checks cannot be admitted
while a verifier remains nonterminal. Mutable development checks do not coalesce by source guess.
Managed execution has one active verifier per workspace; it does not create a second pending-job queue.
Status readers and owned verifier state transactions retry brief lock contention within 40 attempts
at 25 ms intervals. Other state writers fail fast; a timeout never grants lock takeover or reruns a command.

### Job execution

Each job is admitted with a persistent idempotency key, candidate/plan/verifier/runtime identities,
and a reservation from the root budget before it can launch. A running run is never blindly retried. POSIX managed launchers watch their controller and refuse
to leave live descendants after the direct target exits; Windows uses kill-on-close Jobs.
An unavailable POSIX process inventory cannot prove that a managed group is terminal.
Terminal run replay returns the retained receipt without repeating side effects. Actual process
status and nonempty result observations determine pass; zero tests, skips, mixed success/failure
summaries and unmet predicates fail. Same-candidate failure remains a failure across repair epochs.

Each job restores the frozen source into its own run directory. `{root}` names that directory,
`{run_dir}` names its retained outputs, and `{python}` names the running interpreter. Needed dependency
restoration must be declared in lifecycle actions; dependency caches in the developer directory are
not implicitly reused. A producing job declares `outputs`; consuming jobs declare `artifact_inputs`
with preceding build check IDs. Source and artifact integrity are checked after execution.

Resource jobs declare the complete identity/prepare/baseline/stop/terminal/cleanup/recovery lifecycle.
Host resource locks cover the whole lifecycle. Releasing an OS lock after a crash does not establish
resource health; persistent unhealthy records continue to block allocation. A missing recovery
adapter is a real blocked state, not permission to clear resource metadata.

Launch identity is persisted before the command can cross its input gate. `check-recover --run ID
--reason TEXT` requires the previous controller lock to be free and observes its POSIX process group
or Windows named Job as terminal before cleanup. It never blindly kills an unknown PID or repeats the
scenario. A live or unobservable owner remains blocked. Identity/stop/terminal/cleanup/recovered
adapters must be safe to repeat after interruption; their original accepted commands run under the
resource lock with owner validation and retained time budget. Completed recovery produces incomplete
evidence, followed by new checks. A cancelled unlaunched run or controller interruption is not a
product assertion failure. Actual behavior failures remain binding; a passing scenario whose cleanup
failed may retry unchanged source after actual recovery. Recovery does not refund prior reservations.

## External runner integration

`scripts/overnight.py` advances active managed batches from structured state. Mechanical checks need
no model call. Implementation runs one assigned issue in the existing native session, retains its
actual terminal observation, then yields to proof. A verification failure continues in the same
session: the runner admits one bounded diagnosis through the `diagnose` control (idempotent per
incident run, persisted with the state), the session only proposes
`{action: repair|blocked, members, reason, evidence}` into
`.scratch/batches/<id>/diagnosis/<run_id>.json` and never touches managed state itself, and the
runner applies the existing `repair` control with request-id `run-<run_id>`. An identical remedy
already attempted, a blocked proposal, an invalid artifact, or a refused repair stops at 11 with the
evidence retained; completion still requires the proof chain, and every repair round draws its bound
from the goal budget by consuming a real dispatch and check runs. It does not infer completion from
model exit, an empty queue or a handoff. No additional close-out full suite runs. Return codes:
0 closed, 10 waiting for a person, 11 repair/owner/readiness block, 12 budget/incomplete,
13 revision/runtime conflict. Lifecycle, session
and process supervision follow [DRAIN.md](DRAIN.md)'s External runner section and
[SESSION-REUSE.md](SESSION-REUSE.md).

```text
python workflow-state.py batch-prepare ROOT --batch ID
python workflow-state.py batch-run ROOT --batch ID
python workflow-state.py check-admit ROOT --batch ID --check CHECK --request-id REQUEST
python workflow-state.py check-run ROOT --batch ID --run RUN
python workflow-state.py check-recover ROOT --batch ID --run RUN --reason TEXT
python workflow-state.py checkpoint-seal ROOT --batch ID
python workflow-state.py checkpoint-show ROOT --batch ID --checkpoint HASH
python workflow-state.py checkpoint-diff ROOT --batch ID --before HASH --checkpoint HASH
python workflow-state.py checkpoint-materialize ROOT --batch ID --checkpoint HASH --destination DIRECTORY
python workflow-state.py checkpoint-export ROOT --batch ID --checkpoint HASH --artifact CHECK --destination DIRECTORY --archive FILE.zip
```

## Compatibility and return codes

Plans pin `schema_version: 3`; state written in the retired formats (schema 1 or 2) is refused,
and `workflow-state.py batch-prune` disposes their directories — schema 1 in any phase, schema 2
once terminal. A live schema-2 batch continues via its own frozen runtime. The plain-path receipt-conflict barrier remains the
lightweight equivalent of managed decision-event invalidation until the two mechanisms converge. Legacy tasks
without an active batch keep their established command behavior. Managed commands are lazy imports;
non-UI paths do not load UI policy/reporters, install browser dependencies or start browsers.

Plans and run intents bind batch identity, workspace, runtime, verifier and source digests. The
feature wave ledger is the execution authority; batch and ledger publication share a journal
transaction. Dispatch reserves budget before work, and neither yields nor restarts refund it.
Issue `pending` is not dispatchable; `ready` enters implementation and `done` requires proof.

Each managed batch retains a copy of its runtime alongside state. If installed runtime bytes change,
`batch-status` returns `runtime_entry`; invoke that frozen `workflow-state.py` to continue. Do not
rewrite state versions, overwrite an accepted plan or silently reset budgets. The budget command
changes only authorized limits ([BATCH-PROOF.md](BATCH-PROOF.md)). The plan supports accepted-scope amendments as immutable plan revisions in
[BATCH-REVIEW.md](BATCH-REVIEW.md). Active cross-host migration requires explicit reconciliation; copying a live directory is not migration.
Historical exported deliverables remain usable subject to their recorded runtime requirements.

Queries return JSON with phase/status/action/reason_code and exit 0 even when incomplete. Protocol
errors: invalid arguments/contracts 2, budget or unavailable legacy proof 12, revision/identity/
publication/lock conflict 13. Managed dispatch failures retain these codes through legacy entry
points; ordinary legacy read commands retain their prior exit codes. The overnight runner additionally
uses 10 for user waiting and 11 for repair/owner/readiness blocks.
