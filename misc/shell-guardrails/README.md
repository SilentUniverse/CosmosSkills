# shell-guardrails — one engine, one corpus

The combined PreToolUse guardrail for Bash tool calls (Claude Code / ZCode),
plus the language-agnostic corpus that pins its behavior.

- [SKILL.md](SKILL.md) — setup skill surface: policy tiers, execution-domain
  model, wiring steps.
- [WIRING.md](WIRING.md) — the single hook entry per platform and
  verification.
- `scripts/guard-shell.py` — the whole hook. One process, one parse, three
  prioritized tiers (destructive git > POSIX-path-to-native-exe > legacy CLI),
  decided once. Stdlib-only Python 3.6+, same file on Windows (`python`) and
  Unix (`python3`).
- `cases.jsonl` — 163-case golden corpus: `id, command,
  expect(block|allow), tier(git|winpath|legacy|none), platform(any|unix|msys)`.
  Written against bash semantics, not against any one implementation: the
  legacy `.sh`/`.ps1` carriers score 17+9 misses and 5+2 false blocks against
  it, the combined engine scores zero.
- `run_corpus.py` — runner: feeds payloads to any carrier (`.py` via the
  interpreter running the runner, `.ps1` via pwsh, `.sh` via bash), scores
  per-tier misses and false blocks, optional latency bench. Python 3 stdlib
  only.

## Contract

Any change to the engine or the policy tables keeps the corpus green on both
platform profiles:

```bash
python3 run_corpus.py scripts/guard-shell.py
GUARD_SHELL_FORCE_MSYS=1 python3 run_corpus.py scripts/guard-shell.py --platform msys
```

Tier 2 (POSIX paths to native executables) is Windows/MSYS only — an msys/
cygwin `OSTYPE` enables it, any other `OSTYPE` (WSL included) disables it,
and without `OSTYPE` (cmd.exe spawns) `sys.platform` decides;
`GUARD_SHELL_FORCE_MSYS=1` overrides for testing. Tier 2 also covers Android:
an unquoted device path (`/sdcard/…`) handed to `adb`/`fastboot` fails at
runtime on Git Bash (MSYS rewrites it), so it blocks with the working forms;
quoted device commands and `MSYS_NO_PATHCONV=1` prefixes stay allowed.

## Known static-analysis gaps (documented, fail-open)

- Dynamic payloads (`eval "$cmd"`, `bash -c "$var"`) and dynamic command
  words (`x=git; $x reset --hard`) pass.
- `[[ … ]]` interiors drop quoted `]]` sequences blindly — a test operand
  containing the literal string `]]` can close the zone early (harmless:
  the remainder fails to match any command word).
- Comments inside `$( )` / backtick interiors are not stripped (word-start
  `#` handling covers top-level text only).

## Performance notes

Prefilters short-circuit commands with no trigger substring before any
parsing; the scan is single-pass, so a 10 KB command costs the same as a
short one. Measured: ~35 ms per call on Windows Python 3.12, ~32 ms on macOS
CLT Python 3.9 (interpreter start dominates); the legacy `.ps1` pair behind
a pwsh spawn costs ≈470 ms per call, and the legacy `.sh` pair ≈1.2 s on a
single 10 KB command.
