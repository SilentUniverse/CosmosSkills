# Fixed-candidate verification

Load for declared delivery/integration gates or explicit `/tdd -all`; ordinary RED/GREEN stays scoped.

## Fix inputs

Choose an immutable Git commit/tree with a retained ref, or an equivalent verifiable manifest.
Include required dirty/untracked source first. Declare external inputs, dependency artifacts and
environment separately; HEAD does not cover them. Check native checkpoint coverage before reuse.

Materialize an independent checkout or equivalent isolated input. Separate build outputs from
inputs; hash relevant inputs before/after execution. Tests/builds rewriting declared inputs invalidate
the original candidate claim. Make inputs read-only where possible. Shared changing workspace bytes
cannot prove a fixed candidate.

## Execute and import

Use project runners through native command tools or CI with supported cwd, timeout and retained
output. Long commands use native background/output/cancellation tools. Check actual timeout,
descendant cleanup and retention semantics; native entrypoints can differ.

Cosmos deterministically imports raw native results, tester reports and logs; it does not launch
or supervise tests. Retain argv/logical cwd, check definition/version, input/candidate identities,
exit, outcome, timing and log digest. Use project redaction, never credentials in argv or evidence.
Agent prose cannot manufacture a passing receipt.

The normal ZCode path is an ordinary session plus native Bash. Dynamic Workflow requires its own
concrete need; `world.run` does not offer the same cwd/cancel/output contract. Use no unsupported options.

## Judge

Apply [TEST-POLICY.md](../TEST-POLICY.md). Reuse only matching input/check/environment evidence.
Keep all attempts; a later green cannot erase unexplained failure. The evidence gate rejects
mixed results for an unchanged check. Resolve through a real input/environment repair or an
applicable project-owned aggregation policy as described in TEST-POLICY; prose is not an override.

- Pass: retain native result, tally and proof mapping.
- Fail: retain command/exit, failing cases and decisive excerpt; diagnose.
- Timeout: preserve the active phase; retry only with diagnostic value at a bounded, narrower scope.
- Unknown/cancelled/incomplete: cannot prove completion.

Final delivery needs its declared complete gates. Issue completion, session recovery and human
approval are not full-suite triggers. Tests reserved by the user remain explicitly unexecuted.

## Evidence CLI

Use the installed skills root or source `workflow/` directory. `ROOT` is the isolated candidate
checkout and evidence root; referenced files stay within it. Git/project tooling materializes the
checkout. An existing accepted Spec can be bound with `--spec`; omit it for preflight, settled
inline work or a standalone Issue without a Parent. No approval is invented for that case. A
Parent-bound Issue still requires its candidate's matching accepted Spec before completion.

```text
python evidence.py candidate ROOT --ref REF [--spec SPEC_PATH] [--input REPO_REL_FILE] --out CANDIDATE
python evidence.py prepare ROOT --candidate CANDIDATE --definition CHECK_JSON --out CONTEXT
python evidence.py reuse ROOT --context CONTEXT --receipt RECEIPT
python evidence.py seal ROOT --context CONTEXT --out RECEIPT --duration OBSERVED_SECONDS
python evidence.py review ROOT --candidate CANDIDATE --receipt RECEIPT --artifact REPO_REL_FILE --scope TEXT --out REVIEW_JSON
python evidence.py validate ROOT RECORD
```

`--ref` accepts a Git commit or tree; `--commit` is a compatibility alias. For uncommitted work,
prepare the tree through a temporary index so the user's staged state stays untouched: with one
`GIT_INDEX_FILE=$(mktemp)` export, run `git read-tree HEAD`, `git add -- <intended paths>`, then
`git write-tree`. Inspect what the tree contains; do not stage unrelated work. The evidence helper
retains the object via a Git ref without creating a commit or checking out files.

`--input`, `--receipt` and `--artifact` repeat where applicable; optional inputs/artifacts can be
omitted. `--duration` is optional and must be measured. Check definition JSON has `argv` array,
repository-relative `cwd`, nonempty `environment` identity object and `scope`. Optional `inputs`
declares the complete relevant source closure; omission checks all source. Optional `outputs`
declares generated files or directories; sealing preserves their file hashes and bytes. Outputs cannot
overlap fixed source or the candidate/context/receipt records. Failed checks can retain incomplete
outputs; a passing check needs every declared output. Review artifacts must match these outputs or
the selected check's fixed inputs, so a later workspace replacement cannot inherit old proof.

When a receipt closes an Issue, `environment.contract` must match the verifier's declared
`fingerprint` (excluding `git`), `prerequisites`, and `prepare`. Record actual runtime/dependency
identities alongside this contract, without Issue or session IDs in the check key. For example:

```json
{
  "argv": ["python", "-m", "pytest", "tests/test_example.py"],
  "cwd": ".",
  "scope": "targeted",
  "environment": {
    "runtime": "Python 3.12.9",
    "contract": {
      "fingerprint": {"lock": "requirements.lock@sha256:…", "runtime": "Python 3.12", "tools": "pytest", "services": "none"},
      "prerequisites": {"fixtures": "local", "services": "none", "permissions": "workspace", "network": "none"},
      "prepare": "无（已就绪）"
    }
  }
}
```

Retain the candidate's Git ref, JSON records, copied inputs/artifacts, contexts, and sealed
log/exit files together. Raw native output can be removed after sealing; its retained copy cannot.

`prepare` records the fixed input identities and returns a native shell command; it runs no test. Query existing proof
with `reuse` first. It reports `hit` (reusable passing proof), `miss` (nothing applicable), `known-failure`
(an intact failed attempt already exists for this exact identity; diagnose it, do not rerun unchanged) or
`conflict` (mixed outcomes; see TEST-POLICY). When new execution is needed, run the returned command
through the host to create its raw `.log` and `.exit`, then `seal`. Use a new location per attempt.
`review` creates the fixed review object, not approval. The human bridge is
`spec-review.py review-candidate ROOT REVIEW_JSON`; no CLI generates an approve event. The bridge
serves exactly one decision and blocks its caller until then or `--timeout` (default 900 s); run it
through a host background task to continue unrelated work meanwhile.
