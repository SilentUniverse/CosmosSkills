# Wiring — settings.json and verification

Loaded on demand by [SKILL.md](SKILL.md) steps 3 and 5. The blocked-tool map
and segment-matching rules live in SKILL.md and `~/.claude/references/cli-tools.md`.

## Preferred: the combined engine

New installs wire ONE entry — `shell-guardrails/scripts/guard-shell.py` covers
this skill's legacy-CLI tier, the path-world tier, AND the destructive-git
tier in one process. Deploy and wire it per
[../shell-guardrails/WIRING.md](../shell-guardrails/WIRING.md); do not also
wire `git-guardrails-claude-code`.

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
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/block-legacy-cli.ps1\""
          }
        ]
      }
    ]
  }
}
```

On Unix/WSL, point `command` at the `.sh` instead (e.g.
`"$CLAUDE_PROJECT_DIR"/.claude/hooks/block-legacy-cli.sh`; needs `jq` on
PATH, fails open without). Composes with `git-guardrails-claude-code` as a
second array entry — legacy carriers are single-tier by design.

## Global (`~/.claude/settings.json`)

**Windows 写绝对路径**，命令里不要出现 `$HOME` / `$USERPROFILE`。Grok 会在 spawn 前展开 `$VAR`，变量不存在就标 `[hooks: 1 failed]`，hook 根本不跑。`$CLAUDE_PROJECT_DIR` 由 runner 注入，项目级接线可用。

## ZCode (`~/.zcode/cli/config.json`)

ZCode runs the same Claude-style command hooks with two differences: config-file hooks stay disabled until `hooks.enabled` is true, and the event lists live under an `events` key. Merge into the existing file; keep `plugins` and anything else already there. `matcher` is a case-sensitive regex: `Bash`, not `bash`. The script deployment stays shared with Claude Code: `install.ps1` copies it to `~/.claude/hooks/`. Exit-code semantics match (`2` blocks with the stderr message, `0` allows).

## Verify

**Shared semantic corpus** (primary; expect every case to pass — it is the
contract for the combined engine; the legacy carriers keep their bundled
suites):

```bash
python3 ../../shell-guardrails/run_corpus.py ../../shell-guardrails/scripts/guard-shell.py --bench
```

**Windows / PowerShell** — the bundled suite for the legacy `.ps1` carrier
(expect "All tests passed."):

```powershell
pwsh -NoProfile -File scripts\test-block-legacy-cli.ps1
```

Or a single spot check on any carrier:

```bash
echo '{"tool_input":{"command":"grep -r foo ."}}' | <path-to-hook>
echo $?   # expect 2
```

A blocked command exits 2 and prints a BLOCKED message to stderr; an allowed command exits 0 with no output.
