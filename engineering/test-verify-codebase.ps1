<#
.SYNOPSIS
    Regression harness for the CODEBASE.md leaves of verify-artifacts.py.

.DESCRIPTION
    Builds throwaway fixture repos in a temp dir, runs verify-artifacts.py against each
    fixture, asserts exit codes. Interpreter: python, then python3 if python is missing.
    Source is ASCII-only on purpose: PS 5.1 parses a BOM-less .ps1 as ANSI,
    so non-ASCII literals would corrupt; the Chinese roster-heading fixture builds its string
    from code points instead.
    Exit codes: 0 = all green, 1 = failures.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File test-verify-codebase.ps1
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
    Write-Output "test-verify-codebase: neither python nor python3 is a working interpreter"
    exit 1
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("va-cb-test-" + [IO.Path]::GetRandomFileName())
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

$rootGood = @'
---
type: codebase
generated: 2026-08-18
---

# demo map

Synthesis line one.
Synthesis line two.

## routing

| goal | where |
|---|---|
| do X | src/alpha/ (real entry: withdraw) |

## roster

<!-- detail per area: its CLAUDE.md generated block -->
- `src/alpha/` - alpha responsibility
- `src/beta/` - beta responsibility
'@

$blockGood = @'
<!-- BEGIN GENERATED codebase (/zoom-out) - do not edit between markers; regen: /zoom-out AREA -->
git_base: abc1234
- invariant one
- seam two
<!-- END GENERATED codebase -->
'@

$blockAlpha = $blockGood -replace 'AREA', 'src/alpha'
$blockBeta = $blockGood -replace 'AREA', 'src/beta'
$filler = (1..45 | ForEach-Object { "filler line $_" }) -join "`r`n"
$rootLong = $rootGood -replace 'Synthesis line two\.', ("Synthesis line two.`r`n" + $filler)
$issueGood = @'
---
type: issue
feature: featA
status: ready
category: enhancement
blocked_by: []
created: 2026-08-18
---

## body
'@

# --- fixtures ---

Assert-Case "F00 empty repo" (New-FixtureDir "f00") 0

$d = New-FixtureDir "f01"
Write-Fixture "f01/CODEBASE.md" $rootGood
Write-Fixture "f01/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f01/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F01 valid skeleton + 2 blocks" $d 0

$d = New-FixtureDir "f02"
Write-Fixture "f02/CODEBASE.md" ($rootGood -replace 'type: codebase', 'type: map')
Write-Fixture "f02/src/alpha/CLAUDE.md" $blockAlpha
Assert-Case "F02 root type != codebase" $d 1

$d = New-FixtureDir "f03"
Write-Fixture "f03/CODEBASE.md" $rootLong
Write-Fixture "f03/src/alpha/CLAUDE.md" $blockAlpha
Assert-Case "F03 root over default budget" $d 1

$d = New-FixtureDir "f04"
Write-Fixture "f04/CODEBASE.md" $rootGood
Write-Fixture "f04/src/alpha/CLAUDE.md" (($blockAlpha -split "`r?`n" | Where-Object { $_ -notmatch 'END GENERATED' }) -join "`n")
Assert-Case "F04 marker missing END" $d 1

$d = New-FixtureDir "f05"
Write-Fixture "f05/CODEBASE.md" $rootGood
Write-Fixture "f05/src/alpha/CLAUDE.md" ($blockAlpha -replace 'git_base: abc1234', 'was_base_here')
Assert-Case "F05 block missing git_base" $d 1

$longItems = (1..10 | ForEach-Object { "- item $_" }) -join "`n"
$d = New-FixtureDir "f06"
Write-Fixture "f06/CODEBASE.md" $rootGood
Write-Fixture "f06/src/alpha/CLAUDE.md" ("<!-- BEGIN GENERATED codebase (/zoom-out) - do not edit between markers -->`ngit_base: abc1234`n" + $longItems + "`n<!-- END GENERATED codebase -->")
Assert-Case "F06 block over 8 lines" $d 1

$d = New-FixtureDir "f07"
Write-Fixture "f07/CODEBASE.md" ($rootGood -replace '- `src/beta/` - beta responsibility', '- `src/gone/` - gone area')
Write-Fixture "f07/src/alpha/CLAUDE.md" $blockAlpha
Assert-Case "F07 roster points at missing dir" $d 1

