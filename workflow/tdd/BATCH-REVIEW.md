# Managed batch review, feedback and delivery

Loaded when an active managed batch reaches a revision, human review, runnable delivery,
live preview, or manual-observation boundary; an implementation wave does not load this file.
Execution, admission and job semantics stay in [BATCH-FORMAT.md](BATCH-FORMAT.md); durable
proof and budget in [BATCH-PROOF.md](BATCH-PROOF.md).

## Revisions, review and feedback

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
In parent-turn mode, notification waits for a safe boundary; a closed or unsupported host has no
promise of immediate background display, and no extra model heartbeat is required. Prerequisite,
capture, delivery and acknowledgement timestamps remain available in state; they are not evidence of
an unmeasured notification-latency SLA.

A minimal host adapter is three concerns — render one event read as JSON on stdin, keep a
stable-ID dedup file, and print `{"acknowledged_event_id": ID}` on stdout. A Windows pwsh sample
(opt-in; a host configures its own argv; the deduped event log is the durable surface, the toast is
best-effort):

```powershell
param([Parameter(Mandatory=$true)][string]$StateFile)
$event = [Console]::In.ReadToEnd() | ConvertFrom-Json
$seen = @{}; if (Test-Path $StateFile) { $seen = Get-Content $StateFile -Raw | ConvertFrom-Json }
if (-not $seen.PSObject.Properties[$event.decision_id]) {
  $seen | Add-Member -NotePropertyName $event.decision_id -NotePropertyValue (Get-Date).ToString('o')
  $seen | ConvertTo-Json | Set-Content $StateFile -Encoding UTF8
  $line = '{0} batch {1}: {2} {3} v{4}' -f (Get-Date).ToString('HH:mm:ss'),
    $event.batch_id, $event.action, $event.scene, $event.version
  Add-Content -Path (Join-Path (Split-Path $StateFile) 'batch-events.log') -Value $line -Encoding UTF8
  if (Get-Module -ListAvailable -Name BurntToast) { New-BurntToastNotification -Text 'Cosmos batch', $line }
}
[Console]::Out.Write(('{{"acknowledged_event_id":"{0}"}}' -f $event.decision_id))
```

## Checkpoints, pauses and operator decisions

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
retains the obligation to review the next candidate. `batch-repair --request-id ID --members REF... --reason TEXT`
records the diagnosis and starts another verification epoch without refunding budget or erasing
failures; a combined incident must name its affected members instead of reopening every issue. Existing required gates remain required; default gates remain `none`.

Checkpoint history is immutable content-addressed data under `objects/`. Historical show/diff and
materialization do not change the active phase or acquire runtime resources. Plain source
materialization restores code only; it is not a runnable review delivery.

## Runnable review delivery

A human gate or manual obligation projects `prepare_review_delivery` after all technical checks
pass. The controller prepares a tested fixed directory before publishing its pending review with its
path, checkpoint and artifact identities. Schema 2 returns the same pending delivery while waiting. Schema 3 retains that delivery and may return independent work; it uses `reviews` and `point_reviews`. Repeated viewing does not rebuild. Human approval checks the delivery bytes and metadata. Observations may update `latest_checkpoint_ref` without replacing a pending review.

Release is selected first from the checkpoint's declared release producers. A job producing
artifacts declares `release: {argv: [...], requirements: [...]}`; an `artifact_only: true` behavior
check must consume that producer and execute the **complete same argv**, from its artifact root.
A passing command with added smoke arguments does not prove an untested shorter launch command.
Every review entry must have an executable behavior/readiness check appropriate to the application;
GUI or server harnesses must exercise the declared launch contract, not infer readiness from build
exit. A project may use PyInstaller, Node SEA + esbuild, another native builder, an installer, or its
existing packaging system. Build/sign/package actions remain explicit argv jobs. Final signed
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

## Live source preview

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

## Manual observations

Plan `manual_checks: {ID: {instruction: TEXT, issue_refs: [...]}}` records agent-inaccessible checks.
A milestone may select `required_manual_checks`. Schema 3 requires their union across review points to cover every declared manual obligation; schema 2 carries them all at final.
Approval carries `observations: {ID: {result: passed, observation: ACTUAL_RESULT}}` for every required
check. A generic approval, skipped operation, old checkpoint or blank observation cannot close it.
Manual evidence never changes machine proof or triggers an extra full suite after approval.
