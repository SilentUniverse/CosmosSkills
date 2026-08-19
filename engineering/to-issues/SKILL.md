---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues using vertical slices. For a change that touches existing code, first runs an impact-detection pass (blast radius + regression risk) before slicing. When a PRD is re-run after revision, produces a reconciliation report against existing issues (kept / redo / edit / delete / new).
argument-hint: "PRD/issue path, or a detail ask like \"在 03-slug 上加 X\"; nothing to use the latest PRD"
disable-model-invocation: true
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

The issue tracker has been provided to you — run `/hys-setup` if not.

## Process

### 0. Reconcile against existing issues (MANDATORY when issues exist for this feature)

Before drafting slices, check `.scratch/<feat>/issues/`. If there are existing issues, produce a **reconciliation report** comparing the new plan against them (classify each existing issue into 仍然有效 / 需返工 / 范围变了 / 删除 / 全新切片), then ask the user to confirm before doing anything. Full report format + classification rules: **[RECONCILE.md](RECONCILE.md)**.

**Adding a small detail without a PRD revision.** When the user invokes `/to-issues "在 03-balance-api 上加 X"` to tack a sub-behavior onto an existing slice (rather than re-deriving from a revised PRD), skip the full reconciliation report. Create a single `detail` issue: `category: detail`, `refines: <parent-slug>`, `blocked_by` including the parent if it isn't `done` yet. This is the supported path for incremental detail — it stays traceable to its parent and never silently drifts away from the PRD. `/tidy` later folds these into `SUMMARY.md`.

If no existing issues directory, skip to step 1.

### 1. Gather context

Work from the latest non-superseded `PRD*.md` in the feature directory. If the user passes an explicit issue path or PRD path as an argument, use that.

If the PRD carries a **尚未明确（Fog of War）** section, test each item's sharpness — can you phrase it precisely enough to slice *now*? Graduate the sharp ones into slices in step 3 (record the lineage in the issue's `## 上级`); leave the rest to ride forward to the next PRD. The PRD stays untouched — report which items graduated in the step 4 quiz.

### 2. Detect impact (coupling check — before slicing)

**One cheap probe gates this whole step; scale the response to the blast radius it reveals.** Don't
guess whether a change is "big" or "coupled" — measure it. Anchor the symbols the request names
(`CONTEXT.md` vocabulary — Order, Refund, Balance) and `rg` / `ast-grep` for references:

| Probe result | Do this |
|---|---|
| **No references** — genuinely new | Skip to step 3 and slice. |
| **A few references, one module, no known invariant** — small blast radius | Note it in one line ("touches `Order.total`, 2 callers, no invariant") and slice. **No report, no subagent** — a tiny change finishes here. |
| **Many references / multiple modules / a known-invariant area** — real coupling | Produce the impact report below before slicing. |

When unsure which tier, round **up** — a missed coupling is a regression; an extra glance is cheap.

**Impact report** (only the third tier). It's to slicing what the reconciliation report is to a
re-run — present it, then continue to slicing: visibility, not an approval gate.

1. **Static reachability** — callers/importers of the anchored symbols, and which existing tests
   cover them. Machine-determinable — query it, don't eyeball it. Per-language commands + their
   confidence: [impact-detection.md](./impact-detection.md) (also recorded in `docs/agents/domain.md`).
2. **Semantic coupling** — behaviour the change might break that no import edge shows (invariants
   like "amount ≥ 0", ordering constraints). **Deterministic tools first**: run the runtime /
   coverage commands recorded in `docs/agents/domain.md` (they catch dynamic coupling) and pull
   from `CODEBASE.md`'s invariants. A subagent only fills what those miss — greppable-invisible assumptions —
   one Explore per unresolved area, not a full re-read.
3. **Existing tests whose expectations this change alters** — coupled changes often *edit* a test's
   expectation, not just add tests; flag those so the slices carry the right AC.
