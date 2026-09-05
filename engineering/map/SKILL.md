---
name: map
description: Generate or refresh the structural map in CODEBASE.md — synthesis, routing table, roster, per-area invariant blocks filtered by the two-axis test. Use when raw rg/tsc navigation turns noisy (large or legacy codebases, repeated cross-module impact work, many same-name seams), when CODEBASE.md is stale/legacy, or after a change that moved a seam or invariant. Small greenfield repos skip the map — invariants are born event-driven from /spec and /tdd instead. Never touches the hand-maintained ## Verifier commands section.
argument-hint: "Area path to refresh (optional; no args or --all = whole repo)"
disable-model-invocation: true
---

# Map

Draw or refresh this repo's structural map into `CODEBASE.md`. Read `CONTEXT.md` when present so the
names line up. One-time understanding without an artifact → `/show <path>`.

Scope: `/map <path>` refreshes that area; no args or `--all` maps the whole repo. The request
authorizes writing the map unless preview-only. Missing maps are not prerequisites for other work.

## First pass (draft mode) — mapping a whole repo

**When:** `CODEBASE.md` is absent or empty, or holds only the hand-maintained `## Verifier
commands` zone, or is a legacy monolith (per-area sections, no roster), and the user wants a map
of the *whole* project, not one area (`/map` with no path, or `/map --all`). A hand zone already
present is preserved verbatim; the generated skeleton is assembled around it.

**Steps:**

1. **Partition first.** Infer areas from existing paths, ownership, and domain concepts. Ask only
   when unresolved ownership would materially change the map; explore clear areas meanwhile.
2. **Explore the relevant areas.** Work inline; delegate separable areas to bounded read-only
   subagents when useful and available. Local files only; no web mirrors. Collect per area:
   - a **roster line** — a real existing directory path + responsibility in ≤10 words,
     never `<placeholder>`, `{brace-set}`, or glob syntax;
   - **candidate facts** — each pre-filtered by the two-axis test below.
3. **Assemble the final shape directly**, never a monolith first:
   - **>8 areas:** root `CODEBASE.md` = synthesis + routing table + roster only. Every area with
     surviving facts → generated block in `src/<area>/CLAUDE.md`. Areas without facts → roster
     line only, no file.
   - **≤8 areas:** single root file, one `## ` section per area.
4. **Verify and write.** Check paths, apply the two-axis test, and preserve hand-maintained content.
   Write evidence-backed blocks directly; report unresolved facts instead of inventing invariants.
5. Clarify only consequential unknowns that inspection cannot settle. Resume the caller's task
   after the scoped refresh; do not restart whole-map review for a local correction.

## The two-axis test (what earns a persisted line)

A fact is recorded only if **both** hold:

1. **Can't rg it** — a fresh agent couldn't rebuild it with a couple of `rg`/`glob` queries.
   Locations, exports, caller lists, import graphs fail this axis.
2. **Bites if missing** — a normal task in this area goes wrong or takes a wrong turn without it.
   Curiosities and harmless trivia fail this axis.

Decisions → ADR. Vocabulary → CONTEXT.md.

## Writing CODEBASE.md

**Schema, templates, and budgets are owned by [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#codebasemd--structural-map-generated-not-authored)**. Read the relevant section before writing. Use its deterministic checks; a preview-only request returns the proposed blocks without writes.

## Maintaining existing blocks

Re-running on a mapped area, or refreshing after drift:

- **Drift check:** diff each block's `git_base` against HEAD.
  - **Code gone** (file/symbol deleted) → delete the block and its roster line.
  - **Code drifted** → refresh + re-stamp `git_base`.
  - **Duplicate** → merge.
- **Same-change refresh:** a change that alters an area's seam or invariant refreshes that area's
  block in the same change (duty rule in ARTIFACT-FORMAT.md).
