---
name: spec
description: The single planning entry — turn any need into dispatchable issues, with a versioned PRD when the intent warrants one. Writes artifacts only, never code. Use for any new or changed requirement; /tdd executes what this plans.
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Writes PRDs and issues only. Never code. Never invoke `/tdd`. Frontmatter:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) issue/PRD anchors (not the whole file).
`done` issues are immutable.

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

Both write paths end in [WRITE-LOOP.md](WRITE-LOOP.md). A genuine design trade-off →
`/prototype` before slicing. Wide refactors (mechanical change, blast radius spans the
codebase): expand → contract — expand adds the new form beside the old; migrate batches move
call sites (each staying green); contract deletes the old form.
