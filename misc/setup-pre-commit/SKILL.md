---
name: setup-pre-commit
description: Set up Husky pre-commit hooks with lint-staged (Prettier), type checking, and tests in the current repo. Use when user wants to add pre-commit hooks, set up Husky, configure lint-staged, or add commit-time formatting/typechecking/testing.
disable-model-invocation: true
---

# Setup Pre-Commit Hooks

## What This Sets Up

- **Husky** pre-commit hook
- **lint-staged** running Prettier on all staged files
- **Prettier** config (if missing)
- **typecheck** and **test** scripts in the pre-commit hook

## Steps

### 1. Detect package manager

Inspect `packageManager`, lockfiles, existing hooks, and CI commands. Use the established package
manager; default to npm only when the repository has none. Resolve conflicting evidence before installing.

### 2. Install dependencies

Install as devDependencies:

```
husky lint-staged prettier
```

### 3. Initialize Husky

Before init, check that this is a git repo and `package.json` exists. Adapt existing hooks instead
of reinitializing `.husky/`; preserve existing `prepare` actions when adding Husky.

```bash
npx husky init
```

This creates `.husky/` dir and adds `prepare: "husky"` to package.json.

### 4. Create `.husky/pre-commit`

Merge these commands into the existing hook; preserve its checks and failure propagation:

```
npx lint-staged
npm run typecheck
npm run test
```

**Adapt**: use the detected package manager and existing non-watch verification commands. Reuse
the project's commit-check scope; do not add costly full suites by default. If a requested check
has no runnable command, report that limitation; do not silently treat it as verified.

### 5. Create `.lintstagedrc` + `.prettierignore`

Merge into existing lint-staged and ignore configuration; create only missing files.

```json
{
  "*": "prettier --ignore-unknown --write"
}
```

`.prettierignore` must exclude lockfiles and generated files. Prettier counts YAML/JSON as known types, so `--ignore-unknown` won't skip them; reformatting a lockfile on every commit is churn.

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

- [ ] Effective Husky, lint-staged, and Prettier configuration is valid, including existing config
  formats; `prepare` retains existing actions and initializes Husky.
- [ ] Exercise formatting on a disposable fixture with the final configuration in an isolated
  temporary repository. Check successful formatting and hook failure propagation without touching
  the user's index or partially staged files. An empty staged set verifies no formatting behavior.

### 8. Hand off to submit workflow

Report the setup and verification. If submission was already requested, continue through `/commit`;
otherwise finish with validated changes. Hook setup alone does not authorize a submission.

## Notes

- `prettier --ignore-unknown` skips files Prettier can't parse (images, etc.)
- The pre-commit runs lint-staged first, then the selected non-watch checks.
