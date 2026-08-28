---
name: eval
description: Run opt-in behavior evaluation of agent skills or workflow revisions with isolated paired trials, evidence grading, and regression/Pareto reports. Use only when the user explicitly asks to evaluate, benchmark, compare, or validate the workflow.
disable-model-invocation: true
argument-hint: "smoke|full [scope], export <campaign>, status/report <path>"
---

# Workflow Eval

This is the manual circuit breaker for expensive workflow evaluation. Never invoke it from normal
`/spec`, `/tdd`, review, install, or commit flows. No session means eval is off. The normal artifact
gate and task-local SPEC preflight are not eval; they stay cheap and protect the current task.
Run it from the CosmosSkills source checkout (resolve this installed skill's symlink when needed),
because the case corpus and fixtures are source assets, not copied into ordinary product repos.

Read [`../../evals/README.md`](../../evals/README.md) for a same-project run. When comparing Cosmos
with a native workflow or another project/harness, instead read
[`../../evals/CAMPAIGN-PROTOCOL.md`](../../evals/CAMPAIGN-PROTOCOL.md). For Claude Code traces also
read [`../../evals/adapters/claude-code.md`](../../evals/adapters/claude-code.md).

## Modes

- `/eval smoke <scope>`: one `previous`/`candidate` trial over selected cases. It catches obvious
  breakage but cannot support “better/faster” claims.
- `/eval full <scope>`: three trials by default over `previous`, `candidate`, and blind
  `no-skill`; use 3–5 for an upstream claim. This is the only claimable mode.
- `/eval status <session>`: show the fixed run matrix and missing slots.
- `/eval report <session>`: validate evidence, summarize metrics, and issue the paired verdict.
- `/eval export <campaign>`: freeze a standalone public exam and private judge pack for Cosmos
  versus any external workflow. This is a separate rail, not a replacement for local A/B.

## Open a session

Resolve scope from changed skill(s), the real failure reproducer, or an explicit case. Show selected
case IDs and expected cost before launching agents. Create a local ignored session:

```bash
python3 scripts/eval.py start-session .eval-runs/<name> --cases evals/cases \
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
the session's `artifacts/`; append only valid run records to `results.jsonl`. Deterministic product
gates grade first. AI judges are independent, blind, versioned, and calibrated; humans adjudicate
only irreducible properties. A model's own success message is never a grader.

Use `session-status` between batches. Do not change controls or cases inside an open session; start a
new one instead. Stop on budget exhaustion, unsafe external mutation, or a missing fixture and mark
the slot incomplete rather than inventing a score.

## Decide

```bash
python3 scripts/eval.py session-status .eval-runs/<name>
python3 scripts/eval.py session-report .eval-runs/<name> --output .eval-runs/<name>/report.md
# full only, when making an upstream improvement claim:
python3 scripts/eval.py session-report .eval-runs/<name> --require-improvement \
  --output .eval-runs/<name>/report.md
```

`regression` rejects the candidate. `trade-off` needs the user's explicit choice. `tied` means no
verified improvement. Only `quality-improved`, `efficiency-improved`, or `pareto-improved` from a
claimable full session supports “better.” Put the retained report summary/evidence link in the
upstream change; raw sessions remain local and ignored by default. After merge/update, turn every
real failure into a permanent regression case. Eval closes simply by leaving this skill:
there is no global hook or active flag to slow later development.

## Cross-project campaign

Keep the two rails separate. Use session commands for previous/candidate revisions of this project.
Use `scripts/eval_campaign.py` when an arm runs in another harness or project. Require a materialized
fresh fixture for every claimable case. Choose `policy-only` only when all harness controls can be
paired; otherwise label the result `whole-system`.

```bash
python3 scripts/eval_campaign.py export .eval-campaigns/<name> --cases evals/cases \
  --profile full --comparison <policy-only|whole-system> --case <id> \
  --fixture <id>=<prepared-fixture>
```

Send only `public/`; keep `judge/` and `campaign.lock.json` private. Each participant uses the
exported `public/campaign.py` to verify, initialize, and seal one opaque-arm submission. Participants
record observations and evidence but never self-assign `verified_success`. After blind independent
assessment through an arm-anonymous `prepare-judging` packet, use `judge`, then `report` over two or
more judged JSONL files. Reveal arm labels only in the final report. Preserve unavailable metrics as
`null`; `insufficient-data` blocks an improvement claim rather than treating unknown as zero.
