---
name: tdd
description: >-
  Use when implementing a named issue or feature test-first, running red-green-refactor, completing ready issues, or recording verification evidence. Defines engineering method and completion; the host owns execution, tasks, parallelism and recovery.
argument-hint: "Issue path, feature slug, -s, -p, -all, -log, or the current goal"
---

# Test-Driven Development

Use the accepted outcome, constraints and existing authorization. A new unresolved material decision
holds only dependent work. Explicit user implementation/testing instructions override this default method.

## Invocation and admission

- `/tdd <issue-path>`: inspect contract and proof. `workflow-state.py start ROOT FEATURE SLUG` is
  a read-only engineering admission check returning a packet; it starts no task or execution lock.
  The packet is the worker input at an execution boundary ([DRAIN.md](DRAIN.md)) — no second,
  re-transcribed dispatch brief.
- Bare `/tdd`: continue the accepted goal. Missing arguments never authorize repository-wide work.
- `/tdd <feature>`: complete authorized ready work using [DRAIN.md](DRAIN.md).
- `-s` requests serial work; `-p` permits native parallelism when dependencies, writes and resources
  allow it. Neither creates a Cosmos scheduler or fixed concurrency limit.
- `-all` requests the whole applicable suite/build: [FULL-SUITE.md](FULL-SUITE.md).
- `-log` replaces test-writing with a control action plus a log predicate that fails when the
  behavior is absent; a launcher/capture exit alone is insufficient. Retain action, exit,
  input/candidate identity, log digest and a decisive excerpt; bound long-stream capture with an
  explicit stop condition, and follow the host's device-stream rules. Scope, readiness, evidence
  identity and completion rules are unchanged.

Create new Issues only on Spec's giant-task route with a persistent execution queue. An explicit
existing Issue path follows its admission and history rules. Ordinary new work uses the inline
outcome and verification route, without PRD, Issue, artifact checks or issue
admission; temporary delegation and internal dependencies stay in the native plan.
Requested plans and consequential unresolved requirements use `/spec`; unknown failures use
`/diagnose`. Inspect existing ownership before shared writes. Running status comes from the host.

| Engineering status | Action |
|---|---|
| `ready` | Validate accepted scope, dependencies and readiness, then implement. |
| `pending` | Resolve its concrete engineering gap; independent work continues. |
| `done` | Inspect existing proof; changed behavior uses a linked detail/redo/fix contract. |

Status cannot override missing or contradictory proof. Prior completion on an open Issue keeps the
previous record; old status never validates stale evidence, and a session change alone reopens
nothing. Interrupted work reads native task/session state; across a host boundary use
[handoff](../handoff/SKILL.md)/[resume](../resume/SKILL.md), and confirm a previous writer has
stopped before assigning its paths again. redo/fix contract rules live in
[SUPERSEDE.md](../spec/SUPERSEDE.md).

## Prepare and implement

Read the public seam, existing coverage, governing ADRs and domain terms. For queued work, replay P# only when no
valid matching observation exists; compare action, relevant inputs, prerequisites and environment.
Session changes alone do not invalidate evidence. Failed readiness pauses only dependent work while
the declared setup or stale record is repaired. Never substitute weaker proof.

Briefly state the behavior, proof route and material assumption, then act. Use project commands.
Implement missing run/drive/observation capabilities as bounded prerequisites through `/verify`
before dependent behavior. Refresh only dependent readiness with observed evidence; queued behavior
cards remain pending until their required capability and preflight exist. Ordinary prerequisites
stay inline. Update affected existing drivers with their scenario.
Pure prose uses necessary structure checks and skips RED/GREEN. Machine-consumed templates/schema
use targeted contract cases. For logic, choose a case, class or file covering the changed behavior.

1. Find the existing case that pins the behavior. An already-failing behavioral assertion is RED;
   import/collection failure is an environment problem. Extend existing coverage before adding a case.
2. Observe RED, implement enough to pass, and run the case driving this change.
3. After related logic edits settle, add checks only for a changed shared seam, fixture or concrete
   uncovered integration risk. Reuse passing checks whose relevant inputs and environment match;
   completion or later prose edits do not trigger another pass. Refactor while green and recheck
   affected behavior. Address only debt introduced or exposed here; the full baseline lives in `/code-review`.

Apply [test quality](tests.md). Load [mocking.md](mocking.md) only for mocks and
[UI-TESTING.md](UI-TESTING.md) only for graphical behavior. Agent summaries, screenshots or successful
launcher exits cannot replace acceptance predicates.

A clear contract conflict records exact evidence and routes the affected scope to `/spec`; an
ambiguous conflict uses the independent [classifier](../atk/RECEIPT-CONFLICT.md). Preserve unrelated
work. Contract-preserving fixes stay in the slice. Repeated failure without new evidence requires
diagnosis, not automatic Repair Issues.

Repeated follow-up patches on one seam are a design signal: re-derive the affected design before
adding another workaround.

## Evidence and completion

Apply [TEST-POLICY.md](../TEST-POLICY.md): check selection and evidence validity are independent of
Issue/session/task lifecycles. One valid check can cover several Issues. Native `completed` proves
no AC by itself; retain every real attempt, including failures.

Fixed candidate checks use [FULL-SUITE.md](FULL-SUITE.md); queued Issue completion goes through
`close --evidence/--candidate`, which validates proof and writes the completion record in one
protected write: [COMPLETION-RECORD.md](COMPLETION-RECORD.md). `close` reads proof without capturing
the workspace or running tests. Human acceptance separately binds the displayed Spec or fixed
delivery candidate; pending review holds only dependent work.

Retain hard-to-recover invariants at their existing owner under `/map`'s two-axis rule. Transient
hypotheses stay in the native task. Use `/tidy` for obligations and cleanup; `/pr` only when requested.
