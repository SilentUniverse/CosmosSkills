# Drain mode

Bare `/tdd` drains all active features serially; `<feat>` scopes one feature; `-p` enables
independent subagent waves, at most four issues per wave. `--log` always runs one issue per wave.
The caller owns the entire requested batch through implementation, integration, and remaining fixes.

## Driver and inputs

Start each scheduling round with:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py step <repo-root> [<feat>]
```

Follow its next action and exact command. `next` calculates eligible waves; `dispatch` records
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
`(cwd, P# action, environment fingerprint)` tuple. `dispatch` already checks this; inspect duplicates
separately only when needed:

```text
python3 <tdd-skill-dir>/scripts/preflight-receipt.py plan <repo-root> [<feat>]
```

No duplicates means no shared cache; continue normal execution. For each cache miss, the
orchestrator runs the action through `test-supervisor.py --scope preflight`, then records it:

```text
python3 <tdd-skill-dir>/scripts/preflight-receipt.py record <receipt> --cwd <cwd> --action <action> --fingerprint <value> --execution-receipt <execution.json>
```

Rerun `plan` or dispatch after recording. A cache entry requires actual passing execution evidence.
Only the orchestrator writes the cache. Dispatch persists assignments and emits
`receipt-hit:<key>` for each applicable issue; copy it verbatim into the brief.

Before the first issue edit, recompute its fingerprint. Exact tuple, matching fingerprint, and
supplied key permit reuse; unique checks replay normally. Drift or failed replay leaves the card
`ready` with expected/observed evidence. The caller repairs declared setup outside the active
behavior wave, refreshes readiness, and resumes. New consequential dependency or authority choices
follow `/spec`; never substitute weaker proof. Subagents return repair to the caller. This cache
covers readiness only; RED/GREEN and final behavior evidence are not cached.

## Execute serially or dispatch a wave

Serial mode runs one issue at a time through [SKILL.md](SKILL.md)'s autonomous loop. Use the same
per-issue evidence and recovery rules as parallel work; no subagent or worktree is required.

For `-p`, use the driver's computed collision-free wave. Overlapping `touches` or `test_paths`
serialize, and missing declarations run alone. Declare shared root/config paths explicitly;
serialize runtime-resource conflicts even if paths are disjoint. Do not run competing suites
against the same device, database, build output, or constrained runner.

Before execution record:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py dispatch <repo-root> <slug>...
```

Dispatch writes `.scratch/<feat>/wave-ledger.json` with the wave baseline and issue assignments.
Its dependency, collision, four-issue cap, and preflight refusals are gates to resolve, not bypass.
For a serial batch dispatch only the chosen issue. Save its baseline diff as needed to distinguish
pre-existing or concurrent edits; status alone cannot establish ownership.

Disjoint subagents may edit the shared tree. Overlap serializes by default. Use worktrees when
requested or necessary for authorized isolation, while honoring the driver's collision rules;
follow host branch naming (Codex: `codex/`). Merge in dependency order, resolve conflicts through
`/merge-conflicts`, and verify on the integrated tree. Worktrees cannot write shared stash/tmp state.

Each worker receives a self-contained brief:

- Run `/tdd <issue-path>` with inherited `--log`, not drain mode. No nested agents.
- Supply objective/constraints from the card, scoped-test/build commands, and any exact receipt key.
  Reuse settled decisions; only new consequential choices return to the caller.
- Supply prior waves' `test_paths` as the tests-so-far manifest. Reuse existing coverage.
- Copy `## 相关面` pointers; read those first and expand only for a discovered dependency.
- Require actual commands/actions, observed results, evidence paths, and changed-file ownership.

Per-issue GREEN requires all AC plus the touched module's scoped tests and applicable build.
Write the [completion record](COMPLETION-RECORD.md), sync `test_paths`, then close to `done`.
Only the batch close runs the whole suite unless an issue explicitly requires it.

Return one outcome; red/blocked summaries should stay under 400 words:

| Result | Evidence and state |
|---|---|
| `green` | P# and fingerprint result; final commands, exits/tallies, retained evidence, changed files and test coverage; completion record on disk and `done` |
| `red` | Failing cases, trimmed error, attempted remedy, confirmed facts, next action; retain `ready` |
| `blocked` | Exact unavailable condition or needed decision, attempted safe alternatives where useful, completed independent work; retain `ready` |
| `conflict` | Failing command/output and the precise contract clause it invalidates; append evidence, retain `ready`, return to `/spec` |

A slow or difficult issue is not blocked. Confirmed missing access/authority needs no ceremonial
retry. For other failures, try a materially different evidence-backed approach when one can help.
Diagnose or repair before redispatching an unchanged failure; never loop identical retries.

## Collect and recover

Resolve abandoned dispatched work first using [EDGE-CASES.md](EDGE-CASES.md): adopt useful code
by finishing/verifying it, or revert only attributable edits that cannot safely be retained. Keep
user/concurrent work and `.scratch/**` history. An ambiguous baseline is a reason to preserve work.

Collect each result:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py collect <repo-root> <slug>=<result>[,...]
```

Supported results: `green|red|blocked|conflict|aborted`. Disk and report must agree: green requires
a `done` card with valid completion evidence; a non-green result cannot leave an accepted `done`
card. For an oddly formatted report, inspect disk evidence and the relevant scoped check before
rejecting otherwise valid work. Completion records are evidence, not an agent confidence statement.

After all wave edits land, run the union of touched modules' scoped tests once and reconcile
changed paths against the baseline and reported owners, excluding `.scratch/**`. Reuse current
per-issue evidence only when no integration change can invalidate it. Append undeclared test
ownership to `test_paths`; record an unexpected production path in the issue's completion note.
Two workers claiming one path, unowned changes, dependency/lock drift, a nonexistent assigned
issue, a contradictory test manifest, or broken base build is wave-level failure.

On wave failure, pause scheduling, determine ownership, and repair or restore only attributable
wave changes. Reopen affected active-batch cards to `ready` with evidence and preserve prior
records. Existing shipped history is not rewritten. Resolve the failure, then resume the task;
finish other independent work when isolation permits. Defer dependents of failed cards.

A possible receipt conflict is a dispatch barrier. Workers start no nested reviewer. Collect the
conflicted card, safely interrupt/revert unfinished siblings and collect them as `aborted`; keep
already verified green siblings. The ledger rejects new dispatch while the recorded contract
digest is unchanged. The caller resolves it through `/spec` within this task, asking only the new
consequential decision. Update the actual affected contract and readiness before resuming; cosmetic
changes made solely to release the digest guard are invalid.

If `/spec` disproves a recorded conflict, preserve the unchanged contract. Retain its neutral
review under `.scratch/<feat>/receipts/<slug>-conflict-review.json`, with `feature`, `slug`, `wave`,
`contract_sha256` from the recorded conflict, `classification: noise|artifact_defect`, `reason`,
and `evidence` containing the observed command/result or source. Then run:

```text
python3 <tdd-skill-dir>/scripts/drain-wave.py dismiss-conflict <repo-root> <feat> <slug> <review.json>
```

The command requires a closed wave, a ready issue, a matching recorded/current contract, and
feature-local evidence. It retains the correction and evidence hash, changes only that result to
`red`, and leaves the issue ready for execution. It rejects `contract_change`, missing evidence,
and inconclusive classifications. The caller verifies the review's substantive evidence; the
script validates its identity and shape, not the truth of a model's claim. Other conflicts remain.

After a clean collection, add green issues' test paths to the manifest and recompute eligibility.
Use a rolling handoff only for unattended continuation or a real session boundary, with pointers
to the ledger and remaining work; do not rewrite a handoff after every interactive wave.

## External runner

With `scripts/overnight.py`, the runner owns scheduling and dispatches before launching the
session. Execute only its assigned wave, collect, and write a resumable Continue chain. The session
then returns to the runner, which continues the batch; this is not completion of the user's task.
A zombie recovery session only adopts/reverts and collects. A separate session performs close-out.
Exit 5 permits a preparation-only session to replay/record the named P# tuples, with no product
edit, dependency install, or dispatch; the runner then retries with the emitted receipt keys.
Interactive sessions schedule their own waves and do not require external session rotation.

## Close the batch

When no dispatchable work remains, account for failed/deferred issues before claiming success.
Run `drain-wave.py audit <repo-root> [<feat>]`: test files under `touches` must have issue ownership.
Assign proven ownership or resolve the gap; do not attribute unrelated tests just to pass the gate.

Run the full suite plus applicable build once via [FULL-SUITE.md](FULL-SUITE.md). For `--log`,
replay each shipped issue's recorded log command instead. Run each feature PRD's executable
端到端验证 when present; registered human-only checks remain explicitly pending.

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

Report one screen, omitting empty blocks:

1. 结果: shipped/failed/deferred counts, exact closing commands and observed verdicts/tallies.
2. Frontier: each unfinished issue, its cause and next action.
3. 待裁决: consequential unresolved choices with quoted evidence and recommendations.
4. 等你验证: pending human checks with runnable steps; do not claim the whole outcome verified.
5. 详文: completion/evidence paths. Handoff only when a later session must continue.

Account for every dispatched issue, integrate every task worktree, and collect every worker.
Delete a rolling handoff only when its remaining objective is complete. After all waves close and
the batch ships, `workflow-state.py gc <repo-root> <feat>` may remove closed ledger/preflight caches;
it never moves issues/tests, deletes durable receipts, or launches another suite.
