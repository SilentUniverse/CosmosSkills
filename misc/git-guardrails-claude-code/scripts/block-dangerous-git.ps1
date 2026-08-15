# Claude Code PreToolUse hook — blocks destructive git commands on Windows (PowerShell).
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if a HOST-side git invocation is destructive.
#
# Matching is token-level: within each host-side segment, every `git` word is
# examined with its subcommand and flags — `git checkout -- .`, `git clean
# -xdf`, double spaces, and flag reordering all match. Quoted strings and
# heredoc bodies are data, so `rg "git push" docs` never blocks.
#
# No escape hatch by design — user-reserved operations (per SKILL.md).
#
# Failure-safe direction: parse errors, missing stdin, or unexpected failures
# exit 0 (allow). Only a confirmed destructive match exits 2.
# All emitted text is ASCII (GBK console safety).

$ErrorActionPreference = 'Stop'

try {
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

try {
    # Strip heredoc bodies: data, not commands.
    $stripped = [regex]::Replace(
        $command,
        '(?ms)<<\s*-?\s*["'']?(\w+)["'']?\r?\n.*?^\1(?:\r?\n|$)',
        '')

    # Split into segments, quote-aware (same discipline as block-legacy-cli):
    # separators inside '...'/"..." belong to the quoted string, not the host shell.
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

    foreach ($seg in $segs) {
        $tokens = @($seg.Trim() -split '\s+')
        # Only a `git` in command position counts: segment-initial, or right
        # after a known wrapper (sudo/env/…). A bare "git push" inside a quoted
        # argument ("revert git push docs") is data, never a call. -ceq/-ccontains:
        # PS comparison is case-insensitive by default; git flags are not (-d vs -D).
        $wrappers = @('sudo', 'env', 'nohup', 'nice', 'timeout', 'xargs')
        for ($i = 0; $i -lt $tokens.Count; $i++) {
            $isCall = ($tokens[$i] -ceq 'git') -and
                ($i -eq 0 -or $wrappers -contains $tokens[$i - 1])
            if (-not $isCall) { continue }
            if ($i + 1 -gt $tokens.Count - 1) { continue }

            # Cleaned tokens after `git`: value-taking flags (-C <path>, -c <k=v>, …)
            # drop themselves AND their value, so neither is mistaken for the
            # subcommand or a path operand (git -C . checkout x must not see '.').
            $knownValueFlags = @('-C', '-c', '--git-dir', '--work-tree', '--namespace')
            $after = [System.Collections.Generic.List[string]]::new()
            for ($j = $i + 1; $j -lt $tokens.Count; $j++) {
                if ($knownValueFlags -contains $tokens[$j]) { $j++; continue }
                $after.Add($tokens[$j])
            }

            # Subcommand = first remaining token that is not a flag.
            $sub = $null
            foreach ($tk in $after) {
                if ($tk -notmatch '^-') { $sub = $tk; break }
            }
            if (-not $sub) { continue }

            $rest = @($after)
            $why = switch ($sub) {
                'push'     { 'git push' }
                'reset'    { if ($rest -contains '--hard') { 'git reset --hard' } }
                'clean'    {
                    $f = $rest | Where-Object { $_.Length -gt 1 -and $_.StartsWith('-') -and $_.TrimStart('-') -match 'f' }
                    if ($f) { "git clean ($f)" }
                }
                'branch'   {
                    if ($rest -ccontains '-D' -or (($rest -ccontains '--delete') -and ($rest -ccontains '--force'))) { 'git branch -D' }
                }
                'checkout' { if ($rest -contains '.') { 'git checkout .' } }
                'restore'  { if ($rest -contains '.') { 'git restore .' } }
            }
            if ($why) {
                [Console]::Error.WriteLine(
                    "BLOCKED: destructive git operation ($why). The user has reserved these operations for themselves — " +
                    "use the /commit workflow or ask the user to run it by hand.")
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
