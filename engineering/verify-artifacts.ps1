<#
.SYNOPSIS
    Mechanical gate for the ARTIFACT-FORMAT.md contract (.scratch/ artifacts).

.DESCRIPTION
    Checks issue / PRD / handoff / SUMMARY frontmatter: required fields, enum values,
    NN uniqueness, blocked_by / refines resolution and acyclicity, feature vs directory name,
    PRD version vs filename, supersedes targets, single live PRD head. A missing or empty
    .scratch/ passes clean. Contract: ARTIFACT-FORMAT.md (shipped alongside).
    Exit codes: 0 = clean, 1 = violations found, 2 = usage error.

.PARAMETER Root
    Repo root that holds .scratch/. Default: current directory.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File verify-artifacts.ps1 -Root D:\Code\myproj
#>
[CmdletBinding()]
param(
    [string]$Root = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$scratch = Join-Path $Root ".scratch"
if (-not (Test-Path -LiteralPath $scratch -PathType Container)) {
    Write-Output "verify-artifacts: no .scratch/ under $Root - nothing to check, clean."
    exit 0
}

$errors = [System.Collections.Generic.List[string]]::New()
$nIssues = 0; $nPrds = 0; $nHandoffs = 0; $nSummaries = 0

function Get-Frontmatter {
    param([string]$Path)
    # Scalars -> string; flow ([a, b]) and block ("- a") lists -> string[].
    # Returns $null when frontmatter is absent or unterminated.
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    if ($lines.Count -lt 2 -or "$($lines[0])".Trim() -ne "---") { return $null }
    $fm = @{}
    $i = 1
    for (; $i -lt $lines.Count; $i++) {
        $line = "$($lines[$i])"
        if ($line.Trim() -eq "---") { break }
        if ($line -match '^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$') {
            $key = $Matches[1]; $val = $Matches[2].Trim()
            if ($val -eq '') {
                $list = @(); $j = $i + 1
                while ($j -lt $lines.Count -and "$($lines[$j])" -match '^\s+-\s+(.+)$') { $list += $Matches[1].Trim(); $j++ }
                if ($list.Count -gt 0) { $fm[$key] = $list; $i = $j - 1 } else { $fm[$key] = '' }
            }
            elseif ($val -match '^\[\s*(.*)\s*\]$') {
                $inner = $Matches[1]
                $fm[$key] = if ($inner -eq '') { @() } else { @($inner -split ',' | ForEach-Object { "$_".Trim().Trim('"').Trim("'") }) }
            }
            else { $fm[$key] = $val.Trim('"').Trim("'") }
        }
    }
    if ($i -ge $lines.Count) { return $null }
    return $fm
}

# Suggest the sibling the bad ref most likely meant: same name-part first, then same NN.
function Get-RefSuggestion {
    param([string]$Bad, [string[]]$Candidates)
    $name = $Bad -replace '^\d+-', ''
    if ($name.Length -ge 3) {
        foreach ($c in $Candidates) {
            if (("$c" -replace '^\d+-', '') -eq $name) { return "$c" }
        }
    }
    if ($Bad -cmatch '^(\d+)-') {
        $nn = $Matches[1]
        foreach ($c in $Candidates) { if ("$c" -cmatch "^$nn-") { return "$c" } }
    }
    return $null
}

function Check-Handoff {
    param([string]$Path, [string]$ExpectedFeature)  # '' = cross-feature: feature must be null/absent
    $script:nHandoffs++
    $fm = Get-Frontmatter $Path
    if ($null -eq $fm) { $script:errors.Add("${Path}: no YAML frontmatter"); return }
    if ("$($fm['type'])" -ne 'handoff') { $script:errors.Add("${Path}: type '$($fm['type'])' != handoff") }
    $feat = "$($fm['feature'])"
    if ($ExpectedFeature -eq '') {
        if ($feat -ne '' -and $feat -ne 'null') { $script:errors.Add("${Path}: cross-feature handoff must have feature null, got '$feat'") }
    }
    elseif ($feat -ne $ExpectedFeature) {
        $script:errors.Add("${Path}: feature '$feat' != directory '$ExpectedFeature'")
    }
    if (-not "$($fm['git_base'])") { $script:errors.Add("${Path}: git_base missing") }
    if (@('active', 'consumed') -notcontains "$($fm['status'])") { $script:errors.Add("${Path}: status '$($fm['status'])' not in active|consumed") }
    if ("$($fm['date'])" -notmatch '^\d{4}-\d{2}-\d{2}$') { $script:errors.Add("${Path}: date not ISO YYYY-MM-DD") }
}

# Kahn peeling: slugs that survive are in (or feed into) a blocked_by cycle.
function Find-CyclicSlugs {
    param([hashtable]$Graph)
    $remaining = @{}
    foreach ($k in $Graph.Keys) {
        $remaining[$k] = @($Graph[$k] | Where-Object { $Graph.ContainsKey($_) })
    }
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($k in @($remaining.Keys)) {
            if (@($remaining[$k] | Where-Object { $remaining.ContainsKey($_) }).Count -eq 0) {
                $remaining.Remove($k); $changed = $true
            }
        }
    }
    return @($remaining.Keys)
}

