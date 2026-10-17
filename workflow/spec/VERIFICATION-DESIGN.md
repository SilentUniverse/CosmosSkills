# spec — Verification design

Loaded by [`/spec`](SKILL.md) when choosing proof or non-functional bars, and when preparing a
feature document's 共享验证.

## Evidence ladder

Choose the highest runnable product seam and the cheapest evidence that can falsify the claim:

1. **Deterministic behavior** — test, compiler/typechecker, CLI exit/stdout/stderr, API response,
   database invariant, browser/simulator action. Record exact action, expected observation, exit or
   assertion tally, and any log/trace/screenshot path.
2. **Measured non-functional result** — benchmark, profiler, performance trace, heap snapshot.
   Record baseline, candidate, environment, repetitions, and acceptance threshold. "Faster" without
   those numbers is not verified. A coverage, size, or timing bar follows three rules:
   - **Place it by cost.** Seconds-class checks live in RED/GREEN; suite-class at the declared
     fixed-candidate boundary; campaign-class in explicitly requested `/eval` or project/CI
     campaigns. A disabled slow gate is no gate.
   - **Ratchet without an invented target.** Deterministic counts compare exactly. Timing uses
     repeated samples in the same recorded environment, a named statistic, and an explicit
     tolerance or confidence rule; the AC records the post-change candidate and compares like
     for like.
   - **Use a fitting independent oracle.** An existing checker counts only if this dimension can
     make it red. Never add an unrelated tool; without a fitting oracle, ratchet the project
     measurement and state the gap.
3. **Human judgment** — taste, irreversible choice, permission, inaccessible external account, or a
   property deterministic checks cannot express. Give exact steps and the decision requested. Keep
   it outside unit AC/status; an unadjudicated property stays unverified, not passed.

AI can summarize deterministic evidence; it cannot replace it. A screenshot proves pixels existed,
not that the interaction or business invariant worked, unless the rubric is explicitly visual.

## Falsification contract

Evidence is useful only if the target defect makes it fail. An ordinary deterministic code test
proves this with its actual TDD RED; snapshots and other deterministic assertions use that same RED,
with no duplicate falsifier prose. Only an opted-in graphical UI names one concrete counterfactual
in its AC text. Human-judged or measurement-proxy claims belong to explicit `/eval`, whose case
contract owns its negative controls; they do not add prose fields to ordinary non-UI units.
DOM presence, a non-empty `src`, source snapshots, and an agent's own success report are not
sufficient when the claim is about what the user receives.

## SPEC-stage execution readiness

`ready` means a fresh executor can start implementation without designing a verifier, installing a
runner, discovering a missing service, or requesting access. A missing capability that requires
code is a planned prerequisite unit, not SPEC implementation; dependent units stay `pending` until
its observed evidence exists.

1. Prepare a durable project environment with repository-declared setup/bootstrap commands, never a
   temporary one that disappears before execution. Routine local setup implied by the task needs no
   additional approval; ask only for a new consequential dependency, cost, external mutation or
   authority. Record the executed setup and result in 共享验证 `prepare`.
2. Record `cwd` and the result-affecting `environment` identities (runtime, tools, dependency lock,
   relevant services; secret *names* and access state, never values). These are the identities a
   completion receipt must match; they make drift visible, not impossible.
3. Name each harness once in `commands` and actually run a cheap representative preflight through
   it: collection, an existing smoke test, a browser launch, service health, a fixture round-trip or
   a device/log probe — not the future RED test. Record the action, `passed`, evidence and date.
4. A unit needing a command the shared block lacks adds one `命令` line and its own `预检`; it never
   copies shared fields.

Before implementation, validate matching retained preflight evidence or replay it when the action,
relevant inputs or environment changed; session or unit identity alone does not invalidate it. A
failure pauses only dependent work while declared setup or stale readiness is repaired; never weaken
proof to obtain green. A declared command without matching execution evidence, a version probe
without a representative harness action, or unreplayable evidence is not readiness.

## Stack profiles

**TypeScript.** Treat `tsc --noEmit` as strong type-level reachability, then prove behavior at the
public seam with Vitest/Jest and related-test selection. Static green alone does not prove runtime
behavior.

**Python.** Pyright/mypy cover typed boundaries only. Planning uses read-only references and existing
runtime evidence. An optional execution-stage differential probe follows
[impact detection](impact-detection.md)'s isolation rule. Compare a baseline with the candidate in
the same task-owned copy and classify only new diagnostics as typed impact candidates;
pre-existing diagnostics and line-only movement are not attributed to the mutation. This does not
relax an independent repository typecheck gate. Pair static results with pytest at the public seam. Use an installed runtime selector/coverage
signal when dynamic coupling makes selection uncertain; otherwise select cases for the changed
public seam under [test policy](../TEST-POLICY.md).
Dynamic dispatch, fixtures, registries, and `**kwargs` limit static completeness. Property tests are useful for
broad input spaces when the project already supports them. Report the remaining dynamic-dispatch
gap.

**CLI / service / device.** CLI evidence is command + exit + stdout/stderr predicate. Service
evidence is request + response + durable side effect. Device evidence is the control action plus log
predicate/trace. The agent launches and operates the system; the human receives the replay recipe.

## Trigger and cost

Assign each verifier to its behavior loop, module, review candidate, final delivery or declared campaign
boundary using [test policy](../TEST-POLICY.md). Share existing project commands. Keep safety timeouts
separate from measured performance targets; investigate unknown influence and widen only to its
defensible boundary, retaining complete checks when it cannot be bounded.

## AC-to-evidence rule

Every AC names exactly one command whose 预检 proves the action can run, and states the
observation that the command's evidence must show. Opted-in graphical UI also names, in the AC text,
the defect that must make it fail; ordinary deterministic tests retain their actual RED result
instead. Reuse one verifier across several ACs.
A verifier that cannot go red on the missing behavior is not evidence.
