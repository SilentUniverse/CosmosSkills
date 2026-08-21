# Windows Command Line Reference

Companion to CLAUDE.md §8. The three hard rules live there (directory truth, explicit UTF-8 PowerShell wrapping, PS/cmd never write files) — they must fire at action time, so they stay resident. This file holds the lookup content: when to reach for PowerShell natively, and the notes behind the rules.

## When PowerShell native is the right tool (vs bash/GNU tools)

| Situation | Use | Why |
|---|---|---|
| Directory truth incl. hidden/ignored | `Get-ChildItem -Force`, `dir /a` | fd/rg/Glob hide by default |
| Hidden/system attributes, services, processes, registry, scheduled tasks | PS native (`attrib`, `Get-Service`…) | GNU tools can't see Windows objects |
| Bulk rename/move, paths with spaces | `Rename-Item` / `Move-Item` | object pipeline, no re-parsing |
| Encoding-sensitive file I/O from shell | `Get-Content -Encoding UTF8` | PS5.1 write defaults are three-way broken — see matrix below; read with explicit encoding |
| Long paths (>260), zip | `Expand-Archive` / `\\?\` | GNU tools hit MAX_PATH |
| ADB and device workflows | plain bash (`adb …`) | device output is UTF-8 bytes; wrapping in PowerShell adds GBK |
| Text pipelines, code search, JSON, git | bash + `rg` `sd` `jq` | faster, composable |

## File-writing encodings (codepage 936 host)

| Write form | PS5.1 | PS7 |
|---|---|---|
| `echo x > f` / `Out-File f` | UTF-16LE + BOM (`FF FE`) | UTF-8 no BOM |
| `Out-File -Encoding utf8` / `Set-Content -Encoding UTF8` | UTF-8 **with BOM** (`EF BB BF`) | UTF-8 no BOM |
| `Set-Content f` (bare) | GBK | UTF-8 no BOM |
| `[IO.File]::WriteAllText($p, $s)` | UTF-8 no BOM | UTF-8 no BOM |
| bash redirect of PS output `> f` | GBK | GBK |
| cmd `echo x > f` (any form) | GBK | GBK |

Corruption before the write:

- **BOM-less `.ps1` + `-File`** — PS5.1 parses the script as ANSI; Chinese literals inside it are re-decoded wrong at parse time. Chinese-bearing scripts need a BOM (or stay ASCII).
- **Chinese match-strings in a BOM-less `.ps1`** — construct at runtime from code points (`[string][char]0x5206 + [string][char]0x533A`), never as literals.
- **`\uXXXX` in Edit/Write parameters is decoded to the character by the tool layer** — old_string and new_string come out identical. Use code-point construction.
- **Pipe into PS** — stdin is decoded GBK unless `[Console]::InputEncoding = UTF8` is set before reading (included in the §8 wrapper).

## cmd.exe from git-bash

- `cmd /c` — MSYS rewrites `/c` into a path; cmd then starts an **interactive session** (banner + hang). Use `cmd //c`, or `MSYS_NO_PATHCONV=1 cmd /c`.
- Output, filenames, and redirection are GBK (codepage 936). `cmd //U` switches output to UTF-16 (unreadable to text tools).
- `%VAR%` passes through bash quotes untouched — no escaping needed.
- `cmd //c "a && b"` — `&&` works inside the quoted string.

## Observed behavior

- Raw `pwsh` / `powershell.exe` from bash with Chinese output: PS7 raw garbles, PS5.1 raw sometimes clean — never rely on either unwrapped; the §8 wrapper command is the safe form.
- `fd` / Glob / Grep (rg) hide gitignored + hidden + dot files by default; a non-empty directory can read as "empty" until a truth command runs.
- **git-bash rewrites leading-`/` paths in unquoted args to native Windows executables**: `adb shell ls /sdcard` arrives on-device as `ls C:/Program Files/Git/sdcard`. Quote the device command (`adb shell "ls /sdcard"`), or prefix `MSYS_NO_PATHCONV=1` for mixed commands.
- **Two path worlds** — git-bash's `/tmp` is an MSYS virtual mount; a native process (`python`, `pwsh`, `cmd`, `node`, winget tools) resolves `/tmp` as `<cwd-drive>:\tmp` or fails outright. Hand native processes Windows absolute paths; temp files go to `$env:TEMP` (`cygpath -w "$TEMP"` converts from bash). The modern-cli-guardrails hook blocks POSIX path tokens on native-exe segments.
- **awk keeps a UTF-8 BOM; `Get-Content -Encoding UTF8` strips it** — match line 1 of a possibly-BOM'd file only after `NR == 1 { sub(/^\357\273\277/, "") }`.
