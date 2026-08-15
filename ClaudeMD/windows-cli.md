# Windows Command Line Reference

Companion to CLAUDE.md §8. The two hard rules live there (directory truth, explicit UTF-8 PowerShell wrapping) — they must fire at action time, so they stay resident. This file holds the lookup content: when to reach for PowerShell natively, and the notes behind the rules.

## When PowerShell native is the right tool (vs bash/GNU tools)

| Situation | Use | Why |
|---|---|---|
| Directory truth incl. hidden/ignored | `Get-ChildItem -Force`, `dir /a` | fd/rg/Glob hide by default |
| Hidden/system attributes, services, processes, registry, scheduled tasks | PS native (`attrib`, `Get-Service`…) | GNU tools can't see Windows objects |
| Bulk rename/move, paths with spaces | `Rename-Item` / `Move-Item` | object pipeline, no re-parsing |
| Encoding-sensitive file I/O from shell | `Get-Content -Encoding UTF8` | bash redirection mangles GBK |
| Long paths (>260), zip | `Expand-Archive` / `\\?\` | GNU tools hit MAX_PATH |
| ADB and device workflows | plain bash (`adb …`) | device output is UTF-8 bytes; wrapping in PowerShell adds GBK |
| Text pipelines, code search, JSON, git | bash + `rg` `sd` `jq` | faster, composable |

## Experiment notes (verified)

- Raw `pwsh` / `powershell.exe` from bash with Chinese output: PS7 raw garbles, PS5.1 raw sometimes clean — never rely on either unwrapped; the §8 wrapper command is the verified-safe form.
- `fd` / Glob / Grep (rg) hide gitignored + hidden + dot files by default; a non-empty directory can read as "empty" until a truth command runs.
- **git-bash rewrites leading-`/` paths in unquoted args to native Windows executables**: `adb shell ls /sdcard` arrives on-device as `ls C:/Program Files/Git/sdcard`. Quote the device command (`adb shell "ls /sdcard"`), or prefix `MSYS_NO_PATHCONV=1` for mixed commands. Verified live on 2026-08-16.
