---
name: atk
description: "Attack-mode review of the agent's own output: a diff, design, plan, skill text, or decision. Re-derives load-bearing choices from first principles (what breaks without it?), then hunts failure modes (semantics, consistency, runtime, necessity, cost). Manual diff runs also explain every change; non-diff targets and spec WRITE-LOOP return findings only. Use when the user says 对抗式审查 / 再审一轮 / 第一性原理再想想 / 给我讲讲你改了什么. Not a substitute for `/code-review` or a `/tdd` completion 审查."
argument-hint: "Target, --all (entire uncommitted diff), or empty = changes since the last /atk"
---

# Adversarial

Two moves on your own output. **Re-derive**: is each load-bearing choice justified from
fundamentals? What breaks without it? **Attack**: where does it break? Not `/code-review`,
which judges a diff against standards and spec; this judges any output against itself.

## Target

- User-typed `/atk` — manual mode. Bare: the changes since this session's last `/atk` run
  (first run in a session: this conversation's latest round). `--all`: the entire uncommitted
  working tree — `git status` + per-file `git diff HEAD`. A named target: that target only. A
  file target covers both its current state and its uncommitted diff. Caller-invoked acceptance
  checks return findings to that caller; they do not require a separate user command.
- Invoked by spec WRITE-LOOP step 4 — audit-only: attack the artifacts it names, return
  findings, nothing else.
- Invoked by `/tdd` to classify a possible receipt conflict — blind classifier: return only the
  response defined in [RECEIPT-CONFLICT.md](RECEIPT-CONFLICT.md) to the calling loop.

Name what is out of scope.

## Method

1. **Re-derive each load-bearing choice.** What breaks without it? No answer → cut. Propped up only
   by analogy or sunk cost → rebuild it from the constraints, or drop it.
2. **Attack five surfaces:** semantics (meaning changed?), consistency (stale or renamed refs?),
   runtime (does it run on Windows?), necessity (readerless file, fake pause, unclosed state,
   doorless entry?), cost (tokens, attention).
3. **A restructure gets both directions.** 正向 — walk every entry, pointer, and cross-skill link
   as its consumer would; each link must still connect. 反向 — diff against the predecessor and
   account for every rule, trigger, and checklist item in the predecessor: still present,
   relocated, and reachable from the replacing head, or dropped with a reason.
4. **Verdict each finding with a quote:** 修复 / 否决 / 保留. Record the deliberate keeps so the
   next round doesn't re-litigate them.

For a large target with an independently checkable risk, get one unbiased read-only subagent pass
when available; otherwise review inline and disclose the missing independence. Brief it with the
target, the single claim to attack, a bounded evidence return, and the contract to attack against, never a
deleted predecessor. Launch it first and attack inline while it runs. Import its check results
instead of re-running them; verify each finding against its quote before importing. Small
target: attack inline. Harness and gate runs: once, after the fixes, scoped to what changed.

## Output

Mode is fixed by the invocation source: user-typed → audit + 讲解; spec WRITE-LOOP → findings
only; tdd blind classifier → the response shape in [RECEIPT-CONFLICT.md](RECEIPT-CONFLICT.md).

Lead with scope, actionable findings, and checks actually run. A clean review is valid. A caller
may integrate this result into its own report instead of repeating a full skill report.

**发现** — manual and spec audit modes. Findings include location, exact quote, consequence, and disposition. 处置 is
three-valued: 修复—改成什么 / 否决—为什么不改 / 保留—何时再动. No quote, no finding.

Calibration — only the second entry is a finding; the first survives any outcome:

Not a finding (“查了什么”凑数：无位置、无引用、无可证伪断言):

```text
位置：workflow-state.py
原句：（无）
问题：导入和路径逻辑整体看下来没发现问题
处置：保留
```

A finding (定位到行、引用原句、断言可错):

```text
位置：workflow-state.py:121
原句：os.path.join(root, *relative.split("/"))
问题：../ 组件可逃逸仓库根
处置：修复—路径锁在 .scratch/<feat>/receipts/ 下
```

**改动讲解** — user-typed only. One item per change:

```
1. <文件 位置>：<原文关键片段> → <改后关键片段>（add `+ …`, delete `- …`）
   原因：<一句短语，机制性理由，不写论证>
```

A finding's fix item writes 原因 as 见发现 #N; long text compresses to its load-bearing part.
Audit-only runs return their scoped response to the caller; no lead line or chat output. Non-diff
targets (design, plan, decision): findings only, both modes. Questions riding on the invocation
are answered after the findings; they are the caller's ask, not leakage.

Round discipline: a later `/atk` covers only changes since the last `/atk`; an earlier item
reappears only if it changed again. An explicitly named scope overrides the round default.
No process narration. Prose fixes can chain to `/lint`.
