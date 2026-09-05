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
- Question cannot be stated precisely now → **fog**. Investigate the nearest concrete scenario.
  Park optional future work in 尚未明确; if it blocks the requested outcome, surface what is missing
  and a useful question. Finish independent units; parked in-scope work is not completion.
- Check the agent cannot run (irreducible taste, inaccessible external account, permission) → not an AC. Park: PRD
  端到端验证; no PRD → `### 完成` 手动验证 on the issue that has the agent-runnable AC.
  A unit that is only that check is not an issue.

Split when units have independent outcomes, verification, or scheduling needs. A dependency is
`blocked_by`; wording such as “and also” is not a split criterion. Keep one coherent behavior and
its error paths together. Each extra card must repay its handoff and verification overhead.

Parallel-bound slices declare their write set: `touches:` (dirs) + `test_paths:` (test files,
from the AC). `--log` slices declare no `test_paths`; their acceptance is a log predicate. `-p` wave
semantics live with the field: [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). Only a graphical UI
slice adds `experience_review`: use `runtime` for operated-state/runtime integrity and `graded` when
visual hierarchy or usability is itself an aligned requirement. Backend, library, API, CLI,
document, report, config, and other non-graphical slices omit the field entirely. Operable visual
properties are AC when browser/CDP or an equivalent surface can capture them. Split only irreducible
taste or inaccessible surfaces to PRD human verification. An opted-in UI slice without fixed-state
evidence and a verifier that can fail on the named visual defect is not writable.

Slice order: first card = the smallest correct working core (tracer); later cards grow on it.
No abstraction for a future the PRD doesn't name.

`status`: `ready` | `done`. Human-only work is never an issue.

## Slice review

For each slice check outcome, evidence, dependencies, and reasoning radius: how many modules must
be read to trust the change. Start with one vertical cut; compare alternatives only if it cannot be
verified independently or creates avoidable coupling. Write a receipt only for decision intake.
Internal regrouping is autonomous when it preserves settled scope, public interfaces, and proof.