foreach ($fd in @(Get-ChildItem -LiteralPath $scratch -Directory | Sort-Object Name)) {
    $feat = $fd.Name

    # --- PRD files ---
    $prdFiles = @(Get-ChildItem -LiteralPath $fd.FullName -File -Filter "PRD*.md")
    if ($prdFiles.Count -gt 0) {
        $names = @{}; foreach ($p in $prdFiles) { $names[$p.Name] = $true }
        $parsed = @{}
        foreach ($p in $prdFiles) {
            $nPrds++
            $fm = Get-Frontmatter $p.FullName
            $parsed[$p.Name] = $fm
            if ($null -eq $fm) { $errors.Add("$($p.FullName): no YAML frontmatter"); continue }
            if ("$($fm['type'])" -ne 'prd') { $errors.Add("$($p.FullName): type '$($fm['type'])' != prd") }
            if ($p.Name -eq 'PRD.md') {
                if ("$($fm['version'])" -ne '1') { $errors.Add("$($p.FullName): PRD.md must carry version 1, got '$($fm['version'])'") }
            }
            elseif ($p.Name -cmatch '^PRD-v(\d+)\.md$') {
                if ("$($fm['version'])" -ne $Matches[1]) { $errors.Add("$($p.FullName): filename says v$($Matches[1]) but version: $($fm['version'])") }
            }
            else { $errors.Add("$($p.FullName): PRD filename must be PRD.md or PRD-vN.md") }
            if ("$($fm['supersedes'])") {
                if (-not $names.ContainsKey("$($fm['supersedes'])")) { $errors.Add("$($p.FullName): supersedes '$($fm['supersedes'])' not found in this directory") }
            }
        }
        if ($prdFiles.Count -gt 1) {
            $superseded = @{}
            foreach ($e in $parsed.Values) { if ($e -and "$($e['supersedes'])") { $superseded["$($e['supersedes'])"] = $true } }
            $live = @($prdFiles | Where-Object { -not $superseded.ContainsKey($_.Name) } | ForEach-Object { $_.Name })
            if ($live.Count -ne 1) { $errors.Add("$($fd.FullName): PRD chain must leave exactly one live head, found: $($live -join ', ')") }
        }
    }

    # --- SUMMARY / handoff / issues ---
    $sumPath = Join-Path $fd.FullName "SUMMARY.md"
    if (Test-Path -LiteralPath $sumPath -PathType Leaf) {
        $nSummaries++
        $fm = Get-Frontmatter $sumPath
        if ($null -eq $fm) { $errors.Add("${sumPath}: no YAML frontmatter") }
        elseif ("$($fm['type'])" -ne 'summary') { $errors.Add("${sumPath}: type '$($fm['type'])' != summary") }
    }
    $hPath = Join-Path $fd.FullName "handoff.md"
    if (Test-Path -LiteralPath $hPath -PathType Leaf) { Check-Handoff $hPath $feat }

    $iDir = Join-Path $fd.FullName "issues"
    if (Test-Path -LiteralPath $iDir -PathType Container) {
        $files = @(Get-ChildItem -LiteralPath $iDir -File -Filter "*.md")   # top level only; archive/ excluded
        $bySlug = @{}; $nnSeen = @{}
        foreach ($f in $files) {
            $slug = $f.BaseName
            $bySlug[$slug] = $f.FullName
            if ($slug -cmatch '^(\d{2,})-') {
                $nn = $Matches[1]
                if ($nnSeen.ContainsKey($nn)) { $errors.Add("$($f.FullName): duplicate NN $nn (also $($nnSeen[$nn]))") }
                else { $nnSeen[$nn] = $slug }
            }
            else { $errors.Add("$($f.FullName): filename not NN-slug") }
        }
        $graph = @{}
        foreach ($f in $files) {
            $nIssues++
            $fm = Get-Frontmatter $f.FullName
            if ($null -eq $fm) { $errors.Add("$($f.FullName): no YAML frontmatter"); continue }
            if ("$($fm['type'])" -ne 'issue') { $errors.Add("$($f.FullName): type '$($fm['type'])' != issue") }
            if ("$($fm['feature'])" -ne $feat) { $errors.Add("$($f.FullName): feature '$($fm['feature'])' != directory '$feat'") }
            if (@('ready-for-agent', 'ready-for-human', 'done') -notcontains "$($fm['status'])") { $errors.Add("$($f.FullName): status '$($fm['status'])' not in ready-for-agent|ready-for-human|done") }
            $cat = "$($fm['category'])"
            if (@('enhancement', 'detail', 'redo', 'fix') -notcontains $cat) { $errors.Add("$($f.FullName): category '$cat' not in enhancement|detail|redo|fix") }
            $deps = @()
            foreach ($b in @($fm['blocked_by'])) {
                if ("$b" -eq '') { continue }
                if (-not $bySlug.ContainsKey("$b")) {
                    $sug = Get-RefSuggestion "$b" @($bySlug.Keys)
                    $errors.Add("$($f.FullName): blocked_by '$b' resolves to no sibling file$(if ($sug) { " (did you mean '$sug'?)" })")
                }
                elseif ("$b" -eq $f.BaseName) { $errors.Add("$($f.FullName): blocked_by itself") }
                else { $deps += "$b" }
            }
            $graph[$f.BaseName] = $deps
            if (@('detail', 'redo', 'fix') -contains $cat) {
                if ("$($fm['refines'])") {
                    if (-not $bySlug.ContainsKey("$($fm['refines'])")) {
                        $sug = Get-RefSuggestion "$($fm['refines'])" @($bySlug.Keys)
                        $errors.Add("$($f.FullName): refines '$($fm['refines'])' resolves to no sibling file$(if ($sug) { " (did you mean '$sug'?)" })")
                    }
                }
                else { $errors.Add("$($f.FullName): category '$cat' requires refines:") }
            }
            $created = "$($fm['created'])"
            if ($created -eq '') { $errors.Add("$($f.FullName): created missing") }
            elseif ($created -notmatch '^\d{4}-\d{2}-\d{2}$') { $errors.Add("$($f.FullName): created not ISO YYYY-MM-DD") }
        }
        foreach ($c in (Find-CyclicSlugs $graph)) {
            $errors.Add("$($bySlug[$c]): in (or depends on) a blocked_by cycle")
        }
    }
}

$cfh = Join-Path $scratch "handoff.md"
if (Test-Path -LiteralPath $cfh -PathType Leaf) { Check-Handoff $cfh '' }

if ($errors.Count -gt 0) {
    Write-Output "verify-artifacts: $($errors.Count) violation(s)"
    foreach ($e in $errors) { Write-Output "  $e" }
    exit 1
}
Write-Output "verify-artifacts: OK - checked $nIssues issue(s), $nPrds PRD(s), $nHandoffs handoff(s), $nSummaries summary(s)."
exit 0
