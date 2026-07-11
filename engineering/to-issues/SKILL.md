---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues using vertical slices. For a change that touches existing code, first runs an impact-detection pass (blast radius + regression risk) before slicing. When a PRD is re-run after revision, produces a reconciliation report against existing issues (kept / redo / edit / delete / new).
disable-model-invocation: true
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

The issue tracker has been provided to you — run `/hys-setup` if not.

## Process

### 0. Reconcile against existing issues (MANDATORY when issues exist for this feature)

Before drafting slices, check `.scratch/<feat>/issues/`. If there are existing issues, produce a **reconciliation report** comparing the new plan against them, then ask the user to confirm before doing anything.

Classify every existing issue into one bucket:

```
📋 对账报告
──────────────────────────────────────────────────────────────
仍然有效（不动）:
  ✓ 01-add-schema.md (done)
  ✓ 03-mobile-ui.md (ready-for-human)

已完工但需返工（新建 redo 文件，旧的永不动）:
  ⚠ 02-balance-api.md (done) → 新 PRD 反转了 API 形状
    建议新建：05-redo-balance-api.md (ready-for-agent)

未做且仍相关，但范围/AC 有变（直接改原文件）:
  ✏ 04-cache-strategy.md (ready-for-agent)
    建议改：验收标准 #2 从 X 改 Y，加一条 AC 点...

未做但新 PRD 已不需要（删除）:
  🗑 06-trend-chart.md (ready-for-agent)
    建议：rm 06-trend-chart.md

全新切片（新建）:
  ➕ 07-dark-mode.md (ready-for-human)
──────────────────────────────────────────────────────────────
```

Classification rules:

- **仍然有效** — the existing issue's behavior is unchanged in the new PRD.
- **已完工但需返工** — issue is `done` AND the new PRD invalidates the implementation. Hard rule: never edit a `done` issue. Always produce a new `NN-redo-X.md` (`category: redo`, `refines:` pointing at the original slug). The old file stays as a historical record.
- **未做且范围变了** — issue is `ready-for-X` AND the new PRD changes its scope or AC. Edit the file in place — there's no `done` history to preserve.
- **未做但不需要了** — issue is `ready-for-X` AND the new PRD no longer requires it. Delete the file.
- **全新切片** — nothing existing covers this part of the new PRD.

Let the user confirm the report (item-by-item or yes-all). Then execute: `rm` for deletes, edit for in-place changes, write new files for new + redo. Continue to step 3 to draft the new + redo slices.

**Adding a small detail without a PRD revision.** When the user invokes `/to-issues "在 03-balance-api 上加 X"` to tack a sub-behavior onto an existing slice (rather than re-deriving from a revised PRD), skip the full reconciliation report. Create a single `detail` issue: `category: detail`, `refines: <parent-slug>`, `blocked_by` including the parent if it isn't `done` yet. This is the supported path for incremental detail — it stays traceable to its parent and never silently drifts away from the PRD (痛点 1). `/tidy` later folds these into `SUMMARY.md`.

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
re-run — a checkpoint you show the user, not a silent decision:

1. **Static reachability** — callers/importers of the anchored symbols, and which existing tests
   cover them. Machine-determinable — query it, don't eyeball it. Per-language commands + their
   confidence: [impact-detection.md](./impact-detection.md) (also in `docs/agents/domain.md`).
2. **Semantic coupling** — behaviour the change might break that no import edge shows (invariants
   like "amount ≥ 0", ordering constraints). **Deterministic tools first**: run the runtime /
   coverage commands recorded in `docs/agents/domain.md` (they catch dynamic coupling) and pull
   from `CODEBASE.md`'s invariants. A subagent only fills what those miss — greppable-invisible assumptions —
   one Explore per unresolved area, not a full re-read.
3. **Existing tests whose expectations this change alters** — coupled changes often *edit* a test's
   expectation, not just add tests; flag those so the slices carry the right AC.
4. If a grep-invisible invariant surfaced, **offer to persist it to `CODEBASE.md`** — the next
   coupled change here reuses it instead of re-deriving it.

