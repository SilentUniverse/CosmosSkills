---
name: atk
description: Attack-mode review of the agent's own output — a diff, a design, a plan, a skill's text, or a decision. Re-derives load-bearing choices from first principles (what breaks without it?), then hunts failure modes (semantics, consistency, runtime, necessity, cost). Use when the user says 对抗式审查 / 再审一轮 / 第一性原理再想想, or before committing a significant batch.
argument-hint: "Target (empty = uncommitted diff)"
---

# Adversarial

Two moves on your own output: **re-derive** (is each load-bearing choice justified from
fundamentals — what breaks without it?) and **attack** (where does it break?). Not `/code-review`,
which judges a diff against standards and spec; this judges any output against itself.

## Target

Explicit argument > uncommitted diff (`git status` + per-file diffs) > ask. Name what is out of
scope.

## Method

1. **Re-derive each load-bearing choice.** What breaks without it? No answer → cut. Propped up only
   by analogy or sunk cost → rebuild it from the constraints, or drop it.
2. **Attack five surfaces:** semantics (meaning changed?), consistency (stale or renamed refs?),
   runtime (does it run — on Windows?), necessity (readerless file, fake pause, unclosed state,
   doorless entry?), cost (tokens, attention).
3. **Verdict each finding with a quote:** 修复 / 否决 / 存疑保留. Record the deliberate keeps so the
   next round doesn't re-litigate them.

Big or unfamiliar target? Optionally get an unbiased pass from a read-only subagent — brief it with
the target, the claim to attack, and a tool-call cap, then verify each finding against its quote
before importing (outside reports run heavy on false positives). Small target: attack inline.

## Output

One verdict table, the fixes applied, the deliberate keeps, and a one-line cost ledger (changed vs
confirmed). Prose fixes can chain to `/lint`.
