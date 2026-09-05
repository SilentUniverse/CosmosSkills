---
name: git-guardrails-claude-code
description: Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, branch -D, etc.) before they execute. Use when user wants to prevent destructive git operations, add git safety hooks, or block git push/reset in Claude Code.
disable-model-invocation: true
---

# Setup Git Guardrails

Sets up a PreToolUse hook that intercepts and blocks dangerous git commands before Claude executes them.

Use the standalone carrier for git-only or push-blocking requests. Use
[shell-guardrails](../shell-guardrails/SKILL.md) when the requested policy includes its additional
tiers and allows pushes. Its parser covers more host command forms, but its git tier allows
`git push`, including `--force`; replacing a push-blocking hook with it alone loses that protection.

## What Gets Blocked

The standalone carriers match host-side git commands and check subcommands and flags:

- `git push` — all variants, including `--force`
- `git reset --hard`
- `git clean` with any force flag (`-f`, `-fd`, `-xdf`, `--force`)
- `git branch -D` (and `--delete --force`)
- `git checkout .` / `git restore .` (including `-- .`)

Quoted command text is data. The standalone parsers approximate shell syntax; the
[combined engine's execution-domain model](../shell-guardrails/SKILL.md) and
[known limits](../shell-guardrails/README.md) distinguish carrier coverage. Verify the selected
carrier against the requested forms. `# force-legacy` does not bypass git blocking.

## Steps

### 1. Resolve scope

Reuse the requested scope or existing target. A request scoped to this repository uses
`.claude/settings.json`; all-project scope uses `~/.claude/settings.json`. Ask only if the
intended scope remains unclear after inspecting the request and existing configuration.

### 2. Copy the hook script

- **Standalone:** [scripts/block-dangerous-git.ps1](scripts/block-dangerous-git.ps1) on Windows;
  [scripts/block-dangerous-git.sh](scripts/block-dangerous-git.sh) on Unix, requiring `jq`.
- **Combined, when its policy fits:** [../shell-guardrails/scripts/guard-shell.py](../shell-guardrails/scripts/guard-shell.py).

Target locations by scope: `.claude/hooks/` (project) or `~/.claude/hooks/` (global).

Copy only to the selected target. A source edit does not itself request global installation.

### 3. Add hook to settings

Wire the hook into the settings file per scope and platform: [WIRING.md](WIRING.md). If the
settings file already exists, merge the hook into the existing `hooks.PreToolUse` array; don't
overwrite other settings. With the combined engine you wire ONE entry — it
already includes the legacy-CLI tier, so do not also wire `modern-cli-guardrails`.

### 4. Apply requested customization

Keep the default blocked set unless customization was requested. Modify the selected carrier's
rule table when needed, preserving other protections, then verify that policy.

### 5. Verify

Verify the selected carrier and deployed wiring: [WIRING.md](WIRING.md) §Verify.
