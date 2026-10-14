# Workflow

Engineering policy skills. The host owns task/session execution, scheduling and recovery. The per-skill catalog lives once in the
[root README](../README.md#skill).

Shared artifact schemas, indexes, and directory contracts live in
[ARTIFACT-FORMAT.md](ARTIFACT-FORMAT.md).

## Continuation

[Handoff](handoff/SKILL.md) preserves otherwise inaccessible unfinished engineering facts;
[resume](resume/SKILL.md) retrieves the named source, checks relevant drift and continues.
Same-task context compaction and session recovery stay native. Neither skill manages execution state.

## Application verification loop

SPEC and TDD use the project's existing test and driver entrypoints. SPEC records a missing
operation or observation capability as an execution prerequisite. The authorized execution phase
uses [/verify](../tooling/verify/SKILL.md) to build that capability, exercise a representative
scenario and retain evidence before dependent behavior. Ordinary prerequisites stay inline;
queued behavior cards remain pending until readiness is proven. DIAGNOSE uses the same capability
route when a reproduction cannot be driven or observed within its authorized repair scope.
Missing tests and failing business assertions remain in TDD when the runner or driver already works.

An application change also updates affected existing drivers and operating instructions. Use
`/verify -maintain <area>` when their drift needs investigation, then replay the affected paths.
Their replay belongs to the change's ordinary checks; a matching observed run can be reused.
The next executor discovers these assets through the project's agent entry file and runs them
directly. Ordinary tasks with adequate checks add no verification-building or maintenance phase.
Model comparisons stay in the explicitly invoked `/eval` workflow.
