---
name: shell-guardrails
description: Set up a single Claude Code / ZCode PreToolUse hook that guards every Bash tool call with three prioritized tiers — destructive git operations (hard, no escape), POSIX paths handed to native Windows executables (hard, no escape), and legacy CLI tools grep/find/sed (block with force-legacy escape hatch). One self-contained Python script, one process, one parse; replaces wiring the separate modern-cli-guardrails and git-guardrails-claude-code hooks. Use when the user wants to install, rewire, or tune the combined shell guardrail hook.
disable-model-invocation: true
---

# Setup Shell Guardrails (combined)

One PreToolUse hook, one Python process per Bash tool call, three policy tiers.
Supersedes dual wiring (`modern-cli-guardrails` + `git-guardrails-claude-code`):
the two separate hooks each spawn their own interpreter, so ZCode's sequential
hook execution pays twice; this script decides everything in one process.
A Python interpreter starts in ~25 ms where pwsh needs ~210 ms (measured), so
the guardrail costs ~35 ms per Bash call end to end.

## Policy tiers (evaluated in this order, first hit wins)

| Tier | Rule | Escape hatch |
|---|---|---|
| 1 — destructive git | `git push`, `reset --hard`, `clean -f…`, `branch -D`, `checkout .`, `restore .` in host command position | none, by design |
| 2 — path correctness | POSIX path tokens (`/tmp/…`, `/c/…`) handed to native Windows executables (python/node/rg/…) | none — `# force-legacy` must not bypass a correctness rule |
| 3 — modern CLI | `grep`/`find`/`sed` as the command word of a host-side segment | `# force-legacy` line or `ALLOW_LEGACY_CLI=1` |

Tier 3 is the only preference tier and stays fail-open on ambiguity: unclear
constructs are allowed, not guessed into a block.

## Execution-domain model (what counts as a HOST-side command)

- Quoted text is data — `adb shell "ps -A | grep system"`, `ssh host "git push"` never block (device/remote side).
- But `$(…)` and `` `…` `` interiors ARE host code, even inside double quotes — `echo "$(grep x)"` blocks.
- `name=( … )` array literals are data; `arr=(find grep)` never blocks.
- Heredoc bodies are data, stripped before matching; a pipeline on the opener line (`cat f <<EOF | grep x`) still blocks.
- Command position = the segment's command word, reachable through a prefix chain of keywords (`if/while/until/then/do/else/!/{`), wrappers (`sudo/env/nohup/nice/timeout/time/xargs/stdbuf/watch/command/builtin/setsid/exec`), `VAR=val` assignments, and wrapper flags with their values (`env -u VAR find`, `nice -n 5 find`). `echo sudo git push` and `adb shell sudo git push` are NOT calls.
- Host pipelines after remote commands still block: `adb logcat -d | grep x` (that grep runs on the host) — use `rg`.
- Redirect targets are bash-side, not native-exe arguments: `python x.py > /tmp/out` is allowed; `python x.py /tmp/out` still blocks.

Beyond first-word matching, command-position resolution covers condition
positions (`if grep -q x f`), substitutions (`echo "$(grep x)"`,
`X=$(git push)`, `` echo `git push` ``), wrapper-flag prefixes
(`env -u VAR find`), and keyword-prefixed positions (`then git push`,
`FOO=1 git push`). Data stays data: array literals (`opts=(find grep)`),
redirect targets (`python x.py > /tmp/out`), argument and remote positions
(`echo sudo git push`, `adb shell sudo git push`) never block.

Known limits (fail-open by design): literal `case`-arm commands
(`case $x in a) grep y;; esac`), and string arguments to `eval`/`sh -c`/`cmd /c`
beyond the quoted-path check.

## Perf contract

Necessary-condition prefilters run first — commands containing no `git` /
`grep|find|sed` / POSIX-path token never reach the parser at all. Measured on
a Windows dev box (Python 3.12): bare interpreter start ≈ 24 ms, full hook
≈ 35 ms per Bash call; the slowest measured case (a block with full parse)
was 45 ms. For scale, the same logic behind a pwsh spawn costs ≈ 470 ms per
call.

## Files

- [scripts/guard-shell.py](scripts/guard-shell.py) — the whole hook: stdin JSON
  read (bytes, decoded UTF-8 explicitly — GBK-console safe), heredoc strip,
  prefilters, quote/substitution-aware segment split, command-word walker,
  the three tier checks, ASCII block messages. Stdlib only, Python 3.6+.

The script is platform-neutral: Unix machines can wire the same file with
`python3` instead of running the two `.sh` hooks.

## Steps

### 1. Ask scope

Project only (`.claude/settings.json`) or all projects (`~/.claude/settings.json`)?

### 2. Deploy the script

In this repo, `scripts/install.ps1` copies it to `~/.claude/hooks/`; on other
machines copy `guard-shell.py` there. Requires a Python 3 interpreter on PATH
(`python` on Windows, `python3` on Unix).

### 3. Wire a single hook entry

Follow [WIRING.md](WIRING.md). If the two old hooks are wired, REPLACE both
entries with this one — running all three triples the work for no extra
protection.

### 4. Verify

Run the spot checks in [WIRING.md](WIRING.md) §Verify and confirm the exit codes.
