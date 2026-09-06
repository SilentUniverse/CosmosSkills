# Push-blocking Git carrier

Loaded when the user requires every `git push` to be blocked or wants only Git protections.

## Policy

The standalone carrier blocks host-side forms of:

- every `git push`, including forced variants;
- `git reset --hard`;
- `git clean` with a force flag;
- `git checkout .` and `git restore .`, including `-- .`.

Branch deletion stays allowed: dropping a landed topic ref after a squash merge is routine
cleanup, and a dropped ref remains recoverable through the reflog.

Quoted command text is data. The carrier approximates shell syntax and fails open on ambiguity.
`# force-legacy` never bypasses Git policy.

## Install and wire

Copy [block-dangerous-git.ps1](../scripts/block-dangerous-git.ps1) on Windows or
[block-dangerous-git.sh](../scripts/block-dangerous-git.sh) on Unix to the selected `.claude/hooks/`
directory. The Unix carrier requires `jq` and fails open when it is missing.

Merge a Claude Code `hooks.PreToolUse` entry with matcher `Bash`. On Windows, invoke the deployed
script through `pwsh -NoProfile -File`; use `powershell` when PowerShell 7 is unavailable. On Unix,
invoke `bash "<deployed-hook-path>/block-dangerous-git.sh"`; copied files need no executable bit.
For ZCode, place the same entry under `hooks.events.PreToolUse`
and set `hooks.enabled` to true.

Use the JSON shape in [WIRING.md](../WIRING.md), replacing the combined-engine command with the
selected carrier invocation.

Global Windows wiring uses an explicit absolute path. Project wiring may use
`$CLAUDE_PROJECT_DIR/.claude/hooks/`; preserve unrelated settings and hooks.

## Verify

Run the bundled PowerShell suite when available:

```powershell
pwsh -NoProfile -File tooling\shell-guardrails\scripts\test-block-dangerous-git.ps1
```

Otherwise feed quoted JSON payloads to the same deployed invocation. Confirm `git push origin main`
exits 2 and `git status` exits 0; the payload is parsed but never executed.
