---
name: tidy
description: Inspect effective feature state and garbage-collect closed transient caches without changing product semantics. Use when a feature's workflow state needs a compact current-reality view or closed batch caches need cleanup.
argument-hint: "Feature slug (optional; omit to survey .scratch)"
---

# Tidy

A compatibility entry for read-only state projection and safe cache GC. It never moves issue or
test files, edits requirement lineage, or writes a derived summary.

## Invocation

- `/tidy <feat>`: inspect one feature, then preview removable transient caches.
- `/tidy`: survey every feature with an `issues/` directory. No file-count threshold.

The shared module lives beside `ARTIFACT-FORMAT.md`:

```text
python <skills-root>/workflow-state.py survey <repo-root> --format human
python <skills-root>/workflow-state.py inspect <repo-root> <feat> --format human
python <skills-root>/workflow-state.py gc <repo-root> <feat>
```

Use `python3` only when `python` is absent. The projection reads top-level and legacy archived done
issues, folds completed redo lineage, and prints source digests. It writes nothing.

## GC

`gc` lists only `preflight-receipt.json` and a fully closed `wave-ledger.json`. A ready issue or
open wave makes the candidate list empty. Inspect the JSON plan; an explicit cleanup request
authorizes `--apply` for these proven disposable caches without a second confirmation. Inspect-only
requests stop at the preview. Drain close may apply the same plan after every wave is closed.

Run `verify-artifacts.py <repo-root>` before GC. A gate failure stops cleanup. The apply pass uses
explicit paths from one feature and reports every removed cache.

If the runtime is unavailable, inspect source artifacts read-only and report that GC was not run.
Historical `done` issues stay immutable; active-batch failed-verification recovery belongs to
[DRAIN](../tdd/DRAIN.md), never to GC. Resume the caller's authorized work after inspection or cleanup.

## Ownership

- Effective delivered behavior: `workflow-state.py inspect`, generated on demand.
- Redo test fate: the redo/fix execution contract; an omission is not delete authority.
- Missing or ambiguous `refines`: `/spec`; keep the issue live until intent is resolved.
- Duplicate coverage: ordinary test review with behavioral evidence, never this skill.

Legacy `SUMMARY.md` remains readable during migration but is not current reality and is never
regenerated. `/cosmos-setup` can remove it after consumers use the projection.
