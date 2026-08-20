---
name: hys-setup
description: Sets up an `## Agent skills` block in AGENTS.md/CLAUDE.md and `docs/agents/` so the engineering skills know this repo's issue tracker (local markdown by default) and domain doc layout. Run before first use of `spec`, `tdd`, `diagnose`, `improve-arch`, or `zoom-out` — or if those skills appear to be missing context about the issue tracker or domain docs.
disable-model-invocation: true
---

# Setup (hys-setup)

Scaffold the per-repo configuration that the engineering skills assume:

- **Issue tracker** — where issues live (local markdown by default; see below)
- **State vocabulary** — the strings used for the two issue states
- **Domain docs** — where `CONTEXT.md` and ADRs live, and the consumer rules for reading them

This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `AGENTS.md` and `CLAUDE.md` at the repo root — does either exist? Is there already an `## Agent skills` section in either?
- `CONTEXT.md` and `CONTEXT-MAP.md` at the repo root
- `docs/adr/` and any `src/*/docs/adr/` directories
- `docs/agents/` — does this skill's prior output already exist? If yes, what does `issue-tracker.md` describe (local markdown, GitHub `gh` CLI, GitLab `glab`, other)?
- `.scratch/` — sign that the local-markdown issue tracker convention is already in use. If present, sample one issue file: does it have YAML frontmatter (a `---` fence with `type: issue`), or only a bare `Status:` line? Also check whether any `issues/archive/` directories exist.
- Other PRD-like locations: `docs/prd/`, `docs/specs/`, `requirements/`, `prds/`, `specs/`
- Other issue-like locations: `issues/`, `tasks/`, `tickets/`

### 2. Migration check

Classify the repo into one of four cases based on what step 1 found, and announce the case to the user before proceeding:

**Case 1 — Clean repo.** No `.scratch/`, no `docs/agents/`, no existing `## Agent skills` block. Skip migration; proceed to step 3.

**Case 2 — Already on hys conventions.** `.scratch/<feat>/issues/*.md` files have `Status:` lines (or frontmatter) that already match the 2-state vocabulary in `ARTIFACT-FORMAT.md` (`ready` / `done`). Tell the user setup will refresh `docs/agents/*.md` only, leaving issue files untouched. Legacy `ready-for-human` issues: offer to fold their hands-on checks into the PRD's 端到端验证 and set `ready` (or `done` if the user already did the work). If the issue files still carry only a bare `Status:` line (no YAML frontmatter), also run the **Case 5 frontmatter migration** ([MIGRATION.md](MIGRATION.md)) before proceeding. Otherwise proceed to step 3.

**Case 3 — Old setup detected.** `docs/agents/issue-tracker.md` references `gh` / `glab` CLI, or issue files use deprecated states (`needs-triage`, `needs-info`, `wontfix`, `inbox`, `blocked`, `doing`, `shelved`). Offer to switch to local-markdown + 2-state, or keep the old tracker — full procedure in [MIGRATION.md](MIGRATION.md).

**Case 4 — PRD/issue-like files at non-default paths.** Surface the paths found. Offer two options, recommending (i) by default since it is non-destructive:

- (i) **Configure paths in place.** Write the actual paths into `docs/agents/issue-tracker.md` so the skills read/write there. No file moves.
- (ii) **Adopt new layout.** Help the user move/symlink existing files into `.scratch/<feat>/` structure. Show the planned moves before executing; use `git mv` where possible.

**Case 5 — Frontmatter migration (bare `Status:` lines).** Triggered from Case 2 (or on its own) when `.scratch/` issues use the legacy bare `Status:` line instead of YAML frontmatter, or `issues/archive/` is missing. Idempotent, dry-run-first upgrade to the [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) contract — full scan → preview → execute procedure in [MIGRATION.md](MIGRATION.md).

In all cases, present what was found and the proposed migration plan for the user to confirm before any file is changed. Do not silently rewrite existing user content.

### 3. Present findings and ask

Walk the user through the three decisions **one at a time** — present a section, get the user's answer, then move to the next. Don't dump all three at once.

