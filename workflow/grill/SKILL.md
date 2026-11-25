---
name: grill
description: >-
  Use when the user asks to grill, challenge, or stress-test an existing idea, plan, or design before building. Runs focused adversarial interview rounds to expose hidden premises and trade-offs without authoring an execution plan or FEATURE.md.
---

# Grill

Standalone adversarial challenger for an existing idea, draft, PRD or design. Start from first
principles and test hidden premises — do **not** use this skill to author an execution plan or
`FEATURE.md` (when the user wants a full plan from scratch, `/spec` owns intent confirmation,
alignment and plan output).

Reuse settled requirements and authorization from the whole task, including `/spec` artifacts.
Investigate repository-answerable facts before questioning the user; run a read-only command
(or a quick test only when execution authority already exists) to settle a checkable question and
report the observed result instead of asking.

## Decision tree

Map consequential premises, trade-offs and their dependencies as a design tree; the frontier holds
unresolved decisions whose prerequisites are settled. Node classification, 2-pass convergence
discipline and the batched receipt shape are owned by [spec's alignment loop](../spec/ALIGNMENT-LOOP.md):
derive repo-answerable facts and reversible defaults yourself, reserve for the user only choices
that change behavior, public contract, cost or authority, and recommend an answer with each
question.

Work in rounds:

1. Challenge the riskiest unexamined premises and ask a small batch of the frontier's highest-impact
   material choices, with concrete options, recommendations and trade-offs. Target one or two
   decision rounds; an additional round names the prerequisite or new evidence that prevented
   combining it earlier.
2. Continue read-only fact-finding and independent branches while answers are pending. When local
   evidence is insufficient, use `/research`; only downstream questions wait.
3. Recompute the frontier after each answer. Stop when consequential choices and blind spots are
   exposed and resolved for the caller; defer details that cannot change the outcome.

Use the host's question tool for enumerable choices when available. A decision requiring a runnable
experiment may route to `/prototype` only within existing execution authorization (or after asking
permission during planning).

## Domain persistence

During `/spec` or plan-only requests, never write `CONTEXT.md` or `docs/adr/` (`CLAUDE.md` §2
planning write boundary): return candidate terms and ADRs in the summary only. When called inside
an active implementation or documentation task where `CONTEXT.md` or `docs/adr/` already exists and
domain-document updates are within authorization, use `/domain-modeling` to write resolved glossary
terms and qualifying ADRs; otherwise remain stateless.

The interview writes no production code, execution plan, `FEATURE.md`, or submissions. A plan-only
or `/spec` caller keeps its planning boundary and still stops at the plan.

End with: premises challenged, decisions reached, domain documents changed or candidate list,
route-changing assumptions, pending research or prototype candidates, and the next skill.
