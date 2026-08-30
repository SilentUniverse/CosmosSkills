# cosmos-setup — Migration detail (Case 2, Case 3 & Case 5)

Loaded on demand by [`/cosmos-setup`](SKILL.md) step 2 **only** when the repo holds a legacy
`docs/agents/domain.md` (Case 2), is an old setup (Case 3), or its issue files use bare
`Status:` lines (Case 5).

In all cases, present what was found and the proposed migration plan for the user to confirm before
any file is changed. Do not silently rewrite existing user content.

## Case 3 — Old setup detected (`mattpocock/skills` 5-state, or earlier cosmos 6-state)

Trigger: either `docs/agents/issue-tracker.md` references `gh` / `glab` CLI, or existing issue files
use deprecated states (`needs-triage`, `needs-info`, `wontfix`, `inbox`, `blocked`, `doing`,
`shelved`, `ready-for-human`, `ready-for-agent`). Offer:

- (a) **Switch to local-markdown + 2-state vocabulary.** Rewrite `docs/agents/*.md`. The `ready-for-agent` → `ready` rename is mechanical: `sd 'ready-for-agent' 'ready'` over `.scratch/**/issues/*.md`; show the file list first. Every other deprecated state asks the user one-by-one: promote to `ready` or mark `done` (if commit already exists) / delete. Do not silently rewrite the `Status:` line.
- (b) **Keep the old GitHub/GitLab tracker.** User explicitly chose `Other` in Section A.

## Case 5 — Frontmatter migration (bare `Status:` lines)

Triggered from Case 3 (or runnable on its own) when `.scratch/` issues use the legacy bare `Status:`
line instead of YAML frontmatter, or when `issues/archive/` is missing. This upgrades the repo to the
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) contract. It is **idempotent**: skip any file that
already has a `---` frontmatter fence. It is **dry-run-first**: never touch a file before showing the
plan.

Steps:

1. **Scan.** For every `.scratch/<feat>/issues/*.md`, classify: already has frontmatter (skip), or bare `Status:` line (migrate). Note each file's current state string and whether it is `done`.
2. **Build the plan** and print it as a single preview, no writes yet:

   ```
   Frontmatter 迁移计划（dry-run，未落盘）
   加 frontmatter（bare Status: → YAML）:
     .scratch/balance/issues/01-init-schema.md   (done)
     .scratch/balance/issues/04-cache.md          (ready)
   已有 frontmatter（跳过）:
     .scratch/auth/issues/01-login.md
   移动到 archive/（done issue，git mv 保历史）:
     .scratch/balance/issues/01-init-schema.md → issues/archive/01-init-schema.md
   生成索引:
     .scratch/balance/SUMMARY.md   (从 done issue 的 ## Comments 完成记录聚合)
   确认执行？(y / 逐项挑)
   ```

3. **On confirm, execute.** For each bare-`Status:` file, derive the frontmatter fields from the [issue schema](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd): `type: issue`; `feature` from the directory name; `status` from the old `Status:` line with the legacy mapping: `ready-for-agent` → `ready`; `ready-for-human` → fold its hands-on check into the PRD's 端到端验证 and set `ready`. `category: enhancement` by default; the user can refine later. `blocked_by` parsed from any existing `前置依赖` section if filenames are referenced, else `[]`; `created` from one `git log --diff-filter=A --name-only --format=%as -- <issues dir>` pass (paths→dates; today if unseen by git). Remove the now-redundant bare `Status:` line. Do not touch the body otherwise; the change is surgical, frontmatter only.
4. **Archive done issues** with `git mv` into `issues/archive/`. Skip if the user opted out of archiving during migration.
5. **Generate** each feature's `.scratch/<feat>/SUMMARY.md` per the format doc.

Report what changed. If `refines` can't be inferred for a non-top-level issue, leave it unset and note it. The orphan check in `/tidy` will surface it later.

## Case 2 — Legacy `docs/agents/domain.md` fold

Trigger: `docs/agents/domain.md` exists. Consumer skills read `CODEBASE.md`'s
`## Verifier commands` zone, so a repo still carrying the old file has an orphaned cache until
folded.

1. Read the file; classify every line as **real** (an exact command or adapter a run actually
   used — e.g. `pytest -q`, `vitest run <path>`) or **template** (boilerplate headings, empty
   placeholders, consumer-rule prose).
2. Show the user the real lines. On confirm, append them under `## Verifier commands` in the
   root `CODEBASE.md`, lazy-birth per the ARTIFACT-FORMAT stub when absent.
3. Delete `domain.md` only when zero non-template lines remain unaccounted for; otherwise
   `git mv docs/agents/domain.md docs/agents/domain.md.bak` and say why.
4. Remove `docs/agents/` entirely when it is now empty and the tracker is default; a
   non-default `issue-tracker.md` stays.
