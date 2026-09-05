# cosmos-setup — The two decisions

Loaded by [cosmos-setup](SKILL.md) step 3 for unresolved setup decisions. Reuse the user's
choices and repo configuration; explain only choices whose consequences still need a decision.

## Section A — Issue tracker（issue 追踪位置）

> Explainer: The "issue tracker" is where issues and PRDs live for this repo. `/spec` and `/tdd` read from and write to it.

Default and recommended: **local markdown**. Pick this unless the user specifically requests otherwise:

- **Local markdown（default）** — issues live as files under `.scratch/<feature>/`; pure local, zero external dependencies.
- **Other** (GitHub / GitLab / Jira / Linear, etc.) — preserve an existing choice or use the user's requested tracker. Inspect its configuration and available CLI/connector first; record the verified workflow in `docs/agents/issue-tracker.md`. Ask only for missing account access or consequential workflow choices, and continue local setup meanwhile.

## Section B — State vocabulary（状态词汇）

> Explainer: Each issue file under `.scratch/<feat>/issues/` carries a `status:` field in its YAML frontmatter. A **2-state model**: the issue queue is the agent's dispatch queue.

The two canonical states:

- `ready` — fully specified and aligned, with every AC mapped to agent-runnable evidence and every
  verifier harness prepared and preflighted by SPEC;
  fire-and-forget OK (dispatch to a subagent)
- `done` — completed; historical issues are immutable and later behavior changes use new issues.
  Only active-batch failed-verification recovery may reopen one under [DRAIN](../tdd/DRAIN.md).

Hands-on checks no agent can run live in the PRD's 端到端验证; never as a state or issue AC (schema: `ARTIFACT-FORMAT.md`; check list: `/spec` card test).
