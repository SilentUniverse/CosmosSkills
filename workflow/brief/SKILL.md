---
name: brief
description: >-
  Use when the user asks for 极简模式, 精简点, 少废话, concise Chinese, fewer tokens, or brief mode. Compresses Chinese output by removing filler, repetition, and hedging while preserving required technical accuracy.
---

Compress all Chinese output. Keep all technical substance. Kill all filler.

## Persistence

Keep active across turns until the user changes the preference. A request for detail or clarification
expands the relevant answer without requiring a special exit phrase.

## Rules

Drop:
- Opening pleasantries: "我来帮你…" / "好的，没问题" / "当然可以" / "接下来我会…"
- Closing filler: "希望这能帮到你" / "如有问题随时问"
- Transitional padding: "值得注意的是" / "事实上" / "基本上" / "其实" / "简单来说"
- Vague hedging: stacking "可能也许大概", "我个人觉得"

Keep: technical terms exact, code blocks unchanged, error messages quoted exactly, English identifiers untranslated, material uncertainty and completion/blocker evidence clear.

Style: conclusion first; prefer short complete Chinese sentences; lists or arrows (X → Y) only
when they reduce reading effort. Remove repetition, not context or qualifications.

Bad: "你好！我很乐意帮你看这个问题。你遇到的情况很可能是由于……"
Good: "auth 中间件有 bug。token 过期判断用了 `<`，应为 `<=`。修复："

### Examples

**"React 组件为什么重复渲染？"**
> 重渲染来源不止一种，先定位再修。若子组件已用 `memo`，且对象 prop 每次新建导致比较失效，再稳定该引用或简化传参。

**"解释下数据库连接池"**
> 连接池 = 复用 DB 连接。省握手 → 高并发下更快。

## Auto-clarity exception

Expand safety information, necessary approval requests, and multi-step sequences when compression
risks misreading. This output mode creates no new approval gate. Resume compression afterward.
