---
name: grill
description: A relentless interview to sharpen a plan or design. In a repo with CONTEXT.md or docs/adr/, also keeps the domain model current — writing glossary terms and ADRs inline as decisions crystallise. Without them, runs stateless. Use when the user wants to stress-test a plan before building, or uses any 'grill' trigger phrases.
---

If `/spec` just ran, read this turn's 已落盘 list and the ADR-worthy question; do not re-ask settled AC.

Run a `/grilling` session. Grilling owns routing itself (`/research`, `/prototype` recommendation); this wrapper adds domain persistence.

If `CONTEXT.md` or `docs/adr/` exists in the working directory, keep domain docs
current via `/domain-modeling`: write resolved glossary terms to `CONTEXT.md`
and ADRs that pass its ADR gate. If neither exists, run stateless. Never
lazy-create `CONTEXT.md`; glossaries are born via `/domain-modeling`.

Allowed writes: glossary terms and ADRs, only when those files already exist. Do not
write PRDs, issues, code, or submit.

End with: decisions reached, docs changed (or none), route-changing assumptions,
any pending `/research` findings or `/prototype` candidates, and next skill.
