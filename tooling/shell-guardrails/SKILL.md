---
name: shell-guardrails
description: >-
  Use when installing or tuning Claude Code or ZCode shell hooks that block destructive Git operations, unsafe cross-shell paths, or legacy CLI tools. Selects a combined default guard or a narrower push-blocking or modern-CLI policy, then verifies the exact hook behavior.
disable-model-invocation: true
---

# Shell Guardrails

Install one policy carrier per requested behavior. Prefer the combined Python engine because one
process and one parse cover destructive Git, cross-shell path correctness, and modern CLI use.

Reuse the requested scope or existing configuration. Keep the selected carrier's protections unless
the user requests a policy change, and preserve unrelated settings and hooks. Editing a source
carrier does not authorize deploying it into a project or user-level hook directory.

## Select the carrier

| Requested policy | Carrier | Load |
|---|---|---|
| Destructive Git, MSYS path safety, and modern CLI; pushes allowed | `scripts/guard-shell.py` | Common path below |
| Block every `git push` as well as destructive Git | Standalone Git carrier | [push-blocking.md](references/push-blocking.md) |
| Only modern CLI and MSYS path safety | Standalone CLI carrier | [modern-cli-only.md](references/modern-cli-only.md) |

Do not replace a push-blocking carrier with the combined engine: the combined Git tier deliberately
allows every `git push`, including forced variants. Avoid duplicate hooks when one selected carrier
covers the whole requested policy.
When a standalone carrier is selected, follow its linked reference instead of the combined sections
below.

## Combined policy

The engine evaluates the first matching tier:

| Tier | Blocks | Escape |
|---|---|---|
| Destructive Git | `reset --hard`, forced `clean`, `checkout .`, `restore .` in host command position | none |
| Path correctness | POSIX paths passed to native Windows executables and unquoted Android device paths affected by MSYS conversion | none |
| Modern CLI | host-side `grep`, `find`, or `sed` command words | `# force-legacy` or launcher-level `ALLOW_LEGACY_CLI=1` |

Branch deletion is deliberately allowed: squash-merged topic branches need `branch -D` for cleanup,
and a dropped ref stays reflog-recoverable. Quoted remote commands are data; host pipelines and command
substitutions are executable host code.
The parser recognizes shell control flow, wrappers, assignments, subshells, static `-c` or `eval`
payloads, comments, heredocs, arrays, tests, case patterns, and redirects. Dynamic command words and
dynamic payloads pass because static analysis cannot judge them reliably.

The path tier activates only for MSYS or Cygwin, or `GUARD_SHELL_FORCE_MSYS=1` in tests. WSL,
macOS, and Linux keep valid POSIX paths. When changing parsing or policy, load the complete
[execution-domain model](references/execution-domain.md). Measurements and retained parser gaps live
in [README.md](README.md).

## Install the combined engine

1. Reuse the requested scope or existing configuration. Project scope uses
   `.claude/settings.json`; all-project scope uses `~/.claude/settings.json`.
2. Copy `scripts/guard-shell.py` to `.claude/hooks/` or `~/.claude/hooks/`. Preserve local
   customizations. Use `python` on Windows and `python3` on Unix.
3. Follow [WIRING.md](WIRING.md) to merge one hook entry without replacing unrelated settings.
4. Apply requested policy changes while retaining every other selected protection.

## Verify

For an engine or policy change, run both non-executing corpus profiles:

```bash
python tooling/shell-guardrails/run_corpus.py tooling/shell-guardrails/scripts/guard-shell.py
GUARD_SHELL_FORCE_MSYS=1 python tooling/shell-guardrails/run_corpus.py tooling/shell-guardrails/scripts/guard-shell.py --platform msys
```

Use `python` (`python3` on Unix); on Windows Git Bash the POSIX env prefix above works unchanged.

For wiring-only work, verify the deployed copy, parsed settings, one blocked payload, and one allowed
payload. A block exits 2 with an ASCII message on stderr; an allow exits 0 silently. Never execute a
destructive command as a probe.
