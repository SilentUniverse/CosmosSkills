---
name: cosmos-setup
description: >-
  Use only when the user invokes /cosmos-setup for non-default tracker/path setup, legacy artifact folding, MCP/driver inventory, or multi-model slot routing (-models). Default repos need no setup.
argument-hint: "[-models]"
disable-model-invocation: true
---

# Setup (cosmos-setup)

Configure what the engineering skills **cannot assume**: deviations from the default
conventions. Defaults need no setup — the tracker is local markdown at
`.scratch/<feat>/FEATURE.md` and the unit status vocabulary `pending|ready|done`, both defined in
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md); project commands live in the native entry and
`AGENTS.md` `## Commands` (project commands in `../ARTIFACT-FORMAT.md`).

Inspect the repo and existing authorization, then apply the requested setup or mechanical migration.
Preview affected paths; ask only about unresolved tracker choices, semantic mappings, or data loss.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `AGENTS.md` and `CLAUDE.md` at the repo root — does either exist? Is there already an
  `## Agent skills` section in either?
- `docs/agents/` — a legacy `issue-tracker.md` (non-default tracker) or a legacy `domain.md`
  (legacy command cache)
- `.scratch/` — one `FEATURE.md` per feature, or legacy planning files (`PRD*.md`, `issues/`,
  `verifier.json`, `spec-review.json`, `spec-acceptances/`, `experience-contract*.json`, `SUMMARY.md`)?
- Other PRD-like locations (`docs/prd/`, `docs/specs/`, `requirements/`, `prds/`, `specs/`)
  and issue-like locations (`issues/`, `tasks/`, `tickets/`)

### 2. Classify and announce

**Case 1 — Clean repo on defaults.** No `.scratch/`, no `docs/agents/`, no legacy states, no
non-default paths. Nothing to configure: say so in one line ("defaults apply; nothing to set
up — skills proceed on convention"), write nothing, and resume the calling task.

**Case 2 — Legacy domain.md cache.** `docs/agents/domain.md` exists. Offer the fold: move its
real command lines into the native entry or `AGENTS.md` `## Commands`, then remove `domain.md` only when nothing non-template remains —
otherwise rename it `domain.md.bak`. Detail: [MIGRATION.md](MIGRATION.md).

**Case 3 — Tracker change.** The user requests a tracker switch. An existing `gh` / `glab` tracker alone
is not a migration trigger. Preserve it unless the user chose a replacement. Procedure:
[MIGRATION.md](MIGRATION.md).

**Case 4 — PRD/issue-like files at non-default paths.** Surface the paths and their consumers.
The bundled Python workflow tools use `.scratch/`; a path declaration alone does not retarget them.

- (i) **Configure paths in place.** Use this only when a repository adapter supports the selected
  tracker and paths. Verify its execution, state projection, and artifact gate before recording
  the actual paths and adapter entrypoints in `## Agent skills`. No file moves.
- (ii) **Adopt new layout.** Help the user move/symlink existing files into
  `.scratch/<feat>/`. Show the planned moves before executing; use `git mv` where possible.

**Case 5 — Legacy planning files.** Fold them by hand into one `FEATURE.md` per feature, then
delete them; dry-run first ([MIGRATION.md](MIGRATION.md)).

**Case 6 — Verification capability inventory.** The user asks which MCP servers or drivers are
available for UI, device or desktop verification. Detect only: never install, upgrade, enable or
configure anything, never grant or prompt for an OS permission, and write nothing.

- MCP servers: read the MCP configuration files the host uses (`.mcp.json` and the host's project and
  user configuration). Report server names and transport only, never environment values, headers or
  tokens. A configured server is not proof that it connects. A host listing that health-checks
  servers (for example `claude mcp list`) starts them, so run it only when the user accepts that.
- Drivers: check presence and version of the drivers [verify's recipes](../verify/DRIVERS.md)
  name, for example `xcrun simctl help`, `xcodebuild -version`, `idb --help`, `appium --version`,
  `ffmpeg -version`, and the project's own `playwright` or `electron` dependency. Use only probes that
  start no browser, device or application. A permission that cannot be read without a prompt is
  `unknown`.
- Report one table: capability, mechanism, status (`available`, `missing` or `unknown`) and the
  probe command with its output line. Installing a missing driver is the user's decision, outside
  this skill. `/verify` adapters still print their own capability report at run time.

**Case 7 — User-level multi-model routing (`/cosmos-setup -models`).** Configure the four abstract
capability slots (`deep`, `fast`, `panel`, `cross_judge`) in `~/.cosmos/models.json` per
`model-routing.md` (`~/.claude/references/model-routing.md` when installed, `claude/model-routing.md`
in a source checkout; zero resident prompt cost; never writes into project
`CLAUDE.md`/`AGENTS.md` or `~/.codex/AGENTS.md`):

1. **Detect.** Inspect the active host's subagent/swarm tool schema or model-list action to find
   confirmed available models and its tier (`L3` multi-vendor, `L2` single-vendor tiered, `L1`
   inherit-parent, `L0` no subagents). Never write an unconfirmed model slug. On L2 hosts, also note
   whether the user wants an optional read-only external CLI/MCP bridge for `cross_judge` (disabled
   by default; always requires consent before sending repository code externally).
2. **Choose budget and slots.** Ask the user for reasoning budget (`large` / `medium` / `small`)
   and confirm the per-slot mappings (`deep`, `fast`, `panel`, `cross_judge`, allowing
   `inherit-parent` / `auto`). Load existing `~/.cosmos/models.json` first so reruns preserve
   explicit overrides.
3. **Validate and write.** Confirm every concrete slug is in the detected set (or an explicitly
   configured external bridge), then overwrite `~/.cosmos/models.json` idempotently. Report the
   written path, host tier (`L3`–`L0`), active slots, and any cross-vendor limits. Do not touch
   repository files.


### 3. The decisions (deviation cases only)

Case 3 uses only the unresolved decisions in [DECISIONS.md](DECISIONS.md)
(tracker; state vocabulary). Case 4's path choice is decided inline in step 2. The doc
layout is standardized — optional `CONTEXT.md`, optional `docs/adr/`, optional `AGENTS.md`
`## Commands` — and is not a per-repo decision.

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
<!-- omit this subsection entirely while the default (.scratch/<feat>/FEATURE.md) holds -->
Non-default only: one-line summary. See `docs/agents/issue-tracker.md`.

### Orientation
Native entry + AGENTS.md `## Commands`. Optional: CONTEXT.md, docs/adr/.
```

**Behavior authority.** Record repo configuration, not duplicate process policy.

### 5. Done

Verify: exactly one block (Case 1, Case 6 and Case 7 touch no repository files; Case 7 validates
`~/.cosmos/models.json` JSON), and any Case 2 fold left no `domain.md` or a backup.
Name consumers and unresolved deviations; resume the authorized task that setup unblocked.
