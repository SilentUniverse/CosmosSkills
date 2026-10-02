# ZCode history telemetry adapter

Use this adapter only in an explicit workflow eval. It reads ZCode's local SQLite history and fills
resource metrics for a local session run; normal `/spec` and `/tdd` never run it.

List candidate sessions for one fixture checkout:

```bash
python scripts/zcode_telemetry.py list --directory /absolute/path/to/fixture
```

Select only non-overlapping root sessions. Name each phase and retain the generated JSON below the
session's `artifacts/` for the slot it measures:

```bash
python scripts/zcode_telemetry.py summarize \
  --root-session 'sess_spec=SPEC and verifier readiness' \
  --root-session 'sess_tdd=TDD and final verification' \
  --output .eval-runs/<name>/artifacts/<run-id>-zcode-history-metrics.json
```

The adapter defines active wall time as the sum of root `turn_usage.duration_ms`. Child-session time
is not added again, so parallel subagents do not inflate elapsed work. Child Token and tool usage do
count because they are consumed resources. Gaps between turns are excluded, including overnight
human pauses. Cancelled turns retain their actual recorded duration and cost.

Use the totals to fill the run's resource metrics: `wall_time_ms`, input/output Token, `tool_calls`,
and `retry_count`. ZCode input Token may include cached/context accounting, so record the same
telemetry/runtime scope in every arm and keep the counters diagnostic; they cannot support a
cheaper/more-efficient claim.
