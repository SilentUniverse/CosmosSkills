---
name: migrate-to-shoehorn
description: Migrate test files from `as` type assertions to @total-typescript/shoehorn. Use when user mentions shoehorn, wants to replace `as` in tests, or needs partial test data.
disable-model-invocation: true
---

# Migrate to Shoehorn

`shoehorn` lets you pass partial data in tests while keeping TypeScript happy. **Test code only**; never in production code.

Problems with `as` in tests: trained not to use it, must manually specify the target type, double-as (`as unknown as Type`) for intentionally wrong data.

## Install

```bash
npm i -D @total-typescript/shoehorn   # devDependency — test code only
```

## When to use each

| Function        | Use case                                           |
| --------------- | -------------------------------------------------- |
| `fromPartial()` | Pass partial data that still type-checks           |
| `fromAny()`     | Pass intentionally wrong data (keeps autocomplete) |
| `fromExact()`   | Force full object (swap with fromPartial later)    |

Before/after examples: [PATTERNS.md](PATTERNS.md).

## Workflow

1. **Gather requirements** - ask user:
   - What test files have `as` assertions causing problems?
   - Are they dealing with large objects where only some properties matter?
   - Do they need to pass intentionally wrong data for error testing?

2. **Install and migrate**:
   - [ ] Install: `npm i -D @total-typescript/shoehorn`
   - [ ] Find `as` assertions in test files (structural, cross-platform):
     - **ast-grep (preferred):** `sg -p '$EXPR as $TYPE' -l ts --globs '*.test.ts' --globs '*.spec.ts'` — same scope as the rg fallback. For double-casts: `sg -p '$EXPR as unknown as $TYPE' -l ts --globs '*.test.ts' --globs '*.spec.ts'`.
     - **Fallback (rg):** `rg ' as [A-Z]' -g '*.test.ts' -g '*.spec.ts'`
   - [ ] Replace `as Type` with `fromPartial()`
   - [ ] Replace `as unknown as Type` with `fromAny()`
   - [ ] Add imports from `@total-typescript/shoehorn`
   - [ ] Run type check **and the affected test files** to verify
