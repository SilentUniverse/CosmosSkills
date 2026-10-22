# Impact Detection — 影响面探测（按需读）

When a change touches **existing** code, the risk isn't slicing. It's what this change reaches and
might break. This is the per-language playbook for that.

Load only when `/spec` §3 finds many references, several modules or an invariant area; a new or
small-radius change stays inline.

## The one principle

**Deterministic tools first, subagent reading last.** The stronger the type system, the more static
analysis covers; the weaker it is, the more you lean on **runtime** observation (coverage / test
selectors — what actually ran). Either way a subagent only fills what those tools miss: greppable-invisible assumptions.
It never replaces them. TypeScript is near-whitebox: the checker
resolves which `save()` you mean. Python is dynamic: `getattr`, `**kwargs`, DI, registries, and
fixtures make callers invisible to static tools, so static results are a lower bound.

**Planning uses read-only impact analysis.** Use reference queries, import graphs, existing type
information and retained runtime evidence. Declare missing runtime checks in the verification plan; do not run
future behavior suites or temporarily edit product source to discover callers.

**Differential mutation probes are optional execution work.** Use them only when a concrete
uncertainty warrants the cost, within existing execution authorization and a task-owned isolated
copy. Include the actual candidate and relevant configuration, including required dirty/untracked
inputs; HEAD alone need not represent it. Never mutate the real/shared source checkout.
Capture the baseline and mutated candidate in the same copy, using the same working directory,
checker command and version. Only new diagnostics are typed impact candidates; pre-existing
diagnostics, a non-zero baseline exit and line-only movement are not mutation impact. Keep probe
edits out of the deliverable candidate; they do not prove behavior.

Two kinds of impact, very different confidence:

- **Static reachability** — who imports/calls this, what breaks if the signature changes.
  Machine-determinable. Query it, don't let the agent guess.
- **Semantic / behavioural coupling** — "refund makes the amount negative, but reconciliation
  *assumes* amount ≥ 0." No import edge, ungreppable. Only reading + reasoning finds it. This is
  exactly what `CODEBASE.md`'s **invariants** are for. Persist them so the next run reuses them.

## What gets reused on the second run

- **Static reference points** — NOT stored. Re-grep each time; it is cheap and always current.
- **Semantic invariants (the expensive part)** — persist to the area's surviving map surface
  (root 不变量 line, or a legacy area block) so the next coupled change in this area skips
  re-deriving it; but only if the run writes its findings back. Write it; don't pause to offer.

The concrete per-language commands live in the project's
`CODEBASE.md` `## Verifier commands` zone (see "Where the commands live" below), never in a
skill. For browser/Electron work, static reachability is not runtime integrity — the CSP and
resource-ownership checks live in [tdd's UI verification](../tdd/UI-TESTING.md).

---

## Python — static under-reports; add runtime

Planning inspects typed/structural references and retained runtime coverage without changing source.
For a necessary execution-stage differential probe, use the helper from the loaded `spec` skill
in the task-owned isolated copy so Pyright's ordinary non-zero diagnostic exit does not become a
shell gate:

```text
python <spec-skill-dir>/scripts/pyright-impact.py capture .scratch/tmp/pyright-before.json -- pyright --outputjson
# change the target signature only in this isolated copy
python <spec-skill-dir>/scripts/pyright-impact.py capture .scratch/tmp/pyright-after.json -- pyright --outputjson
python <spec-skill-dir>/scripts/pyright-impact.py diff .scratch/tmp/pyright-before.json .scratch/tmp/pyright-after.json
```

The capture accepts Pyright exits `0` and `1`; exit `1` means diagnostics were reported. Exits
`2`–`4` indicate a fatal, configuration, or command failure and stop the probe.
Each capture stores the working directory and a SHA-256 digest of the checker command instead of
retaining raw arguments. The diff rejects reports whose directory, command digest, or Pyright
version differs.

The diff fingerprints `file + severity + rule + normalized message` as a multiset and deliberately
ignores ranges, so a line shift does not manufacture a new error. Only `newDiagnostics` are typed
impact candidates. Pre-existing diagnostics remain visible in the counts but are not attributed to
the mutation. An independent repository typecheck gate keeps its configured pass/fail policy.
Confirm each candidate against the changed symbol; prove behavior at the public seam. Report typed
candidates, structural `rg` candidates, and runtime-observed tests separately.

Report inspected typed/structural facts, observed runtime coverage or its absence, and planned
checks separately. State that dynamic-dispatch paths may be missed; never imply the list is complete.

---

## Where the commands live

Use already installed project tools; the block lists options, not a tool-install checklist.
A module suite is a valid fallback when no related-test selector exists.

These stack-specific commands live as lines in the project's `CODEBASE.md` `## Verifier commands`
zone, never in a skill. Example lines:

```markdown
## Verifier commands
- TS 受影响代码：ts-morph findReferences；必要执行探针仅在同一隔离副本做 `tsc --noEmit` 差分
- TS 受影响测试：`vitest related <file>`
- Py 受影响代码：`rg '\bSYM\b'`；必要执行探针在同一隔离副本用 `pyright-impact.py capture/diff`，只看 new diagnostics
- Py 受影响测试：`pytest --testmon`
- import 图：TS `madge`，Py `grimp`
```

## Other languages

Same axis. Strong-typed (Go, Rust, Java, C#) → use each ecosystem's read-only references and import
queries (gopls, rust-analyzer, LSP), plus existing compiler evidence. A necessary execution-stage
compiler mutation follows the same isolated-copy rule. Dynamic (Ruby, JS-without-types, PHP) → use
`rg`, available runtime coverage and source inspection; plan related behavior checks and flag the
dynamic gap. Missing observations remain explicit rather than forcing suites during planning.
