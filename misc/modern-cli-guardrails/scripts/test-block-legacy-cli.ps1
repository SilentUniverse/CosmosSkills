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

# Should BLOCK (exit 2).
Test-Case 'grep'          'grep -r foo .'        2
Test-Case 'find'          'find . -name x'       2
Test-Case 'cat'           'cat file'             2
Test-Case 'ls'            'ls -la'               2
Test-Case 'sed'           'sed -i s/a/b/ f'      2
Test-Case 'pipe-cat'      'rg foo | cat'         2

# Should ALLOW (exit 0) — modern tools.
Test-Case 'rg'            'rg foo'               0
Test-Case 'fd'            'fd . src'             0
Test-Case 'eza'           'eza -l'               0
Test-Case 'sd'            'sd a b f'             0

# Should ALLOW (exit 0) — look-alikes that must not false-positive.
Test-Case 'ripgrep'       'ripgrep --version'    0
Test-Case 'fdfind'        'fdfind'               0
Test-Case 'path-cat'      'bat cat/notes.md'     0

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
