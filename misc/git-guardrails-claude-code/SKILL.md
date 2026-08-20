---
name: git-guardrails-claude-code
description: Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, branch -D, etc.) before they execute. Use when user wants to prevent destructive git operations, add git safety hooks, or block git push/reset in Claude Code.
disable-model-invocation: true
---

# Setup Git Guardrails

Sets up a PreToolUse hook that intercepts and blocks dangerous git commands before Claude executes them.

> Windows default: use the bundled `.ps1` script invoked via `pwsh`. Unix/WSL users use the `.sh` script.

## What Gets Blocked

Matching is **token-level**: every `git` in command position (segment-initial, or right after `sudo`/`env`/`nohup`/`nice`/`timeout`/`xargs`) is checked with its subcommand and flags — flag reordering, double spaces, and `--` long forms all match:

- `git push` — all variants, including `--force`
- `git reset --hard`
- `git clean` with any force flag (`-f`, `-fd`, `-xdf`, `--force`)
- `git branch -D` (and `--delete --force`)
- `git checkout .` / `git restore .` (including `-- .`)

Quoted strings and heredoc bodies are data (`rg "git push" docs` never blocks). **No escape hatch by design.**

## Steps

### 1. Ask scope

Ask the user: install for **this project only** (`.claude/settings.json`) or **all projects** (`~/.claude/settings.json`)?

### 2. Copy the hook script

Two versions are bundled:

- **Windows (default):** [scripts/block-dangerous-git.ps1](scripts/block-dangerous-git.ps1)
- **Unix / WSL:** [scripts/block-dangerous-git.sh](scripts/block-dangerous-git.sh)

Copy the one matching the user's shell to the target location based on scope:

- **Project**: `.claude/hooks/block-dangerous-git.ps1` (or `.sh`)
- **Global**: `~/.claude/hooks/block-dangerous-git.ps1` (or `.sh`)

On Unix, make the `.sh` executable with `chmod +x`. The `.ps1` needs no chmod; it is invoked through `pwsh`.

### 3. Add hook to settings

Wire the hook into the settings file per scope and platform: [WIRING.md](WIRING.md). If the
settings file already exists, merge the hook into the existing `hooks.PreToolUse` array — don't
overwrite other settings.

### 4. Ask about customization

Ask if the user wants to add or remove subcommands from the blocked set. Edit the `switch ($sub)` / `case "$sub"` rule table in the copied script, then re-run the test suite.

### 5. Verify

Run the regression suite and spot checks: [WIRING.md](WIRING.md) §Verify.
