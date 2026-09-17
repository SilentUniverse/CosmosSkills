---
name: pr
description: >-
  Use when the user asks to commit, submit, push, merge, or land the current change, including a local-only commit. Creates one scoped Git commit, preserves unrelated work, and either stops locally or lands through a pull request with a Summary/Evidence/Merge Danger body or a verified native merge.
argument-hint: "[-local]"
---

# PR

When this change belongs to an active protocol-2 batch, verify its final proof and required decisions through [BATCH-FORMAT.md](../tdd/BATCH-FORMAT.md). A Git commit does not close an incomplete batch.

This is the submit phase after validation. `/pr` runs no test suite, build, or repo-wide gate of
its own: the upstream phase already produced the evidence, so commit the validated scope directly.
Installed repository hooks run as configured. Existing authorization to commit or submit carries
into this skill. Preserve any explicit local-only or narrower file scope.

## Inspect

Before staging, read:

- `git status --short`
- `git diff HEAD`
- `git branch --show-current`
- `git log --oneline -10`

Read every untracked path in scope because `git diff HEAD` omits its contents. Attribute each changed
path to the current task; ambiguous or unrelated work stays outside the commit.

Unless local-only mode is selected, also resolve the upstream, remotes, and default branch. Prefer `gh repo view --json
defaultBranchRef` when authenticated; otherwise inspect `git remote show origin`. A detached HEAD
blocks submission. With no remote, create the local commit and report that landing could not proceed.

The landing unit is the whole topic branch, not only the new commit. Before staging on an existing
non-default branch, inspect `git log --oneline <default>..HEAD` and `git diff --name-status
<default>...HEAD`. Reuse that branch only when every ahead commit and changed path belongs to the
authorized task or the user explicitly selected the whole branch. Otherwise stop before mutation and
ask whether to isolate the task or land the broader branch.

For an HTTPS GitHub remote, authenticated `gh` may configure Git credentials with `gh auth setup-git`.
SSH, non-GitHub, and unauthenticated environments retain native Git authentication.

## Commit modes

- Default: include only task-attributable paths. If currently on the default branch, create a topic
  branch using the repository or host-required prefix; otherwise use `<type>/<slug>` from the commit
  title. Stage explicit paths with
  `git add -- <paths>` and commit them with `git commit --only -- <paths>` so unrelated staged work
  remains staged but outside this commit. Push and land the branch.
- `-local`: use the same scoped staging and commit, then stop without pushing or merging.

Never stage with `git add -A` or `git add .`. A broad “everything” request still applies to the
validated task scope; unrelated work needs its own validation and commit. Ignored files stay
excluded unless explicitly in the validated scope. Preserve intentional partial-file boundaries;
if one file mixes task and unrelated edits, ask for a narrower choice instead of silently submitting
both.

## Land

Resolve the submission remote and inspect the current branch's configured upstream. Its remote ref
must be `refs/heads/<current>`; a differently named target, especially the default branch, is not a
valid topic upstream. Never use an unqualified `git push` in this workflow. Publish with the explicit
refspec `git push <remote> HEAD:refs/heads/<current>`; add `-u` only when creating that same-name
upstream, or stop if the intended remote cannot be resolved without changing repository configuration.

Landing mechanics run through `python <pr-skill-dir>/scripts/land.py <repo-root>` once the
scoped commit exists on the topic branch. The script selects its engine: authenticated `gh` on a
GitHub remote lands through a pull request (`--squash --match-head-commit <verified-head>` when
the installed gh supports it), created with the body from `--pr-body-file` when provided;
any other remote lands natively in an isolated clean worktree —
`git merge --ff-only <branch>`, squash fallback with the same message — then publishes the
default branch after an optional `--verify-command`. It pins the verified head on both engines
(PR head/base identity; ancestry plus per-path content checks), verifies `state: MERGED` or the
published result before reporting landed, is idempotent on a re-run after a mid-sequence
failure, never stages or scopes (the validated commit is its only input), leaves the
caller's checked-out branch untouched, and advances the local default branch to the published
one by fast-forward only; `--mode/--remote/--base/--verify-command` override its
resolutions. On the native engine, the applicable repository gates go in as `--verify-command`; the
script runs them before publishing. The gh engine takes no verify command: `/pr` runs no check
before that merge and no CI watch after it. Where the base branch requires no checks, the delivery
gates therefore first run in CI after the merge; exit 4 reports a merge that a blocked check
stopped. The script's JSON report and exit code are authoritative; read them rather than deriving
them from the repository's CI configuration.

