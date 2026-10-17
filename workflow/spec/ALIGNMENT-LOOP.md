# spec — Alignment loop（AFK grill）

Loaded by [`/spec`](SKILL.md) for unresolved material decisions. Resolve repository facts and
reversible implementation choices before asking the human. Ask a concrete missing decision once
evidence establishes it; continue independent preparation while the current round's focused
receipt awaits answers.

## Requirement tree

Build the tree transiently in this task; it is not a durable artifact:

```text
Goal
├── User Scenarios（normal / boundary / failure）
├── Invariants
├── Constraints
└── Verification
```

Each node is exactly one state:

- **EVIDENCED** — the repository, recorded decisions, code, docs or existing tests already answer
  it. Adopt the answer and keep its source pointer.
- **DEFAULTABLE** — no product difference, only an implementation choice that is reversible,
  matches project convention, and changes no public contract. Choose it; do not ask.
- **HUMAN_DECISION** — two answers yield different product behavior, public contract, risk, cost,
  authority, or an irreversible result. Reserve exactly these for review.
- **FOG** — the question cannot be stated precisely yet. Investigate the nearest concrete
  scenario; fog never becomes an open "how do you want this?" question.

## Dialogue rounds

The decision frontier contains unresolved HUMAN_DECISION items whose prerequisites are settled.
Expose only choices that materially change the goal, boundary, public contract, significant cost,
authority or irreversible effects. Resolve repository facts and reversible implementation details
yourself. Batch independent choices to target one or two user decision rounds; this is an economy
target, not permission to skip an unresolved required decision. Each question gives concrete
options, a recommendation and the result or trade-off of each option. Use the host's conversation
or question tool; it owns delivery, waiting and context.
After answers, recompute only affected branches, investigate any newly answerable facts, and
continue with the next frontier. A dependent choice waits for its prerequisite; do not pack an
entire conditional decision tree into the first question batch. Reuse answered choices. An additional
round names the remaining material choice and why its prerequisites or new evidence prevented
combining it earlier; repeated questions and discoverable details do not justify another round.

Continue until the choices needed for the caller's plan are resolved, or name the missing evidence
that prevents resolution. Honor an explicitly requested final plan review before implementation.
Ordinary interviews stay in the conversation/native plan, with no interview ledger or file.

## Autonomous convergence within a round

For the affected draft, use at most two autonomous passes. This bounds internal investigation,
not the number of user dialogue rounds:

1. **Derive** — read the goal, the related code, the live feature document, ADR/CODEBASE/CONTEXT and
   existing verifiers/tests; build and classify the tree; resolve EVIDENCED nodes, take
   DEFAULTABLE choices, and investigate FOG toward the sharpest state it supports.
2. **Attack** — run one adversarial pass over the draft: the most likely misread user scenario,
   the most likely missed failure mode, invariants without an acceptance route, verification that
   cannot prove the goal, structure added for an imagined future, and questions the repository
   already answers. Re-expand only the affected subtrees; do not re-traverse the whole tree.

The convergence predicate determines whether the draft is ready to present:

1. Goal is unique and explicit.
2. Every in-scope user scenario has an observable outcome.
3. Every invariant maps to at least one acceptance or evidence route.
4. Each remaining HUMAN_DECISION has concrete alternatives, a recommendation and named dependent
   work. It remains unresolved until the user answers.
5. Blocking FOG names the missing evidence; dependent work remains unready.
6. Public API / schema / measurement semantics are explicit.
7. Out of Scope is explicit.
8. Every planned unit has a boundary and a verification entry.
9. No structure exists for an imagined future.
10. Material findings from the attack are resolved or explicitly attached to a blocking decision
    or missing evidence. Do not run another attack merely to prove there are no further findings.

Present the ready frontier as one focused receipt per round, reusing any already-pending question.
A failed predicate names the missing evidence and holds its dependent work; two passes do not make
it complete. With no unresolved decision, follow the original planning or implementation scope and
any explicitly pending review; convergence itself creates no approval requirement.

## Batched receipt shape

Give only the context needed to choose, in four blocks:

1. **目标与边界**: observable outcome, a success example, the relevant exclusion/invariant.
2. **待决定**: the unresolved choice, recommended option, and how alternatives change the result.
3. **证据与影响**: inspected facts or prepared diff/prototype, verification route, affected public
   contract, cost or irreversible effect. Mark unavailable evidence honestly.
4. **问题**: ask the actual missing decision. An answer settles that decision; do not append a
   second request to reply "对齐".

For a broad architectural choice, add the smallest useful requirement/evidence/unit table
(Requirement | Observable outcome | Verification | Unit/dependency). Show only affected rows
after feedback; reprint the complete design only when interactions changed so much that a delta
would mislead. Keep settled choices in the conversation or native inline plan; on the
feature-document route persist them once in that document. Unit count, multiple files and internal
dependency changes do not by themselves require approval; feedback prunes the affected subtree
instead of restarting alignment.

Ask consequential missing information as soon as evidence establishes the question; do not build
an entire disputed plan or require all preflights to pass before asking, and complete independent
already-authorized preparation while waiting. Prior user decisions remain valid unless new
evidence changes their relevant assumptions; reopen only the affected choice. Silence, timeout,
and confidence cannot supply a required decision. The receipt is conversation state, not unit
status; it never weakens the readiness gate in
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) or substitutes for agent-inaccessible checks,
which stay explicit pending human verification.

## Feedback: prune and re-run locally

Apply feedback to the conversation, native plan or feature document. Pure wording or presentation
changes preserve behavior, scope, public contracts, authority, dependencies and verification; apply
them with necessary structure checks and no `/atk`. Semantic feedback prunes the affected subtree,
recomputes its dependents and re-verifies only that scope; changed consequential decisions,
contracts, dependencies, proof requirements or a concrete uncovered risk get a targeted attack.
If the effect is unclear, inspect the affected contract before treating it as prose. Reuse settled
decisions and unchanged evidence; never re-ask an answered question.

For a feature document under human review ([REVIEW.md](REVIEW.md)), one full page plus at most one
delta page is the target. A third page needs a material reason: the user changed the goal, a new
repository fact overturns the design, an external constraint changed, or a new consequential
decision surfaced. Missed obvious code facts, repeated questions or internal contradictions are
Spec workflow defects: fix the skill or harness instead of asking the human again.
