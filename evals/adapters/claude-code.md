# Claude Code trace adapter

The adapter separates three truths:

1. Claude Code records what it consumed and did (`stream-json`).
2. Product gates / blind judges decide whether requirements passed (`assessment.json`).
3. `eval.py` rejects inconsistent controls, missing proof, or success inferred from self-report.

## 1. Isolate and execute

Run each arm/trial in a disposable clone/worktree at the case's exact `repo_revision`. Load the
exact policy revision for that arm; keep model, effort, allowed tools, settings, network, and seed
fixed. Never compare two arms that ran in the same dirty workspace.

Record the installed CLI version and allowed-tool list in `controls.toolset`. Capture JSONL without
session persistence; use the case budget and an explicit model/effort:

```bash
claude -p --output-format stream-json --verbose --no-session-persistence \
  --model <exact-model> --effort <level> --max-budget-usd <cap> \
  --allowed-tools <fixed-list> '<case prompt>' > artifacts/trace.jsonl
```

The fixture controls permission/network isolation. Do not use a live developer checkout or broad
permission bypass. Retain stderr separately when the command fails.

Single-phase cases produce one trace. L2 planner→cold-executor cases produce separate planner and
executor traces; pass both to `from-claude`, which sums their sequential wall time, tokens, turns,
cost, and visible tool uses. If a host hides nested-agent calls, record that scope in `toolset` and
never compare it with a different trace scope. A terminal `result` is telemetry, not a quality
verdict.

The one-shot command above is for single-turn cases. Alignment cases need a scripted multi-turn
driver that sends the correction/approval events and records the resulting stream; do not fold the
answer into the initial prompt and call that human alignment. `seed` controls fixture/input ordering
when the host has no model-seed option; repeated trials capture residual model variance.

## 2. Grade independently

Run deterministic case graders outside the planner/executor session. Feed an AI grader only the
case request, candidate artifact, versioned rubric, and calibration examples; hide arm, skill
revision, rationale, cost, and self-assessment. Record its measured calibration accuracy and require
the case threshold before accepting a pass. Save every referenced log/trace/screenshot.

Write `assessment.json`:

```json
{
  "verified_success": true,
  "metrics": {
    "time_to_first_dispatchable_ms": 42000,
    "time_to_first_green_ms": 180000,
    "alignment_round_count": 1,
    "clarification_count": 0,
    "ac_repair_count": 0,
    "dependency_repair_count": 0,
    "replan_count": 0,
    "executor_discovered_invariant_count": 0,
    "scope_leakage_count": 0,
    "retry_count": 0
  },
  "grader_results": [
    {
      "id": "product-gate",
      "kind": "deterministic",
      "passed": true,
      "evidence_ids": ["suite"]
    }
  ],
  "evidence": [
    {
      "id": "suite",
      "requirement_ids": ["R1"],
      "verifier": "fixture product gate",
      "command": "pytest tests/test_feature.py -q",
      "exit_code": 0,
      "expected": "all feature scenarios pass",
      "observed": "6 passed",
      "artifacts": ["artifacts/product-gate.log"]
    }
  ]
}
```

Include every grader/evidence required by the case, not just the sample row. Time-to markers may be
`null` when a layer has no such event. `alignment_round_count` counts correction rounds after the
first receipt; `clarification_count` starts only after the issue is dispatchable. Every count is
measured from the trajectory/grader; unknown is an incomplete assessment, never silently `0`.

## 3. Import and compare

```bash
python3 scripts/eval.py from-claude artifacts/planner.jsonl artifacts/executor.jsonl \
  --assessment artifacts/assessment.json --cases evals/cases \
  --run-id <case>-<arm>-<trial> --case-id <case> --arm <arm> \
  --policy-revision <git-rev> --trial <n> --reasoning <effort> \
  --repo-revision <fixture-rev> --environment <image-id> \
  --toolset <claude-version+allowed-tools> --network <off|recorded> --seed <seed> \
  >> results.jsonl
```

Then `validate-runs`, `summarize`, and paired `compare`. Keep the raw trace and assessment beside the
result so a human can replay any claimed win.
