# Drain mode

Bare `/tdd` drains all active features serially; `<feat>` scopes one feature; `-p` enables
independent worker waves, at most four issues per wave (mechanics in
[DRAIN-PARALLEL.md](DRAIN-PARALLEL.md)). `-log` always runs one issue per wave.
The caller owns the entire requested batch through implementation, integration, and remaining fixes.

## Driver and inputs

Start each scheduling round with:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py step <repo-root> [<feat>] [-p]
```

Without `-p`, `step` returns one issue even when several do not collide; `-p` returns the
collision-free wave. Declared candidates rank by the longest downstream ready dependency chain
before the slug tie-break, so capacity or collision choices prefer the issue that unlocks the
longest chain. Undeclared cards stay in a lower-priority solo queue but use the same ranking within
that queue. This is a deterministic duration-free heuristic, not a measured critical-path
estimate. Follow the next action and exact
command. `next` calculates eligible waves; `dispatch` records
intent before work; `collect` closes assignments; `audit` checks test ownership before batch close.
Exit meanings: 0 dispatchable; 3 uncollected work; 4 no dispatchable work; 5 missing shared preflight
receipt; 6 unresolved contract conflict. Exit 4 alone does not prove all requested work shipped.

Read only sections needed by the returned action. Enumerate `.scratch/*/issues/*.md`, never
`archive/`, or the named feature's top-level issues. Use status, `blocked_by`, `touches`, and
`test_paths`; the driver parses frontmatter and orders dependencies. Inspect relevant contracts
when a declaration disagrees with the tree. Missing declarations serialize; they do not justify
inventing a write set or asking the user to schedule routine work.

Use cards as durable inputs and compact results as retained context. Serial work continues in the
current session. Rotate only at a real host/context boundary with a resumable packet, or when an
external runner owns continuation. Card count, slow commands, and output size are not rotation or
delegation triggers. If subagents are unavailable, run serially and disclose the concurrency limit.

## Preflight receipts

A batch cache is useful only when two or more ready cards in one feature share the exact
`(cwd, resolved P# action, environment fingerprint, v2 readiness digest, semantic verifier profile digest)` tuple.
JSON formatting, completion-command order, and fingerprint/prerequisite pair order or spacing do
not invalidate it; changed values do. `dispatch` already checks this; inspect duplicates separately only when needed:

```text
python3 <tdd-skill-dir>/scripts/preflight-receipt.py plan <repo-root> [<feat>]
```

No duplicates means no shared cache; continue normal execution. Execute and record every miss in
one serial call — it runs each action through the supervisor (scope `preflight`), records only
passing executions, and returns per-tuple verdicts; a failed tuple is reported, never recorded,
and independent tuples still run:

```text
python3 <tdd-skill-dir>/scripts/preflight-receipt.py run <repo-root> [<feat>]
```

The manual per-tuple path is also available: run the action through
`test-supervisor.py --scope preflight`, then record it:

```text
python3 <tdd-skill-dir>/scripts/preflight-receipt.py record <receipt> --cwd <cwd> --action <resolved-action> --fingerprint <value> --readiness-digest <v2-digest> --verifier-digest <v3-digest> --execution-receipt <execution.json>
```

Rerun `plan` or dispatch after recording. A cache entry requires actual passing execution evidence.
Pass each non-empty digest emitted by `plan`. V2 readiness binds prerequisites and preparation;
v3 profile meaning already owns them. A declared `profile:NAME` action is
rejected without it because the card's effective deviations cannot be reconstructed from the cache
path alone. Legacy non-profile tuples omit the option.
Only the orchestrator writes the cache. Dispatch persists assignments and emits each
`receipt-hit:<key>` once with its issue consumers. The cache owns tuple/evidence details; the ledger
and dispatch output use the same key-to-consumers direction. Copy the token verbatim into each
listed worker brief.

Before the first issue edit, recompute its fingerprint. Exact tuple, matching fingerprint/profile, and
supplied key permit reuse; unique checks replay normally. Drift or failed replay leaves the card
`ready` with expected/observed evidence. The caller repairs declared setup outside the active
behavior wave, refreshes readiness, and resumes. New consequential dependency or authority choices
follow `/spec`; never substitute weaker proof. Subagents return repair to the caller. This cache
covers readiness only; RED/GREEN and final behavior evidence are not cached.

## Execute serially or dispatch a wave

Serial mode runs one issue at a time through [SKILL.md](SKILL.md)'s autonomous loop. Use the same
per-issue evidence and recovery rules as parallel work; no subagent or worktree is required.

For `-p`, load [DRAIN-PARALLEL.md](DRAIN-PARALLEL.md) for collision-free waves, packet and brief
generation, worker launch, supervision, and the open-wave barrier; this file stays loaded alongside it.

Before execution record:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py dispatch <repo-root> <slug>...
```

Dispatch writes `.scratch/<feat>/wave-ledger.json` with issue assignments and only a baseline
digest. The referenced `.scratch/wave-baselines/<sha256>.json` is written once for the whole wave
and contains compact content identity rather than source or diff text: Git HEAD, index/worktree
diff hashes, and one hash/marker per pre-existing dirty path (or declared-path file hashes outside Git, falling back to
the workspace for one serialized undeclared card). It excludes
`.scratch`; packet projection verifies the manifest hash before execution.
Its dependency, collision, four-issue cap, and preflight refusals are gates to resolve, not bypass.
For a serial batch dispatch only the chosen issue. Explicit multi-card dispatch also refuses any
card missing `touches` or `test_paths`; undeclared work runs alone. Inspect the baseline and actual
diff as needed to distinguish pre-existing or concurrent edits.

Disjoint workers may edit the shared tree. Overlap serializes by default. Use worktrees when
requested or necessary for authorized isolation, while honoring the driver's collision rules;
follow host branch naming (Codex: `codex/`). Merge in dependency order, resolve conflicts through
`/conflicts`, and verify on the integrated tree. Worktrees cannot write shared stash/tmp state.

## Worker brief contract (`-p`)

`python3 <skills-root>/workflow-state.py briefs <repo-root> <feat>` renders the mechanical half of
every outstanding worker brief: packet, receipt-hit token(s) when the ledger recorded them, and the
derived tests-so-far manifest (done cards' `test_paths`, archived history included, derived per
call). Generation, launch, and supervision live in [DRAIN-PARALLEL.md](DRAIN-PARALLEL.md). The
bullets below stay the single-sourced brief contract; supply what they name verbatim. Start
delegated workers from these immutable inputs before beginning the orchestrator's RED action. Each
worker receives a self-contained brief:

- Run `/tdd <issue-path>` with inherited `-log`, not drain mode. No nested agents.
- Supply that issue's compact projection from `workflow-state.py packets` and exact receipt-hit token, if
  any. The worker uses the caller-supplied packet directly; do not regenerate it or paste the full
  card/prior Comments. A stale source/status/hash is an attention event, not permission to refresh
  the contract silently.
- Supply only constraints absent from the packet and batch-level commands the issue cannot derive.
  Reuse settled decisions; only new consequential choices return to the caller.
- Derive prior green cards' relevant `test_paths` once as the tests-so-far manifest. Do not persist a
  standalone copy. Use the packet's `context` pointers first and expand only for a discovered dependency.
- Require one compact attention event before guessing beyond the packet or changing declared scope.
- Require evidence pointers and changed-file ownership deltas. Commands, tallies, and declared paths
  already retained by the card/receipt are not repeated in the return.

Worker assignment, launch, the bounded supervision loop, orchestrator write scope, and the
open-wave barrier are owned by [DRAIN-PARALLEL.md](DRAIN-PARALLEL.md).

Per-issue GREEN requires all AC plus the touched module's scoped tests and applicable build.
Write the [completion record](COMPLETION-RECORD.md), sync `test_paths`, then close to `done`.
Only the batch close runs the whole suite unless an issue explicitly requires it.

Return one outcome. Green is at most eight compact lines; red/blocked/conflict stays under 150 words
plus the shortest decisive error excerpt:

| Result | Evidence and state |
|---|---|
| `green` | P#/fingerprint verdict; completion/receipt pointers; only unexpected changed paths, new test ownership, and non-derivable caveats; card is `done` |
| `red` | Failing cases, trimmed error, attempted remedy, confirmed facts, next action; retain `ready` |
| `blocked` | Exact unavailable condition or needed decision, attempted safe alternatives where useful, completed independent work; retain `ready` |
| `conflict` | Failing command/output and the precise contract clause it invalidates; append evidence, retain `ready`, return to `/spec` |

A slow or difficult issue is not blocked. Confirmed missing access/authority needs no ceremonial
retry. For other failures, try a materially different evidence-backed approach when one can help.
Diagnose or repair before redispatching an unchanged failure; never loop identical retries.
Before collecting a retryable `red` or `blocked` result, retain one compact `### 尝试` block on the
card with failure, attempted remedy, confirmed facts, and next action. A later packet projects only
the newest block, so the next worker gets the missing context without receiving Comments history.

## Collect and recover

Resolve abandoned dispatched work first using [EDGE-CASES.md](EDGE-CASES.md): adopt useful code
by finishing/verifying it, or revert only attributable edits that cannot safely be retained. Keep
user/concurrent work and `.scratch/**` history. An ambiguous baseline is a reason to preserve work.

After every worker is terminal, verify the union of touched modules and reconcile changed paths
against the baseline and reported owners, excluding `.scratch/**`. Reuse current per-issue results
only where sibling edits and integration cannot invalidate them; run the remaining scopes once on
the reconciled tree. Append undeclared test
ownership to `test_paths`; record an unexpected production path in the issue's completion note.
Two workers claiming one path, unowned changes, dependency/lock drift, a nonexistent assigned
issue, a contradictory test manifest, or broken base build is wave-level failure.

Only after clean reconciliation, commit every outstanding result with one `collect` invocation:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py collect <repo-root> <slug>=<result|conflict@evidence.json>[,...]
```

Supported results: `green|red|blocked|aborted`, or `conflict@<receipt.json>`. Disk and report must
agree: green requires
a `done` card with valid completion evidence; a non-green result cannot leave an accepted `done`
card. For an oddly formatted report, inspect disk evidence and the relevant scoped check before
rejecting otherwise valid work. Completion records are evidence, not an agent confidence statement.
`collect` rejects a partial outstanding wave, so the dispatch barrier stays open through
reconciliation and the ledger is rewritten once. A legacy partially collected wave commits all of
its remaining assignments together.

On wave failure, pause scheduling, determine ownership, and repair or restore only attributable
wave changes. Reopen affected active-batch cards to `ready` with evidence and preserve prior
records. Existing shipped history is not rewritten. Resolve the failure, then resume the task;
finish other independent work when isolation permits. Defer dependents of failed cards.

A possible receipt conflict is a dispatch barrier. Workers start no nested reviewer. Retain the
conflict evidence, safely interrupt/revert unfinished siblings, and classify them as `aborted`;
keep already verified green siblings. Reconcile, then include every result in the one wave collect.
The ledger rejects new dispatch while the recorded contract
digest is unchanged. The caller resolves it through `/spec` within this task, asking only the new
consequential decision. Apply spec's user-review checkpoint to a changed plan, then update the actual
affected contract and readiness before resuming; cosmetic
changes made solely to release the digest guard are invalid.

Before collecting a conflict, retain `.scratch/<feat>/receipts/<slug>-conflict.json` with
`schema_version: 1`, feature, slug, current `contract_sha256`, exact `command`, compact `observed`,
the precise `contract_clause`, and an evidence pointer. Pass that path after `conflict@`; collect
binds only its path/hash to the ledger and rejects a naked conflict token. The evidence file is the
single owner of the conflict-time digest and observations.

If `/spec` disproves a recorded conflict, preserve the unchanged contract. Retain its neutral
review under `.scratch/<feat>/receipts/<slug>-conflict-review.json`, with `feature`, `slug`, `wave`,
`contract_sha256` from the recorded conflict, `classification: noise|artifact_defect`, `reason`,
and `evidence` containing the observed command/result or source. Then run:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py dismiss-conflict <repo-root> <feat> <slug> <review.json>
```

The command requires a closed wave, a ready issue, a matching recorded/current contract, and
feature-local evidence. It retains only the correction's path/hash/time in the ledger, changes that
result to `red`, and leaves the issue ready for execution. It rejects `contract_change`, missing evidence,
and inconclusive classifications. The caller verifies the review's substantive evidence; the
script validates its identity and shape, not the truth of a model's claim. Other conflicts remain.

After a clean collection, derive the next tests-so-far view from green cards and recompute eligibility.
Use a rolling handoff only for unattended continuation or a real session boundary, with pointers
to the ledger/cards and non-derivable decisions. Do not copy expanded test/evidence inventories or
rewrite a handoff after every interactive wave.

## External runner

With `scripts/overnight.py`, the runner owns scheduling and dispatches before launching the
session. Execute only its assigned wave, collect, and write a resumable Continue chain pointing to
the ledger/cards rather than restating completed work. The session
then returns to the runner, which continues the batch; this is not completion of the user's task.
A zombie recovery session only adopts/reverts, reconciles, and collects the whole outstanding wave.
A separate session performs close-out.
Exit 5 permits a preparation-only session to replay/record the named P# tuples, with no product
edit, dependency install, or dispatch; the runner then retries with the emitted receipt keys.
Interactive sessions schedule their own waves and do not require external session rotation.

## Close the batch

When no dispatchable work remains, account for failed/deferred issues before claiming success.
Run `drain-wave.py audit <repo-root> [<feat>]`: test files under `touches` must have issue ownership.
Assign proven ownership or resolve the gap; do not attribute unrelated tests just to pass the gate.

Run the full suite plus applicable build once via [FULL-SUITE.md](FULL-SUITE.md). For `-log`,
replay each shipped issue's recorded log command and predicate instead. Resolve each feature's live
PRD through its `supersedes` chain and run its executable 端到端验证 when present. Report human-only
checks from that PRD or the issues' `## 手动验证` as pending until their evidence exists.

Map closing failures to owning issues through `test_paths`, reopen affected active-batch cards with
notes, and report unmapped failures. Fix in-scope regressions, return to the drain loop, and rerun
affected and closing checks after repair. A red close or a parked requirement is not completion.

Review coupled behavior, new public contracts, cross-module risks, or any explicitly required axes
using [SUBAGENT-BRIEFS.md](../code-review/SUBAGENT-BRIEFS.md). Independent Standards and Spec
reviewers may run alongside the closing suite; small local batches can review inline. If required
independence is unavailable, return useful findings and report that gate unmet. Fix confirmed
in-scope contract violations; only unresolved consequential choices go to the user.

Every opted-in UI issue passes the artifact evidence gate. `experience_review: graded` also needs
an independent Experience judge with the canonical contract and anonymous operated-state artifacts.
Runtime failure or rubric miss reopens its owning issue; an inconclusive/unavailable judge stays
unverified. Runtime-only and non-graphical work do not launch this axis.

Report one screen, omitting empty blocks, per [REPORT-FORMAT.md](../REPORT-FORMAT.md):

1. 结果: shipped/failed/deferred counts, exact closing commands and observed verdicts/tallies.
2. 未竟: each unfinished issue, its cause and next action.
3. 待裁决: consequential unresolved choices with quoted evidence and recommendations.
4. 等你验证: pending human checks with runnable steps; do not claim the whole outcome verified.
5. 详文: completion/evidence paths. Handoff only when a later session must continue.

Account for every dispatched issue, integrate every task worktree, and collect every worker.
Delete a rolling handoff only when its remaining objective is complete. After all waves close and
the batch ships with no active conflict barrier, `workflow-state.py gc <repo-root> <feat>` may remove
closed ledger/preflight caches;
it also removes unreferenced shared baseline manifests, and never moves issues/tests, deletes
durable receipts, or launches another suite.
