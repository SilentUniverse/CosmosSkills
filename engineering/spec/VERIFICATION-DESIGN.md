# spec — Verification design

Loaded by the Design Receipt and card test when choosing how a result will be proved.

## Evidence ladder

Choose the highest runnable product seam and the cheapest evidence that can falsify the claim:

1. **Deterministic behavior** — test, compiler/typechecker, CLI exit/stdout/stderr, API response,
   database invariant, browser/simulator action. Record exact action, expected observation, exit or
   assertion tally, and any log/trace/screenshot path.
2. **Measured non-functional result** — benchmark, profiler, performance trace, heap snapshot.
   Record baseline, candidate, environment, repetitions, and acceptance threshold. “Faster” without
   those numbers is not verified.
3. **AI semantic judge** — only when deterministic checks cannot express the property. Give an
   independent judge the artifact plus a versioned rubric and labeled examples; blind it to arm,
   implementation rationale, and self-assessment. Measure it on the labeled calibration set before
   grading and require the eval case's accuracy threshold. Save its structured verdict and evidence.
   Judge disagreement, missing calibration, or a missed threshold becomes human adjudication, not a pass.
4. **Human judgment** — taste, irreversible choice, permission, or inaccessible external account.
   Give exact steps and the decision requested. Keep it outside issue AC/status.

AI can summarize deterministic evidence; it cannot replace it. A screenshot proves pixels existed,
not that the interaction or business invariant worked, unless the rubric is explicitly visual.

## Falsification contract

Evidence is useful only if the target defect makes it fail. An ordinary deterministic code test
proves this with its actual TDD RED; snapshots and other deterministic assertions use that same RED,
with no duplicate `反证` prose. Only an opted-in graphical UI records one concrete counterfactual
after `反证：`. AI-judged or measurement-proxy claims belong to explicit `/eval`, whose case contract
owns its negative controls and calibration; they do not add prose fields to ordinary non-UI issues.
DOM presence, a non-empty `src`, source snapshots, and an agent's own success report are not
sufficient when the claim is about what the user receives.

For opted-in graphical UI (`experience_review: runtime|graded`), write one canonical
`.scratch/<feat>/experience-contract.json`; the receipt displays it and durable artifacts reference
it. `runtime` uses deterministic assertions for behavior, state capture, media decoding, and
unexpected runtime failures. `graded` adds an independent rubric review for visual dimensions that
deterministic assertions cannot express. The default visual rubric is
[experience-v1](../code-review/EXPERIENCE-RUBRIC.md); formal blind calibration belongs to explicit
`/eval`, never the normal development gate.

## SPEC-stage execution readiness

`ready` means a fresh executor can start implementation without designing a verifier, installing a
runner, discovering a missing service, or requesting access. SPEC proves that before writing the
card:

1. Group ACs by verifier harness and assign each harness `P1`, `P2`, ... . Each AC names at least
   one P# that makes its final action executable.
2. Record the repo-relative working directory and prerequisites: runtime/tool versions, services,
   fixtures/data, permission or account reachability, and network mode. Record secret *names* and
   access state, never values.
3. Prepare a durable project environment using repository-declared setup/bootstrap commands. Do
   not use a temporary environment that disappears before execution. If setup would add a product
   dependency, change tracked files, mutate an external system, or needs new authority, show that
   exact setup decision and obtain approval first. Then complete only the approved environment/
   dependency preparation, record its diff/result, and rerun preflight; do not implement behavior.
   The behavior card is not `ready` while any preparation remains outstanding.
4. Actually run a cheap representative preflight through every harness. This is not the future RED
   test: use collection, an existing smoke test, tool/version probe, browser launch, service health,
   fixture round-trip, or device/log probe to prove the route can execute. Record command/action,
   `passed`, observed exit/assertion, evidence, and checked date.
5. Fingerprint `git`, dependency lock, runtime, tools, and relevant service state. Use `none` or
   `no-vcs` explicitly when absent. The fingerprint makes later drift visible; it does not promise
   that an environment can never change.

At TDD dispatch, replay the recorded P# checks before editing. That replay is a drift guard, not a
second setup phase. If it fails, leave the card `ready` and report the mismatch; do not install,
upgrade, start an undeclared dependency, or substitute a different verifier.

One P# may support several ACs. A textual command that SPEC did not run, a version probe without a
representative harness action, or a preflight whose evidence cannot be replayed is not readiness.

## Stack profiles

**TypeScript.** Treat `tsc --noEmit` as strong type-level reachability, then prove behavior at the
public seam with Vitest/Jest and related-test selection. UI behavior is operated through the real
browser/CDP at a fixed viewport. Capture the aligned states and fail on unexpected `console.error`,
uncaught page errors, unexpected failed requests, and CSP violations. Expected events used to drive
an aligned error state are asserted separately. An image/content claim checks decoded/rendered output (for an
HTML image, `complete && naturalWidth > 0`), not only element visibility or an attribute. Inspect
Electron renderer CSP plus main/preload/renderer ownership whenever a renderer loads external
resources. Static green alone does not prove runtime behavior.

**Python.** Pyright/mypy cover typed boundaries only. Pair them with pytest at the public seam and a
runtime selector/coverage signal (`pytest --testmon` or coverage contexts) because dynamic dispatch,
fixtures, registries, and `**kwargs` evade static analysis. Property tests are useful for broad input
spaces when the project already supports them. Report the remaining dynamic-dispatch gap.

**CLI / service / device.** CLI evidence is command + exit + stdout/stderr predicate. Service
evidence is request + response + durable side effect. Device evidence is the control action plus log
predicate/trace. The agent launches and operates the system; the human receives the replay recipe.

## AC-to-evidence rule

For every AC, write `action → observation → evidence` and the passed P# that proves the action can
run. Opted-in graphical UI also writes `反证：<the defect that makes it fail>`; ordinary
deterministic tests retain their actual RED result instead. Reuse one verifier across several ACs.
A verifier that cannot go red on the missing behavior is not evidence.
