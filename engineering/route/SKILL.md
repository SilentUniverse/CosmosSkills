---
name: route
description: Router for the engineering workflow — maps a request onto the right next skill and manages context boundaries (smart zone, compact/clear/handoff) so long sessions stay fast and sharp. Use when unsure which skill to run next, when a session is getting long, or at a phase boundary between grill / to-prd / to-issues / tdd / tidy.
disable-model-invocation: true
---

# Route

Two jobs: **routing** (what's next) and **context boundaries** (keep the window inside the
smart zone).

## 1. Route to the next skill

```
需求还没谈清 / 要压方案 ────────────────► /grill        (→ CONTEXT.md, ADR)
        │
方案定了，要落成需求文档 ────────────────► /to-prd       (→ .scratch/<feat>/PRD.md)
        │
PRD 定了，要拆成可执行切片 ──────────────► /to-issues    (→ issues/NN-*.md + DAG)
        │
切片就绪，要写代码 ──────────────────────► /tdd
        │   ├─ 想甩给 subagent 后台跑    ─► /tdd -p       (隔离各自输出，独立切片并行)
        │   └─ 想盯着过程 / 一条依赖长链 ─► /tdd (serial) (在主会话里盯着做)
        │
写完了，要审 ────────────────────────────► /code-review  (Standards + Spec 并行)
        │
done 攒到 ~8+ ──────────────────────────► /tidy
```

On-ramps that jump onto this flow:
- **Bug / 变慢** → `/diagnose`（先建复现回路，再修）。
- **外部事实要查** → `/research`（后台 subagent，主线不阻塞）。
- **设计问题要个具体产物** → `/prototype`。
- **需求又变** → 回 `/grill` 写新 ADR（`Supersedes:` 旧决策）→ `/to-prd` 写 `PRD-vN.md` → `/to-issues` 给对账报告。

## 2. Manage the context boundary

The **smart zone** is the window (~150k tokens on current models) within which the model still
reasons sharply. Past it, quality drops before the hard limit — so treat the smart zone, not the
context limit, as the ceiling.

**Keep grill → to-prd → to-issues in one unbroken window** — don't compact or clear between
them. Then **each `/tdd` slice starts fresh** from its issue file.

At a phase boundary, pick the cheapest option that loses nothing:

| Option | When |
|---|---|
| **Continue** | Nothing to gain from resetting; the window is well inside the smart zone. Rule this out first. |
| **`/clear`** | Nothing in the current window matters to what's next (e.g. planning done, moving to an unrelated slice). |
| **subagent** | The next step is tightly scoped and read-heavy (search, full-suite run, research) — send it to its own window, get back only the result. |
| **`/compact`** | Continuing needs *some* of this context but the window is near the smart zone — compress and seed a fresh session at the boundary. The default at the bottom of the tree. |
| **`/handoff`** | Leaving this harness/directory, handing to a colleague, or forking mid-phase — write a portable doc. |

If a session approaches the smart zone **before** `/to-issues`, don't push on a degraded window —
`/compact` at the nearest phase boundary rather than mid-thought.

End by naming the chosen next skill and, if you reset the window, which boundary option you took.

Unattended runs (drain `-p`, overnight): maintain a rolling `/handoff` — mini-refresh at batch close (/handoff §Rolling mode). Interactive sessions: the user calls `/handoff` at the smart-zone boundary, never auto.
