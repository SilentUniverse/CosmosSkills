# UI verification

Load only when this task changes or verifies observable UI behavior. A UI repository alone is not
the trigger. Non-UI work uses its existing verifier: no UI document reads, capability discovery,
browser launch, dependency installation, UI artifacts, grading, or UI retry budget.

## Choose the executable surface

Use the project's existing regression command when it covers the claim. For interactive diagnosis,
exploration, or runtime smoke, reuse the harness's available browser-use capability when it can
operate the target and retain the required observations. Prepare a project browser runner only for
capabilities the available route lacks: repeatable CI execution, controlled scheduling, required
assertions or reporting, or the actual browser/extension/desktop host. Do not install Node or
Playwright merely to duplicate native browser actions. Native system UI needs its matching driver;
a browser viewport does not stand in for a native device or desktop application.

Probe capabilities only after choosing a UI verifier. Do not infer DOM/CDP, network interception,
traces, console access, extensions, or process control from a tool's name. Missing capabilities
remain explicit readiness gaps; use an available equivalent verifier only when it proves the same
accepted claim. Keep project dependencies pinned through its existing setup contract.

## Bind actions to evidence

Record one scenario in the existing verification design: requirement, target build/source,
fixture and initial state, actions, independently expected observations, actual result, and evidence
locations. Reuse that scenario and its stable ID across native operation and a retained regression;
do not copy it into a second contract. A passed exploratory run does not supply a missing CI test.
A native replay can satisfy a replay requirement only if the next executor can actually rerun its
actions and assertions; a transcript that only says “looks good” is not replayable proof.

Operate the actual entry point and assert the resulting business state. Fix viewport and relevant
environment for visual comparisons. Capture aligned states; fail on unexpected console/page
errors, failed requests, and CSP violations when those observations are required and available.
Assert expected errors separately. Image/content claims check decoded/rendered output (for HTML
images, expected count plus `complete && naturalWidth > 0`), not just attributes or visibility.
For Electron external resources, inspect CSP and main/preload/renderer ownership.

Reproduce ordering bugs with controlled response barriers or triggers, then observe after all
relevant work settles; fixed sleeps and a briefly correct final screen do not prove stale writes
cannot recur. Retain the first failure, run the original scenario after repair, and bind evidence to
the candidate. Zero scenarios, missing required assertions, unexpected skips, and fail-then-pass
without resolution do not establish success. Keep attempts within the existing task/job budget.

Ownership follows the chosen surface. Close only tabs, contexts, profiles, and services created for
the task; leave pre-existing user sessions intact. Record cleanup or the unresolved recovery need.
Human taste/permission decisions remain separate from technical results. Managed batch completion
requires the batch's actual proof consumer to validate the run binding; neither a native-browser
transcript nor a fabricated CLI receipt substitutes for that consumer.

## Optional experience assessment

Only an opted-in graphical UI (`experience_review: runtime|graded`) writes the canonical
`.scratch/<feat>/experience-contract.json`; the receipt displays it and durable artifacts reference
it. `runtime` uses deterministic assertions for behavior, capture, media decoding, and runtime
failures. `graded` additionally loads [experience-v1](../code-review/EXPERIENCE-RUBRIC.md) for
visual dimensions that assertions cannot express. Functional UI verification does not require
opting into visual grading. Formal blind calibration belongs to explicit `/eval`.
