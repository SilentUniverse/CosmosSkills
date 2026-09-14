# Managed batches — `.scratch/batches/<batch_id>/`

## Schema 3: incremental collaboration

Test trigger, quality, performance and retirement rules live in [test policy](../TEST-POLICY.md).
Jobs may declare `measurement_context` for comparable cost reports. Isolated schema-3 jobs can opt into
`reuse: true` with a complete `reuse_environment` declaration; see [test policy](../TEST-POLICY.md).
Actual executable and installed dependency bytes bind reuse. Default reuse is disabled; missing closure means rerun.
A shared admission returns the existing run ID with `shared: true`; observe it rather than starting
another verifier. Aliases do not spend the root budget. Different active checks serialize.

Use schema 3 for rolling plans, independent implementation during human review, versioned decisions,
and portable proof. This is the internal execution protocol for Spec/TDD/TIDY, not a fourth user entry.
A simple settled task may stay inline; open a batch when its coordination or retention is needed.

`pending` means an explicit readiness gap, recorded as `pending_reason`; it is never dispatchable.
`ready` means the engineering contract and verifier are prepared. Engineering dependencies, decision
dependencies, authorization and resources may still block dispatch. `done` means executed engineering
proof, separate from human acceptance. Pending cards retain their goal and dependencies even before
verifier preparation; restoring them takes priority when otherwise-ready consumers cannot run.

In addition to the common fields, a schema-3 plan declares:

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
  configured external integration; a universal Codex/browser notification adapter is not bundled.
- Optional `allow_inherit: true` plus complete `review_inputs` allows retaining a scene conclusion
  across source changes only when those inputs, the actual artifact, launch contract and tested
  environment match. Changed artifacts require review. If final uses another package producer,
  `final_checks: {SCENE_CHECK: FINAL_CHECK}` maps **every** required scene check to an executed final
  check; producer and artifact consumers must map to the actual final artifact. Missing mappings
  project `final_scene_checks_unmapped`; they cannot generate a green review.

The scheduler prioritizes preparing a ready delivery and completing checks for a captured candidate
before new implementation. A capture still needs the shared working tree's entire current wave to
return. Once captured, its checks and delivery use immutable inputs; independent workers can run in
the original repository. One open shared-tree wave remains the ownership boundary. No refill joins
an existing wave, and there is no compulsory separate coordinator agent.

`batch-run --background` admits a check, starts its frozen runner with a retained log and returns
without waiting for the check. `scripts/overnight.py` services mechanical progress and host delivery
while its implementation subprocess is busy. Its default scope is the active goal; without one,
name a feature or explicitly pass `--repo`. A normal interactive harness calls `batch-run` and
consumes the returned actions at safe boundaries. In parent-turn mode, notification waits for that
boundary; a closed or unsupported host has no promise of immediate background display. No extra
model heartbeat is required. Prerequisite, capture, delivery and acknowledgement timestamps remain
available in state; they are not evidence of an unmeasured notification-latency SLA.

Dispatch binds the assigned contract, applicable requirement bodies, upstream proofs and decision
events. `start`, an assigned `packet`, and `briefs` deliver those bindings in `execution_context`,
including decision instructions and values from the retained dispatch plan. The harness must pass
this packet to its worker; the ledger alone does not establish that an agent read it. Stale packets
are rejected. Run admission independently binds its checked inputs.
An in-flight decision change invalidates transitive consumers. A stale worker return goes back to
implementation for reconciliation; a stale run cannot supply proof. A binding-only invalidation can
be rechecked on unchanged source, but a real behavior failure remains a failure. New batches or
retries never refund the original goal's consumption.

### Revisions, review and feedback

`batch-revise --plan FILE --request-id ID --expected-revision N --reason TEXT` appends an immutable
plan and preserves budget consumption, history and unchanged reviews. Quiesce only affected workers;
collect active check runs and explicit capture requests before revision. It cannot change review
keys, notification executables or budget authorization. Editing a completed contract is rejected;
use linked detail/redo/fix work. Explicitly removed members are retained as retired history, not
silently marked done. Closed goals keep their history and use a linked follow-up goal.