Use the domain glossary; respect ADRs in the area. On a dynamic language (Python, untyped JS) static
results are a floor, not the ceiling — say so rather than implying the impact list is complete.

### 3. Draft vertical slices

Start from first principles.

**Prefactor first if it helps** — "make the change easy, then make the easy change." When a cheap restructuring unlocks cleaner slices, sequence it as the first issue(s) the rest are `blocked_by`.

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Each slice has a state: `ready-for-agent` (fire-and-forget OK) or `ready-for-human` (needs hands-on judgment / design taste / manual / device testing). **Default to `ready-for-agent`** — only mark `ready-for-human` when there is a specific reason that an agent can't fully verify (architectural choice, UX taste, real-device verification, external account).

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

**Wide refactors are the exception to slicing.** When step 2's impact probe lands in the top tier — a mechanical change (rename a column, retype a shared symbol) whose blast radius fans across the whole codebase, so no vertical slice can land green — sequence it **expand → contract** instead of forcing a tracer bullet: an *expand* issue adds the new form beside the old so nothing breaks; *migrate* issues then move call sites over in batches sized by blast radius (per package / dir), each `blocked_by` the expand and each staying green because the old form still stands; a *contract* issue finally deletes the old form, `blocked_by` every migrate batch. If a batch can't stay green alone, let the batches share an integration branch, with green promised only at a final integrate-and-verify issue they all block.

### 4. Quiz the user

Run an adversarial review.

Present the proposed breakdown as a numbered list. For each slice, show:

- **标题（Title）**: short descriptive name
- **状态（State）**: `ready-for-agent` / `ready-for-human`
- **前置依赖（Blocked by）**: which other slices (if any) must complete first
- **覆盖的场景**: which scenarios from the source PRD

Ask the user:

- 粒度合适吗？（太粗 / 太细）
- 依赖关系对不对？
- `ready-for-agent` / `ready-for-human` 标记对吗？

Iterate until the user approves the breakdown.

### 5. Write issues to `.scratch/<feat>/issues/`

For each approved slice, write a new file `.scratch/<feat>/issues/<NN>-<slug>.md` (next number, kebab-case slug). Frontmatter follows [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md); the body uses the template below.

Write issues in dependency order (blockers first) so you can reference real filenames in both the `blocked_by` frontmatter field and the `前置依赖` section.

<issue-template>

---
# frontmatter per ARTIFACT-FORMAT.md — type / feature / status / category / blocked_by / refines / created
# a fresh slice defaults to status: ready-for-agent, category: enhancement
---

## 上级（Parent）

A reference to the parent PRD or issue (path or filename), if the source was an existing artifact.

## 做什么（What to build）

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

Avoid specific file paths or code snippets — they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it here and note briefly that it came from a prototype.

## 验收标准（Acceptance Criteria）

- [ ] 具体、可验证的条目 1
- [ ] 具体、可验证的条目 2
- [ ] 具体、可验证的条目 3

**写 AC 的两条规则：**
1. **只写本切片新增的行为**。上一切片已提供的能力（schema、已存在的授权、已覆盖的校验）不要重复列出——靠 `blocked_by` 串联。
2. **验收要可独立验证**（“执行 X 后能看到 Y”），不是“应该工作正常”。

## 前置依赖（Blocked by）

- A reference to the blocking issue file (e.g. `01-init-schema.md`), or "无". Keep this in sync with the `blocked_by` frontmatter list.

## Comments

<!-- agent briefs, completion records, post-implementation notes append here. -->

</issue-template>

**Frontmatter** — fill every field per the schema in [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). The three fields that drive this skill's output: `category` (`enhancement` default; `detail`/`redo`/`fix` for later sub-behaviour / re-work, which MUST also set `refines:`), `blocked_by` (sibling slugs that must reach `done` first — `/ship` topologically sorts on it), and `refines` (parent slug, set for non-top-level slices so incremental work stays traceable instead of orphaned).

After writing the issues, regenerate `.scratch/INDEX.md` (see [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md)) so the feature's state counts reflect the new files.

Do NOT modify any parent PRD or upstream issue.
