# to-issues — Reconciliation report (re-run against existing issues)

Loaded on demand by [`/to-issues`](SKILL.md) step 0 **only** when the feature already has issues in
`.scratch/<feat>/issues/` and the skill is re-run from a revised PRD. A brand-new feature with no
existing issues skips this entirely.

Delivered work may already be archived: also read `SUMMARY.md` and `issues/archive/`, so a `done`
slice the new plan invalidates is classified as 需返工 (redo), not mistaken for 全新切片.

Produce a **reconciliation report** comparing the new plan against the existing issues, then ask the
user to confirm before doing anything. Classify every existing issue into one bucket:

```
📋 对账报告
──────────────────────────────────────────────────────────────
仍然有效（不动）:
  ✓ 01-add-schema.md (done)
  ✓ 03-mobile-ui.md (ready-for-human)

已完工但需返工（新建 redo 文件，旧的永不动）:
  ⚠ 02-balance-api.md (done) → 新 PRD 反转了 API 形状
    建议新建：05-redo-balance-api.md (ready-for-agent)

未做且仍相关，但范围/AC 有变（直接改原文件）:
  ✏ 04-cache-strategy.md (ready-for-agent)
    建议改：验收标准 #2 从 X 改 Y，加一条 AC 点...

未做但新 PRD 已不需要（删除）:
  🗑 06-trend-chart.md (ready-for-agent)
    建议：rm 06-trend-chart.md

全新切片（新建）:
  ➕ 07-dark-mode.md (ready-for-human)
──────────────────────────────────────────────────────────────
```

Classification rules:

- **仍然有效** — the existing issue's behavior is unchanged in the new PRD.
- **已完工但需返工** — issue is `done` AND the new PRD invalidates the implementation. Hard rule: never edit a `done` issue. Always produce a new `NN-redo-X.md` (`category: redo`, `refines:` pointing at the original slug). The old file stays as a historical record.
- **未做且范围变了** — issue is `ready-for-X` AND the new PRD changes its scope or AC. Edit the file in place — there's no `done` history to preserve.
- **未做但不需要了** — issue is `ready-for-X` AND the new PRD no longer requires it. Delete the file.
- **全新切片** — nothing existing covers this part of the new PRD.

Let the user confirm the report (item-by-item or yes-all). Then execute: `rm` for deletes, edit for in-place changes, write new files for new + redo. Continue to step 3 to draft the new + redo slices.
