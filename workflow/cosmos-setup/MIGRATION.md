# cosmos-setup — Migration detail (Case 2, Case 3 & Case 5)

Loaded on demand by [`/cosmos-setup`](SKILL.md) step 2 **only** when the repo holds a legacy
`docs/agents/domain.md` (Case 2), requests a tracker switch (Case 3), or carries legacy planning
files (Case 5).

Preview concrete paths and mappings, then execute changes covered by the migration request.
Ask once for unresolved semantic mappings or removal of content that is not proven derived.
Leave uncertain files intact while completing independent mechanical changes.

## Case 3 — Tracker switch

Trigger: a requested tracker switch. Offer:

- (a) **Switch to local `.scratch/<feat>/FEATURE.md`** when requested. Update only affected configuration; fold live work as in Case 5. Do not infer deletion authority from a tracker state.
- (b) **Keep the configured tracker.** A `gh` / `glab` reference alone does not justify switching it.

## Case 5 — Legacy planning files

Trigger: `.scratch/<feat>/` holds any of `PRD*.md`, `issues/`, `verifier.json`, `spec-review.json`,
`spec-acceptances/`, `experience-contract*.json` or `SUMMARY.md`. The gate rejects them; there is no
compatibility reader. The fold is by hand and **dry-run-first**: never touch a file before showing the
plan.

1. **Scan** each feature's legacy files and classify content: live requirements and decisions,
   undelivered cards, delivered history.
2. **Show the plan** as one preview, no writes yet: the target `FEATURE.md`, which requirements and
   decisions become anchored sections (R#/D#/C#), which undelivered cards become `### T<n>` units,
   and which files will be deleted. Unresolved semantic mappings are listed separately.
3. **Fold.** Write one `FEATURE.md` from [FEATURE-TEMPLATE.md](../spec/FEATURE-TEMPLATE.md):
   live requirements and decisions → anchored sections; shared verification → 共享验证; undelivered
   cards → units (`pending` with a reason until readiness is proven). Delivered history stays in Git
   and is not recreated as units.
4. **Delete** the legacy files once the fold is written. Preserve unique user content and untracked
   files unless their removal is explicitly authorized.

Run `../verify-artifacts.py <repo-root>` and report changes plus unresolved gaps. A feature needing
human acceptance is re-reviewed through `/spec`; old acceptance files do not carry over.

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