A review becomes `pending` only after its actual package and entry have passed required checks and
its export is complete. Each event binds checkpoint, artifact, scene version and that review's
revision. The current batch revision can advance with independent work. User events carry:

```json
{"batch_id":"ID", "decision_id":"HOST_EVENT_ID", "action":"approve",
 "checkpoint_ref":"HASH", "artifact_digest":"HASH", "scene":"SCENE",
 "version":1, "revision":0, "observations":{}}
```

`request_changes` additionally carries the actual `reason`. Scenes may be decided separately;
manual observations are required for their declared scene. Choice events instead carry
`action: choice`, `decision`, `version`, `value` and `expected_decision_id` of the decision replaced,
or null initially. Only the actual operator or pinned host supplies these events.

`batch-feedback --record FILE` accepts `{id, source, description, ...}`. `fixed_review` includes its
checkpoint and scene; `live_preview` includes its actual observation time/session and known reference,
which may be uncertain; `requirements` needs no invented run identity. Optional `artifacts` pins
registered reproduction files. Requesting changes from a review creates feedback automatically.
`batch-feedback-resolve --record FILE` locates `{id, action: repair, members, diagnosis}` or resolves
`{id, action: resolve, members, diagnosis, checkpoint_ref}` against current verified results. A scene
needs a subsequent actual acceptance, not its previous approval. Resolution releases only that
feedback's temporary references. An explicit scope reduction can record `{id, action: cancel, diagnosis, reason, revision_request}`;
the request must identify the current plan revision. It records cancellation, never acceptance.
Unlocated or unresolved feedback prevents final closure.

`batch-notifications` returns durable pending events; `--ack EVENT_ID` records actual host delivery.
`batch-notify` executes the configured adapter. Retries keep the same event ID; withdrawn reviews
cannot accept stale approval. Adapter failure retains the event and its error, backs off retries, and does not block independent implementation; withdrawal emits an update event. A host must check the current event before presenting a retry.
`checkpoint-request --mode observe` remains a diagnostic capture, not acceptance. `--mode review`
requests a declared tested release without adding a global human hold to independent work.

### Durable proof and owned temporary files

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

## Executed checks and local candidates

Schemas 2 and 3 execute `jobs`, retain explicit untracked `inputs`, and enforce run/time budgets. A job declares `argv`, `timeout`, and a `result` adapter (`unittest`, `pytest`, `junit`,
`predicate`, `artifacts`, or `ui`). Every check has one job; no command is inferred from a check ID.
`batch-run` advances mechanical actions until completion or an implementation, repair, resource,
or human decision requires the harness. It does not start a model or claim a worker finished.

Both issue batches and verification-only batches (`members: []`) freeze inputs, execute checks in
isolated restorations, seal exact proof sets and close only on complete passing final proof.
Jobs bind `issue_refs` and `ac_map`; v3 cards also retain `verifier_names`, exact accepted argv/cwd,
AC mapping and actual preflight receipts. Schema 2 requires readiness before admission; schema 3 also retains pending members with concrete readiness gaps. A status
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
same batch. Schema 3 requires diagnosis to locate the affected members; an unmapped combined failure cannot implicitly reopen every issue.

Source snapshots include tracked actual bytes, deletion tombstones and declared untracked inputs.
They preserve the Git index and HEAD. Parent links, external links, unresolved Git state, incomplete
LFS inputs and nonportable aliases fail explicitly. No snapshot promises consistency under an
uncooperative same-account writer that changes and restores bytes between observations.

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
or Windows named Job as terminal before cleanup. It never blindly kills an unknown PID or repeats
the scenario. A live or unobservable owner remains blocked. Identity/stop/terminal/cleanup/recovered
adapters must be safe to repeat after interruption; their original accepted commands run under the
resource lock with owner validation and retained time budget. Completed recovery produces incomplete
evidence, followed by new checks. A cancelled unlaunched run or controller interruption is not a
product assertion failure. Actual behavior failures remain binding; a passing scenario whose cleanup
failed may retry unchanged source after actual recovery. Recovery does not refund prior reservations.

