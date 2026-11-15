<#
.SYNOPSIS
    Windows PowerShell regression harness for verify-artifacts.py.

.DESCRIPTION
    Builds throwaway fixture repos in a temp dir, runs verify-artifacts.py against each
    fixture, asserts exit codes. Interpreter: python, then python3 if python is missing.
    Source is ASCII-only on purpose: PS 5.1 parses a BOM-less .ps1 as ANSI,
    so non-ASCII literals would corrupt.
    Exit codes: 0 = all green, 1 = failures.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File test-verify-artifacts.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vaPy = Join-Path $here "verify-artifacts.py"

$py = $null
foreach ($name in @('python', 'python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    & $cmd.Source -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $cmd.Source; break }
}
if (-not $py) {
    Write-Output "test-verify-artifacts: neither python nor python3 is a working interpreter"
    exit 1
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("va-test-" + [IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $tmp | Out-Null
$failures = [System.Collections.Generic.List[string]]::New()
$passed = 0

function Write-Fixture([string]$RelPath, [string]$Text) {
    $p = Join-Path $script:tmp $RelPath
    $d = Split-Path -Parent $p
    if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    [IO.File]::WriteAllText($p, $Text)
}

function New-FixtureDir([string]$Name) {
    $d = Join-Path $script:tmp $Name
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    return $d
}

function Assert-Case([string]$Name, [string]$Dir, [int]$Expected, [string]$ExpectIn = '') {
    $out = (& $script:py $script:vaPy $Dir 2>&1 | Out-String)
    if ($LASTEXITCODE -ne $Expected) {
        $script:failures.Add("$Name : PY exit $LASTEXITCODE, expected $Expected`n$out")
    } elseif ($ExpectIn -ne '' -and -not $out.Contains($ExpectIn)) {
        $script:failures.Add("$Name : PY output missing '$ExpectIn'`n$out")
    } else { $script:passed++ }
}

# --- shared content ---

$rootLegacy = @'
---
type: codebase
generated: 2026-08-18
---

# demo map

## roster

- `src/gone/` - area deleted since the map was drawn
'@

$blockLegacy = @'
<!-- BEGIN GENERATED codebase (/map) - do not edit between markers; regen: /map src/alpha -->
git_base: abc1234
- invariant one
<!-- END GENERATED codebase -->
'@

# Unit/section rules are covered by tests/test_verify_artifacts.py; this harness only needs a
# structurally valid feature document.
$featureGood = @'
---
type: feature
feature: featA
created: 2026-08-18
---
'@

# --- fixtures ---

Assert-Case "F00 empty repo" (New-FixtureDir "f00") 0

$d = New-FixtureDir "f14"
Write-Fixture "f14/CODEBASE.md" $rootLegacy
Write-Fixture "f14/src/alpha/CLAUDE.md" $blockLegacy
Write-Fixture "f14/.scratch/featA/FEATURE.md" $featureGood
Assert-Case "F14 retired map beside valid .scratch only hints" $d 0 'hint: retired CODEBASE.md map artifacts'

$d = New-FixtureDir "f15"
Write-Fixture "f15/CODEBASE.md" $rootLegacy
Write-Fixture "f15/.scratch/featA/FEATURE.md" ($featureGood -replace 'type: feature', 'type: bogus')
Assert-Case "F15 broken .scratch still caught alongside a retired map" $d 1

$d = New-FixtureDir "f21"
New-Item -ItemType Directory -Path (Join-Path $d ".scratch/featA") -Force | Out-Null
$f21 = [System.Collections.Generic.List[byte]]::New()
$f21.AddRange([Text.Encoding]::ASCII.GetBytes($featureGood))
$f21.AddRange([Text.Encoding]::ASCII.GetBytes("`nstray byte: "))
$f21.Add(0xFF)
$f21.AddRange([Text.Encoding]::ASCII.GetBytes("`n"))
[IO.File]::WriteAllBytes((Join-Path $d ".scratch/featA/FEATURE.md"), $f21.ToArray())
Assert-Case "F21 stray non-UTF-8 byte in FEATURE.md reported as violation" $d 1 "can't decode byte 0xff"

$d = New-FixtureDir "f22"
Write-Fixture "f22/.scratch/featA/FEATURE.md" $featureGood
Write-Fixture "f22/.scratch/featA/issues/01-slice.md" "legacy card"
Assert-Case "F22 legacy issues/ directory beside FEATURE.md rejected" $d 1 'legacy planning artifacts (issues)'

$d = New-FixtureDir "f23"
Write-Fixture "f23/CODEBASE.md" $rootLegacy
Assert-Case "F23 retired CODEBASE.md without .scratch only hints" $d 0 'hint: retired CODEBASE.md map artifacts'

# --- report ---
if ($failures.Count -gt 0) {
    Write-Output "test-verify-artifacts: $($failures.Count) FAILURE(S), $passed passed - fixtures kept at $tmp"
    foreach ($f in $failures) { Write-Output "  FAIL $f" }
    exit 1
}
Write-Output "test-verify-artifacts: OK - $passed assertion(s) passed."
Remove-Item -LiteralPath $tmp -Recurse -Force
exit 0
