# Document Layout Reference

## Artifact format

Frontmatter schemas, locations, and generated-file formats live once in `workflow/ARTIFACT-FORMAT.md`
(distributed beside the installed skills). Read the section for the artifact being produced;
reuse it across the task until the contract changes.

Don't restate what the environment answers (package.json scripts, config values, directory trees, `--help` output) — a copy is a cache that goes stale; query it or link it.

## Session start protocol

Start with named inputs. For unfamiliar nontrivial work, use `CODEBASE.md` routing and relevant
`CONTEXT.md` terms; read ADR titles and open only decisions governing the affected area. Issue or
handoff pointers are the initial read set, not a ban on investigating a discovered dependency.
Skip missing orientation files. Create/refresh a map only when navigation or a changed invariant
needs it; no bootstrap offer or full-map drift scan on every session.

A host may inject per-area `CLAUDE.md` blocks automatically; where it does not, read the relevant
referenced blocks explicitly when needed. Do not assume one host's automatic loading applies to
every host.
At a real resume, follow `/resume`'s minimal boot chain before unrelated orientation work.

Issue state is queried on demand: live roster via `rg '^status:' -g '**/issues/*.md' .scratch`;
effective delivered behavior via `workflow-state.py inspect`. Neither creates `SUMMARY.md`.

## Promoted knowledge

Facts confirmed by an accepted plan live at their narrowest useful scope: task-local in the
PRD/issue (not auto-loaded later), feature-local in the feature PRD's implementation decisions,
area/project invariants in ADR/CODEBASE/CONTEXT only when they pass `/map`'s two-axis test and
record scope, source and reason. When the code, schema or decision a promoted fact cites changes,
revalidate or supersede it; past acceptance does not keep a stale fact true.

`AGENTS.md`/`CLAUDE.md` is the always-loaded doorplate: what this repo is, the pointer block, deviation declarations, repo-specific constraints. Content the workflow adds there is additive-only and never restates process behavior the skills define.

## Immutability rules

- A shipped `done` issue preserves its contract and history. Later requirement changes create a
  redo issue. During its active batch only, failed integration/review may reopen it to `ready` with
  evidence; appending test ownership is also permitted by ARTIFACT-FORMAT. Preserve prior records.
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- Re-running `/spec` writes `PRD-vN.md` only when a recorded AC or decision goes false. Additive re-runs edit `ready` issues or add `detail`; they do not supersede. The older PRD stays untouched.
