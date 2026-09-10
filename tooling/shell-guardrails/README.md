# shell-guardrails — one policy entry, three carriers

One skill selects the smallest Claude Code / ZCode PreToolUse carrier whose policy matches the
request. The combined engine remains the default; the standalone carriers preserve narrower or
push-blocking behavior without adding catalog entries.

- [SKILL.md](SKILL.md) — carrier selection, combined policy, install, and acceptance.
- [WIRING.md](WIRING.md) — the single hook entry per platform and
  verification.
- [references/push-blocking.md](references/push-blocking.md) and
  [references/modern-cli-only.md](references/modern-cli-only.md) — standalone branches, loaded only
  when their narrower policy is requested. The combined parser contract is in
  [references/execution-domain.md](references/execution-domain.md).
- `scripts/guard-shell.py` — the whole hook. One process, one parse, three
  prioritized tiers (destructive git > POSIX-path-to-native-exe > legacy CLI),
  decided once. Stdlib-only Python 3.6+, same file on Windows (`python`) and
  Unix (`python3`).
- `cases.jsonl` — 206-case source corpus (204 apply on MSYS, 176 on Unix): `id, command,
  expect(block|allow), tier(git|winpath|legacy|none), platform(any|unix|msys)`.
  Written against bash semantics, not against any one implementation: the
  legacy `.sh`/`.ps1` carriers, each scored on its own tier (`--tiers git` /
  `--tiers legacy`, msys profile), miss 19 (git) and 22/20 (legacy) with 4-5
  false blocks; the combined engine scores zero.
- `run_corpus.py` — runner: feeds payloads to any carrier (`.py` via the
  interpreter running the runner, `.ps1` via pwsh, `.sh` via bash), scores
  per-tier misses and false blocks, optional latency bench. Python 3 stdlib
  only.
- `scripts/block-dangerous-git.*` and `scripts/block-legacy-cli.*` — standalone carriers retained
  for exact push-blocking or modern-CLI-only policies.

## Contract

Any change to the engine or the policy tables keeps the corpus green on both
platform profiles:

```bash
python run_corpus.py scripts/guard-shell.py --platform unix
python run_corpus.py scripts/guard-shell.py --platform msys
```

`--platform` forces the hook's own platform gate, so either profile scores on any host; CI scores
the unix profile in the `tests` matrix on both OSes (host detection on Linux, gate forced off on
Windows), the msys profile on a forced Linux leg there, and the msys profile by host detection in
`windows-gate`. These lines run
unchanged under Git Bash on Windows. Use `python`; on Unix substitute `python3`.

Tier 2 (POSIX paths to native executables) is Windows/MSYS only — an msys/
cygwin `OSTYPE` enables it, any other `OSTYPE` (WSL included) disables it,
and without `OSTYPE` (cmd.exe spawns) `sys.platform` decides;
`GUARD_SHELL_FORCE_MSYS=1`/`=0` overrides for testing in either direction. Tier 2 also covers Android:
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

Prefilters short-circuit commands with no trigger substring before parsing. Recorded samples
are measurements, not a constant-time bound on input size. Measured: ~35 ms per call on Windows Python 3.12, ~32 ms on macOS
CLT Python 3.9 (interpreter start dominates); the legacy `.ps1` pair behind
a pwsh spawn costs ≈470 ms per call, and the legacy `.sh` pair ≈1.2 s on a
single 10 KB command.
