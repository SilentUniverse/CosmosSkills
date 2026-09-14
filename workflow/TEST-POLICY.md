# Test quality, scope and cost

Load when choosing verification scope, reviewing changed tests, or investigating growing test cost.
Spec owns the evidence and trigger contract; TDD owns execution and test maintenance; TIDY reports
cost concerns and cleans disposable outputs. These are rules for the existing workflow entries.

## Scope and ownership

| Boundary | Required evidence |
|---|---|
| Local behavior loop | New or directly affected cases |
| Issue completion or module refactor | Module and affected consumers |
| Human review candidate | Declared scene integration and actual artifact checks |
| Final delivery | Complete applicable delivery gates on that candidate |
| Stress, longevity or platform campaign | Its declared risk/release/cadence trigger |

Retain existing required gates. Moving one to a later trigger requires an explicit contract change
that identifies affected obligations and equivalent protection. A disabled or quarantined required
gate is incomplete unless its accepted replacement ran. No count or speed target permits weaker ACs.

Use native project commands, markers and selection facilities. A small project needs no new policy
file. For declared group selection, `test-governance.py select --policy FILE --paths-file PATHS.json`
returns selected groups and reasons without launching commands. Unknown or empty change sets select
all declared groups; renames include both paths. Group mappings describe influence, including shared
fixtures/configuration, rather than merely matching test filenames. Full requests bypass selection.
When influence is uncertain, expand the scope. Compare selected results with independent complete
checks before trusting more precise mappings. Record missed failures; selection confidence is not
established by green selected tests alone.

The parent owns shared module/final runs. Workers execute their scoped diagnostics. Coalesce pending
requests for the same immutable check, inspect the admitted run instead of launching it again, and
reuse passing proof only under the accepted validity contract. Final tests follow completed review
fixes; relevant changes afterward invalidate affected proof. Resource and memory limits bound workers
and native runner threads together. A slow test does not justify another model supervisor.

## Reuse and admission

Managed batch admission provides the run sharing and cache rules below. Ordinary supervisor calls
do not deduplicate commands; the parent coordinates their shared checks.

Schema-3 jobs may opt into `reuse: true` only for isolated checks without external state, real-time or
random-dependent results. UI, resource and application lifecycle jobs cannot use this cache.
`reuse_environment: {"paths": [...], "external_state": "none"}` explicitly declares the complete
materialized runtime/dependency closure. Paths may be absolute or relative to the repository.
The runtime hashes the actual command executable and all declared dependency files/directories,
including resolved symlink targets; it does not substitute a lockfile for installed package bytes.
`reuse_inputs` optionally binds additional regular repository files. Source/config/lock/test inputs
still belong in the frozen candidate. Omit reuse when network, clock, randomness, undeclared package
loads or other mutable influences prevent a closed environment. This is a caller contract, not an
automatic proof of hermeticity. No closure, unresolved tool, missing input or directory cycle means
no completed reuse. Hashing a large closure has a cost: opt in only when that cost is justified by
saved runs. Ordinary checks do not scan dependency trees or probe/install browser tooling.

Cache identity includes check name, candidate, job, verification epoch, artifact inputs, member requirement/
proof/decision bindings, process environment, executable bytes and the declared materialized dependency closure. Failed evidence never
enters the cache. Running identical immutable requests share a run ID; the returned `shared: true`
means observe that run. Aliases do not reserve another budget. Different checks cannot be admitted
while a verifier remains nonterminal. Mutable development checks do not coalesce by source guess.
Managed execution has one active verifier per workspace; it does not create a second pending-job queue.
Status readers and owned verifier state transactions retry brief lock contention within 40 attempts
at 25 ms intervals. Other state writers fail fast; a timeout never grants lock takeover or reruns a command.

## Performance and budget

Keep performance baselines separate from safety timeouts and the original goal's cumulative budget.
Timeouts bound commands and stop owned process trees. Goal reservations include retries and lifecycle
stages and are never refunded by reopening a run. Compare measured whole-job cost separately: copy,
setup, cleanup and queueing can exceed command execution time and must remain visible.

Supervisor receipts optionally retain `measurement_context`, identifying hardware/runtime,
dependency identity, warm/cold caches and concurrency. No context means no comparable performance
baseline. The legacy `duration_class` describes timeout pressure only; `normal` does not establish
performance health. `performance.status` is `unmeasured` without a baseline and is independent of
`--timeout`. A single over-limit observation requests investigation, not a confirmed regression.

Read existing command receipts first; enable native per-case timing only to localize cost. The
repository's `scripts/run-tests.py --durations-file NEW_FILE` retains unittest timings without
changing case selection or retrying failures. Other projects keep their native runner reporter.
Do not count skipped tests as passed or use test count/coverage percentage as a quality target.

`test-governance.py` supports these read/measurement operations:

```text
python <skills-root>/test-governance.py report --root ROOT --receipts RECEIPT... --output NEW_REPORT.json
python <skills-root>/test-governance.py report --root ROOT --batch ID
python <skills-root>/test-governance.py baseline --report REPORT.json --group KEY --statistic p50 --min-samples N --relative-tolerance R --absolute-tolerance-seconds S --output NEW_BASELINE.json
python <skills-root>/test-governance.py compare --report CANDIDATE.json --baseline BASELINE.json
```

Choose samples and tolerances from the project's evidence; no universal millisecond bar applies.
Pin the baseline before evaluating the candidate, preserve its report, and do not roll a regression
into a refreshed baseline. Baseline/report outputs refuse overwrite. Comparison requires the same
command/environment/context and enough passing samples: exit 0 within target, 1 observed regression,
2 invalid/incomplete. The tolerance is the larger of the declared relative and absolute allowances.
Measurement sampling is explicit work; ordinary implementation does not manufacture repeated runs.

Supervisor `--performance-baseline FILE --measurement-context CONTEXT` adds a comparable single-run
observation to its receipt and compact output. Its exit still represents the functional result;
use the explicit repeated-sample comparison as a required gate for an accepted performance AC.

Reports deduplicate copies of the same receipt, keep all real failed attempts, and separate summed
job wall time from queue time. The sum is neither CPU time nor a parallel critical path. Repeated
same-candidate runs and mixed outcomes identify investigation candidates; dirty legacy status alone
cannot identify a fixed source. Missing timing or identity remains unknown. Default output is bounded;
full rows and provenance go to the named report. TIDY reads retained evidence and does not rerun tests.

## Quality, instability and retirement

Review changed tests using [tests.md](tdd/tests.md). Review is part of the existing Standards/Spec
passes, not a new agent per case. High-risk concurrency, state and evidence boundaries receive their
normal adversarial review. Judge new tests and affected shared fixtures; do not rescan all history.

A failing attempt remains failed. Diagnostic retries preserve the first failure. An instability
quarantine records owner, repair issue, reason, review deadline and affected obligations in existing
project tracking; isolation alone grants no acceptance. An expired quarantine is visible unfinished
work. Required coverage needs an executed replacement or stays blocked.

A test may retire when its behavior and compatibility consumers retire, or a cheaper test preserves
its distinct failure detection. Long absence of failures, age, names and runtime alone are not
retirement evidence. Test deletion/deduplication is an engineering change with verification; TIDY GC
cannot perform it. Retain useful regression scenarios and the portable history of delivered versions.
