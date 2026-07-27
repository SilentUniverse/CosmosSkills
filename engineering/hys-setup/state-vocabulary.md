# Issue States

This project uses a minimal 3-state workflow tuned for **solo dev + agent assistance**. There is no triage, no inbox, no blocked. Every issue is either ready to do, ready to do hands-on, or done. Issues that turn out unwanted are deleted; superseded work is recorded by creating new redo issues, never by editing old ones.

| Canonical role    | String in our tracker | Meaning                                                                |
| ----------------- | --------------------- | ---------------------------------------------------------------------- |
| `ready-for-agent` | `ready-for-agent`     | Fully specified, fire-and-forget OK — dispatch to a subagent in parallel |
| `ready-for-human` | `ready-for-human`     | Fully specified, but needs hands-on judgment / design taste / manual / device testing |
| `done`            | `done`                | Completed. **Immutable** — git has the commit. To revise, create a new redo issue. |

The state lives in the YAML frontmatter `status:` field at the top of each issue file under `.scratch/<feat>/issues/`, e.g. `status: ready-for-agent` (full schema in `ARTIFACT-FORMAT.md` at the skills root, `~/.claude/skills/ARTIFACT-FORMAT.md`).

## How to inspect / change state

```bash
# Inspect active working set — archive/ excluded by the glob
rg '^status: ready-for-agent' -g '**/issues/*.md' .scratch
rg '^status: ready-for-human' -g '**/issues/*.md' .scratch

# Read one field deterministically: yq --front-matter=extract '.status' <file>
# Done/archived history: list .scratch/<feat>/issues/archive/
# Or VS Code: Ctrl+Shift+F, regex on, search '^status: ready-for-agent'
```

State changes are usually automatic:
- `/to-issues` writes new issues at `status: ready-for-agent` (default) or `ready-for-human`.
- `/tdd` flips the issue to `done` and appends a completion record when all acceptance criteria pass.
- `/tidy` moves `done` issues into `issues/archive/` (it never edits their bodies).

Manual changes are rare — only when toggling between `ready-for-agent` and `ready-for-human`, or (rarely) reverting a `done` to `ready-for-X` to acknowledge that this issue needs revision (in which case `/tdd` will pause and ask whether you intend incremental edit or full rework).

## Migrating from older vocabularies

If this repo previously used a richer state machine, drop these states:

| Old              | What to do                                                |
| ---------------- | --------------------------------------------------------- |
| `inbox`          | Either flesh out to `ready-for-agent`/`ready-for-human` or delete |
| `needs-triage`   | Same as `inbox`                                           |
| `needs-info` / `blocked` | Either resolve and promote to ready, or delete    |
| `doing`          | Set back to `ready-for-X` (state was a transient pointer) |
| `wontfix` / `shelved` | Delete the file (reason can live in a commit message or ADR) |

