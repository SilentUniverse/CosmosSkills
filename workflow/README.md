# Workflow

Engineering and general agent-workflow skills. The per-skill catalog lives once in the
[root README](../README.md#skill).

Shared artifact schemas, indexes, and directory contracts live in
[ARTIFACT-FORMAT.md](ARTIFACT-FORMAT.md).

## Application verification loop

SPEC and TDD use the project's existing test and driver entrypoints. A required operation or
observation that those tools cannot provide routes to [/verify](../tooling/verify/SKILL.md): build
the missing capability, execute a representative scenario, retain evidence, and return to the
original task. DIAGNOSE uses the same route when a reproduction cannot be driven or observed.
Missing tests and failing business assertions remain in TDD when the runner or driver already works.

An application change also updates affected existing drivers and operating instructions. Use
`/verify -maintain <area>` when their drift needs investigation, then replay the affected paths.
Their replay belongs to the change's ordinary checks; a matching observed run can be reused.
The next executor discovers these assets through the project's agent entry file and runs them
directly. Ordinary tasks with adequate checks add no verification-building or maintenance phase.
Model comparisons stay in the explicitly invoked `/eval` workflow.
