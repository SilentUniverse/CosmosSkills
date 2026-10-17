---
name: tdd
description: >-
  Use when implementing a named unit or feature test-first, completing ready units, or recording verification evidence. Defines engineering method and completion; the host owns execution, tasks, parallelism and recovery.
argument-hint: "Feature slug, feature unit (feat T3), -all, -log, or the current goal"
---

# Test-Driven Development

Use the accepted outcome, constraints and existing authorization. A new unresolved material decision
holds only dependent work. Explicit user implementation/testing instructions override this method.

## Invocation

- Bare `/tdd` or an inline goal: implement the accepted inline plan. No file, artifact check or
  admission step; temporary delegation and internal dependencies stay in the native plan.
- `/tdd <feat>` or `/tdd <feat> T3`: work ready units of `.scratch/<feat>/FEATURE.md`
  (see [Feature units](#feature-units)). Missing arguments never authorize repository-wide work.
- `-all` requests the whole applicable suite/build: [FULL-SUITE.md](FULL-SUITE.md).
- `-log` replaces test-writing with a control action plus a log predicate that fails when the
  behavior is absent; a launcher/capture exit alone is insufficient. Retain action, exit, input
  identity, log digest and a decisive excerpt; bound long streams with an explicit stop condition
  and follow the host's device-stream rules.

Requested plans and unresolved consequential requirements use `/spec`; unknown failures use
`/diagnose`. Running status, retries, cancellation and resume come from the host; across a host
boundary use [handoff](../handoff/SKILL.md)/[resume](../resume/SKILL.md).

## Implement

Read the public seam, existing coverage, governing ADRs and domain terms. Briefly state the
behavior, proof route and material assumption, then act with project commands. Build a missing
run/drive/observation capability first through `/verify`; ordinary prerequisites stay inline.

Tests are written before the implementation so they stay an independent oracle; they are **run**
only at the two points that carry information:

1. **Write.** For the whole unit (or inline goal), extend existing coverage first, then add the
   cases its AC need. Do not run them yet.
2. **RED, once.** Run only those cases and confirm each fails for the missing behavior, not for an
   import/collection error; keep the command and its failing line for the change summary. The
   tests are now frozen: change one only when it is wrong, and say why.
3. **Implement** to completion. Do not run tests between edits unless diagnosing a specific failure.
4. **GREEN, once.** Run the AC command once; that run is the completion evidence (feature units:
   `workflow-state.py run`, or for a gated feature the `evidence.py` prepare → host run → seal
   sequence in [FULL-SUITE.md](FULL-SUITE.md) instead). Add checks only for a changed shared seam, fixture or concrete integration
   risk; reuse passing results whose inputs and environment match. Refactor while green and rerun
   only what the refactor touched.

Skip RED and go straight to one GREEN run for pure prose, configuration, behavior-preserving
refactors already pinned by existing tests, prototypes, and exploratory UI layout. Machine-consumed
templates/schema use their targeted contract cases. The full suite runs once per delivery
candidate ([FULL-SUITE.md](FULL-SUITE.md)), never per unit.

Apply [test quality](tests.md). Load [mocking.md](mocking.md) only for mocks and
[UI-TESTING.md](UI-TESTING.md) only for graphical behavior. Agent summaries, screenshots or launcher
exits cannot replace acceptance predicates. A clear contract conflict records exact evidence and
routes the affected scope to `/spec`; an ambiguous one uses the
[classifier](../atk/RECEIPT-CONFLICT.md). Repeated failure without new evidence needs `/diagnose`;
repeated patches on one seam mean re-deriving its design.

## Feature units

`python ../workflow-state.py survey <root> --feature <feat>` lists units as ready, blocked, pending,
done or invalid with reasons; `start <root> <feat> T<n>` is a read-only admission returning the
worker packet (unit contract, covered anchors, invariants, resolved commands).

- **You decide the parallelism.** Default to working ready units one at a time inline. Use native
  parallel tasks only when units are independent, their `touches`/`test_paths` and `resources` do
  not overlap, and each is large enough to repay the coordination; give each worker its packet,
  never a re-transcription of the document.
- **Workers never write FEATURE.md.** They return commands run, log or receipt paths, changed paths
  and remaining gaps. The integrating session resolves shared-file conflicts and closes units one at
  a time.
- **Checkpoint per unit.** After `close`, make one local commit of that unit's changes, the updated
  FEATURE.md and the `runs/` log or receipts it references (no push unless requested); `.scratch/<feat>/`
  must be tracked, not ignored, or a fresh checkout sees the unit as invalid. The commit and FEATURE.md are the progress record a
  fresh session resumes from; see [handoff](../handoff/SKILL.md).
- **Readiness drift.** Replay a 预检 only when no valid matching observation exists; a failure
  pauses dependent work while setup is repaired, never substituting weaker proof.

## Evidence and completion

Apply [TEST-POLICY.md](../TEST-POLICY.md): one valid check may prove several units; native task
completion proves no AC; keep failed attempts visible.

Before closing, trace owned diffs to AC, record actual `test_paths`, review changed tests with
[tests.md](tests.md), apply the [comment deletion test](../lint/references/code-comments.md) to
changed comment blocks, and challenge the most plausible failure against the evidence. Then:

    python ../workflow-state.py run <root> <feat> T<n> <command>      # GREEN; prints the evidence line
    python ../workflow-state.py close <root> <feat> T<n> --evidence "<log>; AC 1,2"

`run` executes the named command from 共享验证 `cwd` and keeps `.scratch/<feat>/runs/<unit>-<command>-<id>.log`
(command header, full output, `exit=` trailer). `close` never runs tests: it pins the log's SHA-256,
checks the command and `exit=0`, appends the `完成` record with the unit's contract digest, and flips
`status: done` in one locked write. A failure writes nothing. A feature with a recorded review gate
(`Door: one-way` or `review: required`) instead needs fixed receipts from `evidence.py` bound to the
accepted contract ([FULL-SUITE.md](FULL-SUITE.md)); pass them as `--evidence "<receipt>.json; AC 1"`.

A chronically failing unit with a concrete gap is parked:
`workflow-state.py park <root> <feat> T<n> --reason TEXT`. Changed behavior after `done` is a new
unit with `refines:`; the gate rejects edits to a done unit's contract or its pinned log.

Retain hard-to-recover invariants at their existing owner under `/map`'s two-axis rule. Use `/tidy`
for obligations and cleanup; `/pr` only when requested.