$d = New-FixtureDir "f08"
Write-Fixture "f08/CODEBASE.md" ($rootGood -replace "`n- ``src/beta/`` - beta responsibility", '')
Write-Fixture "f08/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f08/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F08 block area not in roster" $d 1

$d = New-FixtureDir "f09"
Write-Fixture "f09/CODEBASE.md" ($rootLong -replace 'generated: 2026-08-18', "generated: 2026-08-18`nbudget: 60")
Write-Fixture "f09/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f09/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F09 budget override admits current size" $d 0

$d = New-FixtureDir "f10"
Write-Fixture "f10/CODEBASE.md" $rootGood
Write-Fixture "f10/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f10/src/beta/CLAUDE.md" "hand-written area notes, no markers"
Assert-Case "F10 hand-written nested CLAUDE.md is legal" $d 0

$d = New-FixtureDir "f11"
Write-Fixture "f11/src/alpha/CLAUDE.md" $blockAlpha
New-Item -ItemType Directory -Path (Join-Path $d ".scratch/featA") -Force | Out-Null
Assert-Case "F11 block without root CODEBASE.md (gate active via .scratch)" $d 1

$rootSingle = @'
---
type: codebase
generated: 2026-08-18
---

# demo map

Synthesis line one.

## Alpha <!-- git_base: abc1234 -->
- invariant one
- seam two
'@
$d = New-FixtureDir "f12"
Write-Fixture "f12/CODEBASE.md" $rootSingle
Assert-Case "F12 single-file root shape (no roster)" $d 0

$d = New-FixtureDir "f13"
Write-Fixture "f13/src/alpha/CLAUDE.md" "hand-written notes only"
Assert-Case "F13 no CODEBASE.md, stray hand-written nested file" $d 0

$d = New-FixtureDir "f14"
Write-Fixture "f14/CODEBASE.md" $rootGood
Write-Fixture "f14/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f14/src/beta/CLAUDE.md" $blockBeta
Write-Fixture "f14/.scratch/featA/issues/01-slice.md" $issueGood
Assert-Case "F14 CODEBASE + valid .scratch" $d 0

$d = New-FixtureDir "f15"
Write-Fixture "f15/CODEBASE.md" $rootGood
Write-Fixture "f15/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f15/.scratch/featA/issues/01-slice.md" ($issueGood -replace 'status: ready', 'status: bogus')
Assert-Case "F15 broken .scratch still caught alongside CODEBASE" $d 1

$fen = [string][char]0x5206 + [string][char]0x533A
$d = New-FixtureDir "f16"
Write-Fixture "f16/CODEBASE.md" ($rootGood -replace '## roster', ("## " + $fen + " (roster)"))
Write-Fixture "f16/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f16/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F16 Chinese roster heading" $d 0

$d = New-FixtureDir "f17"
Write-Fixture "f17/CODEBASE.md" ($rootLong -replace 'generated: 2026-08-18', "generated: 2026-08-18`nbudget: 30")
Write-Fixture "f17/src/alpha/CLAUDE.md" $blockAlpha
Assert-Case "F17 lowered budget still red over it" $d 1

$d = New-FixtureDir "f18"
$utf8Bom = New-Object System.Text.UTF8Encoding $true
[IO.File]::WriteAllText((Join-Path $d "CODEBASE.md"), $rootGood, $utf8Bom)
Write-Fixture "f18/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f18/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F18 BOM-prefixed root file" $d 0

$d = New-FixtureDir "f19"
Write-Fixture "f19/src/alpha/CLAUDE.md" $blockAlpha
Assert-Case "F19 gate idle (no .scratch, no root): stray block unchecked, clean" $d 0

$d = New-FixtureDir "f20"
Write-Fixture "f20/CODEBASE.md" ($rootGood -replace '- `src/beta/` - beta responsibility', "- `src/beta/` - beta responsibility`n- ``tests/<app>/`` - per-app tests`n- ``vendor/{python,tools}/`` - vendored families")
Write-Fixture "f20/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f20/src/beta/CLAUDE.md" $blockBeta
Assert-Case "F20 roster placeholder/brace syntax rejected as violation, not crash" $d 1 'placeholder/glob syntax'

$issueArchived = @'
---
type: issue
feature: featA
status: done
category: enhancement
blocked_by: []
created: 2026-08-18
---

