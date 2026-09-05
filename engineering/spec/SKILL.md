---
name: spec
description: "Plan a requirement, resolve consequential decisions, and prepare verifiable execution slices. Use for explicit planning requests or work needing multiple slices, durable handoff, or unresolved product boundaries. Small settled changes can proceed inline; /tdd owns test-first implementation."
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Owns the planning phase and execution readiness. An explicit `/spec` or plan-only request ends
with its plan. When called inside an implementation request, return the settled contract to the
caller, which continues implementation without another user command. This phase may run declared
setup and representative verifier preflights; it does not write product behavior. Frontmatter:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) issue/PRD anchors (not the whole file).
`done` issues are immutable.

Intent has two paths:

- **Settled intake.** The request itself is alignment when its outcome and constraints are clear
  from the request, prior decisions, and repository evidence. Choose routine implementation details
  and a suitable deterministic verifier autonomously; report material reversible assumptions.
- **Decision intake.** Only an unresolved material ambiguity about outcome, scope, public contract,
  irreversible effects, significant cost, or authority loads [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md).
  Ask the remaining decisions together and hold only their dependent work. Missing implementation
  detail, card boundaries, or a previously authorized change does not reopen alignment.

The receipt is conversation state, not a third issue state. Confidence never closes a decision
frontier. A settled request does because the user already supplied the decision. A graphical UI may
opt into an agent-runnable experience contract; non-graphical work creates no experience artifact.

A repo-relative tracked delegation may be referenced by path and content hash instead of copied.
Chat, URLs, Downloads, mutable external files, and untracked files are normalized into the ordinary
PRD/issue contract so a fresh executor does not need the conversation.

## 1. Locate

Named `<feat>` → `rg` that feature only; else 3–5 keywords over `.scratch/**/PRD*.md` and
`.scratch/**/issues/*.md`.

- No hit → new work. Use [PRD-TEMPLATE.md](PRD-TEMPLATE.md) when shared scenarios/decisions need
  a durable owner across slices. Multi-module reach or card count alone does not require a PRD.
  Use [CARD-TEST.md](CARD-TEST.md) for a queue or handoff; a small settled plan can stay inline.
- Hit in the target feature: read the live PRD's 实现决策 (if any) and the hit issue's AC/`status`.
  - Nothing recorded goes false → [ADDITIVE.md](ADDITIVE.md).
  - A recorded AC or decision goes false → [SUPERSEDE.md](SUPERSEDE.md).
- Hit elsewhere → inspect ownership and the requested outcome. Ask only if competing interpretations
  would change behavior or scope; a keyword match alone never supersedes another feature.

## 2. Impact (touches existing code)

Not an approval gate. Cheap `rg`/`ast-grep` first. Small radius (few callers, one module, no
known invariant): write `touches:`, continue. Coupled (many refs, multiple modules, or an
invariant area): [impact-detection.md](impact-detection.md). Persist a new invariant to the
area's `CODEBASE.md` block (two-axis); don't pause to offer.

Issue-producing paths end in [WRITE-LOOP.md](WRITE-LOOP.md). Use `/prototype` only when a
concrete unresolved design question is cheaper to answer with a runnable experiment. Wide refactors (mechanical change, blast radius spans the
codebase): expand → contract. Expand adds the new form beside the old; migrate batches move
call sites (each staying green); contract deletes the old form.

A proposed coverage, size, or timing bar →
[NON-FUNCTIONAL-BARS.md](NON-FUNCTIONAL-BARS.md).
