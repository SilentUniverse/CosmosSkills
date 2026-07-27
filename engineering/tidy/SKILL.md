---
name: tidy
description: Garbage-collect a feature's issue directory — archive done issues, regenerate SUMMARY.md from completion records, audit for zombie/duplicate tests, and flag orphan issues with no PRD or refines link. Use when a feature's done issues pile up (≈8+), when the working set feels cluttered, or after a redo to clean up superseded tests.
argument-hint: "Feature slug (optional; omit to survey .scratch)"
---

# Tidy

A periodic garbage-collection pass over a feature, so the active working set stays small and
`SUMMARY.md` reflects what's actually been built. This is the reverse-direction counterpart to the
forward pipeline (`to-prd` → `to-issues` → `tdd`): it folds delivered work back into a current-reality
view and clears history out of the live set. All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).

## Invocation

- `/tidy <feat>` — tidy that feature.
- `/tidy` — survey `.scratch` (`rg '^status:' -g '**/issues/*.md' .scratch`), list features whose
  `done` count is high relative to active issues, and ask which to tidy.

## When to run

- A feature has roughly 8+ `done` issues cluttering `issues/`.
- Right after a `redo`/`fix` slice lands, to retire the tests it superseded.
- Any time the live working set feels noisy and you want reality re-summarized.

## Process

### 1. Survey

Read `.scratch/<feat>/issues/*.md` (top level only, not `archive/`). Group by frontmatter `status`.
Read the `### 完成` block of each `done` issue. Read the latest non-superseded `PRD*.md` and note
which user stories / slices it covers.

### 2. Present the plan (dry-run, no writes)

Show one preview covering all four actions, then wait for confirmation (yes-all or item-by-item):

```
📋 Tidy 计划：balance（dry-run，未落盘）
──────────────────────────────────────────────────────────────
归档 done issue（git mv → issues/archive/，body 不动）:
  01-init-schema.md, 02-balance-api.md, 05-redo-balance-api.md  (3)

重生成 SUMMARY.md（聚合上述 done 的完成记录）

测试审计:
  ⚠ 僵尸测试 — 被 redo 取代，建议删:
      tests/test_balance_rest.py (4 cases) ← 02-balance-api（已被 05-redo 取代）
  ⚠ 疑似重复覆盖:
      tests/test_balance_edge.py 与 test_balance_api.py 都覆盖「负余额拒绝」
  ✓ 其余测试保留

孤儿检测:
  ⚠ 04-cache.md (category: detail) 既无 refines 也不在任何 PRD 用户故事下
      建议：补 refines / 并入 PRD-vN / 标 detail 归档
──────────────────────────────────────────────────────────────
确认执行？(y / 逐项挑)
```

### 3. Execute on confirm

- **Archive** — `git mv .scratch/<feat>/issues/NN-*.md .scratch/<feat>/issues/archive/` for each
  confirmed `done` issue. Create `archive/` if absent. Never edit the body or `status` — immutability holds.
- **Regenerate `SUMMARY.md`** — aggregate the `### 完成` blocks into `.scratch/<feat>/SUMMARY.md` per the format doc.
- **Test audit** — for zombie tests (those a `redo`/`fix` slice replaced) and duplicates the user confirmed, delete the test files (or the specific cases). Run the test suite after deletion to confirm nothing green turned red unexpectedly — in a subagent, or redirected to `.scratch/tmp/`, pulling back only the pass tally and failing cases.
- **Orphan resolution** — for each flagged orphan, apply the user's choice: add a `refines:` field,
  fold it into a PRD revision (hand off to `/to-prd`), or relabel `category: detail` and archive.

Report what moved, what was deleted, and any orphans left unresolved for the user to decide later.
