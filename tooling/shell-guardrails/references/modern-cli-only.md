# Modern CLI-only carrier

Loaded when the user wants modern CLI and MSYS path enforcement without Git restrictions.

## Policy

The standalone carrier blocks host-side `grep`, `find`, and `sed` command words and points to `rg`,
`fd`, and `sd`; `ls` remains allowed. It also blocks POSIX path tokens passed to native Windows
executables under MSYS and unquoted Android device paths that MSYS would rewrite.

Remote command arguments, quoted data, heredocs, comments, array literals, test operands, case
patterns, lookups such as `command -v`, and tool-name lookalikes remain allowed. Host pipelines and
command substitutions remain executable host code. `# force-legacy` bypasses only the tool preference,
never path correctness. The carrier fails open on malformed input, missing dependencies, and dynamic
forms it cannot judge.

## Install and wire

Copy [block-legacy-cli.ps1](../scripts/block-legacy-cli.ps1) on Windows or
[block-legacy-cli.sh](../scripts/block-legacy-cli.sh) on Unix to the selected `.claude/hooks/`
directory. The Unix carrier requires `jq` and fails open when it is missing.

Merge one Claude Code `hooks.PreToolUse` entry with matcher `Bash`. Invoke the Windows carrier through
`pwsh -NoProfile -File` or Windows PowerShell, and invoke the Unix carrier directly. For ZCode, place
the entry under `hooks.events.PreToolUse` and enable hooks. Use an absolute path for global Windows
wiring; project wiring may use `$CLAUDE_PROJECT_DIR`.

Use the JSON shape in [WIRING.md](../WIRING.md), replacing the combined-engine command with the
selected carrier invocation.

## Verify

Run the bundled PowerShell suite when available:

```powershell
pwsh -NoProfile -File tooling\shell-guardrails\scripts\test-block-legacy-cli.ps1
```

Otherwise feed quoted JSON payloads to the deployed carrier. Confirm `grep -r foo .` exits 2 and
`rg foo` exits 0; the payload is parsed but never executed.
