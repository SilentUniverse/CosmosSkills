# tdd — Full-suite check (§5 detail)

Load only for the automatic batch close or `/tdd --full`. Scoped RED/GREEN cycles do not read it.

## Execution contract

Run each verifier inline through `scripts/test-supervisor.py`; a slow command is not a reason to
delegate. Use one invocation per command so build and test failures remain distinct:

```text
python <tdd-skill-dir>/scripts/test-supervisor.py \
  --receipt .scratch/<feat>/receipts/<owner>-<scope>.json --log .scratch/tmp/<scope>.log \
  --cwd <cwd> --timeout <budget-seconds> --grace 5 --scope <scope> -- <command> <args...>
```

Use `python3` only when `python` is absent. Receipts under `.scratch/<feat>/receipts/` are durable
evidence a completion record can reference; name them `<owner>-<scope>.json` (issue slug for a
single card, feature for batch closes) so batch commands never overwrite an issue's receipt. Logs
stay under `.scratch/tmp/`. Scopes are `preflight`, `targeted`, `module`, `full`, `build`, or
`other`. The receipt records exact
argv, cwd, git state, outcome, exit code, duration, budget-relative duration class, termination,
and log digest. Use the project's known budget; when none exists, choose one explicit budget from
recent local or CI evidence and report that assumption.

The supervisor redirects output before launch. It returns only outcome, scope, exit, duration, log,
and receipt paths to the conversation. On timeout it stops the process group/tree, waits the grace
period, escalates, and exits 124. Launch or signal crashes exit 125. A normal failure preserves its
exit code when possible.

## Reading results

- Green: report command, exit, duration, duration class, and suite tally from the log summary.
- Red: report command, outcome, exit, duration, failing cases, and a trimmed error or tail.
- Timeout: the receipt carries the log tail (last active test or phase). Rerun once at the
  narrowest scope that still shows the hang — for pytest, the single last active node; a second
  timeout routes to `/diagnose`. Never retry unbounded.
- `slow` or `near-timeout`: keep the receipt as evidence and classify the next investigation by
  scope. For pytest, add native `--durations=<N>` on the next bounded run when per-test timing is
  needed; do not make ordinary runs verbose.

Read the full log only when the bounded summary cannot identify the failure. Receipt and log are
evidence; agent prose is not.

## When to run

- Once after the last issue in a drain batch reaches `done`: full suite plus build.
- Immediately for `/tdd --full` or an explicit whole-suite request.
- Never per issue unless that issue's verifier contract requires it.
