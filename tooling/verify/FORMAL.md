# Verify — formal checks

Load for a selected property that needs a reusable formal check, or an existing check whose source
correspondence needs maintenance. Ordinary checks use their existing command. Planning selects the
property, method and prerequisites only; creating models, tool code or tests belongs to authorized
execution. Use the project's tooling layout and evidence owner, not a separate Cosmos proof system.

## Select one useful property

Start with an accepted promise, a costly way it could fail, and the gap in existing checks. Prefer
the most consequential tractable gap over a property chosen because it is easy to prove. First
consider whether ownership, types or a simpler state representation can eliminate the bad state.
A routine local change with adequate checks needs no formal model.

| Question | Suitable evidence |
|---|---|
| Can cancellation, retry, recovery or concurrent events reach an invalid state? | A small transition model and model checker, such as TLA+/TLC, with explicit state bounds. |
| Can the actual code violate an input, arithmetic or memory property? | A code-level verifier supported by the language/toolchain; record assumptions and bounds. |
| Must the property hold beyond any finite explored bound? | A suitable proof with stated assumptions, if feasible. Finite exploration alone cannot establish this claim. |
| No suitable verifier is available, or generated inputs are sufficient for the risk | Property-based, fuzz or differential tests of the real code. Label them testing, not formal proof. |

Use available project tools first. Check current official tool documentation before choosing an
unsupported language integration or installing a verifier. An unavailable tool leaves the claim
unverified unless an authorized alternative supplies the same evidence; a weaker check changes the
claim and must be reported.

## Keep the property connected to code

Keep the following with the model/check and its existing project instructions. Link accepted
requirements instead of copying them; no new feature-document fields are required.

- **Property:** the invariant or progress claim, with an observable violation. For progress,
  state fairness and environment assumptions; distinguish eventual completion from a safety claim.
- **Coverage:** source paths/symbols, state owners and writers, and how each modeled action maps to
  code. Match actual atomic steps: do not turn a read followed by an interruptible write into one
  indivisible action. Name omitted behavior and any unmodeled path that can affect the property.
- **Scope:** initial states, finite bounds, abstraction choices, external failures and assumptions.
  Explain why excluded states or inputs cannot decide the selected claim, or limit the claim.
- **Replay:** exact command, logical cwd, pinned tool/dependency setup, configuration and raw result
  paths. Retain counterexample traces. Distinguish a completed check from timeout, unknown, skipped
  obligations, missing solver or parser failure; process exit alone is not the property verdict.
- **Source correspondence:** the source identity last checked against the model and the mapping
  above. Include relevant uncommitted inputs when applicable. A recorded commit is a comparison
  baseline, not a permanent certification of all later code.

Use existing assertion/report adapters when possible. A new project adapter must reject an actual
violated property and incomplete results, and preserve the native output; it must not turn a model's
pass into a claim that the entire product passed.

## Establish that the check can find the defect

1. Run the selected check and retain its actual result and explored scope. Check that the intended
   transitions and obligations are reachable; an impossible precondition or assumptions that remove
   the failure are not useful assurance.
2. Exercise a relevant broken variant in a task-owned isolated copy. For a code-level checker,
   mutate the covered code. For a handwritten model, mutate the corresponding action or invariant
   protection and identify this explicitly as a **model** negative control. Reuse a matching
   retained negative control when the check and relevant mapping have not changed. An existing
   violation can supply this evidence if it exercises the selected property and check.
3. Confirm the check reports the expected violation, not a syntax error or unrelated failure.
   Preserve the failing trace and the unchanged original property. Restore the selected candidate
   and keep both results distinguishable.
4. Translate any real finding into inputs/events at the product's public seam and attempt replay
   with controlled ordering or fault injection. A reproduced violation is product evidence. An
   infeasible trace requires correcting the model; an unreplayable trace remains an explicit
   correspondence or execution gap, not a verified product defect.

Follow the recorded setup and command as the next executor would, without conversational context;
reuse an identical just-observed run. Unexecuted instructions remain a draft capability.

A handwritten model need not change when actual code is mutated. Its negative control proves the
model's assertion can detect a defect in that model. Claim code-mutation detection only when an
executed code check, model generation or checked correspondence actually detects the mutation.
Passing bounded exploration proves the property only for the checked model and bounds; it does not
establish implementation refinement or whole-system correctness. A separate real-code replay or
regression test complements the model without removing this limit.

## Maintain on relevant change

Compare covered source and assumptions against the last synchronized identity, including working
changes, moves, new writers and changed callers that affect the property. Trace both ways: modeled
actions still match code, and relevant code paths are not silently absent from the model. For a
whole-package maintenance request, inspect every covered property; otherwise keep the affected scope.

| Finding | Action |
|---|---|
| Relevant behavior, assumptions and check inputs are unchanged | Retain the correspondence evidence and reuse valid results under the normal test policy. |
| Model, mapping or tool configuration has drifted | Repair those assets, rerun affected checks, and repeat affected negative controls. |
| Accepted property is violated by the code | Preserve the counterexample and replay evidence; return to the caller's authorized repair. |
| Intended behavior changes the accepted property | Resolve the requirement change before replacing the property; keep the old failure visible. |
| Correspondence or execution cannot be established | Report the exact gap and limit the assurance claim. |

Never weaken an invariant, increase an assumption or shrink the bounds merely to obtain green.
Explain any justified scope change against the requirement. Maintenance alone does not authorize
product repair. Finish with property, covered source, method/tool, assumptions/bounds, actual verdict,
negative-control result, replay evidence and exclusions. Link these from the caller's existing
verification evidence; schedule no recurring run by default.
