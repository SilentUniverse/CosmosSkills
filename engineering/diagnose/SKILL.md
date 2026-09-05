---
name: diagnose
description: Disciplined diagnosis loop for hard bugs and performance regressions. Build a feedback loop → reproduce → minimise → hypothesise → instrument → fix → regression-test. Use when user says "diagnose this" / "debug this", reports a bug, says something is broken/throwing/failing, or describes a performance regression.
---

# Diagnose

Reuse existing repros and combine phases when the cause is clear. Fix requests run through verified repair; diagnosis-only ends with findings.

## Phase 1 — Build a feedback loop

Build a pass/fail signal for the user's exact symptom. Inspect relevant code, logs, configuration,
and existing tests to locate the trigger; treat explanations as hypotheses until evidence tests them.

Use the cheapest loop that distinguishes the bug from correct behavior; refine it only as needed.

Loop construction, tightening, flaky bugs, and missing-environment fallback: **[FEEDBACK-LOOPS.md](FEEDBACK-LOOPS.md)**.

### Completion criterion — a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: you can name **one command**, a script path, a test invocation, a curl, that you have **already run at least once** (paste the invocation and its output), and that is:

- [ ] **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring". It must be able to _catch this specific bug_.
- [ ] **Deterministic** — same verdict every run (flaky bugs: a pinned, high reproduction rate).
- [ ] **Fast** — seconds, not minutes. (Slow-but-justified: proceed, note the cost.)
- [ ] **Agent-runnable** — you can run it unattended; a human in the loop only via the HITL template.

If the loop cannot run, record the missing capability and continue source/trace analysis and local
repro preparation. Request only the access or artifact still needed; do not claim a verified cause.

## Phase 2 — Reproduce + minimise

Confirm:

- [ ] The loop produces the failure mode the **user** described, not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, remove unrelated inputs and steps while preserving the user's failure. Stop shrinking
when the repro isolates the cause well enough to test a fix; keep the original scenario for validation.

Reproduced evidence is required for a verified fix; exact minimality is not a gate.

## Phase 3 — Hypothesise

Start with the best evidence-backed hypothesis and a disconfirming probe; add alternatives for
ambiguous evidence or failed probes. Rank by evidence coverage and parsimony. Bounded independent
subagents may help hard bugs when available; otherwise compare inline.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe; discard or sharpen it.

Briefly state the leading hypothesis and next probe, then test it without a confirmation gate.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single `rg '\[DEBUG-a4f2\]'`. Untagged logs survive; tagged logs die.

**Perf branch.** Establish a measured baseline with a timing harness, profiler, or query plan; bisect only when history helps isolate the regression. Measure first, fix second.

## Phase 5 — Fix + regression test

Write the regression test **before the fix**, but only if there is a **correct seam** for it: one where the test exercises the **real bug pattern** as it occurs at the call site. A too-shallow seam (single-caller test when the bug needs multiple callers, a unit test that can't replicate the triggering chain) gives false confidence.

**If no correct test seam exists**, keep the executable repro as evidence, apply the confirmed fix, and report the regression-test gap. Do not stop the repair merely to redesign the architecture.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

## Phase 6 — Cleanup + post-mortem

Required before declaring done:

- [ ] Original repro passes after the fix; reuse the Phase 5 run if code/environment are unchanged
- [ ] Regression test passes (or absence of seam is documented)
- [ ] Relevant module and integration checks pass; broaden for affected contracts or unresolved risk, not file count (`CODEBASE.md`'s `## Verifier commands` caches commands)
- [ ] All `[DEBUG-...]` instrumentation removed (`rg` the prefix)
- [ ] Remove temporary artifacts created by this task once their regression evidence is retained
- [ ] State the cause, fix, and verification in the result; include them in a commit/PR only if submission is requested

Pursue prevention only within scope. Record an `rg`-invisible invariant in an existing `CODEBASE.md`
block using `/map`'s two-axis test; otherwise mention it in the result. Continue authorized work.
