---
name: diagnose
description: Disciplined diagnosis loop for hard bugs and performance regressions. Build a feedback loop → reproduce → minimise → hypothesise → instrument → fix → regression-test. Use when user says "diagnose this" / "debug this", reports a bug, says something is broken/throwing/failing, or describes a performance regression.
---

# Diagnose

A discipline for hard bugs. Skip phases only when explicitly justified.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug, one that goes red on _this_ bug, you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

Construction menu (failing test / curl / CLI diff / browser script / trace replay / throwaway harness / fuzz / bisect / differential / HITL), loop tightening, non-deterministic bugs, and the cannot-build-a-loop escape: **[FEEDBACK-LOOPS.md](FEEDBACK-LOOPS.md)**.

### Completion criterion — a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: you can name **one command**, a script path, a test invocation, a curl, that you have **already run at least once** (paste the invocation and its output), and that is:

- [ ] **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring". It must be able to _catch this specific bug_.
- [ ] **Deterministic** — same verdict every run (flaky bugs: a pinned, high reproduction rate).
- [ ] **Fast** — seconds, not minutes. (Slow-but-justified: proceed, note the cost.)
- [ ] **Agent-runnable** — you can run it unattended; a human in the loop only via the HITL template.

If you catch yourself reading code to build a theory before this command exists, **stop. Jumping straight to a hypothesis is the exact failure this skill prevents.** No red-capable command, no Phase 2.

## Phase 2 — Reproduce + minimise

Run the loop. Watch it go red — the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described, not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut. Done when removing any one element makes the loop go green. The minimal repro becomes the clean regression test in Phase 5.

Do not proceed until you have reproduced **and** minimised.

## Phase 3 — Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors; so does a same-mind set. Hard bugs: dispatch 2–3 parallel read-only subagents, each proposing hypotheses without seeing the others', then merge and dedupe. Rank by evidence coverage (how many observed facts each explains) × parsimony (fewer assumed moving parts wins).

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe; discard or sharpen it.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly, or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it. Proceed with your ranking if the user is AFK.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single `rg '\[DEBUG-a4f2\]'`. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, profiler, query plan), then bisect. Measure first, fix second.

## Phase 5 — Fix + regression test

Write the regression test **before the fix**, but only if there is a **correct seam** for it: one where the test exercises the **real bug pattern** as it occurs at the call site. A too-shallow seam (single-caller test when the bug needs multiple callers, a unit test that can't replicate the triggering chain) gives false confidence.

**If no correct seam exists, that itself is the finding.** The architecture is preventing the bug from being locked down. Note it; flag it for the next phase.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

## Phase 6 — Cleanup + post-mortem

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] Existing tests of the touched module(s) still green; full suite if the fix crossed modules (commands cached in `CODEBASE.md`'s `## Verifier commands` zone)
- [ ] All `[DEBUG-...]` instrumentation removed (`rg` the prefix)
- [ ] Throwaway prototypes / repro scripts deleted from `.scratch/tmp/`
- [ ] The hypothesis that turned out correct is stated in the commit / PR message so that the next debugger learns

**Then ask: what would have prevented this bug?** If the answer involves architectural change (no good test seam, tangled callers, hidden coupling) hand off to the `/improve-arch` skill with the specifics. If the root cause was an `rg`-invisible invariant (hidden constraint, surprising coupling), persist it to the area's `CODEBASE.md` block, applying the two-axis test per `/map`, and report; no `CODEBASE.md` yet → note it in the wrap-up instead. Make the recommendation **after** the fix is in, not before. You have more information now than when you started.
