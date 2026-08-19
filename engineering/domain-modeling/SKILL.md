---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when the user wants to pin down domain terminology or a ubiquitous language, record an architectural decision, or when another skill needs to maintain the domain model.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline — challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `CONTEXT.md` for vocabulary is not this skill — that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## File structure

Layout: **[CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md)**. Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## First pass (draft mode)

**When:** `CONTEXT.md` is absent or empty — onboarding a fresh repo. Don't interrogate term-by-term on the first pass — most terms have an obvious recommended name. Switch to draft mode: it trades per-term interrogation for a single review gate.

**Steps:**

1. Explore the code to identify the domain concepts worth capturing. Big repo: one `Explore` subagent per area; draft from their reports.
2. Draft the **entire** glossary in one shot, applying your recommended term for every concept. Follow [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md). Pick canonical terms, list synonyms under `_Avoid_`.
3. Write it to `CONTEXT.md` (or the relevant per-context file), with each term tagged `(draft)`.
4. Present the **whole draft at once** — one review gate, not N interruptions, and never zero review (boundaries / naming are what automation gets wrong). Order the review by confidence: low-confidence terms form a focused question block presented first; no term is auto-passed. Drop the `(draft)` tags once the user confirms.
5. **Only** loop back to ask term-by-term where the code contradicts itself or you genuinely couldn't decide. List those few explicitly rather than walking the entire glossary.

Once a baseline exists, later runs use the relentless per-term challenges below (driven by the `/grilling` loop when stress-testing a plan).

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

`CONTEXT.md` is a glossary and nothing else — no implementation details, no spec, no scratch pad.

### Offer ADRs sparingly

All three conditions in **[ADR-FORMAT.md](./ADR-FORMAT.md)** hold → offer to write the ADR; any condition missing → skip. The gate is the filter — no gate, no ADR.
