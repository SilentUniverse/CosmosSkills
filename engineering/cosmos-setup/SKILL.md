---
name: cosmos-setup
description: Configure non-default trackers or paths and migrate legacy workflow metadata. Use when a repo needs a tracker/path deviation, legacy state or domain.md migration, or an ARTIFACT-FORMAT schema upgrade. Default local markdown repos need no setup.
disable-model-invocation: true
---

# Setup (cosmos-setup)

Configure what the engineering skills **cannot assume**: deviations from the default
conventions. Defaults need no setup — the issue tracker is local markdown under
`.scratch/<feat>/issues/` and the two-state vocabulary `ready|done`, both hard-coded in
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md); verifier commands live lazily in
`CODEBASE.md`'s `## Verifier commands` zone.

Inspect the repo and existing authorization, then apply the requested setup or mechanical migration.
Preview affected paths; ask only about unresolved tracker choices, semantic mappings, or data loss.

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
up — skills proceed on convention"), write nothing, and resume the calling task.

**Case 2 — Legacy domain.md cache.** `docs/agents/domain.md` exists. Offer the fold: move its
real command lines into `CODEBASE.md`'s `## Verifier commands` zone (lazy-birth per the
ARTIFACT-FORMAT stub), then remove `domain.md` only when nothing non-template remains —
otherwise rename it `domain.md.bak`. Detail: [MIGRATION.md](MIGRATION.md).

**Case 3 — Legacy states or tracker change.** Issue files use deprecated states (`needs-triage`,
`needs-info`, `wontfix`, `inbox`, `blocked`, `doing`, `shelved`), or the user requests a tracker
switch. An existing `gh` / `glab` tracker alone is not a migration trigger. Preserve it unless
the user chose a replacement. Procedure: [MIGRATION.md](MIGRATION.md).

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

### 3. The decisions (deviation cases only)

Case 3 uses only the unresolved decisions in [DECISIONS.md](DECISIONS.md)
(issue tracker; state vocabulary). Case 4's path choice is decided inline in step 2. The doc
layout is standardized — `CODEBASE.md` (+ optional per-area blocks), optional `CONTEXT.md`,
optional `docs/adr/` — and is not a per-repo decision.

### 4. Edit

Write the resolved `## Agent skills` block. Group consequential open choices into one question;
continue independent migration work while waiting. A requested preview-only run writes nothing.

**Pick the file to edit:** update the existing block's host; otherwise `CLAUDE.md` if present,
else `AGENTS.md` (create lazily if needed). Never append a duplicate block.

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

**Behavior authority.** Record repo configuration, not duplicate process policy. Existing user
authorization persists across phases; required deterministic evidence still must be obtained.

### 5. Done

Verify: exactly one block (Case 1: no writes), and any Case 2 fold left no `domain.md` or a backup.
Name consumers and unresolved deviations; resume the authorized task that setup unblocked.
