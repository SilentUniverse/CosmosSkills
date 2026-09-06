---
name: migrate-to-shoehorn
description: >-
  Use when migrating test fixtures from TypeScript `as` assertions to @total-typescript/shoehorn or when partial test data is needed. Performs the focused test-data migration and validates affected tests and types.
disable-model-invocation: true
---

# Migrate to Shoehorn

`shoehorn` lets you pass partial data in tests while keeping TypeScript happy. **Test code only**; never in production code.

Use partial fixtures to remove unnecessary type assertions while preserving the tested behavior.

## Install

```bash
npm i -D @total-typescript/shoehorn   # devDependency — test code only
```
Use the repository's package manager and reuse an existing dependency; npm above is an example.

## When to use each

| Function        | Use case                                           |
| --------------- | -------------------------------------------------- |
| `fromPartial()` | Pass partial data that still type-checks           |
| `fromAny()`     | Pass intentionally wrong data (keeps autocomplete) |
| `fromExact()`   | Force full object (swap with fromPartial later)    |

Before/after examples: [PATTERNS.md](PATTERNS.md).

## Workflow

1. **Inspect the requested test scope**: locate assertions, fixture intent, package manager,
   and validation commands yourself. Infer partial versus deliberately invalid data from the
   tests; ask only if an unresolved intent would change what behavior is being exercised.

2. **Install and migrate**:
   - [ ] Add the devDependency only if missing.
   - [ ] Find assertions with ast-grep when available, or `rg '\bas\b' <test-paths>` and
     inspect the candidates. Include the repository's actual test naming and TSX files.
   - [ ] Use `fromPartial()` for partial fixtures; use `fromAny()` only for deliberately invalid
     data. A double assertion alone is not evidence that the test intends invalid data.
   - [ ] Preserve meaningful narrowing, `as const`, and fields exercised by the test.
   - [ ] Add imports from `@total-typescript/shoehorn`
   - [ ] Run type check **and the affected test files** to verify
