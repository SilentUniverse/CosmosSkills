# spec — Card test and grain

Loaded on demand by [`/spec`](SKILL.md) when units are being classified and cut — new work and
additive growth both land here. Issue body and frontmatter: [ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md).

A unit is an issue iff `## 做什么` + ≥1 agent-runnable AC + an AC→evidence→passed-P# mapping can be
written for an agent that sees nothing else. AC derive from invariants first, examples second, and run
through a named seam's interface — vocabulary per `/codebase-design`. Pick the seam external
callers enter; prefer existing seams to new ones; use the fewest that cover the ACs. Evidence
and SPEC-stage environment readiness follow
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md). Look up facts and run preflights; do not ask the
user for discoverable environment facts.
Classify each unit:

- Writable, every verifier harness has passed preflight, and no outstanding question can falsify
  its AC / `blocked_by` / module boundary →
  **settled**.
- One missing decision, or two answers yield two AC sets → **open**. Ask that decision only,
  with a recommended answer. When a live PRD exists, bake it as an Implementation Decision instead.
  ADR-worthy — all three in [ADR-FORMAT.md](../domain-modeling/ADR-FORMAT.md) — after this
  turn's writes, next: `/grill`. Do not hold writes the ADR cannot falsify.
- Question cannot be stated precisely now → **fog**. PRD 尚未明确; no PRD → list at stop.
  File nothing. Ask nothing.
- Check the agent cannot run (taste, external account, human-eye) → not an AC. Park: PRD
  端到端验证; no PRD → `### 完成` 手动验证 on the issue that has the agent-runnable AC.
  A unit that is only that check is not an issue.

Write-failures: "depends on X" → `blocked_by`, do not grow the unit. "and also…" → split.
Two units always done together in the same files → one issue.

Parallel-bound slices declare their write set: `touches:` (dirs) + `test_paths:` (test files,
from the AC). `--log` slices declare no `test_paths`; their acceptance is a log predicate. `-p` wave
semantics live with the field: [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). A UI slice
splits first: logic and structure become AC (testable); pure visuals go to
the PRD 端到端验证. An unsplit UI implementation has no AC.

Slice order: first card = the smallest correct working core (tracer); later cards grow on it.
No abstraction for a future the PRD doesn't name.

`status`: `ready` | `done`. Human-only work is never an issue.

## Slice review

The Design Receipt replaces the size-gated grain quiz: every batch exposes its slice DAG before
write, because alignment risk is not proportional to card count. Report per slice: AC count,
`blocked_by`, seam, requirement IDs, P# coverage, and reasoning radius — how many modules one must read to trust
the change. Parallel-draft 2–3 alternatives only when the first cut fails evidence completeness,
dependency depth, or vertical completeness; otherwise review one cut. Approval covers that exact
DAG; changing a boundary or blocker returns to alignment.