## body
'@
$issueChild = @'
---
type: issue
feature: featA
status: ready
category: detail
blocked_by: [01-slice]
refines: 01-slice
created: 2026-08-18
---

## body
'@
$d = New-FixtureDir "f21"
Write-Fixture "f21/CODEBASE.md" $rootGood
Write-Fixture "f21/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f21/src/beta/CLAUDE.md" $blockBeta
Write-Fixture "f21/.scratch/featA/issues/archive/01-slice.md" $issueArchived
Write-Fixture "f21/.scratch/featA/issues/02-detail.md" $issueChild
Assert-Case "F21 live blocked_by/refines resolve archived done parent" $d 0

$d = New-FixtureDir "f22"
Write-Fixture "f22/CODEBASE.md" $rootGood
Write-Fixture "f22/src/alpha/CLAUDE.md" $blockAlpha
Write-Fixture "f22/src/beta/CLAUDE.md" $blockBeta
Write-Fixture "f22/.scratch/featA/issues/02-detail.md" $issueChild
Assert-Case "F22 live blocked_by missing parent still red" $d 1 'no sibling or archived file'

$d = New-FixtureDir "f23"
New-Item -ItemType Directory -Path (Join-Path $d ".scratch/featA/issues") -Force | Out-Null
$f23 = [System.Collections.Generic.List[byte]]::New()
$f23.AddRange([Text.Encoding]::ASCII.GetBytes($issueGood))
$f23.AddRange([Text.Encoding]::ASCII.GetBytes("stray byte: "))
$f23.Add(0xFF)
$f23.AddRange([Text.Encoding]::ASCII.GetBytes("`n"))
[IO.File]::WriteAllBytes((Join-Path $d ".scratch/featA/issues/01-slice.md"), $f23.ToArray())
Assert-Case "F23 stray non-UTF-8 byte in issue body reported as violation" $d 1 'not valid UTF-8'

$WANC = [string][char]0x5B8C + [string][char]0x6210        # 完成
$Xinz = [string][char]0x65B0 + [string][char]0x589E + [string][char]0x6D4B + [string][char]0x8BD5  # 新增测试
$issueDoneRec = ($issueGood -replace 'status: ready', 'status: done') -replace '## body', ("## body`n`n## Comments`n`n### " + $WANC + " - 2026-08-19`n`n- " + $Xinz + ": tests/demo_test.py (3 cases)")

$d = New-FixtureDir "f24"
Write-Fixture "f24/.scratch/featA/issues/01-slice.md" ($issueGood -replace 'status: ready', 'status: done')
Assert-Case "F24 done issue without completion record" $d 1 'no ###'

$d = New-FixtureDir "f25"
Write-Fixture "f25/.scratch/featA/issues/01-slice.md" $issueDoneRec
Assert-Case "F25 record names missing test file" $d 1 'missing test file'

$d = New-FixtureDir "f26"
Write-Fixture "f26/.scratch/featA/issues/01-slice.md" $issueDoneRec
Write-Fixture "f26/tests/demo_test.py" "def test_ok():`n    pass`n"
Assert-Case "F26 record names existing test file" $d 0

$d = New-FixtureDir "f27"
Write-Fixture "f27/.scratch/featA/issues/01-slice.md" $issueDoneRec
Write-Fixture "f27/.scratch/featA/tests/demo_test.py" "def test_ok():`n    pass`n"
Assert-Case "F27 record names test file inside the feature dir" $d 0

$issueDoneColon = $issueDoneRec -replace [regex]::Escape("### " + $WANC + " - "), ("### " + $WANC + [string][char]0xFF1A + " ")
$d = New-FixtureDir "f28"
Write-Fixture "f28/.scratch/featA/issues/01-slice.md" $issueDoneColon
Write-Fixture "f28/tests/demo_test.py" "def test_ok():`n    pass`n"
Assert-Case "F28 fullwidth-colon heading variant accepted" $d 0

# --- report ---
if ($failures.Count -gt 0) {
    Write-Output "test-verify-codebase: $($failures.Count) FAILURE(S), $passed passed - fixtures kept at $tmp"
    foreach ($f in $failures) { Write-Output "  FAIL $f" }
    exit 1
}
Write-Output "test-verify-codebase: OK - $passed assertion(s) passed."
Remove-Item -LiteralPath $tmp -Recurse -Force
exit 0
