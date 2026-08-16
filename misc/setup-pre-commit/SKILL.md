---
name: setup-pre-commit
description: Set up Husky pre-commit hooks with lint-staged (Prettier), type checking, and tests in the current repo. Use when user wants to add pre-commit hooks, set up Husky, configure lint-staged, or add commit-time formatting/typechecking/testing.
---

# Setup Pre-Commit Hooks

## What This Sets Up

- **Husky** pre-commit hook
- **lint-staged** running Prettier on all staged files
- **Prettier** config (if missing)
- **typecheck** and **test** scripts in the pre-commit hook

## Steps

### 1. Detect package manager

Check for `package-lock.json` (npm), `pnpm-lock.yaml` (pnpm), `yarn.lock` (yarn), `bun.lock` (bun ≥1.2), `bun.lockb` (legacy bun). Default to npm if unclear.

### 2. Install dependencies

Install as devDependencies:

```
husky lint-staged prettier
```

### 3. Initialize Husky

Before init, confirm: this is a git repo, `package.json` exists, and `.husky/` is absent (if present, adapt the existing hooks instead of re-init).

```bash
npx husky init
```

This creates `.husky/` dir and adds `prepare: "husky"` to package.json.

### 4. Create `.husky/pre-commit`

Write this file (no shebang needed for Husky v9+):

```
npx lint-staged
npm run typecheck
npm run test
```

**Adapt**: map `npx`/`npm run` to the detected PM (`pnpm exec` / `pnpm run`, `yarn` …). No `typecheck`/`test` script in package.json → omit those lines and say so. Watch-mode test scripts (`jest --watch`): prefix `CI=true`; if it can't run once, omit.

### 5. Create `.lintstagedrc` + `.prettierignore`

```json
{
  "*": "prettier --ignore-unknown --write"
}
```

`.prettierignore` must exclude lockfiles and generated files — Prettier counts YAML/JSON as known types, so `--ignore-unknown` won't skip them, and reformatting a lockfile on every commit is churn.

```
*-lock.yaml
package-lock.json
```

### 6. Create `.prettierrc` (if missing)

Only create if no Prettier config exists. Use these defaults:

```json
{
  "useTabs": false,
  "tabWidth": 2,
  "printWidth": 80,
  "singleQuote": false,
  "trailingComma": "es5",
  "semi": true,
  "arrowParens": "always"
}
```

### 7. Verify

- [ ] `.husky/pre-commit`, `.lintstagedrc`, `.prettierrc` exist; `prepare: "husky"` in package.json
- [ ] End-to-end: stage a badly formatted temp file (`printf 'const  x=1' > fmt-check.ts; git add fmt-check.ts`), run lint-staged, confirm the file comes back formatted, then unstage — an empty staged set always passes and verifies nothing

### 8. Hand off to submit workflow

Do not stage or submit here. Tell the user to run the Submit workflow named in `CLAUDE.md` with summary: `Add pre-commit hooks (husky + lint-staged + prettier)`.

That workflow will exercise the hooks again; Verify is the local smoke test.

## Notes

- `prettier --ignore-unknown` skips files Prettier can't parse (images, etc.)
- The pre-commit runs lint-staged first (fast, staged-only), then full typecheck and tests