Assume the user does not know what these terms mean. Each section starts with a short explainer (what it is, why these skills need it, what changes if they pick differently). Then show the choices and the default.

**Section A — Issue tracker（issue 追踪位置）.**

> Explainer: The "issue tracker" is where issues and PRDs live for this repo. `/spec` and `/tdd` read from and write to it.

Default and recommended: **local markdown**. Pick this unless the user specifically requests otherwise:

- **Local markdown（default）** — issues live as files under `.scratch/<feature>/`; pure local, zero external dependencies.
- **Other** (GitHub / GitLab / Jira / Linear, etc.) — only when the user explicitly asks. Have the user describe the workflow in one paragraph; the skill records it verbatim into `docs/agents/issue-tracker.md`. Note: this introduces external CLI/account dependencies, conflicting with the local-first goal; the user is responsible for the corresponding environment setup.

**Section B — State vocabulary（状态词汇）.**

> Explainer: Each issue file under `.scratch/<feat>/issues/` carries a `status:` field in its YAML frontmatter. A **2-state model**: the issue queue is the agent's dispatch queue.

The two canonical states:

- `ready` — fully specified, fire-and-forget OK (dispatch to a subagent)
- `done` — completed; **immutable** (git has the commit; revisions are new issues)

Hands-on checks no agent can run live in the PRD's 端到端验证 — never as a state or issue AC (schema: `ARTIFACT-FORMAT.md`; check list: `/spec` card test).

**Section C — Domain docs（领域文档布局）.**

> Explainer: Some skills (`improve-arch`, `diagnose`, `tdd`) read `CONTEXT.md` for the project's domain language and `docs/adr/` for past architectural decisions. They need to know whether the repo is single-context or multi-context (e.g. a monorepo with separate frontend/backend contexts) so they look in the right place.

Confirm the layout:

- **Single-context** — one `CONTEXT.md` + `docs/adr/` at the repo root. Most repos are this.
- **Multi-context** — `CONTEXT-MAP.md` at the root pointing to per-context `CONTEXT.md` files (typically a monorepo).

### 4. Confirm and edit

Show the user a draft of:

- The `## Agent skills` block to add to whichever of `CLAUDE.md` / `AGENTS.md` is being edited (see step 4 for selection rules)
- The contents of `docs/agents/issue-tracker.md` and `docs/agents/domain.md`

Let them edit before writing.

### 5. Write

**Pick the file to edit:**

- If `CLAUDE.md` exists, edit it.
- Else if `AGENTS.md` exists, edit it.
- If neither exists, ask the user which one to create — don't pick for them.

If an `## Agent skills` block already exists in the chosen file, update its contents in-place rather than appending a duplicate. Don't overwrite user edits to the surrounding sections.

The session-start orientation convention (load `CODEBASE.md`/`CONTEXT.md`, scan ADR titles, check drift) is **not** written here — it lives once in the global `CLAUDE.md` template (§6 "Local document layout"), which every session loads. Don't inject a per-repo copy; this block only records the three per-repo choices below.

The block:

```markdown
## Agent skills

### Issue tracker

[one-line tracker summary; local markdown: the convention is this block itself]. Non-default
trackers: See `docs/agents/issue-tracker.md`.

### Domain docs

[one-line summary of layout — "single-context" or "multi-context"]. See `docs/agents/domain.md`.
```

Then seed `docs/agents/domain.md` from [domain.md](./domain.md) — consumer rules + layout.
The local-markdown tracker convention lives in the `## Agent skills` block itself; no tracker
file is written. A non-default tracker instead writes `docs/agents/issue-tracker.md`
from the user's description.

### 6. Done

Verify first: `## Agent skills` appears exactly once in the chosen file; `docs/agents/domain.md`
(and, for a non-default tracker, `issue-tracker.md`) exists non-empty. Then tell the user the setup is complete and which engineering skills will now read from these files. Mention they can edit `docs/agents/*.md` directly later — re-running this skill is only necessary if they want to switch issue trackers or restart from scratch.