`checkpoint-request --mode observe` freezes a view after workers are quiescent and preserves other
holds. `--mode review` records a review obligation. An incomplete candidate stays diagnostic and routes to
repair; it never becomes a human approval target. Once green, delivery preparation precedes human waiting. Schema 2 has independent `latest_checkpoint_ref` and `pending_review_ref` fields. Schema 3 keeps per-point reviews and does not impose a global human wait. Identical requests return the original `result_ref`, including
after sealing; changing the payload under that ID is refused. Schema 2 finishes a pending capture before approval advances its milestone; schema 3 binds approval to its independent review.

`batch-pause --request-id ID --reason TEXT` creates its own hold. `batch-resume --request-id ID`
releases only that pause. `checkpoint-decide --interactive` reads an exact-version operator decision
from a terminal. Agents must wait for actual user input; they must not manufacture terminal input.
For host integration, `review_authority: {kind: hmac, key_sha256: HASH}` pins an external signing key.
`checkpoint-decide --event FILE` verifies a signed host event using `COSMOS_REVIEW_KEY_FILE` outside
the project. This protocol authenticates a configured host channel, not an unrestricted same-account
adversary. There is no event-signing CLI or `actor: human` bypass.

`approve` requires the exact pending green checkpoint and its unchanged runnable delivery. `request_changes` permits bounded repair and
retains the obligation to review the next candidate. `batch-repair --request-id ID --reason TEXT`
records the diagnosis and starts another verification epoch without refunding budget or erasing
failures. Existing required gates remain required; default gates remain `none`.

Checkpoint history is immutable content-addressed data under `objects/`. Historical show/diff and
materialization do not change the active phase or acquire runtime resources. Plain source
materialization restores code only; it is not a runnable review delivery.

### Runnable review delivery

A human gate or manual obligation projects `prepare_review_delivery` after all technical checks
pass. The controller prepares a tested fixed directory before publishing its pending review with its
path, checkpoint and artifact identities. Schema 2 returns the same pending delivery while waiting. Schema 3 retains that delivery and may return independent work; it uses `reviews` and `point_reviews`. Repeated viewing does not rebuild. Human approval checks the delivery bytes and metadata. Observations may update `latest_checkpoint_ref` without replacing a pending review.

Release is selected first from the checkpoint's declared release producers. A job producing
artifacts declares `release: {argv: [...], requirements: [...]}`; an `artifact_only: true` behavior
check must consume that producer and execute the **complete same argv**, from its artifact root.
A passing command with added smoke arguments does not prove an untested shorter launch command.
Every review entry must have an executable behavior/readiness check appropriate to the application;
GUI or server harnesses must exercise the declared launch contract, not infer readiness from build
exit. A project may use PyInstaller, Node SEA + esbuild, another native builder, an installer, or
its existing packaging system. Build/sign/package actions remain explicit argv jobs. Final signed
bytes need their own consuming check; signing after verification creates a different artifact.

Optional milestone `review_delivery: {kind: release, check: ID}` selects its producer. The plan-level
field is a preference when its producer and matching behavior consumer are available at the current
milestone. Required review stages are validated for complete delivery checks at plan admission.
Put expensive packaging only in milestones that deliver a release or require package verification.
Local RED/GREEN and historical/source preview never build automatically. Export reuses retained
artifacts; it still incurs copy/hash/archive time. No implicit cross-version build cache is trusted.

For a long-running GUI/service, the consuming job declares `application: {argv: [...]}` matching the
complete release launch entry. The controller owns and records that actual process tree before
running `lifecycle.assert_baseline` as a bounded readiness check. Then `job.argv` runs the harness
against that application. Application logs, launch identity, harness results, termination and final
artifact integrity all enter the receipt. A ready port alone is not a behavior result. Application
state belongs outside the fixed package. A failed or unobservable shutdown blocks completion.
An application that exits before controller shutdown fails, even when the harness passed. If the
harness intentionally closes it, `application.expected_exit: 0` explicitly permits a clean exit;
other exit codes remain failures.

