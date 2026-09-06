---
name: grill
description: >-
  Use when the user asks to grill, challenge, or stress-test a plan or design before building. Runs focused decision-tree interview rounds, investigates answerable facts, and records resolved domain terms or qualifying ADRs when the repository already provides those surfaces.
---

# Grill

Start from first principles. Reuse settled requirements and authorization from the whole task,
including `/spec` artifacts. Investigate repository-answerable facts before questioning the user.

## Decision tree

Map consequential decisions and their dependencies as a design tree. The frontier contains unresolved
decisions whose prerequisites are settled.

Work in rounds:

1. Ask a small batch of the frontier's highest-impact questions and lead with a recommended answer.
2. Resolve reversible implementation details within agreed constraints. Ask only about choices that
   materially change the outcome and are not already settled.
3. Continue fact-finding and independent branches while answers are pending. When local evidence is
   insufficient, use `/research`; only downstream questions wait.
4. Recompute the frontier after each answer. Stop when consequential decisions support the caller's
   next artifact; defer details that cannot change it.

Use the host's question tool for enumerable choices when available. A decision requiring an
experiment may route to `/prototype` within existing authorization.

## Domain persistence

If `CONTEXT.md` or `docs/adr/` exists, use `/domain-modeling` to write resolved glossary terms and
ADRs that pass its gate. If neither exists, remain stateless; do not create domain surfaces merely
for this interview.

The interview writes no production code or submissions. Its only direct writes are glossary entries
in an existing context file and qualifying ADRs in an existing ADR directory. A plan-only request
ends with the plan; a broader authorized task resumes its planning or implementation workflow.

End with decisions reached, domain documents changed or none, route-changing assumptions, pending
research or prototype candidates, deferred dependencies, and the next skill.
