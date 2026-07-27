# Issue tracker: Local Markdown

Issues and PRDs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The PRD is `.scratch/<feature-slug>/PRD.md`. Newer versions that supersede it are `PRD-v2.md`, `PRD-v3.md`, etc.
- Implementation issues are `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`
- Each issue carries YAML frontmatter (`type` / `feature` / `status` / `category` / `blocked_by` / `refines` / `created`); full schema in `ARTIFACT-FORMAT.md` at the skills root, `~/.claude/skills/ARTIFACT-FORMAT.md`. Three states only: `ready-for-agent`, `ready-for-human`, `done` (see `state-vocabulary.md`)
- `done` issues are moved to `.scratch/<feature-slug>/issues/archive/` by `/tidy`; the active working set is the top-level `issues/*.md`
- `.scratch/<feat>/SUMMARY.md` (generated) is the current-reality view aggregated from `done` issues
- Comments and history append to the bottom of each issue file under a `## Comments` heading

## Two hard rules

**Rule 1 — `done` is immutable.** Once an issue is `done`, never edit its body and never change its `Status`. The git commit is the source of truth for what was done. To revise, create a new issue (`NN-redo-foo.md`); the old one stays as a historical record.

**Rule 2 — Re-running `/to-prd` defaults to supersede.** A new run of `/to-prd` writes a new file `PRD-v2.md` (or v3, v4...) with a `Supersedes:` header pointing at the previous version. The older PRD stays untouched. Append-in-place is reserved for cases where the change only adds detail without invalidating any earlier paragraph; the user must explicitly ask for that mode.

## Quick inspection

```bash
rg '^status: ready-for-agent' -g '**/issues/*.md' .scratch
rg '^status: ready-for-human' -g '**/issues/*.md' .scratch
```

The `-g '**/issues/*.md'` glob matches only active top-level issues, not the nested `archive/`. To read one field deterministically (status, blocked_by, refines), use `yq --front-matter=extract '.status' <file>`. For history, list `issues/archive/`. In VS Code: Ctrl+Shift+F, regex on, search `^status: ready-for-agent`.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly. For PRDs, prefer the highest-numbered non-superseded `PRD*.md` in the feature directory.

