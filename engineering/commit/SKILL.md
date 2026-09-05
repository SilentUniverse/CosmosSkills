---
name: commit
description: Create one git commit from every inspected worktree change and push the current branch upstream, authenticating through the GitHub CLI (`gh`) when usable and through native git otherwise; a `--local` path instead stages only the files this change touched and keeps the commit local. Use when the user says /commit, asks to commit or submit, or invokes /commit --local; other skills call this after validation when submission is already requested.
argument-hint: "[--local]"
---

# Commit

The submit phase after validation. An existing request to commit or submit authorizes entering
this skill in the same task; do not ask the user to invoke it again. Preserve an explicit local-only
or narrower file scope even when the default mode would push or stage more.

## Context

Read all four before staging anything:

- `git status`
- `git diff HEAD`
- `git branch --show-current`
- `git log --oneline -10`

Read every untracked path named by `git status`; `git diff HEAD` does not expose its contents.

Unless `--local`, also resolve the current branch's configured upstream and remotes before
staging. If HEAD is detached, stop. If there is no upstream, require `origin` so the push can
create the same-name remote branch; if no remote exists at all, the commit stays local and is
reported as not pushed.

Unless `--local`, prefer gh for the push when usable: `gh` is installed, `gh auth status`
succeeds, and the push remote URL starts with `https://github.com/`. Then run `gh auth
setup-git` before pushing so git authenticates through the gh token. SSH remotes, non-GitHub
hosts, and machines without a usable gh keep native git auth.

## Task

Create a single git commit in one of two modes:

- Default: stage every tracked or untracked path reported by `git status` with `git add -A`,
  create the commit, then push the current branch to its configured upstream. With no upstream,
  use `git push -u origin HEAD`. Git-ignored paths stay excluded.
- `--local`: stage only the files this change touched and commit that path set with
  `git commit --only -- <paths>` so unrelated pre-staged changes stay outside this commit.
  The commit stays local.

For submission, the mutating commands are `git add`, `git commit`, and, unless `--local`,
`git push` plus, on the gh path, `gh auth setup-git`. gh has no commit or push command: content
always moves through git. A failed hook returns to in-scope repair and validation, then retries
submission; preserve hooks and unrelated changes. Never force-push, pull, merge, rebase, or amend to overcome a
rejection. A failed push
leaves a valid local commit and must be reported as not merged remotely.

The message is bilingual by design: the **title line is English** — `type(scope): summary`,
imperative, matching the recent history; the **body is Chinese** — one bullet per change,
naming files and mechanisms, written so the body alone reconstructs the change. An empty body
is allowed only when the title already says everything.

Report the hash and files staged. Unless `--local`, also report the exact remote ref updated,
or the push failure and the fact that the commit remains local.
