---
name: shell-guardrails
description: Set up a single Claude Code / ZCode PreToolUse hook that guards every Bash tool call with three prioritized tiers — destructive git operations (hard, no escape), POSIX paths handed to native Windows executables (hard, no escape), and legacy CLI tools grep/find/sed (block with force-legacy escape hatch). One self-contained Python script, one process, one parse; replaces wiring the separate modern-cli-guardrails and git-guardrails-claude-code hooks. Use when the user wants to install, rewire, or tune the combined shell guardrail hook.
disable-model-invocation: true
---

# Setup Shell Guardrails (combined)

One PreToolUse hook, one Python process per Bash tool call, three policy tiers.
Combines the CLI, path, and destructive-git checks in one process. Unlike the standalone git
carrier, this engine allows `git push`; preserve a requested push block when choosing wiring.

## Policy tiers (evaluated in this order, first hit wins)

| Tier | Rule | Escape hatch |
|---|---|---|
| 1 — destructive git | `reset --hard`, `clean -f…`, `branch -D`, `checkout .`, `restore .` in host command position | none, by design |
| 2 — path correctness | POSIX path tokens (`/tmp/…`, `/c/…`) handed to native Windows executables (python/node/rg/…), and unquoted Android device paths (`/sdcard/…`) handed to `adb`/`fastboot` — MSYS mangles both before the target sees them | none — `# force-legacy` must not bypass a correctness rule |
| 3 — modern CLI | `grep`/`find`/`sed` as the command word of a host-side segment | `# force-legacy` line or `ALLOW_LEGACY_CLI=1` |

Tier 3 is the only preference tier and stays fail-open on ambiguity: unclear
constructs are allowed, not guessed into a block.

## Execution-domain model (what counts as a HOST-side command)

- Quoted text is data — `adb shell "ps -A | grep system"`, `ssh host "git reset --hard"` never block (device/remote side).
- But `$(…)` and `` `…` `` interiors ARE host code, even inside double quotes — `echo "$(grep x)"` blocks.
- `[[ … ]]` test interiors are data (regex operands), except substitutions — `[[ $(grep -c x f) -gt 1 ]]` blocks, `[[ foo =~ (grep|find) ]]` passes.
- `name=( … )` array literal interiors are data — `tools=(grep find sed)` passes.
- `name()` function declarations drop the name (a declaration executes nothing) — `grep() { :; }` passes.
- Comments are dropped to end of line — `echo ok # $(grep x file)` passes.
- `case` zones: patterns are data, bodies are live — `case $x in grep|find) echo y;; esac` passes, `case $x in a) grep y f;; esac` blocks.
- Heredoc bodies are data, stripped before matching (`<<-` tab terminators included); a pipeline on the opener line (`cat f <<EOF | grep x`) still blocks.
- Command position = the segment's command word, **basename-normalized** (`/usr/bin/git`, `/usr/bin/grep` count), reachable through a prefix chain of keywords (`if/elif/while/until/then/do/else/for/in/case/esac/!/{/}…`), wrappers (`sudo/env/nohup/nice/timeout/time/xargs/stdbuf/watch/command/builtin/setsid/exec`), `VAR=val` assignments, and per-wrapper value-taking flags (`sudo -u root`, `env -u VAR`, `timeout --signal TERM 5`, `nice -n 5`, `xargs -I {}`). `echo sudo git clean -f` and `adb shell sudo git clean -f` are NOT calls; `command -v grep` only prints a path and never blocks.
- Static quoted payloads of `bash/sh/zsh -c` and `eval` run on this host and are re-scanned (depth-capped): `bash -c 'git reset --hard'`, `eval 'grep x'` block.
- Host pipelines after remote commands still block: `adb logcat -d | grep x` (that grep runs on the host) — use `rg`.
- Redirect targets are bash-side, not native-exe arguments: `python x.py > /tmp/out` is allowed; `python x.py /tmp/out` still blocks.
- Tier 2 is Windows/MSYS only (an msys/cygwin `OSTYPE` enables it, any other `OSTYPE` — WSL included — disables it, and without `OSTYPE` the cmd.exe-spawned hook falls back to `sys.platform`; `GUARD_SHELL_FORCE_MSYS=1` for tests) — on macOS/Linux, `python3 x.py /tmp/f` is valid and never blocked. On Git Bash, `bash -c 'python x.py /tmp/f'` blocks too: static payloads of local shells re-scan under every tier.
- Android device paths: an unquoted `/sdcard/…` (or `/data`, `/system`, …) argument to `adb`/`fastboot` blocks with the working forms — MSYS rewrites leading-/ arguments into Windows paths before the device sees them, so `adb pull /sdcard/x out/` and `adb shell ls /sdcard` fail at runtime. Quoted device commands (`adb shell "dump /sdcard/x"`), `//` on pull/push remote paths, and `MSYS_NO_PATHCONV=1` prefixes (with Windows-form local paths) stay allowed. Host-side filters after adb still need modern tools: `adb logcat -d | rg x`.

Known limits (fail-open by design): dynamic payloads (`eval "$cmd"`,
`bash -c "$var"`) and dynamic command words (`x=git; $x reset --hard`) cannot be
judged statically and pass.

Performance measurements and parser limits: [README.md](README.md).

## Files

- [scripts/guard-shell.py](scripts/guard-shell.py) — the whole hook: stdin JSON
  read (bytes, decoded UTF-8 explicitly — GBK-console safe), heredoc strip,
  prefilters, quote/substitution-aware segment split, command-word walker,
  the three tier checks, ASCII block messages. Stdlib only, Python 3.6+.
- [cases.jsonl](cases.jsonl) + [run_corpus.py](run_corpus.py) — the shared
  semantic corpus (163 allow/block cases across the git / winpath / legacy
  tiers, platform-tagged) and its runner. Every engine change must keep the
  corpus green; it is the behavior contract.

The script is platform-neutral: Unix machines can wire the same file with
`python3` instead of running the two `.sh` hooks.

## Steps

### 1. Resolve scope

Reuse the requested scope or existing target. A repository-scoped request uses
`.claude/settings.json`; all-project scope uses `~/.claude/settings.json`. Ask only if the
intended scope remains unclear after inspecting the request and existing configuration.

### 2. Deploy the script

Copy `guard-shell.py` to `.claude/hooks/` for project scope or `~/.claude/hooks/` for global
scope. Preserve local customizations. Requires a Python 3 interpreter on PATH
(`python` on Windows, `python3` on Unix).

### 3. Wire a single hook entry

Follow [WIRING.md](WIRING.md). Merge the entry while preserving unrelated settings. Replace
superseded entries only when their required protections remain covered; the standalone git
carrier's push block is not covered by this engine.

### 4. Verify

Run [WIRING.md](WIRING.md) §Verify once for the final changed surface.
