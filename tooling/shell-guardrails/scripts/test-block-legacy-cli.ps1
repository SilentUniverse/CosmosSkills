# Regression test for block-legacy-cli.ps1 — run after editing the tool map.
#   pwsh -NoProfile -File .\test-block-legacy-cli.ps1
# Feeds fake PreToolUse payloads to the hook and asserts the exit code.

$hook = Join-Path $PSScriptRoot 'block-legacy-cli.ps1'
# PS7 if present, else Windows PowerShell 5.1 (most machines ship only 5.1).
$ps = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$failures = 0

function Test-Case {
    param([string]$Name, [string]$Command, [int]$Expected, [hashtable]$Env = @{})

    $payload = @{ tool_input = @{ command = $Command } } | ConvertTo-Json -Compress

    foreach ($k in $Env.Keys) { Set-Item -Path "Env:$k" -Value $Env[$k] }
    # Stdin via temp file (Start-Process -RedirectStandardInput): piping through
    # a PS5.1 host intermittently hands the child an empty stdin (whole run
    # fail-opens); a file feed is deterministic on both 5.1 and 7.
    $tmp = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllText($tmp, $payload, [System.Text.Encoding]::ASCII)
    $p = Start-Process -FilePath $ps -ArgumentList @('-NoProfile', '-File', $hook) `
        -RedirectStandardInput $tmp -NoNewWindow -Wait -PassThru
    Remove-Item $tmp -ErrorAction SilentlyContinue
    $actual = $p.ExitCode
    foreach ($k in $Env.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }

    if ($actual -eq $Expected) {
        Write-Host "PASS  $Name (exit $actual)"
    } else {
        Write-Host "FAIL  $Name (expected $Expected, got $actual)" -ForegroundColor Red
        $script:failures++
    }
}

# Should BLOCK (exit 2) — plain host-side legacy tools.
Test-Case 'grep'          'grep -r foo .'        2
Test-Case 'find'          'find . -name x'       2
Test-Case 'sed'           'sed -i s/a/b/ f'      2
Test-Case 'multiline-sed' "echo hi`nsed -i s/a/b/ f" 2
Test-Case 'pipe-grep'     'adb logcat -d | grep -i crash' 2   # grep runs on the host
Test-Case 'cmdsub-grep'   'echo $(grep -r x .)'  2

# Should BLOCK (exit 2) — legacy tool behind a shell keyword or wrapper prefix.
Test-Case 'for-do-find'   'for d in a b; do find $d -name x; done'   2
Test-Case 'for-do-sed'    'for f in *.txt; do sed -i s/a/b/ $f; done' 2
Test-Case 'sudo-find'     'sudo find . -name x'                      2
Test-Case 'env-find'      'env find . -name x'                       2
Test-Case 'time-find'     'time find .'                              2
Test-Case 'timeout-find'  'timeout find .'                           2
Test-Case 'sudo-env-find' 'sudo env find .'                          2
Test-Case 'xargs-grep'    'cat f | xargs grep y'                     2
Test-Case 'timeout-num'   'timeout 5 find .'                         2
Test-Case 'timeout-suffix' 'timeout 1.5s find .'                     2
Test-Case 'env-flag'      'env -i find .'                            2
Test-Case 'env-varval'    'env FOO=bar find .'                       2
Test-Case 'nice-flag-num' 'nice -n 5 find .'                         2
Test-Case 'wrapper-chain' 'sudo env -i timeout 5 find .'             2
Test-Case 'xargs-flag'    'cat f | xargs -0 grep y'                  2
Test-Case 'varval-prefix' 'FOO=1 find .'                             2
Test-Case 'msys-prefix'   'MSYS_NO_PATHCONV=1 find .'                2
Test-Case 'backtick-sub'  'echo `find .`'                            2
Test-Case 'bang-space'    '! find .'                                 2
Test-Case 'subshell-paren' '(find .)'                                2

# Should BLOCK (exit 2) — host pipeline on the same line as a heredoc opener.
Test-Case 'heredoc-pipe'  "cat notes <<EOF | grep x`nhello`nEOF" 2

# Should ALLOW (exit 0) — remote-exec segments (device / container / WSL / remote shells).
Test-Case 'adb-plain'       'adb shell ls /sdcard'                          0
Test-Case 'adb-quoted-semi' 'adb shell "ls /sdcard; echo done"'             0
Test-Case 'adb-quoted-pipe' 'adb shell "ps -A | grep system"'               0
Test-Case 'adb-serial'      'adb -s emulator-5554 shell "cd /data && ls"'   0
Test-Case 'ssh-remote'      'ssh user@host "ls && grep x /var/log/syslog"'  0
Test-Case 'docker-exec'     'docker exec web ls /etc'                       0
Test-Case 'wsl-ls'          'wsl ls ~'                                      0

# Should ALLOW (exit 0) — modern tools.
Test-Case 'rg'            'rg foo'               0
Test-Case 'fd'            'fd . src'             0
Test-Case 'sd'            'sd a b f'             0

# Should ALLOW (exit 0) — modern tool behind the same prefixes, and keyword-only segments.
Test-Case 'xargs-rg'      'cat f | xargs rg y'   0
Test-Case 'for-do-fd'     'for f in *.txt; do sd a b $f; done' 0
Test-Case 'do-then-only'  'do then done'         0
Test-Case 'quoted-do'     'echo "do find the thing"' 0
Test-Case 'uppercase-do'  'DO find .'            0
Test-Case 'bare-env'      'env'                  0
Test-Case 'time-help'     'time --help'          0
Test-Case 'dash-arg'      'cat - | xargs cat'    0
Test-Case 'msys-adb'      'MSYS_NO_PATHCONV=1 adb shell find /sdcard' 0
Test-Case 'quoted-backtick' 'echo "`grep x`"'    0
Test-Case 'paren-alike'   '(findus)'             0
Test-Case 'rg-eq-arg'     'rg pattern=x file'    0

# Should ALLOW (exit 0) — ls is not in the map (too frequent to replace).
Test-Case 'ls'            'ls -la'               0

# Should ALLOW (exit 0) — look-alikes that must not false-positive.
Test-Case 'ripgrep'       'ripgrep --version'    0
Test-Case 'fdfind'        'fdfind'               0
Test-Case 'path-cat'      'bat cat/notes.md'     0
Test-Case 'quoted-ls-arg' 'echo "ls"'            0

# Should ALLOW (exit 0) — heredoc bodies are data, not commands.
Test-Case 'heredoc-data'  "git commit -F- <<'EOF'`nfix: find the bug`nEOF"  0

# Should ALLOW (exit 0) — escape hatches.
Test-Case 'escape-comment' "# force-legacy`ngrep foo"  0
Test-Case 'escape-env'     'grep foo'            0  @{ ALLOW_LEGACY_CLI = '1' }

# Should BLOCK (exit 2) — POSIX path tokens handed to native executables.
Test-Case 'python-tmp-arg'   'python x.py /tmp/f'          2
Test-Case 'node-drive-path'  'node s.js /c/Users'          2
Test-Case 'py-tmp-bare'      'python x.py /tmp'            2
Test-Case 'cmd-quoted-tmp'   'cmd //c "python /tmp/x.py"'  2

# Should ALLOW (exit 0) — path-world guard does not fire.
Test-Case 'cmd-double-slash' 'cmd //c dir'                 0
Test-Case 'cmd-dir-switches-quoted' 'cmd //c "dir /a /b D:\x 2>nul"' 0  # CLAUDE.md §8 check
Test-Case 'cmd-dir-switches-bare'   'cmd //c dir /a /b D:\Code'      0  # CLAUDE.md §8 check
Test-Case 'redirect-devnull' 'python x.py 2>/dev/null'     0
Test-Case 'rg-normal-args'   'rg pattern src'              0
Test-Case 'cp-to-tmp-bash'   'cp x /tmp/'                  0
Test-Case 'multi-letter-dir' 'python x.py /tests'          0

# Should ALLOW (exit 0) — robustness.
Test-Case 'empty'         ''                     0

if ($failures -gt 0) {
    Write-Host "`n$failures test(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "`nAll tests passed."
exit 0
