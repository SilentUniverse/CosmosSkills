# Regression test for block-legacy-cli.ps1 — run after editing the tool map.
#   pwsh -NoProfile -File .\test-block-legacy-cli.ps1
# Feeds fake PreToolUse payloads to the hook and asserts the exit code.

$hook = Join-Path $PSScriptRoot 'block-legacy-cli.ps1'
$failures = 0

function Test-Case {
    param([string]$Name, [string]$Command, [int]$Expected, [hashtable]$Env = @{})

    $payload = @{ tool_input = @{ command = $Command } } | ConvertTo-Json -Compress

    foreach ($k in $Env.Keys) { Set-Item -Path "Env:$k" -Value $Env[$k] }
    $payload | pwsh -NoProfile -File $hook 2>$null | Out-Null
    $actual = $LASTEXITCODE
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

# Should ALLOW (exit 0) — robustness.
Test-Case 'empty'         ''                     0

if ($failures -gt 0) {
    Write-Host "`n$failures test(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "`nAll tests passed."
exit 0
