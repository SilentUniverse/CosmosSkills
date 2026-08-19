---
name: spec
description: The single planning entry — turn any need into dispatchable issues, with a versioned PRD when the intent warrants one. Writes artifacts only, never code. Use for any new or changed requirement; /tdd executes what this plans.
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Writes PRDs and issues only. Never code. Never invoke `/tdd`. Artifacts: [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).

## Flow

1. **Locate.** `rg` 3–5 keywords over `.scratch/**/PRD*.md` and `.scratch/**/issues/*.md`.
   - No hit → new work.
   - Hit in the target feature, additive (no recorded AC or decision goes false) → `detail` (`refines:` parent) or edit the ready issue.
   - Hit that makes a recorded AC or decision false → `PRD-vN.md` per [PRD-TEMPLATE.md](PRD-TEMPLATE.md); reconcile ([RECONCILE.md](RECONCILE.md)).
   - Hit elsewhere, or unsure → one question: 加一块还是改方向？ Never auto-supersede a cross-feature hit.

2. **Impact** (touches existing code) — [impact-detection.md](impact-detection.md). Not an approval gate.

3. **PRD.** Write when the ask spans multiple modules/features, is likely ≥5 slices, or intent will plausibly change again. Else skip — `## 上级` carries context. Step 1's intent-changed case already writes `PRD-vN`.

4. **Card test.** A unit is an issue iff `## 做什么` + ≥1 agent-runnable AC can be written for an agent that sees nothing else ([ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md)). Look up facts; do not ask them. Classify each unit:
   - Writable, and no outstanding question can falsify its AC / `blocked_by` / module boundary → **settled**.
   - One missing decision, or two answers yield two AC sets → **open**. Ask that decision only, with a recommended answer. ADR-worthy (hard to reverse, confusing out of context, or a real tradeoff) → after this turn's writes, next: `/grill`. Do not hold writes the ADR cannot falsify.
   - Question cannot be stated precisely now → **fog**. PRD 尚未明确; no PRD → list at stop. File nothing. Ask nothing.
   - Check the agent cannot run (taste, external account, human-eye) → not an AC. Park: PRD 端到端验证; no PRD → `### 完成` 手动验证 on the issue that has the agent-runnable AC. A unit that is only that check is not an issue.

   Write-failures: "depends on X" → `blocked_by`, do not grow the unit. "and also…" → split. Two units always done together in the same files → one issue.

   `status`: `ready` | `done`. Human-only work is never an issue.

5. **Grain quiz** only if likely ≥5 slices, or DAG depth ≥2 and ≥3 slices. Report per slice: AC count, `blocked_by`, DAG depth. Ask: 粒度 / 依赖有要调的吗？ 这批切片共同建立在哪条假设上？它错了会塌什么？ ≥5 slices: parallel-draft 2–3 breakdowns; rank by AC verifiability, dependency depth, vertical completeness; quiz the winner; runners-up as one-line alternates. Skip: 1 slice, `detail`, `redo`, `fix`. A quiz asked this turn is outstanding until answered — it falsifies every unwritten card.

6. **Write / ask.** This turn, in order:
   - Fire step 5 if it applies and has not returned.
   - Ask every remaining open question that is not ADR-worthy.
   - Write every settled card that no outstanding question (open, or unanswered grain quiz) can falsify. `status: ready`. Dependency order.
   - Machine gate (`../verify-artifacts.ps1` / `.sh`) on files written this run.
   - Print: 已落盘（paths or （无））；待决（this turn's questions, if any）；尚未明确（fog, if any）；下一句：omit if 待决 is non-empty; else `/grill` if an ADR-worthy open remains; else `/tdd <path>` — first `ready` issue this run; omit if none ready.
   - Outstanding questions → wait. After an answer, resume from step 4 on unwritten units.
   - Nothing outstanding → stop.

Wide refactors (mechanical change, blast radius spans the codebase): expand → contract — expand adds the new form beside the old; migrate batches move call sites (each staying green); contract deletes the old form.

**PRD rules** (when warranted): [PRD-TEMPLATE.md](PRD-TEMPLATE.md); frontmatter per ARTIFACT-FORMAT; supersede is the default on re-runs inside the target feature; machine gate after superseding.
