---
name: atk
description: Attack-mode review of the agent's own output — a diff, a design, a plan, a skill's text, or a decision. Re-derives load-bearing choices from first principles (what breaks without it?), then hunts failure modes (semantics, consistency, runtime, necessity, cost). Manual runs also explain every change in scope; spec WRITE-LOOP gets findings only. Use when the user says 对抗式审查 / 再审一轮 / 第一性原理再想想 / 给我讲讲你改了什么. Not a substitute for `/code-review` or a `/tdd` completion 审查.
argument-hint: "Target, --all (entire uncommitted diff), or empty = changes since the last /atk"
---

# Adversarial

Two moves on your own output: **re-derive** (is each load-bearing choice justified from
fundamentals — what breaks without it?) and **attack** (where does it break?). Not `/code-review`,
which judges a diff against standards and spec; this judges any output against itself.

## Target

- User-typed `/atk` — manual mode. Bare: the changes since this session's last `/atk` run
  (first run in a session: this conversation's latest round). `--all`: the entire uncommitted
  working tree — `git status` + per-file `git diff HEAD`. A named target: that target only — a
  file target covers both its current state and its uncommitted diff.
- Invoked by spec WRITE-LOOP step 4 — audit-only: attack the artifacts it names, return
  findings, nothing else.

Name what is out of scope.

## Method

1. **Re-derive each load-bearing choice.** What breaks without it? No answer → cut. Propped up only
   by analogy or sunk cost → rebuild it from the constraints, or drop it.
2. **Attack five surfaces:** semantics (meaning changed?), consistency (stale or renamed refs?),
   runtime (does it run — on Windows?), necessity (readerless file, fake pause, unclosed state,
   doorless entry?), cost (tokens, attention).
3. **A restructure gets both directions.** 正向 — walk every entry, pointer, and cross-skill link
   as its consumer would; each link must still connect. 反向 — diff against the predecessor and
   account for every rule, trigger, and checklist item of the old version: still present,
   relocated — and reachable from the replacing head — or dropped with a reason.
4. **Verdict each finding with a quote:** 修复 / 否决 / 保留. Record the deliberate keeps so the
   next round doesn't re-litigate them.

Big or unfamiliar target? Get one unbiased pass from a read-only subagent. Brief it with the
target, the single claim to attack, a 12-call cap, and the contract to attack against, never a
deleted predecessor. Launch it first and attack inline while it runs. Import its check results
instead of re-running them; verify each finding against its quote before importing. Small
target: attack inline. Harness and gate runs: once, after the fixes, scoped to what changed.

## Output

Mode is fixed by the invocation source: user-typed → audit + 讲解; spec WRITE-LOOP → findings
only.

Lead line: 范围（N 文件 M 处）· 发现 X · 检查（which harness/parse/line checks ran）. Output is the
lead line plus the lists below — no tables, nothing else.

**发现** — both modes. Findings follow the fixed shape (CLAUDE.md §1); 处置 is three-valued:
修复—改成什么 / 否决—为什么不改 / 保留—何时再动. No quote, no finding.

**改动讲解** — user-typed only. One item per change:

```
1. <文件 位置>：<原文关键片段> → <改后关键片段>（add `+ …`, delete `- …`）
   原因：<一句短语，机制性理由，不写论证>
```

A finding's fix item writes 原因 as 见发现 #N; long text compresses to its load-bearing part.
Audit-only runs return findings to the caller — no lead line, no chat output. Non-diff targets
(design, plan, decision): findings only, both modes.

Round discipline: a later `/atk` covers only changes since the last `/atk`; an earlier item
reappears only if it changed again. No process narration. Prose fixes can chain to `/lint`.
