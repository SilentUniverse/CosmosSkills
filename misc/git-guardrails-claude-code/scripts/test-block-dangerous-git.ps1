# Regression test for block-dangerous-git.ps1 — run after editing the rules.
#   pwsh -NoProfile -File .\test-block-dangerous-git.ps1
# Feeds fake PreToolUse payloads to the hook and asserts the exit code.

$hook = Join-Path $PSScriptRoot 'block-dangerous-git.ps1'
$failures = 0

function Test-Case {
    param([string]$Name, [string]$Command, [int]$Expected)

    $payload = @{ tool_input = @{ command = $Command } } | ConvertTo-Json -Compress
    $payload | pwsh -NoProfile -File $hook 2>$null | Out-Null
    $actual = $LASTEXITCODE

    if ($actual -eq $Expected) {
        Write-Host "PASS  $Name (exit $actual)"
    } else {
        Write-Host "FAIL  $Name (expected $Expected, got $actual)" -ForegroundColor Red
        $script:failures++
    }
}

# Should BLOCK (exit 2) — destructive forms, including previously-missed variants.
Test-Case 'push'              'git push'                     2
Test-Case 'push-remote'       'git push origin main'         2
Test-Case 'push-force'        'git push --force origin'      2
Test-Case 'reset-hard'        'git reset --hard HEAD~1'      2
Test-Case 'clean-f'           'git clean -f'                 2
Test-Case 'clean-fd'          'git clean -fd'                2
Test-Case 'clean-xdf'         'git clean -xdf'               2   # was missed by substring matching
Test-Case 'clean-long-force'  'git clean --force'            2
Test-Case 'branch-D'          'git branch -D feat'           2
Test-Case 'branch-del-force'  'git branch --delete --force feat' 2
Test-Case 'checkout-dot'      'git checkout .'               2
Test-Case 'checkout-dd-dot'   'git checkout -- .'            2   # was missed by substring matching
Test-Case 'restore-dot'       'git restore .'                2
Test-Case 'double-space'      'git  push'                    2   # was missed by substring matching
Test-Case 'chained'           'eza -l && git push'           2
Test-Case 'sudo-git-push'     'sudo git push'                2   # wrapper still counts as a call
Test-Case 'git-C-variant'     'git -C ../repo reset --hard' 2   # flags before subcommand

# Should ALLOW (exit 0) — safe operations and quoted/heredoc data.
Test-Case 'commit'            'git commit -m "wip"'          0
Test-Case 'reset-soft'        'git reset --soft HEAD~1'      0
Test-Case 'clean-dry'         'git clean -n'                 0
Test-Case 'branch-d'          'git branch -d merged'         0
Test-Case 'checkout-file'     'git checkout src/app.ts'      0
Test-Case 'checkout-branch'   'git checkout -b feat/x'       0
Test-Case 'restore-file'      'git restore src/app.ts'       0
Test-Case 'rg-quoted'         'rg "git push" docs'           0
Test-Case 'bare-words'        'echo reverted git push today' 0   # word pair in data, not command position
Test-Case 'git-C-dot-status'  'git -C . status'              0   # -C value '.' must not read as checkout .
Test-Case 'echo-quoted'       'echo "git reset --hard"'      0
Test-Case 'commit-msg-quoted' 'git commit -m "fix: revert git push docs"' 0
Test-Case 'heredoc-data'      "git commit -F- <<'EOF'`nmentioned git push in prose`nEOF" 0
Test-Case 'empty'             ''                             0

if ($failures -gt 0) {
    Write-Host "`n$failures test(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "`nAll tests passed."
exit 0
