---
name: eval
description: >-
  Use only when the user explicitly requests model-run evaluation or benchmarking of agent skills or workflow revisions. Runs isolated paired trials, grades retained evidence, and produces regression and Pareto reports; ordinary audits and deterministic checks do not authorize trials.
disable-model-invocation: true
argument-hint: "smoke|full [scope], status/report <path>"
---

# Workflow Eval

Explicit evaluation requests enable model trials; ordinary development, review, installation, and
commits do not. Deterministic artifact gates and task-local preflights remain ordinary validation.
Run it from the CosmosSkills source checkout (resolve this installed skill's symlink when needed),
because the case corpus and fixtures are source assets, not copied into ordinary product repos.

Read [`../../evals/README.md`](../../evals/README.md) for a same-project run. For Claude Code traces also
read [`../../evals/adapters/claude-code.md`](../../evals/adapters/claude-code.md); for ZCode history
duration and cost read [`../../evals/adapters/zcode.md`](../../evals/adapters/zcode.md); for DeepSeek
Harness session logs read [`../../evals/adapters/dsh.md`](../../evals/adapters/dsh.md).

## Modes

- `/eval smoke <scope>`: one `previous`/`candidate` trial over selected cases. It catches obvious
  breakage but cannot support “better/faster” claims.
- `/eval full <scope>`: three trials by default over `previous`, `candidate`, and blind
  `no-skill`; use 3–5 for an upstream claim. This is the only claimable mode.
- `/eval status <session>`: show the fixed run matrix and missing slots.
- `/eval report <session>`: validate evidence, summarize metrics, and issue the paired verdict.

## Open a session

Resolve scope from changed skill(s), the real failure reproducer, or an explicit case. Show selected
case IDs and expected cost before launching agents. Reuse the approved mode/budget; ask only for
unsettled material cost or scope. Create a local ignored session. Run `python`; on Unix without a
`python` alias use `python3`, and on Windows `python3` is a Store alias that fails:

```bash
python scripts/eval.py start-session .eval-runs/<name> --cases evals/cases \
  --profile <smoke|full> --skill <name> [--case <id>]
```

For smoke, pass one real reproducer and optionally one routing case; the CLI refuses an accidentally
broad smoke scope. Full may select the whole tagged corpus. The command prints the worst-case budget,
freezes the matrix, and launches nothing. Use disposable clone/worktree fixtures
for every slot. Fix model, reasoning, repo revision, environment, toolset, network, seed, and budget.
Never run trials in the developer's live dirty checkout. A cold executor sees only the planned card,
not the planner conversation or arm identity.

## Execute and grade

Run each `case / arm / trial` slot from `session.json`. Store raw traces and grader artifacts below
the session's `artifacts/`, then record the run through the validator rather than editing
`results.jsonl` by hand:

```bash
python scripts/eval.py record-run .eval-runs/<name> --run <run.json>
```

It rejects a record that fails the schema, repeats an already-recorded slot, targets a slot the
session does not expect, or duplicates a `run_id`, and appends one canonical JSON line; `--dry-run`
validates without writing. Deterministic product gates grade first. AI judges are independent, blind,
versioned, and calibrated; humans adjudicate only irreducible properties. A model's own success
message is never a grader.

Use `session-status` between batches. Do not change controls or cases inside an open session; start a
new one instead. Stop runs on budget exhaustion or unsafe external mutation. A missing fixture or
executor blocks only its slots; continue independent slots within budget and deterministic reporting.
Never substitute inline self-grading for a blind executor/judge or score an unrun slot.

## Decide

```bash
python scripts/eval.py session-status .eval-runs/<name>
python scripts/eval.py session-report .eval-runs/<name> --output .eval-runs/<name>/report.md
# full only, when making an upstream improvement claim:
python scripts/eval.py session-report .eval-runs/<name> --require-improvement \
  --output .eval-runs/<name>/report.md
```

`regression` rejects the candidate. Resolve `trade-off` against explicit user priorities; ask if
unsettled. `tied` means no verified improvement. Only `pareto-improved` (or `quality-improved` /
`efficiency-improved`) from a claimable full session supports an improvement claim; provider-specific
Token/tool counters stay diagnostic and cannot support a cheaper/more-efficient claim. Put the
retained report summary/evidence link in the upstream change; raw sessions remain local and ignored
by default. Retain real failures as permanent regression cases. Leaving this skill closes eval; it
creates no global hook or active flag.
