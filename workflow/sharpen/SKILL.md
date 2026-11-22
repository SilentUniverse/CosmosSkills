---
name: sharpen
description: >-
  Use only when the user invokes /sharpen to deepen a rough request or prompt before sending it. Surfaces what a domain expert would do, primary sources, methods/tools, and external verification criteria, then returns a ready-to-send Chinese prompt without executing the task.
argument-hint: "Your rough idea, task, or draft prompt"
disable-model-invocation: true
---

# Sharpen

Deepen a rough request or draft prompt **before** execution — make it sharper and more verifiable,
never bigger in scope. **Do not execute the task, edit repository files, run mutating commands, or
invoke `/spec` or `/tdd`.** Your only deliverable is the analysis and the rewritten prompt.

## 1. Optional light grounding (read-only)

If invoked inside a repository and the draft names a file, symbol, feature, error, or clearly
targets the current project, do at most a minimal read-only lookup (`rg` or read the named file /
native command entry / `AGENTS.md` `## Commands`) so the rewritten prompt points to **real paths,
real commands, and real primary sources** instead of generic placeholders. Skip grounding for
non-code or general tasks. Never plan, write code, or run tests.

## 2. Deepen along four axes (in Chinese)

Before rewriting, answer these four questions concisely — keep every point concrete and specific to
this task (cut generic advice that would fit any task):

1. **顶级专家会多做哪件你没开口的事？** — Identify the highest-leverage blind spot, invariant,
   failure mode, or prerequisite an expert would check first without expanding feature scope.
2. **最原始的一手材料是什么？** — Name the raw primary inputs to start from (exact source files,
   schemas, runtime logs, traces, commit/PR history, official specs) instead of summaries or memory.
3. **具体会用什么方法与工具？** — Name concrete runnable methods, probes, or harnesses (minimal
   repro, differential check, frozen benchmark, statechart, profiler, type/contract check).
4. **除了你和我之外，什么外部客观判据能证明结果是对的？** — Define a falsifiable pass/fail
   oracle that breaks if the solution is wrong (command exit + output, before/after metric on the
   same workload, byte-identical output, real UI state assertion).

## 3. Rewrite the prompt (ready to send)

Return one copy-ready Chinese prompt block in Cosmos's five-element shape so the user can edit or
send it directly:

```text
目标：<更精准、不扩 scope 的结果陈述>
怎么算做好：<可判定通过或失败的外部检查>
要看到的证据：<具体命令输出、改前改后数字、截图或产物路径>
已知信息与一手材料：<具体文件/日志/命令/现状边界>
约束与分工：<红线与明确不做（OUT）；能靠小实验/原型定夺的技术选型自行验证并给建议，产品或偏好取舍留给我拍板>
```

Rules for the rewrite:

- **Deeper, not bigger.** Add rigor, primary sources and falsifiable proof; never bolt on extra
  features or unrequested refactors.
- **Experiments settle empirical forks; humans settle product calls.** Instruct the future agent to
  settle technical uncertainty via cheap probes/prototypes and recommend based on observed results,
  while leaving product, contract, and taste decisions to the user.
- **Keep it compact.** Match length to task size — a sharp 6–10 line prompt beats a bloated essay.

End with a one-line routing hint: whether the rewritten prompt best fits `/spec` (design, boundary,
or multi-stage planning) or direct execution (clear bounded fix/change). Then stop.
