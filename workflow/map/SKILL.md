---
name: map
description: >-
  Use when repository navigation is noisy, CODEBASE.md is missing or stale, or a change moved a seam or invariant. Generates or refreshes the structural map, routing table, roster, and evidence-filtered invariant blocks while preserving verifier commands.
argument-hint: "Area path to refresh (optional; no args or -all = whole repo)"
disable-model-invocation: true
---

# Map

Draw or refresh this repo's structural map into `CODEBASE.md`. Read `CONTEXT.md` when present so the
names line up. One-time understanding without an artifact → `/show <path>`.

Scope: `/map <path>` refreshes that area; no args or `-all` maps the whole repo. The request
authorizes writing the map unless preview-only. Missing maps are not prerequisites for other work.

## First pass (draft mode) — mapping a whole repo

**When:** `CODEBASE.md` is absent or empty, or holds only the hand-maintained `## Verifier
commands` zone, or is a legacy monolith (per-area sections, no roster), and the user wants a map
of the *whole* project, not one area (`/map` with no path, or `/map -all`). A hand zone already
present is preserved except dead commands, which the run repairs or reports (Hand zone below);
the generated skeleton is assembled around it.

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

Facts promoted from an accepted spec enter through this same test and carry their recorded scope,
source and reason; when the code, schema or decision a promoted fact cites changes, revalidate or
supersede it rather than trusting past acceptance.

## Writing CODEBASE.md

**Schema, templates, and budgets are owned by [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#codebasemd--structural-map-generated-not-authored)**. Read the relevant section before writing. Use its deterministic checks; a preview-only request returns the proposed blocks without writes.

## Maintaining existing blocks

Re-running on a mapped area, or refreshing after drift:

- **Drift check:** diff each block's `git_base` against HEAD. `git_base` at HEAD → reuse the block
  untouched. A whole-map rerun stops here for every current block; it re-derives nothing that
  still verifies.
  - Code gone (file/symbol deleted) → delete the block and its roster line.
  - Code drifted → refresh + re-stamp `git_base`.
  - Duplicate → merge.
- **Incremental refresh:** a refresh re-applies the two-axis filter and re-verifies the block's
  surviving lines in place — each named fact is one cheap rg or check, verification not
  re-derivation — then rewrites only lines that fail, deletes lines whose code is gone, drops
  lines that still verify but became rg-able or stopped biting, and appends newly earned facts.
  Unchanged lines stay byte-identical; re-deriving a whole block when some lines drifted is a
  defect.
- **Same-change refresh:** a change that alters an area's seam or invariant refreshes that area's
  block in the same change (duty rule in ARTIFACT-FORMAT.md).
- **Consumption:** a block whose `git_base` is behind HEAD is a lead, not fact. Re-verify its named
  facts before relying on it, then fix, drop, or re-stamp the affected lines in place; escalate to
  a scoped refresh only when the area's structure itself moved.

## Hand zone (Verifier commands)

The `## Verifier commands` zone is hand-maintained and `verify-artifacts.py` never inspects it;
this skill is its only freshness check. Every map run — first pass or refresh — re-validates each
command: run it in its cheapest form when one exists, otherwise check that the paths, binaries and
suite enumerations it names still resolve in the repo. A dead command is never carried forward
silently: replace it with a verified equivalent in the same run when one was found (and report the
change), otherwise report the dead entry with its failure evidence for the owner. A command that
cannot be validated cheaply is reported as unverified, not assumed healthy.
