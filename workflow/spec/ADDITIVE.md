# spec — Additive re-run

Loaded on demand by [`/spec`](SKILL.md) step 1 when a hit in the target feature falsifies
nothing recorded. Existing behavior and done contracts remain valid. The older PRD stays untouched.
If a reviewed PRD needs new anchors, write a new full version with `supersedes:` linking the prior
snapshot, following [PRD-TEMPLATE.md](PRD-TEMPLATE.md); this advances the design without invalidating
unchanged delivered behavior. Review the changed scope; independent accepted cards can continue under
the [scoped acceptance gate](REVIEW.md#acceptance-and-materialization).
Apply the settled request through [spec's write and acceptance steps](SKILL.md#3-prepare-and-write); use a Design Receipt only for a newly unresolved
consequential decision. Prepare and implement additions within existing authorization; wait only for a new unresolved material decision or explicit plan-only review.

- Growing an existing unit → check its execution ownership, then edit an unassigned `pending`/`ready` issue in place; refresh its `## 上级` extract
  if the parent PRD lines it cites moved. `done` issues are never edited. A change that
  invalidates one belongs in [SUPERSEDE.md](SUPERSEDE.md).
- New sub-behaviour on an existing unit → `detail` issue (`category: detail`, `refines:`
  parent slug).
- New independent behaviour → new `enhancement` issue.

Then [CARD-TEST.md](CARD-TEST.md) for the new units.
