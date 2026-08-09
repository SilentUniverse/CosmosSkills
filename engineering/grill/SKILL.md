---
name: grill
description: A relentless interview to sharpen a plan or design. In a repo with CONTEXT.md or docs/adr/, also keeps the domain model current — writing glossary terms and ADRs inline as decisions crystallise. Without them, runs stateless. Use when the user wants to stress-test a plan before building, or uses any 'grill' trigger phrases.
disable-model-invocation: true
---

Run a `/grilling` session. If `CONTEXT.md` or `docs/adr/` exist in the working
directory, use `/domain-modeling` to keep domain docs current — write resolved
glossary terms to `CONTEXT.md` and ADRs that pass `/domain-modeling`'s ADR gate.
If neither exists, run stateless (no writes).

Allowed writes: `CONTEXT.md` glossary terms and ADRs (when in a repo). Do not
write PRDs, issues, code, or submit.

## Mid-session routing

Grilling handles fact-finding (dispatch sub-agent) and decisions (ask user) itself. Two cases need specific tools:

- **External fact** → name the sub-agent as `/research` (findings land as a cited file, not a chat message).
- **Design question needing a concrete artifact** → note it, continue, recommend `/prototype` at the end.

End with: decisions reached, docs changed (or none), route-changing assumptions,
any pending `/research` findings or `/prototype` candidates, and next skill.
