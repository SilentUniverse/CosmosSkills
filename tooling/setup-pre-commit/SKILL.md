---
name: setup-pre-commit
description: >-
  Use only when the user invokes /setup-pre-commit to add or repair pre-commit hooks, staged formatting, or commit-time checks using the repo's hook manager or ecosystem tool.
disable-model-invocation: true
---

# Setup Pre-Commit Hooks

## 1. Detect what exists

Inspect existing hook managers (`.pre-commit-config.yaml`, `lefthook.yml`, `.husky/`,
`simple-git-hooks`, `git config core.hooksPath`), the language ecosystem, the package manager
(`packageManager`, lockfiles), formatter configs and CI commands. Resolve conflicting evidence
before installing anything.

## 2. Choose the tool

- **A hook manager already exists** → extend it; preserve its checks and failure propagation.
- **No manager, JS/TS project with `package.json`** → Husky + lint-staged + Prettier (below).
- **No manager, other ecosystem** → the ecosystem's native route: the `pre-commit` framework for
  Python or polyglot repos, or a versioned hook script wired through `core.hooksPath`. Never add a
  `package.json` only to host hooks.

Run the project's own formatter and checks; add Prettier only when the project has no formatter
for those files. Reuse the commit-check scope CI already defines; do not add costly full suites by
default. A requested check with no runnable command is reported as a limitation, never as verified.

## 3. Husky route (JS/TS without a hook manager)

Use the detected package manager; default to npm only when the repository has none. Check that this
is a git repo and `package.json` exists. Install `husky lint-staged prettier` as devDependencies,
then run `npx husky init` (creates `.husky/` and `prepare: "husky"`; preserve existing `prepare`
actions).

`.husky/pre-commit`, adapted to the package manager and existing non-watch commands:

```
npx lint-staged
npm run typecheck
npm run test
```

Merge into existing lint-staged and ignore configuration; create only missing files.
`.lintstagedrc`:

```json
{
  "*": "prettier --ignore-unknown --write"
}
```

`.prettierignore` must exclude lockfiles and generated files. Prettier counts YAML/JSON as known
types, so `--ignore-unknown` won't skip them; reformatting a lockfile on every commit is churn.

```
*-lock.yaml
package-lock.json
```

Create `.prettierrc` only when no Prettier config exists:

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

## 4. Verify

- [ ] The effective hook, formatter and staged-file configuration is valid in its existing format;
  install hooks (`prepare`, `pre-commit install`, `core.hooksPath`) retain existing actions.
- [ ] Exercise the final configuration on a disposable fixture in an isolated temporary repository:
  formatting applies to staged files and a failing check blocks the commit, without touching the
  user's index or partially staged files. An empty staged set verifies no formatting behavior.

## 5. Hand off

End with the chosen tool and why, files changed, and the verification run. Hook setup alone does
not authorize a submission.