`checkpoint-export --artifact BUILD` exports a tested release with a manifest and optional verification launcher. Native executables can run directly without
Python; only `run-release.py` needs Python 3.9+. ZIP supports ordinary files; `.tar.gz` and directory
export preserve internal links and executable modes needed by native packages and `.app` trees.
Build and test platform-specific binaries on each target OS/architecture. Native package examples:
`scripts/check-native-packaging.py`; a dependency-containing zipapp: `scripts/demo-checkpoint-release.py`.

### Live source preview

Plan `source_preview: {argv: [...], requirements: [...]}` declares a task that runs directly in the
original repository using its existing environment. `batch-source-task` returns the expanded argv,
cwd and latest checkpoint as a reference. The harness may launch it and use its native browser tools
while implementation workers continue writing. The command does not launch anything itself, change
batch state, request yield, take a snapshot, copy dependencies, build, or add a human hold. Use normal
host process ownership and isolated ports/data for the preview. Shared devices/accounts still need
their resource owner; the source task is not a bypass for acquiring those resources.

This is a live view and may show edits after the reference node. Feedback may guide current work;
it supplies no fixed-candidate completion or approval credit. Reading a genuinely fixed older source
still uses checkpoint-show/diff. Formal fixed-version acceptance binds a tested release.

### Manual observations and budget continuation

Plan `manual_checks: {ID: {instruction: TEXT, issue_refs: [...]}}` records agent-inaccessible checks.
A milestone may select `required_manual_checks`. Schema 3 requires their union across review points to cover every declared manual obligation; schema 2 carries them all at final.
Approval carries `observations: {ID: {result: passed, observation: ACTUAL_RESULT}}` for every required
check. A generic approval, skipped operation, old checkpoint or blank observation cannot close it.
Manual evidence never changes machine proof or triggers an extra full suite after approval.

`batch-budget --interactive --limits FILE --reason TEXT` permits an actual operator to raise limits
without discarding the goal or prior consumption. FILE contains `dispatches`, `runs`, `seconds`.
A pinned host may instead supply a signed `--event` with batch_id, plan_digest, action=extend_budget,
limits, reason, decision_id and expected_revision. The retained event binds all increases; replay
is idempotent, changed payloads/lowered limits/stale revisions fail, and holds remain in force.

Each managed batch retains a copy of its runtime alongside state. If installed runtime bytes change,
`batch-status` returns `runtime_entry`; invoke that frozen `workflow-state.py` to continue. Do not
rewrite state versions, overwrite an accepted plan or silently reset budgets. The budget command
changes only authorized limits. Schema 3 supports accepted-scope amendments as immutable plan revisions below. Schema 2 plans remain fixed. Active cross-host migration requires explicit reconciliation; copying a live directory is not migration.
Historical exported deliverables remain usable subject to their recorded runtime requirements.

`scripts/overnight.py` advances active schema-2/3 batches from structured state. Mechanical checks need
no model call. Implementation runs one assigned issue in the existing native session, retains its
actual terminal observation, then yields to proof. Return codes: 0 closed, 10 waiting for a person,
11 repair/owner/readiness block, 12 budget/incomplete, 13 revision/runtime conflict. It does not infer
completion from model exit, an empty queue or a handoff. No additional close-out full suite runs.

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

Schema 1 remains an admission-only compatibility format. It retains obligations and ownership but
cannot execute jobs or produce final proof. Use schema 3 for new incremental goals; schema 2 keeps its sequential milestone behavior. Legacy tasks
without an active batch keep their established command behavior. Managed commands are lazy imports;
non-UI paths do not load UI policy/reporters, install browser dependencies or start browsers.

Plans and run intents bind batch identity, workspace, runtime, verifier and source digests. The
feature wave ledger is the execution authority; batch and ledger publication share a journal
transaction. Dispatch reserves budget before work, and neither yields nor restarts refund it.
Issue `pending` is not dispatchable; `ready` enters implementation and `done` requires proof.

Queries return JSON with phase/status/action/reason_code and exit 0 even when incomplete. Protocol
errors: invalid arguments/contracts 2, budget or unavailable legacy proof 12, revision/identity/
publication/lock conflict 13. Managed dispatch failures retain these codes through legacy entry
points; ordinary legacy read commands retain their prior exit codes. The overnight runner additionally
uses 10 for user waiting and 11 for repair/owner/readiness blocks.
