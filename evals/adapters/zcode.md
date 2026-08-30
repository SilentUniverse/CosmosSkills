# ZCode history telemetry adapter

Use this adapter only in an explicit workflow eval. It reads ZCode's local SQLite history and fills
resource metrics before a campaign submission is sealed; normal `/spec` and `/tdd` never run it.

List candidate sessions for one fixture checkout:

```bash
python3 scripts/zcode_telemetry.py list --directory /absolute/path/to/fixture
```

Select only non-overlapping root sessions. Name each phase and retain the generated JSON with the
submission:

```bash
python3 scripts/zcode_telemetry.py summarize \
  --root-session 'sess_spec=SPEC and verifier readiness' \
  --root-session 'sess_tdd=TDD and final verification' \
  --output /absolute/path/to/submission/artifacts/process/zcode-history-metrics.json \
  --observation /absolute/path/to/submission/observations.jsonl \
  --run-id <case-id>-<trial>
```

The adapter defines active wall time as the sum of root `turn_usage.duration_ms`. Child-session time
is not added again, so parallel subagents do not inflate elapsed work. Child Token and tool usage do
count because they are consumed resources. Gaps between turns are excluded, including overnight
human pauses. Cancelled turns retain their actual recorded duration and cost.

The adapter fills `wall_time_ms`, input/output Token, tool calls, and retry count. ZCode input Token
may include cached/context accounting, so compare it only under the same telemetry/runtime scope.
The script refuses to mutate a submission after `seal.json` exists.
