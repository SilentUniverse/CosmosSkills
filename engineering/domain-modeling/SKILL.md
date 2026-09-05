---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when the user wants to pin down domain terminology or a ubiquitous language, record an architectural decision, or when another skill needs to maintain the domain model.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline — challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. Merely *reading* `CONTEXT.md` for vocabulary is not this skill; that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.

## File structure

Layout: **[CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md)**. Create files lazily, only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## First pass (draft mode)

**When:** `CONTEXT.md` is absent or empty. Inspect code and settled user decisions first; draft only
the domain concepts relevant to the task. Clear existing vocabulary needs no new naming approval.

**Steps:**

1. Explore the relevant code inline. Use bounded read-only subagents only for separable large areas when available.
2. Draft the scoped glossary together, following [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md). Reuse canonical terms and list true synonyms under `_Avoid_`.
3. Write resolved terms to `CONTEXT.md` or the relevant per-context file. Tag only uncertain meanings `(draft)`; a proposal-only request keeps the draft in the response.
4. Present unresolved naming or ownership choices together with examples of how the answers change behavior. Ask only where code and prior decisions cannot settle them; continue documenting clear terms.
5. Remove `(draft)` only when the meaning is resolved. Do not restart glossary review after a local clarification.

Later runs examine only terms affected by the current question or conflicting evidence.

## During the session

### Challenge against the glossary

Check apparent conflicts against context and code before asking. Clarify only when different meanings
change the model; a harmless synonym does not require interrupting the task.

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

Check claimed current behavior against code. An explicit requested change may intentionally differ;
ask only if current behavior versus desired behavior remains consequentially unclear.

### Update CONTEXT.md inline

Capture resolved terms promptly; batch adjacent edits when useful. Use
[CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md) and resume the parent task after updating the model.

`CONTEXT.md` is a glossary and nothing else: no implementation details, no spec, no scratch pad.

### Record ADRs sparingly

Record a settled decision only when all three conditions in **[ADR-FORMAT.md](./ADR-FORMAT.md)**
hold and domain-document updates are in scope. No second permission to document is needed. A
consequential decision still unresolved needs clarification; an ADR must not invent its acceptance.
