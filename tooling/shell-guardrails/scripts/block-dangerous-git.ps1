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
    # Strip heredoc bodies: data, not commands. The terminator's newline stays
    # in the text (lookahead), so the line after EOF keeps its own line —
    # consuming it would glue `git reset --hard` onto the opener as data.
    $stripped = [regex]::Replace(
        $command,
        '(?ms)<<\s*-?\s*["'']?(\w+)["'']?\r?\n.*?^\1(?=\r?\n|$)',
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
        # Command position (mirrors guard-shell.py): the first token after
        # VAR=val assignments, wrapper words, and wrapper flag+value pairs.
        # Windows resolves executable names case-insensitively, so GIT reaches
        # git.exe and heads fold case; git's own flags stay case-sensitive
        # (-ceq/-ccontains below: -d vs -D differ).
        $wrappers = @('sudo', 'env', 'nohup', 'nice', 'timeout', 'time', 'xargs',
                      'stdbuf', 'watch', 'command', 'builtin', 'setsid', 'exec')
        $wrapperValueFlags = @{
            'sudo'    = @('-u', '-g', '-p', '--user', '--group')
            'env'     = @('-u', '--unset', '-S', '--split-string')
            'timeout' = @('-k', '--kill-after', '--signal', '-s')
            'nice'    = @('-n', '--adjustment')
            'xargs'   = @('-I', '-E', '-n', '-P', '-s', '-L')
            'stdbuf'  = @('-o', '-e', '-i')
            'watch'   = @('-n', '-g')
        }
        $prev = ''
        $pendingValue = $false
        $ci = -1
        $cmdWord = ''
        for ($i = 0; $i -lt $tokens.Count; $i++) {
            # Quote-stripped execution view: bash concatenates `"g"it` into git.
            $tk = $tokens[$i].Replace('"', '').Replace("'", '')
            if ($pendingValue) { $pendingValue = $false; continue }
            if ($tk -match '^[A-Za-z_][A-Za-z0-9_]*=') { continue }
            $word = ($tk -replace '\\', '/') -split '/' | Select-Object -Last 1
            if ($word.ToLower().EndsWith('.exe')) { $word = $word.Substring(0, $word.Length - 4) }
            $folded = $word.ToLower()
            if ($wrappers -contains $folded) { $prev = $folded; continue }
            if ($prev) {
                if ($tk.StartsWith('-')) {
                    # -ccontains: PS -contains is case-insensitive and would
                    # read xargs -i as -I, swallowing the git that follows.
                    if ($wrapperValueFlags[$prev] -ccontains $tk) { $pendingValue = $true }
                    continue
                }
                if ($tk -match '^\d+([.]\d+)?[smh]?$') { continue }
            }
            $ci = $i
            $cmdWord = $folded
            break
        }
        if ($ci -lt 0 -or $cmdWord -cne 'git') { continue }
        if ($ci + 1 -gt $tokens.Count - 1) { continue }

        # Cleaned tokens after `git`: value-taking flags (-C <path>, -c <k=v>, …)
        # drop themselves AND their value, so neither is mistaken for the
        # subcommand or a path operand (git -C . checkout x must not see '.').
        $knownValueFlags = @('-C', '-c', '--git-dir', '--work-tree', '--namespace')
        $after = [System.Collections.Generic.List[string]]::new()
        for ($j = $ci + 1; $j -lt $tokens.Count; $j++) {
            $t2 = $tokens[$j].Replace('"', '').Replace("'", '')
            if ($knownValueFlags -ccontains $t2) { $j++; continue }
            $after.Add($t2)
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
            'reset'    { if ($rest -ccontains '--hard') { 'git reset --hard' } }
            'clean'    {
                $f = $rest | Where-Object { $_.Length -gt 1 -and $_.StartsWith('-') -and $_.TrimStart('-') -match 'f' }
                if ($f) { "git clean ($f)" }
            }
            'checkout' { if ($rest -contains '.') { 'git checkout .' } }
            'restore'  { if ($rest -contains '.') { 'git restore .' } }
        }
        if ($why) {
            [Console]::Error.WriteLine(
                "BLOCKED: destructive git operation ($why). The user has reserved these operations for themselves; " +
                "use the /commit workflow or ask the user to run it by hand.")
            exit 2
        }
    }

    exit 0
}
catch {
    # Any unexpected failure — don't block.
    exit 0
}
