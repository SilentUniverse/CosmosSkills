# Document Layout Reference

## Artifact format

The full frontmatter schema, naming/location conventions, and generated-file formats live **once** in `engineering/ARTIFACT-FORMAT.md` (distributed to `~/.claude/skills/`). Read that before producing an artifact.

## Session start protocol

Before working, load the project's orientation layer if present:
0. **Cheap-path escape**: a trivial or read-only task (quick question, single-file glance) pulls only what the task names.
1. `CODEBASE.md` and `CONTEXT.md` in full (root is the skeleton — synthesis + routing + roster; per-area detail lives in `src/<area>/CLAUDE.md` generated blocks, auto-injected by Claude Code when files in that area are read — no manual pull).
2. `docs/adr/` **titles only** (pull an ADR body only when you touch the area it governs).
3. Check `CODEBASE.md` blocks for drift with one `git log --name-only <oldest git_base>..HEAD` pass (collect `git_base` from the root and `**/CLAUDE.md` marker blocks), mapping changed paths to root sections and per-area blocks. Drifted = commits touched the block's area since its `git_base`; HEAD moving alone is not drift. Offer to refresh drifted blocks via `/zoom-out`.
4. Skip silently anything absent — this self-disables in repos that don't use these conventions.
5. If **none** of the three exists yet, don't keep silent: say so once and offer to build the layer (`/grill` for the glossary, `/zoom-out` for the map) — then proceed either way.

This load happens every session unconditionally; `/resume` reuses it and layers a handoff on top. Per-repo layout (single/multi-context) lives in `docs/agents/domain.md`.

## Immutability rules

- An issue with `status: done` (in YAML frontmatter) is immutable: never edit its body or change its `status`. The git commit is the source of truth. To revise, create a new redo issue (`NN-redo-<slug>.md`).
- An ADR superseded by another ADR is immutable: never edit its body. Mark it superseded; the new ADR carries the change.
- Re-running `/plan` with a changed intent defaults to writing a new `PRD-vN.md` with a `Supersedes:` header; the older PRD stays untouched. Append-in-place is reserved for purely additive changes the user explicitly asks for.