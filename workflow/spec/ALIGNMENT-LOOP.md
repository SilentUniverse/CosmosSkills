# spec — Alignment loop（AFK grill）

Loaded by [`/spec`](SKILL.md) for unresolved material decisions. Resolve repository facts and
reversible implementation choices before asking the human. Ask a concrete missing decision once
evidence establishes it; continue independent preparation under the batched receipt below.

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

## Loop: at most two autonomous passes

1. **Derive** — read the goal, the related code, the latest accepted PRD/ADR/CODEBASE/CONTEXT and
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
8. Every implementation slice has a boundary and a verification entry.
9. No structure exists for an imagined future.
10. Material findings from the attack are resolved or explicitly attached to a blocking decision
    or missing evidence. Do not run another attack merely to prove there are no further findings.

Present remaining HUMAN_DECISION items as one batched receipt, reusing any already-pending question.
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
   second request to reply "对齐". Use choices only when they cover the meaningful alternatives.

For a broad architectural choice, add the smallest useful requirement/evidence/slice table
(Requirement | Observable outcome | Verification | Slice/dependency). Show only affected rows
after feedback; reprint the complete design only when interactions changed so much that a delta
would mislead. Persist settled choices once in the PRD/issue contract. Card count, multiple files,
and internal slice-DAG changes do not by themselves require approval; feedback prunes the affected
subtree instead of restarting alignment.

Ask consequential missing information as soon as evidence establishes the question; do not build
an entire disputed plan or require all preflights to pass before asking, and complete independent
already-authorized preparation while waiting. Prior user decisions remain valid unless new
evidence changes their relevant assumptions; reopen only the affected choice. Silence, timeout,
and confidence cannot supply a required decision. The receipt is conversation state, not issue
status; it never weakens the readiness gate in
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) or substitutes for agent-inaccessible checks,
which stay explicit pending human verification.

## Human review shape

An anchored PRD follows [PRD-TEMPLATE.md](PRD-TEMPLATE.md). Load [REVIEW.md](REVIEW.md) when presenting
a consequential PRD for human review; it owns the reading and feedback surfaces, rendering, and
acceptance binding. Show unresolved blockers honestly and keep routine implementation details out
of the human decision area.

## Feedback: prune and re-run locally

After current feedback is bound to its item by REVIEW.md, prune the affected subtree, recompute its
dependents, and re-verify only that scope. The next review is a delta. Reuse settled decisions and
unchanged evidence; never re-ask an answered question.

Budget: one full review plus at most one delta review is the target, not a hard guarantee. A
third round requires a material reason: the user changed the goal, a new repository fact overturns
the design, an external constraint changed, or a new consequential decision surfaced. Missed
obvious code facts, repeated questions, or internal contradictions are Spec workflow defects:
fix the skill or harness instead of asking the human again.
