---
name: modern-cli-guardrails
description: Set up a Claude Code PreToolUse hook that blocks legacy CLI tools (grep, find, ls, sed) in Bash commands, enforcing CLAUDE.md §7 modern tooling. Use when the user wants to hard-enforce rg/fd/eza/sd, forbid legacy CLI tools, or turn the §7 soft rule into a blocking hook.
---

# Setup Modern CLI Guardrails

Turns CLAUDE.md §7 (Modern CLI Tooling) from a soft guideline into a hard rule: a
PreToolUse hook intercepts every `Bash` tool call and blocks it before execution
if the command invokes a legacy tool (`grep`, `find`, `ls`, `sed`).

> Windows default: use the bundled `.ps1` script invoked via `pwsh`. Unix/WSL users use the `.sh` script.

## What Gets Blocked

Legacy tool in command position (start of command, or right after `|`, `&&`, `;`, `(`) → blocked with a pointer to its modern replacement:

| Forbidden | Use instead |
|---|---|
| `grep` | `rg` (or the built-in Grep tool) |
| `find` | `fd` |
| `ls` | `eza` |
| `sed` | `sd` |

When blocked, Claude sees the message on stderr and retries with the modern tool or a built-in `Grep`/`Glob`/`Read`.

### What does NOT get blocked

- Modern tools themselves: `rg`, `fd`, `bat`, `eza`, `sd`.
- Look-alikes: `ripgrep`, `fdfind`, `pcre2grep`, or paths like `bat cat/notes.md` — the tool name is only matched in command position, followed by whitespace or end-of-string.
- **Escape hatch** (for unavoidable cases — third-party Makefiles, inlined scripts, etc.):
  - Prefix the command with a `# force-legacy` comment line, or
  - Set the environment variable `ALLOW_LEGACY_CLI=1`.

## Steps

### 1. Ask scope

Ask the user: install for **this project only** (`.claude/settings.json`) or **all projects** (`~/.claude/settings.json`)?

### 2. Copy the hook script

Two versions are bundled:

- **Windows (default):** [scripts/block-legacy-cli.ps1](scripts/block-legacy-cli.ps1)
- **Unix / WSL:** [scripts/block-legacy-cli.sh](scripts/block-legacy-cli.sh)

Copy the one matching the user's shell to the target location based on scope:

- **Project**: `.claude/hooks/block-legacy-cli.ps1` (or `.sh`)
- **Global**: `~/.claude/hooks/block-legacy-cli.ps1` (or `.sh`)

On Unix, make the `.sh` executable with `chmod +x`. The `.ps1` needs no chmod; it is invoked through `pwsh`.

### 3. Add hook to settings

Add to the appropriate settings file. **Windows / PowerShell** invokes the script through `pwsh`:

**Project** (`.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/block-legacy-cli.ps1\""
          }
        ]
      }
    ]
  }
}
```

**Global** (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$HOME/.claude/hooks/block-legacy-cli.ps1\""
          }
        ]
      }
    ]
  }
}
```

On Unix/WSL, point `command` at the `.sh` script instead (e.g. `"$CLAUDE_PROJECT_DIR"/.claude/hooks/block-legacy-cli.sh`).

If the settings file already exists, merge the hook into existing `hooks.PreToolUse` array — don't overwrite other settings. This composes with `git-guardrails-claude-code`: both are `Bash` matchers and can each live as a separate entry in the array.

### 4. Ask about customization

Ask if the user wants to add or remove any tools from the blocked map. Edit the `$map` (`.ps1`) or the `LEGACY_TOOLS` / `MODERN_TOOLS` arrays (`.sh`) accordingly, then re-run the test script.

### 5. Verify

**Windows / PowerShell** — run the bundled regression suite:

```powershell
pwsh -NoProfile -File scripts\test-block-legacy-cli.ps1   # expect "All tests passed."
```

Or a single spot check:

```powershell
'{"tool_input":{"command":"grep -r foo ."}}' | pwsh -NoProfile -File <path-to-script.ps1>
$LASTEXITCODE   # expect 2
```

**Unix / WSL:**

```bash
echo '{"tool_input":{"command":"grep -r foo ."}}' | <path-to-script.sh>
echo $?   # expect 2
```

A blocked command exits with code 2 and prints a BLOCKED message to stderr; an allowed command exits 0 with no output.
