---
name: spec
description: "The single planning entry: align a need, prove its verifier environment ready, and turn it into dispatchable issues, with a versioned PRD when warranted. Never implements product behavior. Use for any new or changed requirement; /tdd executes what this plans."
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Plans and proves execution readiness; never implements product behavior or invokes `/tdd`. It may
run repository-declared environment setup and representative verifier preflights before writing
PRDs/issues. Frontmatter:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) issue/PRD anchors (not the whole file).
`done` issues are immutable.

Intent has two paths:

- **Settled intake.** The request itself is alignment when it fixes observable outcome, scope,
  constraints, acceptance evidence, and the work is local, reversible, and has a deterministic
  verifier. Do not restate or pause. Prove readiness, then persist the normalized execution contract.
- **Decision intake.** Material ambiguity, product preference, permission, public contract,
  one-way door, high cost, or a claim without an objective verifier loads
  [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md). Ask all material decisions once and wait for alignment.

The receipt is conversation state, not a third issue state. Confidence never closes a decision
frontier. A settled request does because the user already supplied the decision. A graphical UI may
opt into an agent-runnable experience contract; non-graphical work creates no experience artifact.

A repo-relative tracked delegation may be referenced by path and content hash instead of copied.
Chat, URLs, Downloads, mutable external files, and untracked files are normalized into the ordinary
PRD/issue contract so a fresh executor does not need the conversation.

## 1. Locate

Named `<feat>` → `rg` that feature only; else 3–5 keywords over `.scratch/**/PRD*.md` and
`.scratch/**/issues/*.md`.

- No hit → new work. PRD first if the ask spans multiple modules/features or is likely ≥5
  slices → [PRD-TEMPLATE.md](PRD-TEMPLATE.md). Then [CARD-TEST.md](CARD-TEST.md).
- Hit in the target feature: read the live PRD's 实现决策 (if any) and the hit issue's AC/`status`.
  - Nothing recorded goes false → [ADDITIVE.md](ADDITIVE.md).
  - A recorded AC or decision goes false → [SUPERSEDE.md](SUPERSEDE.md).
- Hit elsewhere, or unsure → one question: 加一块还是改方向？ Never auto-supersede a cross-feature hit.

## 2. Impact (touches existing code)

Not an approval gate. Cheap `rg`/`ast-grep` first. Small radius (few callers, one module, no
known invariant): write `touches:`, continue. Coupled (many refs, multiple modules, or an
invariant area): [impact-detection.md](impact-detection.md). Persist a new invariant to the
area's `CODEBASE.md` block (two-axis); don't pause to offer.

Both paths end in [WRITE-LOOP.md](WRITE-LOOP.md). A genuine design trade-off →
`/prototype` before slicing. Wide refactors (mechanical change, blast radius spans the
codebase): expand → contract. Expand adds the new form beside the old; migrate batches move
call sites (each staying green); contract deletes the old form.

A proposed coverage, size, or timing bar →
[NON-FUNCTIONAL-BARS.md](NON-FUNCTIONAL-BARS.md).
