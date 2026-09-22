# Document Layout Reference

## Artifact format

Frontmatter schemas, locations, and generated-file formats live once in `workflow/ARTIFACT-FORMAT.md`
(distributed beside the installed skills). Read the section for the artifact being produced;
reuse it across the task until the contract changes.

Don't restate what the environment answers (package.json scripts, config values, directory trees, `--help` output) — a copy is a cache that goes stale; query it or link it.

## Session start protocol

Start with named inputs. For unfamiliar nontrivial work, use `CODEBASE.md` routing and relevant
`CONTEXT.md` terms; read ADR titles and open only decisions governing the affected area. Issue or
explicit task pointers are the initial read set, not a ban on investigating a discovered dependency.
Skip missing orientation files. Create/refresh a map only when navigation or a changed invariant
needs it; no bootstrap offer or full-map drift scan on every session. A generated block whose
`git_base` is behind HEAD is a lead, not fact: re-verify its named facts before relying on it and
fix, drop, or re-stamp the affected lines in place; do not re-derive the map for it.

A host may inject per-area `CLAUDE.md` blocks automatically; where it does not, read the relevant
referenced blocks explicitly when needed. Do not assume one host's automatic loading applies to
every host.
Same-task compaction/reopening uses native context and session recovery. For a named prior task,
use an actually available native history reader. Native continuation may omit engineering facts.
Use the Cosmos `handoff` skill for an explicit handoff or necessary facts the destination cannot
retrieve; use `resume` to resolve the source, verify relevant drift and continue the objective.
Their contracts live in `workflow/handoff/SKILL.md` and `workflow/resume/SKILL.md` in the source
checkout, or the corresponding directories beside installed skills. These are engineering skills,
not built-in ZCode skills; select them through the current surface's skill entry.
Notes use explicit pointers, not a generation, publish/consume status or lifecycle ledger.

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

- A completed Issue preserves its contract and evidence. Later requirement changes use linked
  follow-up contracts. Damaged or contradicted proof is not repaired by editing status; investigate
  the affected obligation and retain all attempts. Test ownership follows ARTIFACT-FORMAT.
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- Re-running `/spec` writes `PRD-vN.md` only when a recorded AC or decision goes false. Additive re-runs edit `ready` issues or add `detail`; they do not supersede. The older PRD stays untouched.
