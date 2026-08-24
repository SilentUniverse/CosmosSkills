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
# A second guard blocks POSIX path tokens (/tmp, /c/...) handed to native
# Windows executables — those paths only resolve inside the MSYS world
# (windows-cli.md, "two path worlds"). cmd's single-letter switches (/a, /b)
# collide with drive paths, so a cmd-headed segment skips bare /<letter> tokens.
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
    # host shell. Unquoted | & ; ( ` (command substitution) and newlines split;
    # each segment's first word is its command position.
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
        elseif ('|', '&', ';', '(', '`', "`n" -contains $c) {
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

    # Before the command word, skip shell keywords (`do find ...`), wrappers
    # with their flags and args (`sudo find`, `timeout 5 find`, `env -i find`),
    # and VAR=val prefixes (`MSYS_NO_PATHCONV=1 find ...`) - the legacy tool
    # still runs, so the match must see it. Flags/numbers/VAR=val skip only
    # after a keyword or wrapper, so a plain segment starting with `-` is kept.
    $skipWords = @('do', 'then', 'else', '!', '{', 'sudo', 'env', 'nohup', 'nice', 'timeout', 'time', 'xargs')

    foreach ($seg in $segs) {
        $t = $seg.Trim()
        if (-not $t) { continue }

        $toks = @($t -split '\s+')
        $i = 0; $skipped = $false
        while ($i -lt $toks.Count) {
            $w = $toks[$i]
            if ($skipWords -ccontains $w) { $i++; $skipped = $true; continue }
            if ($w -cmatch '^[A-Za-z_][A-Za-z0-9_]*=') { $i++; $skipped = $true; continue }
            if ($skipped -and ($w -cmatch '^-' -or $w -cmatch '^\d+(\.\d+)?[smh]?$')) { $i++; continue }
            break
        }
        if ($i -ge $toks.Count) { continue }
        $t = ($toks[$i..($toks.Count - 1)] -join ' ')

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

        # Path-world guard: native Windows executables cannot resolve POSIX path
        # tokens — /tmp is an MSYS virtual mount, /c/ a drive form; a native
        # process resolves them as <cwd-drive>:\tmp or fails outright.
        if ($t -match '^(?:python3?|py|pwsh|powershell|cmd|node|rg|fd|bat|jq|yq|sd)(?![\w./-])') {
            # cmd-headed segments: bare single-letter tokens (/a, /b) are cmd/dir
            # switches, never paths — skipping them keeps the CLAUDE.md §8 check
            # `cmd //c dir /a /b <path>` allowed. /tmp (any form) and /<letter>/...
            # drive paths still block.
            $cmdSwitchesOk = $t -match '^cmd(?![\w./-])'
            foreach ($tok in ($t -split '\s+')) {
                if ($cmdSwitchesOk -and $tok -match '^/[A-Za-z]$') { continue }
                if ($tok -match '^/(?:tmp|[A-Za-z])(?:/|$)') {
                    [Console]::Error.WriteLine(
                        "BLOCKED: POSIX path '$tok' handed to a native Windows executable. " +
                        "Native processes only understand Windows absolute paths. " +
                        "Temp files: use `$env:TEMP (from bash: cygpath -w `$TEMP); " +
                        "other paths: convert with cygpath -w first. " +
                        "If truly unavoidable, put '# force-legacy' on its own line first, or set ALLOW_LEGACY_CLI=1.")
                    exit 2
                }
            }
        }
    }

    exit 0
}
catch {
    # Any unexpected failure — don't block.
    exit 0
}
