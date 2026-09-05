# cosmos-setup — Migration detail (Case 2, Case 3 & Case 5)

Loaded on demand by [`/cosmos-setup`](SKILL.md) step 2 **only** when the repo holds a legacy
`docs/agents/domain.md` (Case 2), is an old setup (Case 3), or its issue files use bare
`Status:` lines (Case 5).

Preview concrete paths and mappings, then execute changes covered by the migration request.
Ask once for unresolved semantic mappings or removal of content that is not proven derived.
Leave uncertain files intact while completing independent mechanical changes.

## Case 3 — Old setup detected (`mattpocock/skills` 5-state, or earlier cosmos 6-state)

Trigger: a requested tracker switch, or existing issue files
use deprecated states (`needs-triage`, `needs-info`, `wontfix`, `inbox`, `blocked`, `doing`,
`shelved`, `ready-for-human`, `ready-for-agent`). Offer:

- (a) **Switch to local-markdown + 2-state vocabulary** when requested. Update only affected configuration. Rename `ready-for-agent` to `ready` only in status metadata; verify readiness against the current schema. For other states, infer mappings from AC/evidence and completion records; group unresolved mappings for one user decision. Do not infer deletion authority from a deprecated state.
- (b) **Keep the configured tracker.** A `gh` / `glab` reference alone does not justify switching it.

## Case 5 — Frontmatter migration (bare `Status:` lines)

Triggered from Case 3 (or runnable on its own) when `.scratch/` issues use the legacy bare `Status:`
line instead of YAML frontmatter. An absent `issues/archive/` needs no migration. This upgrades to the
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
   保留当前位置（done 由 status 查询，legacy archive 仍兼容）:
     .scratch/balance/issues/01-init-schema.md
    旧派生文件（核对投影和迁移授权后删除）:
     .scratch/balance/SUMMARY.md
    已授权的机械迁移直接执行；未决语义映射单列。
   ```

3. **Execute resolved mappings.** For each bare-`Status:` file, derive fields from the [issue schema](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd): `type: issue`; `feature` from the directory; `status` from the resolved mapping. For `ready-for-human`, retain its hands-on check in the PRD's 端到端验证 and set `ready` only after current readiness requirements pass. Infer `category` from the issue's purpose; `blocked_by` from existing dependency references; `created` from one `git log --diff-filter=A --name-only --format=%as -- <issues dir>` pass (today if unseen by git). Leave ambiguous dependencies or status unresolved. Remove the redundant bare `Status:` line only on migrated files; preserve the body except the explicitly relocated hands-on check.
4. **Keep issue paths stable.** Do not move newly migrated done issues. Existing archive files stay
   supported by the resolver and gate.
5. **Retire legacy SUMMARY.** Compare `workflow-state.py inspect` against the delivered slugs, then
    delete SUMMARY only if it is fully derived and removal is covered by the migration request.
    Preserve unique user content and untracked files unless their removal is explicitly authorized.

Run `verify-artifacts.py <repo-root>` and report changes plus unresolved schema gaps. If `refines`
cannot be proven, leave it unset and resolve intent through `/spec`; GC never hides it. Preserve
historical completion bodies; active-batch failure recovery follows [DRAIN](../tdd/DRAIN.md), not migration.

## Case 2 — Legacy `docs/agents/domain.md` fold

Trigger: `docs/agents/domain.md` exists. Consumer skills read `CODEBASE.md`'s
`## Verifier commands` zone, so a repo still carrying the old file has an orphaned cache until
folded.

1. Read the file; classify every line as **real** (an exact command or adapter a run actually
   used — e.g. `pytest -q`, `vitest run <path>`) or **template** (boilerplate headings, empty
   placeholders, consumer-rule prose).
2. For an authorized fold, append the real lines under `## Verifier commands` in the
   root `CODEBASE.md`, lazy-birth per the ARTIFACT-FORMAT stub when absent.
3. Delete `domain.md` only when zero non-template lines remain unaccounted for; otherwise
   `git mv docs/agents/domain.md docs/agents/domain.md.bak` and say why.
4. Remove `docs/agents/` entirely when it is now empty and the tracker is default; a
   non-default `issue-tracker.md` stays.
