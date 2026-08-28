# spec — Additive re-run

Loaded on demand by [`/spec`](SKILL.md) step 1 when a hit in the target feature falsifies
nothing recorded. The older PRD stays untouched; additive re-runs do not supersede. The bullets
below are proposals until the Design Receipt is aligned; WRITE-LOOP then applies them together.

- Growing an existing unit → edit the `ready` issue in place; refresh its `## 上级` extract
  if the parent PRD lines it cites moved. `done` issues are never edited. A change that
  invalidates one belongs in [SUPERSEDE.md](SUPERSEDE.md).
- New sub-behaviour on an existing unit → `detail` issue (`category: detail`, `refines:`
  parent slug).
- New independent behaviour → new `enhancement` issue.

Then [CARD-TEST.md](CARD-TEST.md) for the new units.
