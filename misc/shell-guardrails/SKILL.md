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
| 2 — path correctness | POSIX path tokens (`/tmp/…`, `/c/…`) handed to native Windows executables (python/node/rg/…), and unquoted Android device paths (`/sdcard/…`) handed to `adb`/`fastboot` — MSYS mangles both before the target sees them | none — `# force-legacy` must not bypass a correctness rule |
| 3 — modern CLI | `grep`/`find`/`sed` as the command word of a host-side segment | `# force-legacy` line or `ALLOW_LEGACY_CLI=1` |

Tier 3 is the only preference tier and stays fail-open on ambiguity: unclear
constructs are allowed, not guessed into a block.

## Execution-domain model (what counts as a HOST-side command)

- Quoted text is data — `adb shell "ps -A | grep system"`, `ssh host "git push"` never block (device/remote side).
- But `$(…)` and `` `…` `` interiors ARE host code, even inside double quotes — `echo "$(grep x)"` blocks.
- `[[ … ]]` test interiors are data (regex operands), except substitutions — `[[ $(grep -c x f) -gt 1 ]]` blocks, `[[ foo =~ (grep|find) ]]` passes.
- `name=( … )` array literal interiors are data — `tools=(grep find sed)` passes.
- `name()` function declarations drop the name (a declaration executes nothing) — `grep() { :; }` passes.
- Comments are dropped to end of line — `echo ok # $(grep x file)` passes.
- `case` zones: patterns are data, bodies are live — `case $x in grep|find) echo y;; esac` passes, `case $x in a) grep y f;; esac` blocks.
- Heredoc bodies are data, stripped before matching (`<<-` tab terminators included); a pipeline on the opener line (`cat f <<EOF | grep x`) still blocks.
- Command position = the segment's command word, **basename-normalized** (`/usr/bin/git`, `/usr/bin/grep` count), reachable through a prefix chain of keywords (`if/elif/while/until/then/do/else/for/in/case/esac/!/{/}…`), wrappers (`sudo/env/nohup/nice/timeout/time/xargs/stdbuf/watch/command/builtin/setsid/exec`), `VAR=val` assignments, and per-wrapper value-taking flags (`sudo -u root`, `env -u VAR`, `timeout --signal TERM 5`, `nice -n 5`, `xargs -I {}`). `echo sudo git push` and `adb shell sudo git push` are NOT calls; `command -v grep` only prints a path and never blocks.
- Static quoted payloads of `bash/sh/zsh -c` and `eval` run on this host and are re-scanned (depth-capped): `bash -c 'git push'`, `eval 'grep x'` block.
- Host pipelines after remote commands still block: `adb logcat -d | grep x` (that grep runs on the host) — use `rg`.
- Redirect targets are bash-side, not native-exe arguments: `python x.py > /tmp/out` is allowed; `python x.py /tmp/out` still blocks.
- Tier 2 is Windows/MSYS only (an msys/cygwin `OSTYPE` enables it, any other `OSTYPE` — WSL included — disables it, and without `OSTYPE` the cmd.exe-spawned hook falls back to `sys.platform`; `GUARD_SHELL_FORCE_MSYS=1` for tests) — on macOS/Linux, `python3 x.py /tmp/f` is valid and never blocked. On Git Bash, `bash -c 'python x.py /tmp/f'` blocks too: static payloads of local shells re-scan under every tier.
- Android device paths: an unquoted `/sdcard/…` (or `/data`, `/system`, …) argument to `adb`/`fastboot` blocks with the working forms — MSYS rewrites leading-/ arguments into Windows paths before the device sees them, so `adb pull /sdcard/x out/` and `adb shell ls /sdcard` fail at runtime. Quoted device commands (`adb shell "dump /sdcard/x"`), `//` on pull/push remote paths, and `MSYS_NO_PATHCONV=1` prefixes (with Windows-form local paths) stay allowed. Host-side filters after adb still need modern tools: `adb logcat -d | rg x`.

Known limits (fail-open by design): dynamic payloads (`eval "$cmd"`,
`bash -c "$var"`) and dynamic command words (`x=git; $x push`) cannot be
judged statically and pass.

## Perf contract

Necessary-condition prefilters run first — commands containing no `git` /
`grep|find|sed` / (on MSYS) POSIX-path token never reach the parser at all,
and long inputs cost the same as short ones (single-pass scan). Measured on a
Windows dev box (Python 3.12): bare interpreter start ≈ 24 ms, full hook
≈ 35 ms per Bash call; the slowest measured case (a block with full parse)
was 45 ms. On macOS (CommandLineTools Python 3.9): ≈ 32 ms per call, flat
across a 10 KB command. For scale, the legacy `.ps1` pair behind a pwsh
spawn costs ≈ 470 ms per call, and the legacy `.sh` pair ≈ 1.2 s on a
single 10 KB command.

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

Primary: the shared corpus (expect every case to pass on both platform
profiles; `run_corpus.py` feeds payloads and asserts exit codes without
executing anything):

```bash
python3 run_corpus.py scripts/guard-shell.py
GUARD_SHELL_FORCE_MSYS=1 python3 run_corpus.py scripts/guard-shell.py --platform msys
python3 run_corpus.py scripts/guard-shell.py --bench   # latency guard
```

Then the spot checks in [WIRING.md](WIRING.md) §Verify for the deployed copy.
