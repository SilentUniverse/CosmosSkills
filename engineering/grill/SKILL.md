---
name: grill
description: A relentless interview to sharpen a plan or design. In a repo with CONTEXT.md or docs/adr/, also keeps the domain model current — writing glossary terms and ADRs inline as decisions crystallise. Without them, runs stateless. Use when the user wants to stress-test a plan before building, or uses any 'grill' trigger phrases.
---

Reuse settled requirements and authorization from the entire task, including `/spec` artifacts.
Investigate repo-answerable facts first; question only unresolved choices that change the plan.

Run a `/grilling` session. Grilling owns routing itself (`/research`, `/prototype` recommendation); this wrapper adds domain persistence.

If `/grilling` is unavailable, inspect the relevant code and ask a focused round about the highest
impact unresolved decision, with a recommendation. Stop interviewing once enough is settled for
the requested outcome; continue independent research while an answer is pending.

If `CONTEXT.md` or `docs/adr/` exists in the working directory, keep domain docs
current via `/domain-modeling`: write resolved glossary terms to `CONTEXT.md`
and ADRs that pass its ADR gate. If neither exists, run stateless. Never
lazy-create `CONTEXT.md`; glossaries are born via `/domain-modeling`.

This interview writes only glossary terms in existing context files and qualifying ADRs in an
existing ADR directory. Plan-only ends with the plan; for a broader authorized task, resume its
planning/implementation workflow after the interview without a new phase approval.

End with: decisions reached, docs changed (or none), route-changing assumptions,
any pending `/research` findings or `/prototype` candidates, and next skill.
