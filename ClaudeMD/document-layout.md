# Document Layout Reference

## Artifact format

The full frontmatter schema, naming/location conventions, and generated-file formats live **once** in `engineering/ARTIFACT-FORMAT.md` (distributed to `~/.claude/skills/`). Read that before producing an artifact.

## Session start protocol

Before working, load the project's orientation layer if present:
0. **Cheap-path escape**: a trivial or read-only task (quick question, single-file glance) pulls only what the task names.
1. `CODEBASE.md` and `CONTEXT.md` in full (the map is kept tiny — only what the code can't be grepped for; in big repos the root `CODEBASE.md` is just a roster, so read the roster and pull a per-area `src/<area>/CODEBASE.md` only when you work there).
2. `docs/adr/` **titles only** (pull an ADR body only when you touch the area it governs).
3. Check `CODEBASE.md` sections for drift with one `git log --name-only <oldest git_base>..HEAD` pass, mapping changed paths to sections in-context. Drifted = commits touched the section's area since its `git_base`; HEAD moving alone is not drift. Offer to refresh drifted sections via `/zoom-out` (those sections only).
4. Skip silently anything absent — this self-disables in repos that don't use these conventions.
5. If **none** of the three exists yet (a fresh checkout of a repo that's never been oriented), don't keep silent: say so once and offer to build the layer (`/grill` for the glossary, `/zoom-out` for the map) — then proceed either way.

This load happens every session unconditionally; `/resume` reuses it and layers a handoff on top, it doesn't own it. Per-repo layout (single/multi-context) lives in `docs/agents/domain.md`.

## Immutability rules

- An issue with `status: done` (in YAML frontmatter) is immutable: never edit its body or change its `status`. The git commit is the source of truth. To revise, create a new redo issue (`NN-redo-<slug>.md`).
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- Re-running `/to-prd` defaults to writing a new `PRD-vN.md` with a `Supersedes:` header; the older PRD stays untouched. Append-in-place is reserved for purely additive changes the user explicitly asks for.