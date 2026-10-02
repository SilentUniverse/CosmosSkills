# DeepSeek Harness session-log telemetry adapter

Use this adapter only in an explicit workflow eval. It reads the harness's own session logs and
fills resource metrics for a local session run; normal `/spec` and `/tdd` never run it.

List candidate sessions for one fixture checkout:

```bash
python scripts/dsh_telemetry.py list --directory /absolute/path/to/fixture
```

Select only non-overlapping root sessions. Name each phase and retain the generated JSON below the
session's `artifacts/` for the slot it measures:

```bash
python scripts/dsh_telemetry.py summarize \
  --root-session 'session-<id>=SPEC and verifier readiness' \
  --root-session 'session-<id>=TDD and final verification' \
  --output .eval-runs/<name>/artifacts/<run-id>-dsh-history-metrics.json
```

The adapter defines active wall time as the sum of root-session `step/start`–`step/end` durations. Gaps
between turns are excluded, including overnight human pauses. Child (subagent) sessions add their
Token and tool cost but never their wall time, so parallel subagents do not inflate elapsed work.

It fills `wall_time_ms`, input/output Token, `tool_calls`, and `retry_count`. Reading the numbers:

- `--sessions-dir` defaults to `$DSH_HOME/sessions` (`~/.dsh/sessions`). Session logs are
  Zstandard-compressed (`session.v4.jsonl.zstd`); the adapter shells out to `zstd -dc` and reports a
  clear error when that executable is missing. A plain `.jsonl` log works offline.
- Harness `usage.inputTokens` counts only the uncached prompt remainder; the adapter reports
  `uncached_input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and their sum.
  Fill the run's `input_tokens` with the uncached remainder and keep the same measure in every arm.
- `tool_calls` counts executed tools: nested programmatic-tool-calling dispatches plus direct tool
  calls. The PTC wrapper (`run_code`) is reported separately as `ptc_wrapper_calls` and excluded from
  the count, because counting it would double one program that carries many dispatches.
- The harness persists no provider-retry counter. `retry_count` is `null`, which means unmeasured;
  it is never silently `0`.
