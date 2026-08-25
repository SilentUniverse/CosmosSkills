---
name: modern-cli-guardrails
description: Set up a Claude Code PreToolUse hook that blocks legacy CLI tools (grep, find, sed) and POSIX path tokens (/tmp, /c/…) handed to native Windows executables in host-shell segments of Bash commands, enforcing CLAUDE.md §7 modern tooling. Use when the user wants to hard-enforce rg/fd/sd, forbid legacy CLI tools, or turn the §7 soft rule into a blocking hook.
disable-model-invocation: true
---

# Setup Modern CLI Guardrails

Turns CLAUDE.md §7 (Modern CLI Tooling) from a soft guideline into a hard rule: a
PreToolUse hook intercepts every `Bash` tool call and blocks it before execution
if a **host-side segment** of the command invokes a legacy tool (`grep`, `find`,
`sed`). `ls` is deliberately not blocked; it is too frequent to replace.

> Windows default: use the bundled `.ps1` script invoked via `pwsh`; on machines without PS7, `powershell` works too (the scripts are 5.1-compatible). Unix/WSL users use the `.sh` script.

## What Gets Blocked

Legacy tool as the first word of a host-side segment (segments split at unquoted `|`, `&&`, `;`, `(`, or a newline) → blocked with a pointer to its modern replacement:

| Forbidden | Use instead |
|---|---|
| `grep` | `rg` (or the built-in Grep tool) |
| `find` | `fd` |
| `sed` | `sd` |

When blocked, Claude sees the message on stderr and retries with the modern tool or a built-in search tool.

**Path-world guard**: a host segment starting with a native Windows executable (`python`/`python3`/`py`, `pwsh`/`powershell`, `cmd`, `node`, `rg`, `fd`, `bat`, `jq`, `yq`, `sd`) that carries a POSIX path token (`/tmp/…`, `/c/…`) is blocked with a `cygpath -w` / `$env:TEMP` pointer. Native processes cannot resolve MSYS paths ("two path worlds", `~/.claude/references/windows-cli.md`). `cmd`-headed segments skip bare single-letter tokens: `/a` and `/b` are `dir` switches, not paths, and the CLAUDE.md §8 directory-truth check `cmd //c dir /a /b <path>` must stay allowed; `/tmp` (any form) and `/c/…` still block. This guard lives in the `.ps1` hook only; on Unix the `.sh` needs none (MSYS paths don't exist there). Same escape hatch.

### What does NOT get blocked

- Data, not command: quoted strings (`adb shell "ls; grep x"`, `ssh host "grep x /var/log"`) and heredoc bodies.
- Tools in argument position (`adb shell ls /sdcard`, `docker exec ctr ls /app`, `wsl ls`) are not the first word of a host segment. Host-side pipelines still block: `adb logcat -d | grep x` → use `rg`.
- Exact first-word match only: look-alikes (`ripgrep`, `fdfind`, `pcre2grep`, `lsd`) and modern tools (`rg`, `fd`, `bat`, `sd`) pass; the bundled test suite pins the edge cases.
- **Escape hatch** for genuinely unavoidable cases (third-party Makefiles, inlined scripts): prefix the command with a `# force-legacy` comment line, or set `ALLOW_LEGACY_CLI=1` in the shell that launches Claude Code. An inline `ALLOW_LEGACY_CLI=1 cmd` prefix is invisible to the hook, which runs in its own process.

The hook is failure-safe: malformed input, a missing dependency, or any internal error exits 0 (allow).

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

On Unix, make the `.sh` executable with `chmod +x`. The `.ps1` needs no chmod; it is invoked through `pwsh`. The `.sh` needs `jq` on PATH; with jq missing it fails open (allows everything).

> In this repo, `install.ps1` distributes the `.ps1` hook scripts to `~/.claude/hooks/`; re-run it after editing anything under `scripts/`. The `.sh` stays repo-only for Unix. The manual copy is for other machines.

### 3. Add hook to settings

Wire the hook into the settings file per scope and platform: [WIRING.md](WIRING.md). If the
settings file already exists, merge the hook into the existing `hooks.PreToolUse` array; don't
overwrite other settings. This composes with `git-guardrails-claude-code`: both are `Bash`
matchers and can each live as a separate entry in the array.

### 4. Ask about customization

Ask if the user wants to add or remove any tools from the blocked map. Edit `$map` (`.ps1`) or `MAP` (`.sh`) accordingly, then re-run the test script.

### 5. Verify

Run the regression suite and spot checks: [WIRING.md](WIRING.md) §Verify.
