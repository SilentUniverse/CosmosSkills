# spec — Card test and grain

Loaded on demand by [`/spec`](SKILL.md) when units are being classified and cut — new work and
additive growth both land here. Issue body and frontmatter: [ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md).

A unit is an issue iff `## 做什么` + ≥1 agent-runnable AC can be written for an agent that sees
nothing else. Look up facts; do not ask them. Classify each unit:

- Writable, and no outstanding question can falsify its AC / `blocked_by` / module boundary →
  **settled**.
- One missing decision, or two answers yield two AC sets → **open**. Ask that decision only,
  with a recommended answer — or, when a live PRD exists, bake it as an Implementation Decision.
  ADR-worthy — all three in [ADR-FORMAT.md](../domain-modeling/ADR-FORMAT.md) — after this
  turn's writes, next: `/grill`. Do not hold writes the ADR cannot falsify.
- Question cannot be stated precisely now → **fog**. PRD 尚未明确; no PRD → list at stop.
  File nothing. Ask nothing.
- Check the agent cannot run (taste, external account, human-eye) → not an AC. Park: PRD
  端到端验证; no PRD → `### 完成` 手动验证 on the issue that has the agent-runnable AC.
  A unit that is only that check is not an issue.

Write-failures: "depends on X" → `blocked_by`, do not grow the unit. "and also…" → split.
Two units always done together in the same files → one issue.

`status`: `ready` | `done`. Human-only work is never an issue.

## Grain quiz

Runs immediately after classification, before any write, only if the batch is likely ≥5 slices.
Skip: 1 slice, `detail`, `redo`, `fix`. Report per slice: AC count, `blocked_by`, DAG depth.
Ask: 粒度 / 依赖有要调的吗？ 这批切片共同建立在哪条假设上？它错了会塌什么？
Parallel-draft 2–3 breakdowns only when the first cut fails AC verifiability, dependency
depth, or vertical completeness; otherwise quiz that cut. An unanswered quiz falsifies only
cards whose AC / `blocked_by` / module boundary it can change — write the rest.
