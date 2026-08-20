---
name: atk
description: Attack-mode review of the agent's own output — a diff, a design, a plan, a skill's text, or a decision. Re-derives load-bearing choices from first principles (what breaks without it?), then hunts failure modes (semantics, consistency, runtime, necessity, cost). Use when the user says 对抗式审查 / 再审一轮 / 第一性原理再想想. Not a substitute for `/code-review` or a `/tdd` completion 审查.
argument-hint: "Target (empty = uncommitted diff)"
---

# Adversarial

Two moves on your own output: **re-derive** (is each load-bearing choice justified from
fundamentals — what breaks without it?) and **attack** (where does it break?). Not `/code-review`,
which judges a diff against standards and spec; this judges any output against itself.

## Target

Explicit argument > every modified file in the project (`git status` + per-file diffs against
HEAD) > ask. No argument, or 所有修改, means the entire uncommitted working tree — all rounds'
changes, not this conversation's latest. Name what is out of scope.

## Method

1. **Re-derive each load-bearing choice.** What breaks without it? No answer → cut. Propped up only
   by analogy or sunk cost → rebuild it from the constraints, or drop it.
2. **Attack five surfaces:** semantics (meaning changed?), consistency (stale or renamed refs?),
   runtime (does it run — on Windows?), necessity (readerless file, fake pause, unclosed state,
   doorless entry?), cost (tokens, attention).
3. **Verdict each finding with a quote:** 修复 / 否决 / 存疑保留. Record the deliberate keeps so the
   next round doesn't re-litigate them.

Big or unfamiliar target? Get one unbiased pass from a read-only subagent. Brief it with the
target, the single claim to attack, a 12-call cap, and the contract to attack against, never a
deleted predecessor. Launch it first and attack inline while it runs. Import its check results
instead of re-running them; verify each finding against its quote before importing. Small
target: attack inline. Harness and gate runs: once, after the fixes, scoped to what changed.

## Output

Lead with one line: 修复 / 否决 / 存疑保留 counts and check status. Then the verdict table:
finding, verdict. Then one lineage block per 修复, transitions in chronological order — the
target's earlier modification first, this round's fixes last, each with its reason in one
sentence. Quote short text verbatim; compress long text to its load-bearing part before the
contrast. 原来 — the state before the earlier modification; 先改 — after it and why; 再改 —
after this round's fix and why. A spot with no earlier modification drops the 先改 line.
否决 / 存疑保留 one line each, quote included. List the deliberate keeps. Cost ledger one
line, changed vs confirmed. No process narration. Prose fixes can chain to `/lint`.
