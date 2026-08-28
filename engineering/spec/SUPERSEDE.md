# spec — Supersede and reconcile

Loaded on demand by [`/spec`](SKILL.md) step 1 when a hit makes a recorded AC or decision
false. The Design Receipt and reconciliation are one confirm gate; nothing writes before it.

1. **Derive the next snapshot.** Live PRD exists → propose `PRD-vN.md` per
   [PRD-TEMPLATE.md](PRD-TEMPLATE.md) — highest + 1, `supersedes:` the previous filename,
   carry forward still-open 尚未明确. No live PRD → propose `PRD.md` v1. This is receipt input,
   not a file write.
2. **Reconcile.** Delivered work may be archived: also read `SUMMARY.md` and
   `issues/archive/`, so a `done` slice the new plan invalidates is classified as redo, not
   mistaken for a brand-new slice. Classify every existing issue into the report, then append it
   under the Design Receipt so goal, verification, slices, and old→new consequences are corrected
   together (item-by-item or yes-all):

   ```
   对账报告
   仍然有效（不动）:
     ✓ 01-add-schema.md (done)
   已完工但需返工（新建 redo，旧的永不动）:
     ⚠ 02-balance-api.md (done) → 新 PRD 反转了 API 形状
       建议新建：05-redo-balance-api.md (ready)
   未做且仍相关，但范围/AC 有变（直接改原文件）:
     ✏ 04-cache-strategy.md (ready)
       建议改：验收标准 #2 从 X 改 Y
   未做但新 PRD 已不需要（删除）:
     🗑 06-trend-chart.md (ready)
       建议：移入 .scratch/tmp/reconcile-<date>/
   全新切片（新建）:
     ➕ 07-dark-mode.md (ready)
   ```

   Hard rule: never edit a `done` issue; always write a new `NN-redo-X.md` (`category: redo`,
   `refines:` the original slug).
3. **Execute on explicit alignment.** Write the PRD, then apply the reconciliation. Deletes
   relocate to `.scratch/tmp/reconcile-<date>/`
   (undo = move back), never `rm`. Ready-issue edits happen in place; refresh the
   `## 上级` extract.
4. New + redo units → [CARD-TEST.md](CARD-TEST.md).
