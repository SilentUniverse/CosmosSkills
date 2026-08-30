---
name: spec
description: The single planning entry — align a need, prove its verifier environment ready, and turn it into dispatchable issues, with a versioned PRD when warranted. Never implements product behavior. Use for any new or changed requirement; /tdd executes what this plans.
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Plans and proves execution readiness; never implements product behavior or invokes `/tdd`. It may
run repository-declared environment setup and representative verifier preflights before writing
PRDs/issues. Frontmatter:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) issue/PRD anchors (not the whole file).
`done` issues are immutable.

Planning has two phases: teach the design back in a [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md),
then write artifacts only after the user explicitly aligns. The receipt is conversation state,
not a third issue state.

The alignment gate covers not only what to build but what would prove it wrong. A graphical UI can
opt into an agent-runnable experience contract; every non-graphical project follows the ordinary
workflow with no experience field, artifact, rubric, or review axis.

A delegation that already fixes the acceptance behaviors, the verification commands, and the
constraints closes the decision frontier: do not re-derive or restate it. Run the ordinary
readiness preflights, then present a receipt whose 目标回放 names the user's document as the
requirements-of-record, with the P# register and the proposed slice DAG. The write step then
produces a PRD stub pointing at that document instead of a restated PRD. The alignment gate is
never compressed away, and one open decision reopens the full loop.

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
