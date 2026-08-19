---
name: plan
description: The single planning entry — turn any need (one-liner, grilled design, or mid-flight change) into dispatchable issues, with a versioned PRD when the intent warrants one. Scales internally: small asks skip the PRD, unclear ones get grilled inline, changed intents supersede. Use for any new or changed requirement; /tdd executes what this plans.
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Plan

One planning activity, two artifacts: the **PRD** (versioned intent snapshot — why + what, for
reconciliation) and **issues** (the dispatch queue). Small asks need no PRD — the issue's
`## 上级` carries its own context. All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).

## Flow

1. **Classify the ask.**
   - Small and clear (one behavior, no cross-feature impact) → skip to step 3; no PRD.
   - Unclear or contested → run the `/grilling` discipline inline (challenge terms, stress
     scenarios) until the intent is writable; then continue here.
   - Existing feature touched → overlap scan: `rg` 3–5 keywords over `.scratch/**/PRD*.md` and
     `.scratch/**/issues/*.md`.
     - Hits inside the target feature + intent unchanged → `detail` issue (`refines:` parent) or
       edit the ready issue in place.
     - Intent changed → write `PRD-vN.md` per [PRD-TEMPLATE.md](PRD-TEMPLATE.md) and reconcile
       against existing issues ([RECONCILE.md](RECONCILE.md)).
     - Hits elsewhere, or ambiguous whether the intent changed → one soft confirm ("加一块还是
       改方向？") — never auto-supersede a cross-feature hit.

2. **Impact probe** (the change touches existing code) — [impact-detection.md](impact-detection.md):
   one cheap reference probe gates the depth; the report is visibility, not an approval gate.

3. **Draft issues by the dispatchability test** — [ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md). A unit
   is an issue iff a self-sufficient card (`## 做什么` + AC) can be written for an agent that
   sees nothing else. Each failure to write the card maps to an action:
   - "depends on X" → `blocked_by` link, don't grow the unit
   - "decide later" → bake the decision into the spec, or grill it now
   - "and also…" → split
   - a check no agent can run (device, taste, external account) → not an AC: register it in the
     PRD's 端到端验证 (no PRD — small ask? the issue's `### 完成` 手动验证 line instead) and
     flag it for the batch report; the issue carries only agent-verifiable AC
   - reverse guard: two units always done together in the same files → one issue

   `status` has two values: `ready` (dispatchable) and `done`. Human-only work never
   becomes an issue.

4. **Quiz the user.** Report mechanically per slice (AC count, `blocked_by` resolution, DAG
   depth), then ask: 粒度 / 依赖有要调的吗？ + 这批切片共同建立在哪条假设上？它错了会塌什么？
   For likely ≥5-slice features: parallel-draft 2–3 breakdowns, rank mechanically (AC
   verifiability, dependency depth, vertical completeness), quiz the winner, list runners-up as
   one-line alternates (same pattern as `/codebase-design`'s design-it-twice).

5. **Write** issues in dependency order (blockers first), then run the machine gate
   (`../verify-artifacts.ps1` / `.sh`).

Wide refactors (mechanical change whose blast radius spans the codebase) sequence **expand →
contract** — an expand issue adds the new form beside the old, migrate batches move call sites
(each staying green), a contract issue deletes the old form.

**PRD rules** (when warranted): template per [PRD-TEMPLATE.md](PRD-TEMPLATE.md); frontmatter per
ARTIFACT-FORMAT; supersede is the default on re-runs inside the target feature; machine gate
after superseding.
