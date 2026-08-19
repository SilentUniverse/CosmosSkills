# Impact Detection — 影响面探测（按需读）

When a change touches **existing** code, the risk isn't slicing — it's what this change reaches and
might break. This is the per-language playbook for that.

**Read this only for the third tier** — `/plan` step 2 gates impact work on a cheap reference
probe and scales the response to the blast radius: a new change or a small-radius one (a few
callers, one module, no known invariant) is handled inline and never reaches this file. Only a real
coupled change — many references, multiple modules, or an invariant area — needs the playbook below.
The slicing skill itself stays stack-agnostic.

## The one principle

**Deterministic tools first, subagent reading last.** The stronger the type system, the more static
analysis covers; the weaker it is, the more you lean on **runtime** observation (coverage / test
selectors — what actually ran). Either way a subagent only fills what those tools miss —
greppable-invisible assumptions — it never replaces them. TypeScript is near-whitebox — the checker
resolves which `save()` you mean. Python is dynamic — `getattr`, `**kwargs`, DI, registries, and
fixtures make callers invisible to static tools, so static results are a lower bound.

Two kinds of impact, very different confidence:

- **Static reachability** — who imports/calls this, what breaks if the signature changes.
  Machine-determinable. Query it, don't let the agent guess.
- **Semantic / behavioural coupling** — "refund makes the amount negative, but reconciliation
  *assumes* amount ≥ 0." No import edge, ungreppable. Only reading + reasoning finds it. This is
  exactly what `CODEBASE.md`'s **invariants** are for — persist them so the next run reuses them.

## What gets reused on the second run

- **Static reference points** — NOT stored (re-grep each time; cheap and always current). The
  `CODEBASE.md` two-axis rule (can't rg it AND bites if missing).
- **Semantic invariants (the expensive part)** — persist to the area's `CODEBASE.md` generated
  block (`src/<area>/CLAUDE.md`, auto-injected on read) so the next coupled change in this area
  skips re-deriving it — but only if the run writes its findings back. Always offer to.

---

## TypeScript — the type-checker IS the impact detector

| Need | Command | Confidence |
|---|---|---|
| Affected code (gold standard) | change the target signature, then `tsc --noEmit` — every error is a real affected site | **complete + precise**, type-level not text |
| Affected code without editing | `ts-morph`: `getFunction('refund').findReferences()` | refactor-grade |
| Module dependents | `npx madge --json src/` (`--circular` for cycles); `npx knip` (dead exports — safe to change) | reliable |
| **Affected tests** (key for coupling) | `vitest related <file>` / `jest --findRelatedTests <file>` | reliable — answers "which existing tests need their expectations changed" |
| Structural fallback | `ast-grep -p 'refund($$$)' --lang ts` | type-blind (can't tell same-named methods apart) |

`tsc --noEmit` + `vitest related` cover ~90%. The subagent only needs to add the behavioural-
assumption layer that neither compile nor grep can see. **TS report = high confidence.**

## Python — static under-reports; add runtime

| Need | Command | Confidence |
|---|---|---|
| Affected code (typed parts only) | `pyright --outputjson` / `mypy` after a signature change | misses untyped + dynamic dispatch |
| Reference lookup | `rope` (scriptable find-occurrences) / `jedi` `Script(...).get_references()` | refactor-grade where resolvable |
| Module dependents | `grimp` (programmatic import graph — what import-linter uses); `pydeps` (visual) | import-level only |
| Dynamic fallback (**do this**) | `rg -n '\brefund\b'` — noisy (same names) but catches string/dynamic calls static tools miss | catch-all |
| **Affected tests** | `pytest --testmon` (runtime coverage — reruns only tests that actually executed the changed lines); or `coverage.py` dynamic contexts | **runtime-observed** — catches dynamic coupling static analysis drops |

Note the asymmetry: in a dynamic language **runtime tools are more trustworthy than static ones**,
because they watch what actually ran, not what looks reachable.

**Python report MUST state: "static + runtime coverage below; dynamic-dispatch paths may be
missed — scan manually."** Never imply the list is complete.

---

## Where the commands live

These commands are **stack-specific**, so they belong in the project's `docs/agents/domain.md`
(its "stack adaptation" home), not in any skill. Drop a section in once:

```markdown
## 影响面探测命令（impact detection）
- TS 受影响代码：改签名后 `tsc --noEmit`；不动代码用 ts-morph findReferences
- TS 受影响测试：`vitest related <file>`
- Py 受影响代码：`pyright --outputjson` + `rg '\bSYM\b'`（动态兜底）
- Py 受影响测试：`pytest --testmon`
- import 图：TS `madge`，Py `grimp`
```

Then any session loads it at startup and knows which commands this repo uses — no skill edit, and
skills stay stack-agnostic.

## Other languages

Same axis. Strong-typed (Go, Rust, Java, C#) → lean on the compiler: rename/change the signature and
let `go build` / `cargo check` / `tsc`-equivalent enumerate the breaks; pair with each ecosystem's
"find references" (gopls, rust-analyzer, LSP). Dynamic (Ruby, JS-without-types, PHP) → treat like
Python: `rg` for dynamic calls + a coverage-based test selector + more subagent reading, and flag
the dynamic gap in the report.
