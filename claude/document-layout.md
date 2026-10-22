# Document Layout Reference

## Artifact format

Frontmatter schemas, locations, and generated-file formats live once in `workflow/ARTIFACT-FORMAT.md`
(distributed beside the installed skills). Read the section for the artifact being produced;
reuse it across the task until the contract changes.

Don't restate what the environment answers (package.json scripts, config values, directory trees, `--help` output) — a copy is a cache that goes stale; query it or link it.

## Session start protocol

Start with named inputs. For unfamiliar nontrivial work, use `CODEBASE.md` routing and relevant
`CONTEXT.md` terms; read ADR titles and open only decisions governing the affected area. Feature-unit or
explicit task pointers are the initial read set, not a ban on investigating a discovered dependency.
Skip missing orientation files. Create/refresh a map only when navigation or a changed invariant
needs it; no bootstrap offer or full-map drift scan on every session. A generated block with
relevant committed, staged, working-tree or untracked drift from `git_base` is a lead, not fact:
re-verify its named facts before relying on it and
fix, drop, or re-stamp the affected lines in place; do not re-derive the map for it.

A host may inject per-area `CLAUDE.md` blocks automatically; where it does not, read the relevant
referenced blocks explicitly when needed. Do not assume one host's automatic loading applies to
every host.
At a unit boundary use the Cosmos `handoff` skill; a fresh session uses `resume`. A host's
same-name native command is not these skills.

Unit state is queried on demand via `workflow-state.py survey`; it creates no summary file.

## Promoted knowledge

Facts confirmed by an accepted plan live at their narrowest useful scope: task-local in the
conversation/native plan or the owning unit (not auto-loaded later), feature-local in
the feature's FEATURE.md decisions and invariants,
area/project invariants in ADR/CODEBASE/CONTEXT only when they pass `/map`'s two-axis test and
record scope, source and reason. When the code, schema or decision a promoted fact cites changes,
revalidate or supersede it; past acceptance does not keep a stale fact true.

`AGENTS.md`/`CLAUDE.md` is the always-loaded doorplate: what this repo is, the pointer block, deviation declarations, repo-specific constraints. Content the workflow adds there is additive-only and never restates process behavior the skills define.

## Immutability rules

- A done unit preserves its contract and evidence. Later requirement changes use a new
  `refines:` unit. Damaged or contradicted proof is not repaired by editing status; investigate
  the affected obligation and retain all attempts. Test ownership follows ARTIFACT-FORMAT.
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- On the giant-task queue route, re-running `/spec` edits the one FEATURE.md in place and adds a 变更记录 line for each contract change; a changed reviewed contract needs new acceptance. Inline plans keep changes in the conversation/native plan.