A moved head, a wrong PR target, pending required checks, an unavailable engine, or a failed
verify command returns to this skill's recovery: resolve the target, revalidate only the head that
changed since the upstream phase, or stop with the scoped commit intact. Enabling auto-merge or
entering a merge queue is pending work, not landing. An advanced target need not have the topic
branch's identical tree.

Never switch branches or create a native squash commit through an index or worktree containing
unrelated changes. Use an isolated clean worktree for native landing, or stop with the scoped commit
intact when isolation is unavailable.

After verified landing, return to the default branch only when the worktree permits it. Clean up
the exact local/remote topic refs only if they still identify the landed work; preserve any new
commits. If policy blocks cleanup after a squash merge, leave the branch and report it.

Never force-push, pull, rebase, amend, bypass hooks or checks, use administrator overrides, or push
the default branch except to publish the authorized landing. A hook failure returns to in-scope
repair and validation. A failed push or merge leaves the valid commit or branch intact and is
reported at the exact stopping point.

## PR body

When the gh engine will create the pull request, write its body to a file under the OS temp
directory and pass `--pr-body-file <path>` to the landing script; the commit message body is
not reused as the PR body. The script gates the file on three fixed headings, in this order,
before any mutation:

```markdown
## Summary

<the smallest view that makes the point clear>

## Evidence

- **Before:** <failing test, error output, or pre-change behavior>
  **After:** <the same check passing after the change>

## Merge Danger

**Door:** two-way (cheap to roll back) or one-way (hard to reverse)
**Blast Radius:** <what this merge can affect beyond its paths: consumers, layout, protocols>
```

Pick one visual for Summary, not several: a diff-sketch when the surrounding shape already
exists, a file or component tree for structure, pseudocode for logic, a sequence diagram for
interaction. Prose is Chinese with code-matching English terms; no preamble. Evidence cites the
upstream phase's real checks — the exact failing→passing test or output — never a claim without a
run, and never a run launched to produce one; when the upstream phase left no check, state that
absence in one line. Merge Danger states the rollback class and the widest plausible impact of the
merge; a cheap two-way door with no outside consumers is a valid, complete answer. A re-run that
finds the PR already open or merged leaves the existing body untouched. Delete the file once
landing reports landed; keep it when a landing stopped short of success, so the retry reuses it.

## Message and report

Title: an English imperative `type(scope): summary`. Repository history informs only the type
and scope vocabulary, never the language; a Chinese or prefix-less subject is invalid. Body:
Chinese, one bullet per meaningful mechanism and file group. An empty body is acceptable only
when the title fully reconstructs the change. Write the message to a file under the OS temp
directory, gate it, then commit with that file:

```text
python <pr-skill-dir>/scripts/land.py <repo-root> --check-message --message-file <path>
git commit --only -F <path> -- <paths>
```

Delete the message file once the commit exists; a failed commit keeps it for the retry.

Both landing engines enforce the same subject gate on the verified head before publishing.

Report the commit hash and included paths. For a landed change, also report the pushed ref, pull
request URL when applicable, default-branch result, and any cleanup still pending; when CI was not
awaited, say so rather than leaving a green run implied. Layout follows
[REPORT-FORMAT.md](../REPORT-FORMAT.md).
