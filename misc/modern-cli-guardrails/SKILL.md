---
name: modern-cli-guardrails
description: Set up a Claude Code PreToolUse hook that blocks legacy CLI tools (grep, find, sed) and POSIX path tokens (/tmp, /c/…) handed to native Windows executables in host-shell segments of Bash commands, enforcing CLAUDE.md §7 modern tooling. Use when the user wants to hard-enforce rg/fd/sd, forbid legacy CLI tools, or turn the §7 soft rule into a blocking hook.
disable-model-invocation: true
---

# Setup Modern CLI Guardrails

> **Prefer `shell-guardrails`** (one self-contained Python script, three prioritized tiers — this hook plus the git hook plus the path-world guard, with the `# force-legacy` escape scoped to the legacy-CLI tier only; same file on Windows `python` and Unix `python3`). This skill's legacy `.ps1`/`.sh` carriers remain for standalone installs and machines not yet rewired.

Turns CLAUDE.md §7 (Modern CLI Tooling) from a soft guideline into a hard rule: a
PreToolUse hook intercepts every `Bash` tool call and blocks it before execution
if a **host-side segment** of the command invokes a legacy tool (`grep`, `find`,
`sed`). `ls` is deliberately not blocked; it is too frequent to replace.

> Not yet on `shell-guardrails`? Windows uses the bundled `.ps1` via `pwsh` (5.1-compatible); Unix/WSL uses the `.sh`. Both are superseded carriers — new installs should take the combined hook.

## What Gets Blocked

A legacy tool in a **host-side command position** — found by a real parse
(`guard-shell.py` in `shell-guardrails`; the legacy carriers approximate it) —
is blocked with a pointer to its modern replacement:

| Forbidden | Use instead |
|---|---|
| `grep` | `rg` (or the built-in Grep tool) |
| `find` | `fd` |
| `sed` | `sd` |

Command positions include: segment heads, control-flow bodies (`if grep -q …`,
`while … do find …`), pipelines, subshells, process substitution,
`$(…)`/backtick substitution **even inside double quotes** (the host executes
it), wrappers (`sudo`, `env`, `timeout`, `nice`, `nohup`, `xargs`, `command`,
`exec`, `stdbuf`, `watch`) including value-taking options (`sudo -u root`,
`env -u NAME`, `timeout --signal TERM 5`, `xargs -I {}`), absolute paths
(`/usr/bin/grep`), `VAR=val` prefixes, and static quoted payloads of
`bash -c` / `eval`.

When blocked, Claude sees the message on stderr and retries with the modern tool or a built-in search tool.

**Path-world guard** (MSYS / Git Bash only — the tier disables itself on macOS/Linux): a host segment headed by a native Windows executable (`python`/`python3`/`py`, `pwsh`/`powershell`, `cmd`, `node`, `rg`, `fd`, `bat`, `jq`, `yq`, `sd`) that carries a POSIX path token (`/tmp/…`, `/c/…`) is blocked with a `cygpath -w` / `$env:TEMP` pointer. `cmd`-headed segments skip bare single-letter tokens: `/a` and `/b` are `dir` switches. This is a correctness rule, not a preference: **`# force-legacy` does not bypass it**.

### What does NOT get blocked

- Data, not command: quoted strings (`adb shell "ls; grep x"`, `ssh host "grep x /var/log"`), heredoc bodies, comments (`echo ok # $(grep x file)`), array literals (`tools=(grep find sed)`), `[[ =~ ]]` regex operands, `case` patterns, and bare function declarations (`grep() { :; }`).
- Remote execution domains: tools in argument position of `adb shell`, `ssh`, `docker exec`, `wsl` (`docker exec web grep x /etc` runs inside the container). Host-side pipelines still block: `adb logcat -d | grep x` → use `rg`.
- Name lookups, not executions: `which grep`, `type grep`, `command -v grep`.
- Look-alikes (`ripgrep`, `fdfind`, `pcre2grep`, `lsd`, `git grep`) and modern tools (`rg`, `fd`, `bat`, `sd`).
- **Escape hatch** for the legacy tier only: prefix the command with a `# force-legacy` comment line, or set `ALLOW_LEGACY_CLI=1` in the shell that launches Claude Code. An inline `ALLOW_LEGACY_CLI=1 cmd` prefix is invisible to the hook, which runs in its own process.
- Dynamic forms static analysis cannot judge (`x=git; $x push`, `eval "$cmd"`) pass — documented gaps, see `../../shell-guardrails/README.md`.

The hook is failure-safe: malformed input, a missing dependency, or any internal error exits 0 (allow).

## Steps

### 1. Ask scope

Ask the user: install for **this project only** (`.claude/settings.json`) or **all projects** (`~/.claude/settings.json`)?

### 2. Copy the hook script

New installs take the combined engine — one file, both platforms:

- **Preferred:** [../shell-guardrails/scripts/guard-shell.py](../shell-guardrails/scripts/guard-shell.py) (deploy + wire per that skill's WIRING)
- **Legacy carriers, standalone installs only:** [scripts/block-legacy-cli.ps1](scripts/block-legacy-cli.ps1) (Windows) / [scripts/block-legacy-cli.sh](scripts/block-legacy-cli.sh) (Unix; needs `jq` on PATH, fails open without)

Target locations by scope: `.claude/hooks/` (project) or `~/.claude/hooks/` (global).

> In this repo, `install.ps1` distributes guard-shell.py and the legacy `.ps1` pair to `~/.claude/hooks/`; re-run it after editing anything under `scripts/`. The legacy `.sh` is synced manually. The manual copy is for other machines.

### 3. Add hook to settings

Wire the hook into the settings file per scope and platform: [WIRING.md](WIRING.md). If the
settings file already exists, merge the hook into the existing `hooks.PreToolUse` array; don't
overwrite other settings. With the combined engine you wire ONE entry — it
already includes the git tier, so do not also wire `git-guardrails-claude-code`.

### 4. Ask about customization

Ask if the user wants to add or remove tools from the blocked map. Edit the
legacy tier's tuple in `guard-shell.py` (`legacy_cli_hit`; the `$map` in the
legacy `.ps1` mirrors it), then re-run the corpus.

### 5. Verify

Run the shared corpus (expect every case to pass): [WIRING.md](WIRING.md) §Verify.
