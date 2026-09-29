# DeepSeek Harness session-log telemetry adapter

Use this adapter only in an explicit workflow eval. It reads the harness's own session logs and
fills resource metrics before a campaign submission is sealed; normal `/spec` and `/tdd` never run it.

List candidate sessions for one fixture checkout:

```bash
python scripts/dsh_telemetry.py list --directory /absolute/path/to/fixture
```

Select only non-overlapping root sessions. Name each phase and retain the generated JSON with the
submission:

```bash
python scripts/dsh_telemetry.py summarize \
  --root-session 'session-<id>=SPEC and verifier readiness' \
  --root-session 'session-<id>=TDD and final verification' \
  --output /absolute/path/to/submission/artifacts/process/dsh-history-metrics.json \
  --observation /absolute/path/to/submission/observations.jsonl \
  --run-id <case-id>-<trial>
```

The adapter defines active wall time as the sum of root-session `step/start`–`step/end` durations. Gaps
between turns are excluded, including overnight human pauses. Child (subagent) sessions add their
Token and tool cost but never their wall time, so parallel subagents do not inflate elapsed work.

The adapter fills `wall_time_ms`, input/output Token, tool calls and retry count. Its wall time is
harness step duration, not an external-runner stopwatch, so it is eligible for policy-only
comparison under the same harness scope but not for a whole-system speed verdict. Whole-system arms
must retain the adapter output as diagnostics and put externally measured elapsed time in the
observation with `controls.wall_time_scope=external-runner-elapsed`.

Reading the numbers:

- `--sessions-dir` defaults to `$DSH_HOME/sessions` (`~/.dsh/sessions`). Session logs are
  Zstandard-compressed (`session.v4.jsonl.zstd`); the adapter shells out to `zstd -dc` and reports a
  clear error when that executable is missing. A plain `.jsonl` log works offline.
- Harness `usage.inputTokens` counts only the uncached prompt remainder; the adapter reports
  `uncached_input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and their sum. The
  observation's `input_tokens` is the uncached remainder, the same measure the ZCode adapter writes,
  so the two stay comparable only under the same telemetry scope.
- `tool_calls` counts executed tools: nested programmatic-tool-calling dispatches plus direct tool
  calls. The PTC wrapper (`run_code`) is reported separately as `ptc_wrapper_calls` and excluded from
  the count, because counting it would double one program that carries many dispatches.
- The harness persists no provider-retry counter. `retry_count` is `null`, which means unmeasured;
  it is never silently `0`.
- The script refuses to mutate a submission after `seal.json` exists.
