# Wiring — settings.json and verification

Loaded on demand by [SKILL.md](SKILL.md) steps 3 and 4. The tier rules live in
SKILL.md; this file only wires and verifies the single hook entry.

## Project (`.claude/settings.json`)

One entry replaces the `block-legacy-cli.ps1` + `block-dangerous-git.ps1`
pair. Windows invokes `python` (a real install on PATH, not the WindowsApps
stub); Unix uses `python3` on the same script.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:/Users/<you>/.claude/hooks/guard-shell.py\""
          }
        ]
      }
    ]
  }
}
```

Unix project scope: `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard-shell.py"`.

## Global (`~/.claude/settings.json`)

Windows 写绝对路径，命令里不要出现 `$HOME` / `$USERPROFILE`。Grok 会在 spawn 前展开 `$VAR`，变量不存在就标 `[hooks: 1 failed]`，hook 根本不跑。`$CLAUDE_PROJECT_DIR` 由 runner 注入，项目级接线可用。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:/Users/<you>/.claude/hooks/guard-shell.py\""
          }
        ]
      }
    ]
  }
}
```

## ZCode (`~/.zcode/cli/config.json`)

Same entry under the `events` key, with `hooks.enabled` true. ZCode runs
command hooks SEQUENTIALLY, so collapsing two hooks into one is where the
latency saving comes from (a pwsh pair costs ≈839 ms per Bash call; this
Python entry ≈35 ms).

```json
{
  "hooks": {
    "enabled": true,
    "events": {
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            {
              "type": "command",
              "command": "python \"C:/Users/<you>/.claude/hooks/guard-shell.py\""
            }
          ]
        }
      ]
    }
  }
}
```

## Verify

Primary — the shared semantic corpus (run from `misc/shell-guardrails/`;
expect every case to pass on both platform profiles):

```bash
python3 run_corpus.py scripts/guard-shell.py
GUARD_SHELL_FORCE_MSYS=1 python3 run_corpus.py scripts/guard-shell.py --platform msys
python3 run_corpus.py scripts/guard-shell.py --bench
```

Spot checks — feed a fake payload and assert the exit code (a blocked command
exits 2 with a BLOCKED message on stderr; an allowed command exits 0 silently):

```powershell
'{"tool_input":{"command":"git reset --hard"}}' | python C:/Users/<you>/.claude/hooks/guard-shell.py; $LASTEXITCODE  # 2
'{"tool_input":{"command":"grep -r foo ."}}'   | python C:/Users/<you>/.claude/hooks/guard-shell.py; $LASTEXITCODE  # 2
'{"tool_input":{"command":"rg foo"}}'          | python C:/Users/<you>/.claude/hooks/guard-shell.py; $LASTEXITCODE  # 0
'{"tool_input":{"command":"adb shell ls"}}'    | python C:/Users/<you>/.claude/hooks/guard-shell.py; $LASTEXITCODE  # 0
```

Quoting matters when the host running the probe already has the hook wired:
trigger words inside the quoted JSON payload are data and pass, but an
unquoted POSIX path or host-side legacy tool in the probe line itself gets
intercepted before the probe runs. When in doubt, run probes from PowerShell
with the payload fully quoted as above.
