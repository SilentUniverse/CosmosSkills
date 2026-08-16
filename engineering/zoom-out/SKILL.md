---
name: zoom-out
description: Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you're unfamiliar with a section of code or need to understand how it fits into the bigger picture. Can optionally persist the structural map to CODEBASE.md so future sessions don't re-explore.
argument-hint: "Path/module to map (optional; --all = whole repo, --save = persist to CODEBASE.md)"
disable-model-invocation: true
---

# Zoom Out

I don't know this area of code well. Go up a layer of abstraction. Give me a map of all the relevant
modules and callers, using the project's domain glossary vocabulary (read `CONTEXT.md` first so the
names line up).

By default this is **read-only, use-and-discard** — print the map, don't write anything.

Scope first: map the named path/module/question only. Whole-repo mapping requires `/zoom-out --all` or an explicit "whole project" request.

## First pass (draft mode) — mapping a whole unfamiliar repo

**When:** `CODEBASE.md` is absent or empty and the user wants a map of the *whole* project, not one
area — onboarding an inherited codebase (`/zoom-out` with no path, or `/zoom-out --all`).

**Steps:**

1. **Partition first.** Identify the top-level modules/areas (by directory or domain concept) — the
   sections the map will have. Confirm the partition with the user *before* deep exploration; that's
   the cheapest moment to fix wrong boundaries.
2. **Explore in parallel, isolated.** Dispatch one `Agent` (subagent_type=Explore) per partition so
   each area's exploration burns a *subagent's* context, not the main session's. Each returns a
   section bounded by the CODEBASE.md budget in `ARTIFACT-FORMAT.md` — not a brain-dump.
3. **Assemble the draft.** Write one `## ` section per area, each tagged `(draft)` and stamped with
   the current `git_base`. Run every section through the persist filter (next section).
4. **One review gate.** Present the whole draft at once for the user to edit — merge sections that
   are too granular, drop ones that are wrong, add what's missing, set the level of detail. Drop the
   `(draft)` tags once confirmed. Never write the file without this gate.
5. **Only** loop back on areas where the code structure genuinely confused you — list those few,
   don't re-walk the whole map.

After this baseline exists, later runs work per-area on demand — refresh one section, not the whole
file (see persist rules below).

## Optionally persist to CODEBASE.md

After printing the map, if it's worth keeping, offer to persist: _"Want me to save this to
CODEBASE.md so the next session skips re-exploring?"_ Write only on a yes (or `/zoom-out --save`).

**What to write is governed by the CODEBASE.md schema in [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#codebasemd--repo-root-generated-not-authored)**
— read it before writing rather than restating it here. The one judgment call that drives everything:

> **The "can't rg it" test** — persist a fact only if a fresh agent *couldn't* rebuild it with a
> couple of `rg`/`glob` queries. Locations, exports, caller lists, import graphs fail the test (grep
> finds them; a stored copy just goes stale) — drop them. What passes is the operational
> understanding the code can't hand you: invariants, seam judgment, cross-module synthesis, mid-weight
> why. Decisions → ADR, vocabulary → CONTEXT.md.

## Maintaining existing sections

Re-running on an area already mapped? Diff each section's `git_base` against HEAD:

- **Code gone** (file/symbol deleted) → **delete the section**.
- **Code drifted** → refresh + re-stamp `git_base`.
- **Duplicate** (same invariant found twice) → merge.
