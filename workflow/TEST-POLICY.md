# Test quality, scope and evidence

Cosmos selects and judges checks; host/CI owns execution, scheduling, cancellation and provider retries.

## Select

| Trigger | Required evidence |
|---|---|
| Pure prose, comments or links with no executable consumer | Necessary structure/link checks; no unit suite |
| Machine-consumed template, schema or runner configuration | Targeted producer/parser/consumer contract cases |
| RED/GREEN | The case driving the behavior change |
| Changed shared seam, fixture or integration behavior | Cases covering that changed contract and affected consumers |
| Fixed human-review candidate | Declared scenario integration and artifact checks |
| Fixed delivery candidate | Complete declared delivery gates |
| Stress/platform campaign | Explicit risk, release or cadence trigger |

Select the smallest useful case, class or test file. Batch related edits before widening verification.
A shared file or import alone does not require every consumer suite; name the changed contract or
uncovered risk that requires expansion. Pure prose does not invalidate a passing behavior check
unless the runner consumes it. Task completion and reporting do not add a verification pass.
Issue/task completion, session resume and human approval are not automatic full-suite triggers.
Keep required gates. Changing their triggers must preserve obligations with equivalent protection.
Use project commands/markers. `test-governance.py select --policy FILE --paths-file PATHS.json`
selects groups without running them. Include fixtures/configuration and both sides of renames in
influence mappings. Investigate unknown influence before expanding to the smallest defensible
boundary; preserve the complete fallback when it cannot be bounded. Validate finer selection at
declared complete CI/delivery gates, without duplicating those gates in each local edit loop.
Small projects need no extra policy file. This repository's `scripts/ci-scope.py` compares committed
base..HEAD paths, including cumulative PR changes; local checks use current edited inputs and
project test selectors. Rules may declare `test_paths`; matching paths are unioned into one pytest
selection. Candidates containing only ordinary Markdown paths select catalog; mapped templates/schema
add contract tests. Source comments follow their source path's rule. Unmapped changes and explicit
full verification retain the complete CI fallback. Local proof reuse does not supply a cross-run CI cache.

## Reuse

Read valid evidence before running. Identity comprises check definition/version, argv/logical cwd,
relevant source/input closure, dependency artifacts and result-affecting environment. Session IDs, Issue
numbers, batch IDs and global verification epochs are not validity inputs. AC/check mapping is
many-to-many: one result may prove several cards.

Default reuse requires the same fixed candidate/check and comparable environment. Cross-candidate
reuse additionally proves the entire relevant input closure unchanged; incomplete mappings require
rerun. Unrelated prose edits, a new task boundary or reporting do not invalidate that closure.
Declare all result-affecting inputs; do not narrow the identity merely to obtain reuse.
Check input integrity before/after execution. Concurrent writes or test/build mutations of
inputs invalidate the original candidate claim. Separate outputs from declared inputs.

Import raw native results, tester reports and logs deterministically. Chat summaries are not receipts.
Missing provenance remains unknown. Preserve every distinct attempt and known failure; one later
green cannot hide unresolved contradiction. The evidence gate rejects mixed results under an
unchanged check identity. Diagnose and repair a result-affecting input/environment, then prepare
a new check. If an authorized project flaky policy defines aggregate acceptance, use its actual
runner/aggregation command with the policy and complete attempt set as relevant inputs and retained
outputs. Cosmos imports that aggregate result; it does not implement another retry engine.
The command must match the AC verification contract; revise an open contract when necessary and
reconfirm only material acceptance changes. Never change a nonce/version label, hide receipts or
add an unrelated input merely to evade a conflict. A prose explanation alone cannot clear it.

## Failure and resources

Provider/transport retries belong to the host. Assertion failures are engineering evidence. Timeout
retry must be bounded and diagnostically useful at the narrowest reproducing scope. After code or
environment repair, rerun only the failing cases; no new evidence means no repeated full suite. Update the
existing root cause. Within a feature document, add a unit only for an independent persistent
gap; ordinary work remains inline.

Use native background execution for long checks. Stable inputs require actual isolated checkouts or
equivalent input control. Devices/databases/ports use their fixture/resource-service/CI owner for
exclusion and recovery. Missing guarantees restrict dependent operations, without a Cosmos queue,
global verifier lock or resource registry.

## Measure

Read existing receipts first. Separate command time, setup/copy/cleanup, queue time and model usage.
Summed test wall time is not CPU time or parallel critical path. Compare p50/p95 only with sufficient
samples and matching hardware/runtime/dependency/cache/concurrency context. A timeout is not a
performance baseline; increasing it cannot cure regression. Missing context means unmeasured.

Use native per-case timings when needed. This repository supports
`scripts/run-tests.py --durations-file NEW_FILE`. Sampling needs an explicit measurement purpose;
ordinary work does not repeat suites to populate reports.

```text
python ../test-governance.py report --root ROOT --receipts RECEIPT... --output NEW_REPORT.json
python ../test-governance.py baseline --report REPORT.json --group KEY --statistic p50 --min-samples N --relative-tolerance R --absolute-tolerance-seconds S --output NEW_BASELINE.json
python ../test-governance.py compare --report CANDIDATE.json --baseline BASELINE.json
```

Pin baselines first and preserve source reports. Deduplicate copied receipts, retain real failed
attempts and group comparable environments. Comparison requires valid identity and sufficient passing
samples; choose tolerances from project evidence. Native model usage is not test-performance evidence.

## Quality and retirement

Review changed tests with [tests.md](tdd/tests.md). Quarantine records owner/reason/review boundary
and affected obligations in existing tracking; required coverage still needs executed replacement.
Retire a test only when its behavior/compatibility consumer retires or equivalent coverage preserves
its distinct detection. Age, names, duration and long green history alone do not justify deletion.
Tidy never removes tests as disposable output.
