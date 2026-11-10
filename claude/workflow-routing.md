# Engineering workflow routing

Load when choosing the next engineering step is unclear. Resolve skills through the active host's
catalog and read only the selected entry. This map adds no invocation permission: explicit-only
skills keep their triggers, and a planning request stays within its write limit. Known, bounded
work proceeds directly; neither this map nor the full skill chain is a required opening ritual.

## Choose by the missing result

| Current need | Capability and handoff |
|---|---|
| Understand existing behavior or establish a fact | Inspect the named source first; use research for substantial external investigation. Explicit show explains an area; map maintains structural knowledge. Return the evidence and uncertainty to the current task. |
| Plan a requested change | Spec owns the outcome, constraints and verification route. Use domain-modeling for disputed terms/ownership, codebase-design for a real interface decision, grill for requested challenge, prototype for a concrete experiment. Explicit improve-arch audits architecture friction. Return those answers to the same plan; spec stops at the plan. |
| Implement a settled request | Work directly within the accepted contract. TDD is a user-selected method, not an automatic stage after planning. Reuse existing checks; build a missing reusable verification capability through verify before dependent work. |
| Explain or repair a failure | Diagnose owns symptom → distinguishing probe → cause → verified repair. A model counterexample helps choose a concrete replay; it does not alone establish a product bug. Return unresolved requirement changes to planning. |
| Check a difficult state or concurrency property | Use spec's verification design to select the claim and method; verify builds or maintains a missing checker during authorized execution. Existing checkers run through normal project commands. Keep model bounds and code coverage with the result. |
| Assess correctness before accepting work | Code-review checks a fixed diff against standards and requirements; atk challenges a load-bearing decision or failure mode. Use independent review when justified, with the same evidence and without the author's verdict. Return confirmed findings and gaps. |
| Deliver an authorized change | Pr owns submission and landing evidence; conflicts resolves an encountered merge/rebase conflict within that operation. Passing review does not itself request submission. |
| Continue, retain knowledge or clean up | Handoff/resume preserve the next action through Git and existing artifacts; tidy derives obligations and disposable outputs. Map, domain-modeling and ADRs retain only facts with future consumers. These do not own runtime recovery. |
| Improve instructions | Explicit write-skill owns skill structure; lint owns its requested prose audit; brief adjusts presentation. Repeated deterministic errors belong in architecture/types/checks before more instructions. Model trials require explicit eval. |
| Configure a project or produce a specialist artifact | Apply cpp-oop-style to C++ work. Cosmos-setup, setup-pre-commit, shell-guardrails, migrate-to-shoehorn, record-gif and teach keep their explicit triggers; they are not automatic setup or delivery stages. |

## Handoff only what changes the next action

Carry the accepted outcome and scope, relevant source/artifact identity, observed evidence, and
the remaining gap. Reference the existing plan or command instead of transcribing it. The receiving
skill returns its result to the caller; it does not restart intake, expand authority or create a
second plan. A helper cannot turn a planning request into implementation.

For example, an unclear interface may need a caller sketch before a plan can settle. A settled
feature with a working runner can go straight to implementation and its relevant checks. A retry
ordering bug may need diagnosis, a bounded state model, then a real-code replay. Each chain ends
when the missing engineering evidence is supplied; no chain is mandatory for every task.
