---
name: git-guardrails-claude-code
description: Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, branch -D, etc.) before they execute. Use when user wants to prevent destructive git operations, add git safety hooks, or block git push/reset in Claude Code.
disable-model-invocation: true
---

# Setup Git Guardrails

> **Prefer `shell-guardrails`** (one self-contained Python script, three prioritized tiers — the destructive-git tier of this hook plus the legacy-CLI and path-world tiers; it covers command forms this hook's legacy carriers miss, such as `sudo -u root git push`, `X=$(git push)`, `then git push`, and does not false-block data like `echo sudo git push` or `adb shell sudo git push`; same file on Windows `python` and Unix `python3`). This skill's legacy `.ps1`/`.sh` carriers remain for standalone installs and machines not yet rewired.

Sets up a PreToolUse hook that intercepts and blocks dangerous git commands before Claude executes them.

> Not yet on `shell-guardrails`? Windows uses the bundled `.ps1` via `pwsh` (5.1-compatible); Unix/WSL uses the `.sh`. Both are superseded carriers — new installs should take the combined hook.

## What Gets Blocked

The combined engine (`guard-shell.py` in `shell-guardrails`) finds
every **host-side git command position** — control flow (`if git push; then`),
pipelines, subshells, `$(…)`/backticks **inside double quotes** (`echo "$(git push)"`),
wrappers with value-taking options (`sudo -u root git push`, `env -u NAME …`,
`timeout --signal TERM 5 …`, `time git push`), absolute paths
(`/usr/bin/git push`), and static `bash -c 'git push'` / `eval 'git push'`
payloads — then checks subcommand and flags (flag reordering, double spaces,
`-C <path>` variants, `--` long forms all match):

- `git push` — all variants, including `--force`
- `git reset --hard`
- `git clean` with any force flag (`-f`, `-fd`, `-xdf`, `--force`)
- `git branch -D` (and `--delete --force`)
- `git checkout .` / `git restore .` (including `-- .`)

Data never blocks: quoted strings, heredoc bodies, comments, array literals,
case patterns (`rg "git push" docs`, `echo sudo git push`, a `git push` inside
a commit message). Remote execution domains are not this machine's git:
`ssh host git push`, `adb shell sudo git push`, `docker exec dev git push`
pass. `# force-legacy` does not bypass this tier. **No escape hatch by design.**

## Steps

### 1. Ask scope

Ask the user: install for **this project only** (`.claude/settings.json`) or **all projects** (`~/.claude/settings.json`)?

### 2. Copy the hook script

New installs take the combined engine — one file, both platforms:

- **Preferred:** [../shell-guardrails/scripts/guard-shell.py](../shell-guardrails/scripts/guard-shell.py) (deploy + wire per that skill's WIRING)
- **Legacy carriers, standalone installs only:** [scripts/block-dangerous-git.ps1](scripts/block-dangerous-git.ps1) (Windows) / [scripts/block-dangerous-git.sh](scripts/block-dangerous-git.sh) (Unix; needs `jq` on PATH, fails open without)

Target locations by scope: `.claude/hooks/` (project) or `~/.claude/hooks/` (global).

> In this repo, `install.ps1` distributes guard-shell.py and the legacy `.ps1` pair to `~/.claude/hooks/`; re-run it after editing anything under `scripts/`. The legacy `.sh` is synced manually. The manual copy is for other machines.

### 3. Add hook to settings

Wire the hook into the settings file per scope and platform: [WIRING.md](WIRING.md). If the
settings file already exists, merge the hook into the existing `hooks.PreToolUse` array; don't
overwrite other settings. With the combined engine you wire ONE entry — it
already includes the legacy-CLI tier, so do not also wire `modern-cli-guardrails`.

### 4. Ask about customization

Ask if the user wants to add or remove subcommands from the blocked set. Edit the `sub` rule table in `dangerous_git_hit` in `guard-shell.py` (the `switch ($sub)` in the legacy `.ps1` mirrors it), then re-run the corpus.

### 5. Verify

Run the shared corpus (expect every git-tier case to pass): [WIRING.md](WIRING.md) §Verify.
