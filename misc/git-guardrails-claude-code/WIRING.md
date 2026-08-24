# Wiring — settings.json and verification

Loaded on demand by [SKILL.md](SKILL.md) steps 3 and 5. The blocked-subcommand list and
token-level matching rules live in SKILL.md.

## Project (`.claude/settings.json`)

**Windows / PowerShell** invokes the script through `pwsh` (on machines without PS7, write `powershell` in the command instead — the hook scripts are 5.1-compatible):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/block-dangerous-git.ps1\""
          }
        ]
      }
    ]
  }
}
```

On Unix/WSL, point `command` at the `.sh` script instead (e.g. `"$CLAUDE_PROJECT_DIR"/.claude/hooks/block-dangerous-git.sh`).

## Global (`~/.claude/settings.json`)

**Windows 写绝对路径**，命令里不要出现 `$HOME` / `$USERPROFILE`。Grok 会在 spawn 前展开 `$VAR`，变量不存在就标 `[hooks: 1 failed]`，hook 根本不跑。`$CLAUDE_PROJECT_DIR` 由 runner 注入，项目级接线可用。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"C:/Users/<you>/.claude/hooks/block-dangerous-git.ps1\""
          }
        ]
      }
    ]
  }
}
```

## Verify

**Windows / PowerShell** — run the bundled regression suite (expect "All tests passed."):

```powershell
pwsh -NoProfile -File scripts\test-block-dangerous-git.ps1
```

No PS7 on the machine? Same command with `powershell` — the suite self-selects the interpreter.

**Unix / WSL** (the `.sh` needs `jq` on PATH — missing jq fails open):

```bash
echo '{"tool_input":{"command":"git push origin main"}}' | <path-to-script.sh>
echo $?   # expect 2
```

A blocked command exits 2 and prints a BLOCKED message to stderr; an allowed command exits 0 with no output.
