---
name: tidy
description: Garbage-collect a feature's issue directory — archive done issues, regenerate SUMMARY.md from completion records, audit for zombie/duplicate tests, and flag orphan issues with no PRD or refines link. Use when a feature's done issues pile up (≈8+), when the working set feels cluttered, or after a redo to clean up superseded tests.
argument-hint: "Feature slug (optional; omit to survey .scratch)"
---

# Tidy

A periodic garbage-collection pass over a feature, so the active working set stays small and
`SUMMARY.md` reflects what's actually been built. All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md).

## Invocation

- `/tidy <feat>` — tidy that feature.
- `/tidy` — survey `.scratch` (`rg '^status:' -g '**/issues/*.md' .scratch`), list features whose
  `done` count is high relative to active issues, and ask which to tidy.

## Process

### 1. Survey

Survey by extraction: one `rg '^status:' -g '*.md' .scratch/<feat>/issues` pass, each `done`
issue's `### 完成` block, and the latest non-superseded `PRD*.md` in full. Never read whole issue
bodies.

### 2. Present the plan, then execute

Show one preview covering all four actions, then execute it. Destructive steps relocate instead of delete: zombie/duplicate tests move to `.scratch/tmp/tidy-<date>/` (move back restores; the suite sees them gone), orphan files archive rather than delete.

```
Tidy 计划：balance（dry-run，未落盘）
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
确认执行？(y / 逐项挑)
```

### 3. Execute on confirm

- **Archive** — `git mv .scratch/<feat>/issues/NN-*.md .scratch/<feat>/issues/archive/` for each
  confirmed `done` issue. Create `archive/` if absent. Never edit the body or `status` — immutability holds.
- **Regenerate `SUMMARY.md`** — aggregate the `### 完成` blocks (excluding 审查 lines) of all
  done issues, top-level **plus `issues/archive/`**, into `.scratch/<feat>/SUMMARY.md` per the
  format doc.
- **Test audit** — **zombie = a test in the parent's `### 完成` 新增测试 that the redo's
  `### 完成` did not carry forward**; derive it by diffing the two lists. Move zombies and
  duplicates to the staging dir, then run the **full suite** (subagent, or redirect to
  `.scratch/tmp/`). Report every moved test with its case counts — a green suite does not prove
  coverage was not lost. On unexpected red: move the tests back, re-run, re-audit.
- **Orphan resolution** — resolve by the safe heuristic: obvious parent → add the `refines:`
  field; no PRD linkage and stale → relabel `category: detail` and archive. Ambiguous ones are
  reported unresolved — never guess on a may-be-load-bearing orphan.

Report what moved, what was deleted, and any orphans left unresolved for the user to decide later.
