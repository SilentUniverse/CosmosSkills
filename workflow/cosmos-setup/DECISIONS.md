# cosmos-setup — The two decisions

Loaded by [cosmos-setup](SKILL.md) step 3 for unresolved setup decisions. Reuse the user's
choices and repo configuration; explain only choices whose consequences still need a decision.

## Section A — Tracker（追踪位置）

> Explainer: The tracker is where feature documents live for this repo. `/spec` and `/tdd` read from and write to it.

Default and recommended: **local markdown**. Pick this unless the user specifically requests otherwise:

- **Local markdown（default）** — one `.scratch/<feat>/FEATURE.md` per feature; pure local, zero external dependencies.
- **Other** (GitHub / GitLab / Jira / Linear, etc.) — preserve an existing choice or use the user's requested tracker. Inspect its configuration and available CLI/connector first; record the verified workflow in `docs/agents/issue-tracker.md`. Ask only for missing account access or consequential workflow choices, and continue local setup meanwhile.

## Section B — State vocabulary（状态词汇）

> Unit `status` describes engineering readiness and completion, never native task state.

- `pending`: a concrete engineering goal has a recorded `reason`.
- `ready`: the contract and required verification route are prepared; acceptance, dependencies and
  real resource constraints must still permit this operation.
- `done`: validated completion evidence covers the contract. Missing or damaged proof cannot be
  repaired by changing the marker; retain history and diagnose the affected obligation.

Native queued/running/stopped state stays with the host. Human-only checks live in FEATURE.md's
端到端验证, separate from engineering AC and status. Schema:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).
