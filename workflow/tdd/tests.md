# Test quality review

Load when writing or changing tests. Review the changed tests and affected fixtures within the
existing code review, using the accepted behavior as the oracle.

## Existing evidence

Use project configuration and `CODEBASE.md` verifier commands to locate existing coverage. For a
parallel wave, use the supplied tests-so-far manifest before scanning. An AC already covered needs
verification, not a duplicate test. Test paths, AC mappings and native runner metadata are the
registry; do not create a parallel per-case ledger.

## Acceptance criteria for tests

| Dimension | Required judgment |
|---|---|
| Detection | The actual defect or missing behavior makes the test fail; preserve RED or a relevant negative control |
| Contract | Assertions follow observable behavior or a stable interface, and survive irrelevant refactors |
| Oracle | Expected results come from the requirement, a worked example or another independent source |
| Isolation | Fixtures own mutable state; order, shared files, wall clocks, sleeps and network access are deliberate and controlled |
| Contribution | Each new case or layer protects a distinct failure mode, boundary or compatibility obligation |
| Cost | Use the least expensive seam that detects that failure; real IO/process integration remains where that boundary matters |
| Diagnosis | A failure identifies the violated behavior and useful inputs without dumping unrelated state |

Choose representative cases for contract boundaries and meaningful input partitions. Do not force
one assertion per test when several observations establish one invariant. Source/string/snapshot
assertions are appropriate when those bytes are the published contract, such as a schema or generated
artifact; they cannot substitute for behavior reached through that source.

Use direct module calls for domain behavior when that interface is the contract. Retain real CLI,
service, filesystem, process and packaging tests for their distinct boundary failures. A local
predicate does not require a new subprocess per example. Broad integration wrappers around every
unit case make fixture/startup cost grow without necessarily improving detection.

Mocks may isolate external dependencies at an explicit seam. Do not mock the behavior being proved
or assert internal call order unless that order is itself the accepted contract. A storage invariant
can require observing the real database; a retrieval API alone may not prove its transaction behavior.

When two tests look similar, identify what each can uniquely falsify before merging them. Parameterize
true repetitions; keep separate layer/edge cases when they cover different risks. Record only concrete
review findings in the existing completion/review record. A clean review needs no extra prose.

For trigger, cost, cache and retirement decisions, use the shared
[test policy](../TEST-POLICY.md). Test removal is normal engineering work; temporary-file GC never
removes regression tests or changes verification obligations.
