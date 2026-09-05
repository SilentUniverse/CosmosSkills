# Writing skills — behavior eval

Loaded only after the user authorizes behavior evaluation for a skill edit that changes trigger, routing,
a decision, step order, tool use, or output contract. Without an eval session, run deterministic L0
checks but label behavior/performance unverified. Spelling/link/layout-only edits need no behavior
session. Structural review is not evidence that agent behavior improved.

Use skill TDD:

1. **Case from reality.** Turn the observed failure into the smallest case with prompt, repo
   snapshot, expected observable result, and budget. Preserve the exact rationalization/trajectory
   that escaped the previous policy revision; do not rewrite it into an easier synthetic exercise.
2. **RED.** Run the previous policy (and no-skill/upstream arm when useful) under identical model,
   reasoning, repo, tools, network, seed, and budget. The case must reproduce at least once. If it
   does not, investigate within the agreed eval budget and report it as unreproduced if needed;
   never manufacture a failure or claim a verified behavior fix.
3. **GREEN.** Make the smallest skill change that closes the reproduced loophole. Run 3–5 paired
   trials. The executor/judge must not see the arm or the skill author's rationale.
4. **Pressure.** Exercise interacting pressures supported by the failure (time, ambiguity,
   sunk cost, authority, missing context), without padding to a fixed count. Capture any new rationalization verbatim and tighten only
   that loophole; do not pile on generic warnings.
5. **REFACTOR.** After a meaningful revision, run L0, the reproducer, and regressions tagged to
   the changed entry. Shared routing/planning changes also run their routing smoke set. Broaden to
   the corpus when required by the agreed eval scope or cross-skill impact. Keep deterministic constraints in scripts/types/CI; keep judgment and routing
   in the skill. Delete prose a machine gate now owns.

Record each run with the repository's `scripts/eval.py` JSONL contract (installed copy may live at
`~/.claude/skills/eval.py`). Compare `previous`, `candidate`, and `no-skill`/`upstream`:

```bash
python3 scripts/eval.py validate-runs results.jsonl --cases evals/cases
python3 scripts/eval.py compare results.jsonl --cases evals/cases \
  --baseline previous --candidate candidate --require-improvement
```

When `upstream` must run in another project or harness, do not fake it as a paired local arm. Export
the standalone public packet with `scripts/eval_campaign.py` and follow
[`../../evals/CAMPAIGN-PROTOCOL.md`](../../evals/CAMPAIGN-PROTOCOL.md); retain this local contract for
previous/candidate revisions of the current project.

Automatic acceptance requires `quality-improved` / `efficiency-improved` / `pareto-improved` and no
losing case. A `trade-off` needs an explicit human decision and cannot be reported as “better”; a
tie is “not improved.” A semantic AI judge is allowed only with a blind, versioned rubric
and human-labeled calibration set whose measured accuracy clears the case threshold; runnable tests
and traces remain ground truth. Every production failure that a skill should have prevented becomes
a permanent regression case.

**No reproducer = no verified behavior fix. No real run = no performance claim.**
