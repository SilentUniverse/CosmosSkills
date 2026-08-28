# Spec receipt semantic rubric — v1

Judge only the original user request and the final Design Receipt. Do not receive the arm name,
skill revision, planner rationale, planned file contents, or self-score.

Return JSON:

```json
{
  "pass": true,
  "criteria": {
    "goal_fidelity": {"pass": true, "evidence": "..."},
    "boundary_falsifiability": {"pass": true, "evidence": "..."},
    "seam_and_flow": {"pass": true, "evidence": "..."},
    "verification_observability": {"pass": true, "evidence": "..."},
    "execution_readiness": {"pass": true, "evidence": "..."},
    "slice_traceability": {"pass": true, "evidence": "..."}
  }
}
```

All six criteria must pass:

1. **Goal fidelity** — role, trigger, observable behavior, motivation, and the user's important
   examples survive without adding a different goal.
2. **Boundary falsifiability** — invariants/non-goals and at least one nearest counterexample make
   a wrong interpretation easy to identify; one-way doors are named when present.
3. **Seam and flow** — the receipt names the external/public entry and gives a coherent end-to-end
   flow. A new seam is justified rather than assumed.
4. **Verification observability** — every requirement has an agent-runnable action, expected
   observation, and replayable evidence. Self-report, a screenshot standing in for behavior, or a
   static checker standing in for runtime behavior fails.
5. **Execution readiness** — every requirement references a passed P# with cwd, prerequisites,
   completed durable setup, actual representative action/result/evidence/date, and an environment
   fingerprint. A merely proposed command or deferred install fails.
6. **Slice traceability** — every requirement maps to a vertical slice and evidence; every slice
   produces independently observable behavior, has real blockers only, and fits one fresh context.

Quote the shortest receipt fragment supporting each verdict. Do not reward verbosity or headings;
semantic omission fails even when the template shape is present.
