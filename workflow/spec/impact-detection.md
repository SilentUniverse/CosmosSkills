# Impact Detection — 影响面探测（按需读）

When a change touches **existing** code, the risk isn't slicing. It's what this change reaches and
might break. This is the per-language playbook for that.

**Read this only for the third tier** — `/spec` step 2 gates impact work on a cheap reference
probe and scales the response to the blast radius: a new change or a small-radius one (a few
callers, one module, no known invariant) is handled inline and never reaches this file. Only a real
coupled change — many references, multiple modules, or an invariant area — needs the playbook below.
The slicing skill itself stays stack-agnostic.

## The one principle

**Deterministic tools first, subagent reading last.** The stronger the type system, the more static
analysis covers; the weaker it is, the more you lean on **runtime** observation (coverage / test
selectors — what actually ran). Either way a subagent only fills what those tools miss: greppable-invisible assumptions.
It never replaces them. TypeScript is near-whitebox: the checker
resolves which `save()` you mean. Python is dynamic: `getattr`, `**kwargs`, DI, registries, and
fixtures make callers invisible to static tools, so static results are a lower bound.

**Mutation probes are differential.** Capture a type-checker baseline before changing the target,
make one temporary signature change, capture the candidate, and inspect only new diagnostics.
Pre-existing diagnostics, a checker's non-zero baseline exit, and diagnostics that only moved lines
are not impact. Restore the temporary mutation after the probe.

Two kinds of impact, very different confidence:

- **Static reachability** — who imports/calls this, what breaks if the signature changes.
  Machine-determinable. Query it, don't let the agent guess.
- **Semantic / behavioural coupling** — "refund makes the amount negative, but reconciliation
  *assumes* amount ≥ 0." No import edge, ungreppable. Only reading + reasoning finds it. This is
  exactly what `CODEBASE.md`'s **invariants** are for. Persist them so the next run reuses them.

## What gets reused on the second run

- **Static reference points** — NOT stored. Re-grep each time; it is cheap and always current. The
  `CODEBASE.md` two-axis rule (defined in `/map`).
- **Semantic invariants (the expensive part)** — persist to the area's `CODEBASE.md` generated
  block (`src/<area>/CLAUDE.md`, auto-injected on read) so the next coupled change in this area
  skips re-deriving it; but only if the run writes its findings back. Write it; don't pause to offer.

---

## TypeScript — the type-checker is the primary impact detector

| Need | Command | Confidence |
|---|---|---|
| Affected code (gold standard) | baseline `tsc --noEmit`, change the target signature, rerun, then inspect only new errors | **complete + precise** when the typed graph and config are complete |
| Affected code without editing | `ts-morph`: `getFunction('refund').findReferences()` | refactor-grade |
| Module dependents | `npx madge --json src/` (`--circular` for cycles); `npx knip` (dead exports — safe to change) | reliable |
| **Affected tests** (key for coupling) | `vitest related <file>` / `jest --findRelatedTests <file>` | reliable — answers "which existing tests need their expectations changed" |
| Structural fallback | `ast-grep -p 'refund($$$)' --lang ts` | type-blind (can't tell same-named methods apart) |

`tsc --noEmit` plus related-test selection constrain typed reachability. Inspect semantic coupling
that neither can establish; report the actual coverage limits, not an assumed percentage.

For browser/Electron work, static reachability is not runtime integrity. Inspect the current CSP
and the main/preload/renderer ownership of network and file resources before fixing the design.
The verification plan must operate the real surface and collect unexpected console errors, uncaught
page errors, unexpected failed requests, and CSP violations; expected error-state events are named
fixtures/assertions. Media assertions check decoded content (for HTML images,
`complete && naturalWidth > 0`); element visibility or an absolute URL alone is a known false
positive. Persist a discovered runtime invariant to the area's `CODEBASE.md` like any other
semantic coupling.

## Python — static under-reports; add runtime

| Need | Command | Confidence |
|---|---|---|
| Affected code (typed parts only) | baseline/candidate `pyright --outputjson`, then `scripts/pyright-impact.py diff` | new diagnostics are candidates; misses untyped + dynamic dispatch |
| Reference lookup | `rope` (scriptable find-occurrences) / `jedi` `Script(...).get_references()` | refactor-grade where resolvable |
| Module dependents | `grimp` (programmatic import graph — what import-linter uses); `pydeps` (visual) | import-level only |
| Dynamic fallback (**do this**) | `rg -n '\brefund\b'` — noisy (same names) but catches string/dynamic calls static tools miss | catch-all |
| **Affected tests** | `pytest --testmon` (runtime coverage — reruns only tests that actually executed the changed lines); or `coverage.py` dynamic contexts | **runtime-observed** — catches dynamic coupling static analysis drops |

Note the asymmetry: in a dynamic language **runtime tools are more trustworthy than static ones**,
because they watch what actually ran, not what looks reachable.

Use the helper from the loaded `spec` skill so Pyright's ordinary non-zero diagnostic exit does not
become a shell gate:

```text
python <spec-skill-dir>/scripts/pyright-impact.py capture .scratch/tmp/pyright-before.json -- pyright --outputjson
# make one temporary target-signature change
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

**Python report MUST state: "static + runtime coverage below; dynamic-dispatch paths may be
missed — scan manually."** Never imply the list is complete.

---

## Where the commands live

Use already installed project tools; the tables list options, not a tool-install checklist.
A module suite is a valid fallback when no related-test selector exists.

These commands are **stack-specific**, so they live as lines in the project's `CODEBASE.md`
`## Verifier commands` zone — the single hand section; they never open a section of their own
(its "stack adaptation" home), not in any skill. Drop a section in once:

```markdown
## Verifier commands
- TS 受影响代码：baseline/candidate `tsc --noEmit` 差分；不动代码用 ts-morph findReferences
- TS 受影响测试：`vitest related <file>`
- Py 受影响代码：`pyright-impact.py capture/diff`（只看 new diagnostics）+ `rg '\bSYM\b'`（动态候选）
- Py 受影响测试：`pytest --testmon`
- import 图：TS `madge`，Py `grimp`
```

Then a session reads this zone when choosing a verifier; no skill edit, and
skills stay stack-agnostic.

## Other languages

Same axis. Strong-typed (Go, Rust, Java, C#) → lean on the compiler: rename/change the signature and
let `go build` / `cargo check` / `tsc`-equivalent enumerate the breaks; pair with each ecosystem's
"find references" (gopls, rust-analyzer, LSP). Dynamic (Ruby, JS-without-types, PHP) → treat like
Python: `rg` for dynamic calls + a coverage-based test selector + more subagent reading, and flag
the dynamic gap in the report.
