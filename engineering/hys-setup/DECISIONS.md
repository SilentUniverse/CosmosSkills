# hys-setup — The three decisions

Loaded on demand by [hys-setup](SKILL.md) step 3 while walking the user through the setup
decisions, one at a time. Each section opens with a short explainer (what it is, why these
skills need it, what changes if they pick differently), then the choices and the default.

## Section A — Issue tracker（issue 追踪位置）

> Explainer: The "issue tracker" is where issues and PRDs live for this repo. `/spec` and `/tdd` read from and write to it.

Default and recommended: **local markdown**. Pick this unless the user specifically requests otherwise:

- **Local markdown（default）** — issues live as files under `.scratch/<feature>/`; pure local, zero external dependencies.
- **Other** (GitHub / GitLab / Jira / Linear, etc.) — only when the user explicitly asks. Have the user describe the workflow in one paragraph; the skill records it verbatim into `docs/agents/issue-tracker.md`. Note: this introduces external CLI/account dependencies, conflicting with the local-first goal; the user is responsible for the corresponding environment setup.

## Section B — State vocabulary（状态词汇）

> Explainer: Each issue file under `.scratch/<feat>/issues/` carries a `status:` field in its YAML frontmatter. A **2-state model**: the issue queue is the agent's dispatch queue.

The two canonical states:

- `ready` — fully specified, fire-and-forget OK (dispatch to a subagent)
- `done` — completed; **immutable** (git has the commit; revisions are new issues)

Hands-on checks no agent can run live in the PRD's 端到端验证 — never as a state or issue AC (schema: `ARTIFACT-FORMAT.md`; check list: `/spec` card test).

## Section C — Domain docs（领域文档布局）

> Explainer: Some skills (`improve-arch`, `diagnose`, `tdd`) read `CONTEXT.md` for the project's domain language and `docs/adr/` for past architectural decisions. They need to know whether the repo is single-context or multi-context (e.g. a monorepo with separate frontend/backend contexts) so they look in the right place.

Confirm the layout:

- **Single-context** — one `CONTEXT.md` + `docs/adr/` at the repo root. Most repos are this.
- **Multi-context** — `CONTEXT-MAP.md` at the root pointing to per-context `CONTEXT.md` files (typically a monorepo).
