---
name: commit
description: Create one git commit and land it through the standard flow: branch off the default branch when working on it, push the branch, then merge it — a squash-merged PR through the GitHub CLI (`gh`) when usable, otherwise a native git merge into the default branch pushed from local. A `-local` path instead stages only the files this change touched and commits without pushing or merging. Use when the user says /commit, asks to commit, submit, or merge, or invokes /commit -local; other skills call this after validation when submission is already requested.
argument-hint: "[-local]"
---

# Commit

The submit phase after validation. An existing request to commit or submit authorizes entering
this skill in the same task; do not ask the user to invoke it again. Preserve an explicit local-only
or narrower file scope even when the default mode would stage, push, or merge more.

## Context

Read all four before staging anything:

- `git status`
- `git diff HEAD`
- `git branch --show-current`
- `git log --oneline -10`

Read every untracked path named by `git status`; `git diff HEAD` does not expose its contents.

Unless `-local`, also resolve the current branch's configured upstream and remotes before
staging. If HEAD is detached, stop. If there is no upstream, require `origin` so the push can
create the same-name remote branch; if no remote exists at all, the commit stays local and is
reported as not pushed. Also resolve the repo's default branch — `gh repo view --json
defaultBranchRef` when gh is usable, `git remote show origin` otherwise; working on it triggers
the branch-off step in Task.

Unless `-local`, prefer gh for the push when usable: `gh` is installed, `gh auth status`
succeeds, and the push remote URL starts with `https://github.com/`. Then run `gh auth
setup-git` before pushing so git authenticates through the gh token. SSH remotes, non-GitHub
hosts, and machines without a usable gh keep native git auth.

## Task

Create a single git commit in one of two modes:

- Default: if on the repo's default branch, first `git switch -c <type>/<slug>` with a short
  kebab-case slug from the planned commit title. Stage every tracked or untracked path
  reported by `git status` with `git add -A`, create the commit, push the branch to its
  configured upstream (`git push -u origin HEAD` when it has none), then land it. Git-ignored
  paths stay excluded.
- `-local`: stage only the files this change touched and commit that path set with
  `git commit --only -- <paths>` so unrelated pre-staged changes stay outside this commit.
  Nothing is pushed or merged.

Landing (default mode): with gh usable, run `gh pr create` with the commit's title and body,
then `gh pr merge --squash --delete-branch`, adding `--auto` while required checks are pending;
a branch that already has an open PR merges that PR instead; the merge returns the worktree to
the default branch. Without gh, land natively: `git switch` to the default branch and
`git merge --ff-only <branch>`; with diverged histories, use `git merge --squash <branch>`
plus `git commit` with the same message. Push the default branch, then delete the merged branch
with `git branch -d` and `git push origin --delete <branch>`. After a squash landing `-d` refuses;
verify the landed tree matches the branch (`git diff HEAD <branch>` empty), then `-D`. Where the
host reserves `git branch -D` (git-guardrails), report the verified branch for the user to delete
by hand: the landing stands, cleanup is reported, never bypassed.

For submission, the mutating commands are `git add`, `git commit`, `git switch`, `git push`,
`git merge`, the post-landing `git branch -d` (`-D` only after a squash landing), and, on the
gh path, `gh auth setup-git`, `gh pr create`, and `gh pr merge`. gh has no commit or push
command: content always moves through git. A failed hook returns to in-scope repair and
validation, then retries submission; preserve hooks and unrelated changes. Never force-push,
pull, rebase, or amend to overcome a rejection, never bypass failing checks or branch
protection (`--admin`, `--no-verify`), and never push the default branch except to publish a
landing merge or on an explicit user request. A failed push or merge leaves a valid commit or
pushed branch and must be reported with the exact point where the chain stopped.

The message is bilingual by design: the **title line is English** — `type(scope): summary`,
imperative, matching the recent history; the **body is Chinese** — one bullet per change,
naming files and mechanisms, written so the body alone reconstructs the change. An empty body
is allowed only when the title already says everything.

Report the hash and files staged. Unless `-local`, also report the landing result: the remote
ref pushed and, for a PR, its URL and squash-merge into the default branch — or the exact point
where the chain stopped (push, PR creation, merge, branch cleanup) and what remains valid.
