---
name: map
description: Generate or refresh the structural map in CODEBASE.md — synthesis, routing table, roster, per-area invariant blocks filtered by the two-axis test. Use when onboarding a repo, when CODEBASE.md is missing/stale/legacy, or after a change that moved a seam or invariant.
argument-hint: "Area path to refresh (optional; no args or --all = whole repo)"
disable-model-invocation: true
---

# Map

Draw or refresh this repo's structural map into `CODEBASE.md`. Read `CONTEXT.md` first so the
names line up. One-time understanding without an artifact → `/show <path>`.

Scope: `/map <path>` drafts that area's block and shows it before writing; no args or `--all`
maps the whole repo.

## First pass (draft mode) — mapping a whole repo

**When:** `CODEBASE.md` is absent or empty, or a legacy monolith (per-area sections, no roster),
and the user wants a map of the *whole* project, not one area (`/map` with no path, or `/map --all`).

**Steps:**

1. **Partition first.** Identify the top-level areas (by directory or domain concept). Confirm the
   partition with the user *before* deep exploration.
2. **Explore in parallel, isolated.** Dispatch one read-only `Explore` subagent
   per partition so each area's exploration burns a *subagent's* context, not the main
   session's. Local files only (Read/Glob/Grep); no web mirrors. Each returns:
   - a **roster line** — a real existing directory path + responsibility in ≤10 words,
     never `<placeholder>`, `{brace-set}`, or glob syntax;
   - **candidate facts** — each pre-filtered by the two-axis test below.
3. **Assemble the final shape directly**, never a monolith first:
   - **>8 areas:** root `CODEBASE.md` = synthesis + routing table + roster only. Every area with
     surviving facts → generated block in `src/<area>/CLAUDE.md`. Areas without facts → roster
     line only, no file.
   - **≤8 areas:** single root file, one `## ` section per area.
4. **One review gate.** Present root + all area blocks at once for the user to edit: merge, drop,
   set the level of detail. Order the review by confidence: low-confidence entries (roster line /
   routing row / block line) form a focused question block presented first. Naming and boundaries
   are never auto-passed. Never write the files before this gate.
5. **Only** loop back on areas where the code structure genuinely confused you. List those few;
   don't re-walk the whole map.

## The two-axis test (what earns a persisted line)

A fact is recorded only if **both** hold:

1. **Can't rg it** — a fresh agent couldn't rebuild it with a couple of `rg`/`glob` queries.
   Locations, exports, caller lists, import graphs fail this axis.
2. **Bites if missing** — a normal task in this area goes wrong or takes a wrong turn without it.
   Curiosities and harmless trivia fail this axis.

Decisions → ADR. Vocabulary → CONTEXT.md.

## Writing CODEBASE.md

**Schema, templates, and budgets are owned by [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#codebasemd--structural-map-generated-not-authored)**. Read it before writing. Files are written only after the review gate (whole-repo) or the block showing (single area).

## Maintaining existing blocks

Re-running on a mapped area, or refreshing after drift:

- **Drift check:** diff each block's `git_base` against HEAD.
  - **Code gone** (file/symbol deleted) → delete the block and its roster line.
  - **Code drifted** → refresh + re-stamp `git_base`.
  - **Duplicate** → merge.
- **Same-change refresh:** a change that alters an area's seam or invariant refreshes that area's
  block in the same change (duty rule in ARTIFACT-FORMAT.md).
