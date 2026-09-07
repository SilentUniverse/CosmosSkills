---
name: atk
description: >-
  Use when the user asks for atk, 对抗式审查, 再审一轮, a first-principles recheck, or an explanation of recent changes. Audits a diff, design, plan, skill, or decision for load-bearing choices and failure modes; use code-review for ordinary review.
argument-hint: "[-r] [target | -all]; empty target = changes since the last review"
---

# ATK

Two moves on your own output. **Re-derive**: is each load-bearing choice justified from
fundamentals? What breaks without it? **Attack**: where does it break? Not `/code-review`,
which judges a diff against standards and spec; this judges any output against itself.

## Target

- User-typed `/atk` — manual mode. An optional leading `-r` selects pure read-only review.
  `/atk -r`, `/atk -r -all`, and `/atk -r <target>` use the same scopes as their unflagged
  forms but return findings only. For the whole invocation, including delegated passes, do not
  edit, create, delete, rename, stage, or commit files; do not run formatters, fixers, migrations,
  generators, or checks that may mutate the filesystem. Name a useful check as not run when its
  read-only behavior cannot be guaranteed. Bare: the changes since this session's last `/atk` run
  (first run in a session: this conversation's latest round). `-all`: the entire uncommitted
  working tree — `git status` + per-file `git diff HEAD`. A named target: that target only. A
  file target covers both its current state and its uncommitted diff. Caller-invoked acceptance
  checks return findings to that caller; they do not require a separate user command.
- Invoked by spec acceptance — audit-only: attack the artifacts it names, return
  findings, nothing else.
- Invoked by `/tdd` to classify a possible receipt conflict — blind classifier: return only the
  response defined in [RECEIPT-CONFLICT.md](RECEIPT-CONFLICT.md) to the calling loop.

Name what is out of scope.

## Method

`-r` changes execution, not scrutiny: complete the same analysis, but treat every cut, rebuild,
drop, or fix below as a recommendation and never apply it.

1. **Re-derive each load-bearing choice.** What breaks without it, and who consumes it now (a
caller, a test, or a recorded decision)? No answer → cut. Propped up only by analogy or sunk cost →
rebuild it from the constraints, or drop it.
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
target: attack inline. Harness and gate runs: once, after the fixes, scoped to what changed. Under
`-r`, run only checks guaranteed read-only; skip the rest rather than risk a write.

## Output

Mode is fixed by the invocation source and flag: user-typed → audit + 讲解; user-typed `-r` →
findings only, read-only; spec acceptance → findings only; tdd blind classifier → the response
shape in [RECEIPT-CONFLICT.md](RECEIPT-CONFLICT.md).

Lead with scope, actionable findings, and checks actually run. A clean review is valid. A caller
may integrate this result into its own report instead of repeating a full skill report.

**发现** — manual and spec audit modes. Findings include location, exact quote, consequence, and disposition. 处置 is
three-valued: 修复—改成什么 / 否决—为什么不改 / 保留—何时再动. No quote, no finding. All findings
live in one section, compact first and impact-level last; no separate 讲解 or 其他改动 sections
follow.

**N. <位置[:行]> — <处置>**

原句：关键片段，≤1 行；核对需要全句时才给全句。

问题：一句话说本质——什么跟什么冲突、什么坏了；不说推导。

改法：一句话方向，仅 修复；格式、排版、措辞类改动通常止于处置行。

An impact-level finding — the change alters how the whole codebase or workflow behaves: a new
guarantee, a changed contract, a different failure mode, a moved invariant — goes last in the
section and adds a 讲解 field inside its own block: 改前 → 改后 and why, as long as clarity
needs, no cap, no derivation prose. Non-impact findings come first and stay compact, and every
applied change still appears — its own line or a pointer inside the finding it serves — never
silently dropped.

Fields sit on their own lines separated by blank lines; no code fence, no bullet chrome. Findings
are numbered so later prose can cite 发现 #N.

Calibration — only the second entry is a finding; the first survives any outcome:

Not a finding（"查了什么"凑数：无位置、无引用、无可证伪断言）:

**1. workflow-state.py — 保留**

原句：（无）

问题：导入和路径逻辑整体看下来没发现问题。

A finding（定位到行、引用原句、断言可错）:

**2. workflow-state.py:121 — 修复**

原句：os.path.join(root, *relative.split("/"))

问题：../ 组件可逃逸仓库根。

改法：路径锁在 .scratch/<feat>/receipts/ 下。

**讲解 rides inside impact findings** — see the 发现 spec above. Under `-r`, a 修复 disposition
proposes what to change but never performs the change.
Audit-only runs return their scoped response to the caller; no lead line or chat output. Non-diff
targets (design, plan, decision): findings only, both modes. Questions riding on the invocation
are answered after the findings; they are the caller's ask, not leakage.

Round discipline: a later `/atk` covers only changes since the last `/atk`; an earlier item
reappears only if it changed again. An explicitly named scope overrides the round default.
No process narration. Outside `-r`, prose fixes can chain to `/lint`. Report layout follows
[REPORT-FORMAT.md](../REPORT-FORMAT.md); the finding block above is its 发现 form.