4. A grep-invisible invariant that passes the two-axis test → **persist it to the area's
   `CODEBASE.md` block and report it**. Repo has no `CODEBASE.md` yet → note it in the report
   instead (never bootstrap the orientation layer uninvited).

Use the domain glossary; respect ADRs in the area. On a dynamic language (Python, untyped JS) static
results are a floor, not the ceiling — say so rather than implying the impact list is complete.

### 3. Draft vertical slices

Start from first principles about the plan.

**Prefactor first if it helps** — "make the change easy, then make the easy change." When a cheap restructuring unlocks cleaner slices, sequence it as the first issue(s) the rest are `blocked_by`.

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Each slice has a state: `ready-for-agent` (fire-and-forget OK) or `ready-for-human` (needs hands-on judgment / design taste / manual / device testing). **Default to `ready-for-agent`** — only mark `ready-for-human` when there is a specific reason that an agent can't fully verify (architectural choice, UX taste, real-device verification, external account).

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

**Wide refactors are the exception to slicing.** When step 2's impact probe lands in the top tier — a mechanical change (rename a column, retype a shared symbol) whose blast radius fans across the whole codebase, so no vertical slice can land green — sequence it **expand → contract** instead of forcing a tracer bullet: an *expand* issue adds the new form beside the old so nothing breaks; *migrate* issues then move call sites over in batches sized by blast radius (per package / dir), each `blocked_by` the expand and each staying green because the old form still stands; a *contract* issue finally deletes the old form, `blocked_by` every migrate batch. If a batch can't stay green alone, resize or merge batches until each does; if that's genuinely impossible, mark those issues `ready-for-human`.

**Large feature (likely ≥5 slices): design the breakdown more than once.** Dispatch 2–3 parallel
subagents, each drafting a full slice plan from the same PRD extract and impact report (they can't
see this conversation — brief them fully). Rank mechanically: share of ACs independently
verifiable, dependency depth (shallower wins), vertical completeness. The best draft feeds the
step-4 quiz; runners-up appear as one-line alternates the user can promote. Smaller features:
draft once inline. Same pattern as `/codebase-design`'s design-it-twice.

### 4. Quiz the user

Run an adversarial review: check every PRD 用户场景/实现决策 item; list any no slice covers, each with a disposition (fold into a slice / Out of Scope / 尚未明确).

Present the proposed breakdown as a numbered list. For each slice, show:

- **标题（Title）**: short descriptive name
- **状态（State）**: `ready-for-agent` / `ready-for-human`
- **前置依赖（Blocked by）**: which other slices (if any) must complete first
- **覆盖的场景**: which scenarios from the source PRD

Ask the user:

- 粒度合适吗？（太粗 / 太细）
- 依赖关系对不对？
- `ready-for-agent` / `ready-for-human` 标记对吗？
- 这批切片共同建立在哪条假设上？它错了会塌什么？

Iterate until the user approves the breakdown.

### 5. Write issues to `.scratch/<feat>/issues/`

For each approved slice, write a new file `.scratch/<feat>/issues/<NN>-<slug>.md` (next number, kebab-case slug), in dependency order (blockers first). Frontmatter follows [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd); the body template + the three driving frontmatter fields (`category` / `blocked_by` / `refines`): **[ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md)**. Fill `## 上级`'s PRD extract and `touches:` from the step-2 probe; omit `touches:` if the probe skipped. If the probe found the slice alters a mapped area's seam or invariant, add one AC line: 完成时同批刷新该区 `CODEBASE.md` 生成块并 re-stamp `git_base`.

Do NOT modify any parent PRD or upstream issue.

**Post-write integrity check (mandatory).** Run the machine gate — `../verify-artifacts.ps1` (or `verify-artifacts.sh`) against the repo root: `blocked_by` / `refines` resolution, `NN` uniqueness, acyclicity, and the rest of the mechanical contract ([ARTIFACT-FORMAT.md §Machine gate](../ARTIFACT-FORMAT.md#machine-gate)). Script unavailable? Do the same checks by hand in one pass.
