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

**When:** `CODEBASE.md` is absent or empty — or a legacy monolith (per-area sections, no roster) —
and the user wants a map of the *whole* project, not one area — onboarding an inherited codebase
(`/zoom-out` with no path, or `/zoom-out --all`).

**Steps:**

1. **Partition first.** Identify the top-level areas (by directory or domain concept). Confirm the
   partition with the user *before* deep exploration.
2. **Explore in parallel, isolated.** Dispatch one `Agent` (subagent_type=general-purpose,
   read-only) per partition so each area's exploration burns a *subagent's* context, not the main
   session's — local files only (Read/Glob/Grep), no web mirrors. Each returns:
   - a **roster line** — a real existing directory path + responsibility in ≤10 words
     (never `<placeholder>`, `{brace-set}`, or glob syntax);
   - **candidate facts** — each pre-filtered by the two-axis test below.
3. **Assemble the final shape directly** — never a monolith first:
   - **>8 areas:** root `CODEBASE.md` = synthesis + routing table + roster only. Every area with
     surviving facts → generated block in `src/<area>/CLAUDE.md`. Areas without facts → roster
     line only, no file.
   - **≤8 areas:** single root file, one `## ` section per area.
4. **One review gate.** Present root + all area blocks at once for the user to edit — merge, drop,
   set the level of detail. Never write the files before this gate.
5. **Only** loop back on areas where the code structure genuinely confused you — list those few,
   don't re-walk the whole map.

## The two-axis test (what earns a persisted line)

A fact is recorded only if **both** hold:

1. **Can't rg it** — a fresh agent couldn't rebuild it with a couple of `rg`/`glob` queries.
   Locations, exports, caller lists, import graphs fail this axis.
2. **Bites if missing** — a normal task in this area goes wrong or takes a wrong turn without it.
   Curiosities and harmless trivia fail this axis.

Decisions → ADR. Vocabulary → CONTEXT.md.

## Optionally persist to CODEBASE.md

After printing the map, if it's worth keeping, offer to persist: _"Want me to save this to
CODEBASE.md so the next session skips re-exploring?"_ Write only on a yes (or `/zoom-out --save`).

**Schema, templates, and budgets are owned by [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#codebasemd--structural-map-generated-not-authored)** — read it before writing.

## Maintaining existing blocks

Re-running on a mapped area, or refreshing after drift:

- **Drift check:** diff each block's `git_base` against HEAD.
  - **Code gone** (file/symbol deleted) → delete the block and its roster line.
  - **Code drifted** → refresh + re-stamp `git_base`.
  - **Duplicate** → merge.
- **Same-change refresh:** a change that alters an area's seam or invariant refreshes that area's
  block in the same change (duty rule in ARTIFACT-FORMAT.md).
