# Wiring — settings.json and verification

Loaded on demand by [SKILL.md](SKILL.md) steps 3 and 5. The blocked-subcommand list and
token-level matching rules live in SKILL.md.

## Preferred: the combined engine

New installs wire ONE entry — `shell-guardrails/scripts/guard-shell.py` covers
the destructive-git tier of this skill plus the legacy-CLI and path-world
tiers in one process. Deploy and wire it per
[../shell-guardrails/WIRING.md](../shell-guardrails/WIRING.md); do not also
wire `modern-cli-guardrails`.

## Legacy carriers (machines not yet rewired)

**Windows / PowerShell** invokes the `.ps1` through `pwsh` (5.1-compatible;
write `powershell` on machines without PS7):

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

On Unix/WSL, point `command` at the `.sh` instead (e.g.
`"$CLAUDE_PROJECT_DIR"/.claude/hooks/block-dangerous-git.sh`; needs `jq` on
PATH, fails open without). Composes with `modern-cli-guardrails` as a second
array entry — legacy carriers are single-tier by design.

## Global (`~/.claude/settings.json`)

**Windows 写绝对路径**，命令里不要出现 `$HOME` / `$USERPROFILE`。Grok 会在 spawn 前展开 `$VAR`，变量不存在就标 `[hooks: 1 failed]`，hook 根本不跑。`$CLAUDE_PROJECT_DIR` 由 runner 注入，项目级接线可用。

## ZCode (`~/.zcode/cli/config.json`)

ZCode runs the same Claude-style command hooks with two differences: config-file hooks stay disabled until `hooks.enabled` is true, and the event lists live under an `events` key. Merge into the existing file; keep `plugins` and anything else already there. `matcher` is a case-sensitive regex: `Bash`, not `bash`. The script deployment stays shared with Claude Code: `install.ps1` copies it to `~/.claude/hooks/`. Exit-code semantics match (`2` blocks with the stderr message, `0` allows).

## Verify

**Shared semantic corpus** (primary; expect every case to pass — for the
combined engine, not the legacy carriers, which predate it):

```bash
python3 ../../shell-guardrails/run_corpus.py ../../shell-guardrails/scripts/guard-shell.py --bench
```

**Windows / PowerShell** — the bundled suite for the legacy `.ps1` carrier
(expect "All tests passed."):

```powershell
pwsh -NoProfile -File scripts\test-block-dangerous-git.ps1
```

No PS7 on the machine? Same command with `powershell`; the suite self-selects the interpreter.

**Unix spot check** (jq required for the legacy `.sh` carrier):

```bash
echo '{"tool_input":{"command":"git push origin main"}}' | <path-to-script.sh>
echo $?   # expect 2
```

A blocked command exits 2 and prints a BLOCKED message to stderr; an allowed command exits 0 with no output.
