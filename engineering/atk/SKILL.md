---
name: atk
description: Attack-mode review of the agent's own output — a diff, a design, a plan, a skill's text, or a decision. Re-derives load-bearing choices from first principles (what breaks without it?), then hunts failure modes (semantics, consistency, runtime, necessity, cost). Use when the user says 对抗式审查 / 再审一轮 / 第一性原理再想想, or before committing a significant batch.
argument-hint: "Target (empty = uncommitted diff)"
---

# Adversarial

Two protocols, one pass: **re-derive** (is each part justified from fundamentals?) then **attack**
(where does it break?). Not a code review — `/code-review` judges a diff against standards and
spec; this judges any agent output against itself.

## Target

Explicit argument > uncommitted diff (`git status` + per-file diffs) > ask. Name what is OUT of
scope.

## Protocol

1. **Fresh eyes first.** Dispatch a read-only subagent that cannot see this conversation — brief
   it with the target, the claim to attack, and a tool-call cap; findings come back as
   `file:line | quote | failure mode | confidence`. Subagent unavailable → attack inline and say
   so.
2. **Verify every finding before importing it** — attacker reports run at least one-third false
   positives in practice; quote the evidence that makes each true one true, drop the rest.
3. **Re-derive the load-bearing choices**: for each, what breaks without it? No answer → cut.
   Justified only by analogy or sunk design → rebuild the justification from constraints.
4. **Attack surfaces, in order**: semantics (does any change alter meaning?) → consistency
   (cross-file references, renamed-but-missed spots, stale names) → runtime (does it execute —
   on Windows?) → necessity (fake pause, readerless file, state without closure, doorless entry)
   → cost (tokens per session, wall-clock, attention).
5. **Verdicts with evidence**: 修复 / 否决 / 存疑保留. Record the deliberate keeps — they
   prevent re-litigating the same question next round.
6. **Chain to lint.** Fixes that changed prose → run `/lint` over the touched files (docs,
   artifacts, and comments in code — prose surfaces only; code logic is `/code-review`'s job).

## Output

One verdict table, fixes applied, deliberate keeps, and a one-line honest cost ledger (what this
review changed vs confirmed).
