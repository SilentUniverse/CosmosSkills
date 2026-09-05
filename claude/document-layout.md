# Document Layout Reference

## Artifact format

The full frontmatter schema, naming/location conventions, and generated-file formats live **once** in `engineering/ARTIFACT-FORMAT.md` (distributed to `~/.claude/skills/`). Read that before producing an artifact.

Don't restate what the environment answers (package.json scripts, config values, directory trees, `--help` output) — a copy is a cache that goes stale; query it or link it.

## Session start protocol

Start with named inputs. For unfamiliar nontrivial work, use `CODEBASE.md` routing and relevant
`CONTEXT.md` terms; read ADR titles and open only decisions governing the affected area. Issue or
handoff pointers are the initial read set, not a ban on investigating a discovered dependency.
Skip missing orientation files. Create/refresh a map only when navigation or a changed invariant
needs it; no bootstrap offer or full-map drift scan on every session.

Claude Code may inject per-area `CLAUDE.md` blocks. Other hosts read the relevant referenced blocks
explicitly when needed. Do not assume one host's automatic loading applies to every host.
At a real resume, follow `/resume`'s minimal boot chain before unrelated orientation work.

Issue state is queried on demand: live roster via `rg '^status:' -g '**/issues/*.md' .scratch`;
effective delivered behavior via `workflow-state.py inspect`. Neither creates `SUMMARY.md`.

`AGENTS.md`/`CLAUDE.md` is the always-loaded doorplate: what this repo is, the pointer block, deviation declarations, repo-specific constraints. Content the workflow adds there is additive-only and never restates process behavior the skills define.

## Immutability rules

- A shipped `done` issue preserves its contract and history. Later requirement changes create a
  redo issue. During its active batch only, failed integration/review may reopen it to `ready` with
  evidence; appending test ownership is also permitted by ARTIFACT-FORMAT. Preserve prior records.
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- Re-running `/spec` writes `PRD-vN.md` only when a recorded AC or decision goes false. Additive re-runs edit `ready` issues or add `detail`; they do not supersede. The older PRD stays untouched.
