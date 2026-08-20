---
name: route
description: Router for the engineering workflow — maps a request onto the right next skill and manages context boundaries (smart zone, compact/clear/handoff) so long sessions stay fast and sharp. Use when unsure which skill to run next, when a session is getting long, or at a phase boundary between grill / spec / tdd / tidy.
disable-model-invocation: true
---

# Route

Two jobs: **routing** (what's next) and **context boundaries** (keep the window inside the
smart zone).

## 1. Route to the next skill

```
需求还没谈清 / 要压方案 ────────────────► /grill        (→ CONTEXT.md, ADR)
        │
方案要落档 / 要拆成可执行切片 ───────────► /spec         (→ PRD.md* + issues/NN-*.md；不写代码)
        │
切片就绪，要写代码 ──────────────────────► /tdd
        │   ├─ 想甩给 subagent 后台跑    ─► /tdd -p       (隔离各自输出，独立切片并行)
        │   └─ 想盯着过程 / 一条依赖长链 ─► /tdd (serial) (在主会话里盯着做)
        │
写完了，要审 ────────────────────────────► /code-review  (已随 drain 关批跑过 Spec+Standards 则跳过)
        │
done 攒到 ~8+ ──────────────────────────► /tidy
```

On-ramps that jump onto this flow:
- **Bug / 变慢** → `/diagnose`（先建复现回路，再修）。
- **外部事实要查** → `/research`（后台 subagent，主线不阻塞）。
- **设计问题要个具体产物** → `/prototype`。
- **需求又变** → `/spec`（AC/决策被推翻才 supersede + 对账报告；只加一块 → detail；重大方向反转先 `/grill` 写新 ADR，旧的标 `Status: superseded`）。

## 2. Manage the context boundary

The **smart zone** (~150k tokens) is the quality ceiling, not the context limit. **Keep grill →
spec in one unbroken window**; then **each `/tdd` slice starts fresh** from its issue file.

At a phase boundary, take the options in order — Continue → `/clear` → `/handoff` → subagent →
`/compact`; the cheapest that loses nothing wins, and `/compact` is the lossy default, never
the first reach: [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md).

Approaching the smart zone **before** `/spec`: don't push a degraded window — reset at the
nearest boundary, never mid-thought.

End by naming the chosen next skill and, if you reset the window, which boundary option you took.

Unattended runs (drain `-p`, overnight): maintain a rolling `/handoff` — mini-refresh at batch close (/handoff §Rolling mode). Interactive sessions: the user calls `/handoff` at the smart-zone boundary, never auto.
