# Verify — build project capabilities

Loaded when the current scenario needs a new or extended operation, observation or replay path.
Inspect the target project before selecting files, dependencies or a driver.

## Choose the seam

Identify the user surface, its existing launch path, required data and access, available control
mechanism, observable result and isolation limits. Read the installed tool's help or owning docs when
its capability is uncertain. For UI work, load `../tdd/UI-TESTING.md` before choosing a
driver; the parent skill defines the shared root. A platform-specific recipe must come from the
actual project and tools.

Prefer existing tests, native commands and available host tools. Add a script only for an operation
or assertion that those cannot supply reliably. Use a semantic operation when it can hide repeated
navigation or state preparation; retain enough inspection to diagnose which step failed. Keep
application-specific behavior in the application repository.

## Project assets

Extend an existing verification package when present. Otherwise follow the project's tooling layout;
a dedicated directory contains its local `SKILL.md`, needed helpers and `features/` only when
operating knowledge needs an index. Name the local skill for the application and match its parent
directory. Its discovery description identifies the application, surface and supported tasks.
Do not duplicate scripts or tests already owned elsewhere; link their exact runnable entrypoints.

Write only observed commands and supported behavior into the local instructions:

| Contract | What the next executor needs |
|---|---|
| Start | Exact invocation, cwd, required setup, fixture state and a concrete readiness condition. Short-lived tools use isolated invocations. |
| Target check | A read-only check of the actual instance, version or artifact, ownership and required access. Check again after an unexpected result; report identity uncertainty. |
| Operate | Stable selectors or commands, required starting state and the real public path they exercise. Mark setup and fault-injection interfaces separately. |
| Observe | Actual business state and side effects, the completion condition being awaited and bounded failure output. Keep large logs at evidence paths. |
| Recover | How to inspect an interrupted operation and restore owned state. Never repeat a write whose outcome is unknown without resolving that outcome. |
| Clean up | Resource handles acquired by the run, precise stop and cleanup commands, and evidence retained outside disposable state. Check before acting on a stale handle. |

Keep target checks read-only; a reset or relaunch is a separate explicit operation. Prefer stable
handles over coordinates. Report the target, completed operation, observed state, failure stage and
evidence location compactly using the existing runner's format. Reuse caller-provided run identity;
do not invent a parallel evidence schema. Name environment variables without recording secret values.
Keep test-only control surfaces within the project's existing access and deployment boundaries.

Protect retained evidence in the writer: allocate a fresh caller-owned run location or reject a
nonempty destination before any write. Follow an existing explicit replacement policy if one applies.
Test a second invocation against retained output and confirm it cannot silently overwrite that proof.

Document every helper's invocation. Use the project's runtime, path quoting and text encoding on its
supported hosts. Verify executable permission when invoking a script directly. Persist only setup
that the next executor can reproduce through the repository's declared environment.

## Feature map

Record knowledge needed to reach and operate the selected feature: entry points, prerequisite state,
the relevant driver commands, observation pitfalls and links to existing scenario tests. Start with
the selected feature; add an index when multiple entries need routing. Include source or test pointers
for maintenance. Selectors and action sequences belong in the driver when it already encodes them.

Requirements and tests own expected behavior; the map links to them. Code shows the current
implementation and cannot authorize a changed expectation. Run coverage and results belong in
evidence, not durable "verified" badges. Unexercised entry points remain explicit coverage gaps.

Keep stable scenario IDs when the project already has them. Extend the original regression when an
exploration becomes replayable, rather than copying its assertions into another scenario system.

## Wire and exercise

Add a discovery pointer through the project's existing agent entry file or supported local skill
mechanism, using one instruction source. Add a reusable command to `CODEBASE.md`'s verifier zone only
under its existing lazy-creation rule. Check local links and frontmatter with the project's available
validator; inspect the resulting entry through its actual discovery path.

Return to the parent skill's capability proof. Generated files with unexecuted commands remain
drafts. Evidence should identify the actual target and distinguish the covered path from omitted
features; a representative pass does not establish whole-application coverage.
