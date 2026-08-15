# Claude Code PreToolUse hook — enforces CLAUDE.md §7 (modern CLI tooling) on Windows (PowerShell).
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if a HOST-side segment of the command invokes a
# forbidden legacy tool.
#
# Matching: only the first word of each segment is checked, so a tool name in
# argument position — `adb shell ls`, `docker exec ctr ls`, `wsl ls` — never
# blocks, and quoted strings plus heredoc bodies are data, not commands. So
# `adb shell "ls; grep x"` passes while `adb logcat -d | grep x` blocks (that
# grep runs on the host).
#
# Failure-safe direction: any parse error, unexpected failure, or explicit
# escape hatch exits 0 (allow). Only a confirmed host-side match exits 2.
#
# All emitted text is ASCII on purpose: PowerShell console output under a GBK
# codepage mangles non-ASCII, and a block message the agent can't read is worse
# than no message.

$ErrorActionPreference = 'Stop'

try {
    # stdin arrives as UTF-8 JSON; decode it as such, not as the console codepage.
    try { [Console]::InputEncoding = [System.Text.Encoding]::UTF8 } catch {}
    $raw = [Console]::In.ReadToEnd()
    $command = [string]($raw | ConvertFrom-Json).tool_input.command
} catch {
    # Malformed / empty input — don't block.
    exit 0
}

if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

# Escape hatch: allow when the command explicitly opts out.
if ($command -match '(?m)^\s*#\s*force-legacy' -or $env:ALLOW_LEGACY_CLI -eq '1') {
    exit 0
}

try {
    # Strip heredoc bodies before matching: lines inside <<'EOF' ... EOF are DATA
    # (commit messages, file content), not commands. English prose routinely starts
    # a line with "find" or "sed" — those must not be blocked.
    $stripped = [regex]::Replace(
        $command,
        '(?ms)<<\s*-?\s*["'']?(\w+)["'']?\r?\n.*?^\1(?:\r?\n|$)',
        '')

    # Split into segments, quote-aware: a separator inside '...'/"..." belongs to
    # the quoted string (e.g. the device command in adb shell "..."), not to the
    # host shell. Unquoted | & ; ( and newlines split; each segment's first word
    # is its command position.
    $segs = [System.Collections.Generic.List[string]]::new()
    $buf = [System.Text.StringBuilder]::new()
    $quote = $null
    $len = $stripped.Length
    for ($i = 0; $i -lt $len; $i++) {
        $c = $stripped[$i]
        if ($quote) {
            if ($c -eq '\' -and $quote -eq '"' -and ($i + 1) -lt $len) {
                [void]$buf.Append($c); [void]$buf.Append($stripped[$i + 1]); $i++
            }
            else {
                if ($c -eq $quote) { $quote = $null }
                [void]$buf.Append($c)
            }
        }
        elseif ($c -eq '\' -and ($i + 1) -lt $len) {
            [void]$buf.Append($c); [void]$buf.Append($stripped[$i + 1]); $i++
        }
        elseif ($c -eq "'" -or $c -eq '"') {
            $quote = $c; [void]$buf.Append($c)
        }
        elseif ('|', '&', ';', '(', "`n" -contains $c) {
            $segs.Add($buf.ToString()); [void]$buf.Clear()
        }
        else {
            [void]$buf.Append($c)
        }
    }
    $segs.Add($buf.ToString())

    # Legacy tool -> modern replacement. ('ls' is not listed: too frequent to force eza.)
    $map = [ordered]@{
        'grep' = 'rg'
        'find' = 'fd'
        'sed'  = 'sd'
    }

    foreach ($seg in $segs) {
        $t = $seg.Trim()
        if (-not $t) { continue }

        foreach ($old in $map.Keys) {
            # Exact first word: the lookahead rejects ripgrep, fdfind, lsd,
            # paths like src/cat/x, and flags glued to the name (ls-la).
            if ($t -match "^$old(?![\w./-])") {
                [Console]::Error.WriteLine(
                    "BLOCKED: '$old' is forbidden on the host shell (CLAUDE.md section 7). " +
                    "Use '$($map[$old])' instead. For routine search/read prefer the built-in Grep/Glob/Read tools. " +
                    "If truly unavoidable, put '# force-legacy' on its own line first, or set ALLOW_LEGACY_CLI=1.")
                exit 2
            }
        }
    }

    exit 0
}
catch {
    # Any unexpected failure — don't block.
    exit 0
}
