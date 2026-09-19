# spec — Alignment loop（AFK grill）

Loaded on demand by [`/spec`](SKILL.md) for decision intake: complex or consequential work whose
requirement tree has not converged. The agent grills itself before the human sees anything; human
review then judges a converged PRD, not a question stream. The value of this phase is not asking
more questions; it is compressing what genuinely needs a human down to the few choices that
change the product.

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

Stop on the convergence predicate, not on felt confidence. All ten must hold:

1. Goal is unique and explicit.
2. Every in-scope user scenario has an observable outcome.
3. Every invariant maps to at least one acceptance or evidence route.
4. No unhandled HUMAN_DECISION remains.
5. FOG does not block the requested goal; blocking fog is surfaced explicitly.
6. Public API / schema / measurement semantics are explicit.
7. Out of Scope is explicit.
8. Every implementation slice has a boundary and a verification entry.
9. No structure exists for an imagined future.
10. A further adversarial pass produces no new material finding.

Then hand the remaining HUMAN_DECISION items to [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md) as one
batched receipt and present the PRD for review.

## Human review shape

The human reads the PRD's five-part projection — Goal/Success, Scope/Out of Scope,
Invariants/Decisions, User Scenarios/Failure Cases, Verification/Delivery — plus two counts:
items still needing a human decision, and load-bearing defaults the agent took. Routine
implementation details are not listed. A blocker that cannot be resolved is shown as a blocker;
it is never guessed away to satisfy a round count.

The converged PRD carries stable R/D/S anchors
([PRD-TEMPLATE.md](PRD-TEMPLATE.md)); the review page itself is the deterministic projection of
[scripts/spec-review.py](scripts/spec-review.py): Full on round one, Delta
(ADDED/MODIFIED/REMOVED/AFFECTED, unchanged collapsed) afterwards. Hashing, delta classification,
the slice graph and rendering belong to the script; the agent never hand-assembles the review page.
A consequential PRD presents through that surface ([REVIEW.md](REVIEW.md)); a chat projection
remains acceptable only where the harness cannot run local tooling.

## Feedback: prune and re-run locally

Review feedback arrives as structured items (id + hash + action + comment, plus optional global
feedback) or as prose naming the affected R/D/S. Locate that item, prune its subtree, recompute its
dependents, and re-verify acceptance and verification for that subtree only — the next review
is a delta (ADDED/MODIFIED/REMOVED/AFFECTED, unchanged collapsed), rendered by the script, not a
full PRD reread. Feedback bound to an older PRD digest is stale: re-render instead of applying it.
Never re-grill the whole requirement, regenerate the PRD, or re-ask an answered question.

Budget: one full review plus at most one delta review is the target, not a hard guarantee. A
third round requires a material reason: the user changed the goal, a new repository fact overturns
the design, an external constraint changed, or a new consequential decision surfaced. Missed
obvious code facts, repeated questions, or internal contradictions are Spec workflow defects:
fix the skill or harness instead of asking the human again.
