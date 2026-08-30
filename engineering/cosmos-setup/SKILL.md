---
name: cosmos-setup
description: Handles per-repo configuration that deviates from the defaults — a non-default issue tracker, non-default PRD/issue paths, legacy states to migrate, or a legacy docs/agents/domain.md to fold into CODEBASE.md. Default-convention repos (local markdown .scratch/, ready|done) need neither this skill nor a docs/agents/ tree; consumer skills proceed on convention and CODEBASE.md's ## Verifier commands zone is born lazily on first backfill. Also the entry for ARTIFACT-FORMAT schema upgrades.
disable-model-invocation: true
---

# Setup (cosmos-setup)

Configure what the engineering skills **cannot assume**: deviations from the default
conventions. Defaults need no setup — the issue tracker is local markdown under
`.scratch/<feat>/issues/` and the two-state vocabulary `ready|done`, both hard-coded in
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md); verifier commands live lazily in
`CODEBASE.md`'s `## Verifier commands` zone.

This is a prompt-driven skill, not a deterministic script. Explore, present what you found,
confirm with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `AGENTS.md` and `CLAUDE.md` at the repo root — does either exist? Is there already an
  `## Agent skills` section in either?
- `docs/agents/` — a legacy `issue-tracker.md` (non-default tracker) or a legacy `domain.md`
  (legacy command cache)
- `.scratch/` — sample one issue file: YAML frontmatter with `type: issue`, or only a bare
  `Status:` line? Any `issues/archive/` directories? Deprecated states?
- Other PRD-like locations (`docs/prd/`, `docs/specs/`, `requirements/`, `prds/`, `specs/`)
  and issue-like locations (`issues/`, `tasks/`, `tickets/`)

### 2. Classify and announce

**Case 1 — Clean repo on defaults.** No `.scratch/`, no `docs/agents/`, no legacy states, no
non-default paths. Nothing to configure: say so in one line ("defaults apply; nothing to set
up — skills proceed on convention"), write nothing, done.

**Case 2 — Legacy domain.md cache.** `docs/agents/domain.md` exists. Offer the fold: move its
real command lines into `CODEBASE.md`'s `## Verifier commands` zone (lazy-birth per the
ARTIFACT-FORMAT stub), then remove `domain.md` only when nothing non-template remains —
otherwise rename it `domain.md.bak`. Detail: [MIGRATION.md](MIGRATION.md).

**Case 3 — Old setup detected.** `docs/agents/issue-tracker.md` references `gh` / `glab` CLI,
or issue files use deprecated states (`needs-triage`, `needs-info`, `wontfix`, `inbox`,
`blocked`, `doing`, `shelved`). Offer to switch to local-markdown + 2-state, or keep the old
tracker. Full procedure in [MIGRATION.md](MIGRATION.md).

**Case 4 — PRD/issue-like files at non-default paths.** Surface the paths found. Offer two
options, recommending (i) by default since it is non-destructive:

- (i) **Configure paths in place.** Record the actual paths in the `## Agent skills` block so
  the skills read/write there. No file moves.
- (ii) **Adopt new layout.** Help the user move/symlink existing files into
  `.scratch/<feat>/`. Show the planned moves before executing; use `git mv` where possible.

**Case 5 — Frontmatter migration (bare `Status:` lines).** Idempotent, dry-run-first upgrade
to the ARTIFACT-FORMAT contract: full scan → preview → execute ([MIGRATION.md](MIGRATION.md)).

**Case 6 — Schema upgrade.** A field is becoming required per an ARTIFACT-FORMAT revision;
run the upgrade it names.

In all cases, present what was found and the proposed plan for the user to confirm before any
file is changed. Do not silently rewrite existing user content.

### 3. The decisions (deviation cases only)

Case 3 reaches the two decision explainers, one at a time: [DECISIONS.md](DECISIONS.md)
(issue tracker; state vocabulary). Case 4's path choice is decided inline in step 2. The doc
layout is standardized — `CODEBASE.md` (+ optional per-area blocks), optional `CONTEXT.md`,
optional `docs/adr/` — and is not a per-repo decision.

### 4. Confirm and edit

Show a draft of the `## Agent skills` block; let the user edit before writing.

**Pick the file to edit:** `CLAUDE.md` if it exists, else `AGENTS.md`; if neither exists, ask
which to create — don't pick for them. If a block already exists, update it in-place rather
than appending a duplicate.

**Additive-only rule.** The block is the only content this skill touches. Never edit, reorder,
or remove surrounding user content in the host file — existing AGENTS.md/CLAUDE.md prose stays
byte-identical. Keep the block ≤10 lines:

```markdown
## Agent skills
<!-- what this repo is: 1 line; repo-specific constraints the skills can't know: 1 line each -->

### Issue tracker
<!-- omit this subsection entirely while the default (local markdown under .scratch/) holds -->
Non-default only: one-line summary. See `docs/agents/issue-tracker.md`.

### Orientation
CODEBASE.md (## Verifier commands + map). Optional: CONTEXT.md (monorepo: CONTEXT-MAP.md), docs/adr/.
```

**Behavior authority.** Content this workflow adds anywhere must not restate or override
process behavior the skills already define (autonomy, pauses, gates, summaries); such text in
a per-repo file is a bug, and skill-defined gates are never waived by standing instructions.

### 5. Done

Verify: the block appears exactly once (Case 1: nothing was written); any Case 2 fold left
either no `domain.md` or a `domain.md.bak`. Name which skills consume what. Re-run only to
switch trackers or handle another deviation.
