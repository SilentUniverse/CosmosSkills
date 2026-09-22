# cosmos-setup — The two decisions

Loaded by [cosmos-setup](SKILL.md) step 3 for unresolved setup decisions. Reuse the user's
choices and repo configuration; explain only choices whose consequences still need a decision.

## Section A — Issue tracker（issue 追踪位置）

> Explainer: The "issue tracker" is where issues and PRDs live for this repo. `/spec` and `/tdd` read from and write to it.

Default and recommended: **local markdown**. Pick this unless the user specifically requests otherwise:

- **Local markdown（default）** — issues live as files under `.scratch/<feature>/`; pure local, zero external dependencies.
- **Other** (GitHub / GitLab / Jira / Linear, etc.) — preserve an existing choice or use the user's requested tracker. Inspect its configuration and available CLI/connector first; record the verified workflow in `docs/agents/issue-tracker.md`. Ask only for missing account access or consequential workflow choices, and continue local setup meanwhile.

## Section B — State vocabulary（状态词汇）

> Issue frontmatter describes engineering readiness and completion, never native task state.

- `pending`: a concrete engineering goal has a recorded `pending_reason`.
- `ready`: the contract and required verification route are prepared; acceptance, dependencies and
  real resource constraints must still permit this operation.
- `done`: validated completion evidence covers the contract. Missing or damaged proof cannot be
  repaired by changing the marker; retain history and diagnose the affected obligation.

Native queued/running/stopped state stays with the host. Human-only checks live in the PRD's
端到端验证 or the Issue's 手动验证, separate from engineering AC and status. Schema:
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).
