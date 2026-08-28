<#
.SYNOPSIS
    Install skills from this repo into Claude Code skills folder using junctions.

.DESCRIPTION
    The script scans every <category>/<skill>/SKILL.md under repo root, reads
    frontmatter field `name`, and creates a directory junction in target folder:
    <target>/<name> -> <repo>/<category>/<skill>

    It also distributes the global layer to $ClaudeRoot (default ~/.claude):
    claude/CLAUDE.md -> ~/.claude/CLAUDE.md; claude/*.md -> ~/.claude/references/
    (pruning removed ones); ARTIFACT-FORMAT.md -> <target>; hook scripts (explicit
    list) -> ~/.claude/hooks/. CLAUDE.md additionally -> ~/.zcode/AGENTS.md, and the
    shared contract files -> ~/.agents/skills/. These are COPIES, not links — re-run after edits.

    Behavior:
    - Existing link: recreate it.
    - Existing real directory: backup to _backup-<timestamp> unless -Force.
    - No admin needed (junctions need none).

.PARAMETER Target
    Target skills folder. Default: ~/.claude/skills

.PARAMETER DryRun
    Preview only.

.PARAMETER Force
    Remove existing real directory directly instead of backup.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
#>

[CmdletBinding()]
param(
    [string]$Target = (Join-Path $HOME ".claude/skills"),
    [string]$ClaudeRoot = (Join-Path $HOME ".claude"),
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

function New-JunctionCompat {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    # In-process junction creation (PS 5.1+) — no cmd.exe spawn per link.
    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
}

function Get-JunctionTarget {
    param([string]$Path)

    # LinkTarget exists only on PS 7+; PS 5.1 parses `dir /aL` output for the [target] bracket.
    # The bracket shows the raw NT path — strip the `\??\` prefix so it compares like LinkTarget.
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.LinkTarget) { return $item.LinkTarget }
    $name = [regex]::Escape((Split-Path -Leaf $Path))
    $parent = Split-Path -Parent $Path
    foreach ($line in (cmd /c dir /aL "$parent")) {
        if ($line -match "\s$name\s+\[(.+)\]\s*$") { return ($Matches[1] -replace '^\\\?\?\\', '') }
    }
    return $null
}

function Get-SkillName {
    param([string]$SkillMdPath)

    $lines = Get-Content -LiteralPath $SkillMdPath -Encoding utf8
    if ($lines.Count -lt 2 -or $lines[0].Trim() -ne "---") { return $null }

    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq "---") { break }
        if ($lines[$i] -match "^\s*name:\s*(.+?)\s*$") {
            return $matches[1].Trim().Trim('"').Trim([char]39)
        }
    }
    return $null
}

$skillMds = Get-ChildItem -LiteralPath $root -Recurse -Filter "SKILL.md" -File
if (-not $skillMds) {
    Write-Error "No SKILL.md found under $root. Put install.ps1 at repository root."
    exit 1
}

$seen = @{}
foreach ($md in $skillMds) {
    $name = Get-SkillName $md.FullName
    $dir = $md.Directory.FullName

    if (-not $name) {
        Write-Warning "Skip (frontmatter has no name): $($md.FullName)"
        continue
    }
    if ($seen.ContainsKey($name)) {
        Write-Error "Duplicate name '$name' in $($seen[$name]) and $dir"
        exit 1
    }

    $seen[$name] = $dir
}

$skills = @(
    foreach ($k in ($seen.Keys | Sort-Object)) {
        [pscustomobject]@{ Name = $k; Source = $seen[$k] }
    }
)

Write-Host ("Found {0} skills, target: {1}" -f $skills.Count, $Target) -ForegroundColor Cyan
if ($DryRun) { Write-Host "[DryRun] Preview only." -ForegroundColor Yellow }

if (-not (Test-Path -LiteralPath $Target)) {
    if ($DryRun) { Write-Host "[DryRun] Create folder: $Target" }
    else { New-Item -ItemType Directory -Path $Target -Force | Out-Null }
}

$backupDir = Join-Path $Target ("_backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

$linked = 0
$backedUp = 0

foreach ($s in $skills) {
    $linkPath = Join-Path $Target $s.Name

    if (Test-Path -LiteralPath $linkPath) {
        $item = Get-Item -LiteralPath $linkPath -Force
        $isLink = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0

        if ($isLink) {
            if ($DryRun) { Write-Host ("[DryRun] Recreate link {0}" -f $s.Name) }
            else { [System.IO.Directory]::Delete($linkPath) }
        }
        elseif ($Force) {
            if ($DryRun) { Write-Host ("[DryRun] -Force remove real folder {0}" -f $linkPath) -ForegroundColor Red }
            else { Remove-Item -LiteralPath $linkPath -Recurse -Force }
        }
        else {
            if (-not $DryRun -and -not (Test-Path -LiteralPath $backupDir)) {
                New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            }

            $dest = Join-Path $backupDir $s.Name
            if ($DryRun) { Write-Host ("[DryRun] Backup {0} -> {1}, then relink" -f $s.Name, $dest) -ForegroundColor Yellow }
            else {
                Move-Item -LiteralPath $linkPath -Destination $dest
                $backedUp++
            }
        }
    }

    if ($DryRun) {
        Write-Host ("[DryRun] Link {0,-26} -> {1}" -f $s.Name, $s.Source)
    }
    else {
        New-JunctionCompat -LinkPath $linkPath -TargetPath $s.Source
        Write-Host ("Linked {0,-26} -> {1}" -f $s.Name, $s.Source) -ForegroundColor Green
        $linked++
    }
}

# --- Clean orphan links: reparse points in $Target that resolve into this repo but match no current skill
#     (the source skill was renamed/removed). Safe to delete — they're junctions, not real data. ---
$linkedNames = $skills | ForEach-Object { $_.Name }
Get-ChildItem -LiteralPath $Target -Directory -Force | Where-Object {
    ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and
    ((Get-JunctionTarget $_.FullName) -like "$root*") -and
    $linkedNames -notcontains $_.Name
} | ForEach-Object {
    if ($DryRun) {
        Write-Host ("[DryRun] Remove orphan link: {0}" -f $_.FullName) -ForegroundColor Yellow
    }
    else {
        [System.IO.Directory]::Delete($_.FullName)
        Write-Host ("Removed orphan link: {0}" -f $_.FullName) -ForegroundColor Yellow
    }
}

Write-Host ""

# --- Distribute ARTIFACT-FORMAT.md to the skills root so engineering skills' `../ARTIFACT-FORMAT.md`
#     links resolve. On Windows `..` is normalized textually (it does not traverse the junction),
#     so `<skills>/tdd/../ARTIFACT-FORMAT.md` -> `<skills>/ARTIFACT-FORMAT.md`. Put the file there. ---
$afSource = Join-Path $root "engineering/ARTIFACT-FORMAT.md"
if (Test-Path -LiteralPath $afSource) {
    $afTarget = Join-Path $Target "ARTIFACT-FORMAT.md"
    if ($DryRun) {
        Write-Host ("[DryRun] Copy ARTIFACT-FORMAT.md -> {0}" -f $afTarget) -ForegroundColor Yellow
    }
    else {
        Copy-Item -LiteralPath $afSource -Destination $afTarget -Force
        Write-Host ("Contract: copied ARTIFACT-FORMAT.md -> {0}" -f $afTarget) -ForegroundColor Green
    }
}

# --- Ship the artifact gate scripts next to ARTIFACT-FORMAT.md (same distribution reason). ---
foreach ($gate in @("verify-artifacts.py")) {
    $gSrc = Join-Path $root "engineering/$gate"
    if (-not (Test-Path -LiteralPath $gSrc)) { continue }
    $gTarget = Join-Path $Target $gate
    if ($DryRun) {
        Write-Host ("[DryRun] Copy gate {0} -> {1}" -f $gate, $gTarget) -ForegroundColor Yellow
    }
    else {
        Copy-Item -LiteralPath $gSrc -Destination $gTarget -Force
        Write-Host ("Gate: copied {0} -> {1}" -f $gate, $gTarget) -ForegroundColor Green
    }
}

$evalSource = Join-Path $root "scripts/eval.py"
if (Test-Path -LiteralPath $evalSource) {
    $evalTarget = Join-Path $Target "eval.py"
    if ($DryRun) {
        Write-Host ("[DryRun] Copy eval.py -> {0}" -f $evalTarget) -ForegroundColor Yellow
    }
    else {
        Copy-Item -LiteralPath $evalSource -Destination $evalTarget -Force
        Write-Host ("Eval: copied eval.py -> {0}" -f $evalTarget) -ForegroundColor Green
    }
}

$campaignSource = Join-Path $root "scripts/eval_campaign.py"
if (Test-Path -LiteralPath $campaignSource) {
    $campaignTarget = Join-Path $Target "eval_campaign.py"
    if ($DryRun) {
        Write-Host ("[DryRun] Copy eval_campaign.py -> {0}" -f $campaignTarget) -ForegroundColor Yellow
    }
    else {
        Copy-Item -LiteralPath $campaignSource -Destination $campaignTarget -Force
        Write-Host ("Eval: copied eval_campaign.py -> {0}" -f $campaignTarget) -ForegroundColor Green
    }
}

# Prune pre-Python gate corpses (the gate was once .ps1/.sh; on upgraded machines
# stale copies outlive the rewrite and read as "still old"). Fresh installs never see them.
foreach ($stale in @("verify-artifacts.ps1", "verify-artifacts.sh")) {
    $stalePath = Join-Path $Target $stale
    if (Test-Path -LiteralPath $stalePath) {
        if ($DryRun) { Write-Host ("[DryRun] Remove stale gate {0}" -f $stalePath) -ForegroundColor Yellow }
        else { Remove-Item -LiteralPath $stalePath -Force; Write-Host ("Gate: removed stale {0}" -f $stalePath) -ForegroundColor Yellow }
    }
}


# --- Distribute global guidelines: claude/CLAUDE.md -> ~/.claude/CLAUDE.md, and the
#     reference files -> ~/.claude/references/. CLAUDE.md is auto-loaded every session; the
#     references are read on demand via the `→ ~/.claude/references/...` pointers inside it. ---
# Explicit distribution root; a custom -Target must not move it.
$claudeRoot = $ClaudeRoot
$cmSource = Join-Path $root "claude"
if (Test-Path -LiteralPath $cmSource) {
    $cmMain = Join-Path $cmSource "CLAUDE.md"
    if (Test-Path -LiteralPath $cmMain) {
        $cmTarget = Join-Path $claudeRoot "CLAUDE.md"
        if ($DryRun) { Write-Host ("[DryRun] Copy CLAUDE.md -> {0}" -f $cmTarget) -ForegroundColor Yellow }
        else {
            Copy-Item -LiteralPath $cmMain -Destination $cmTarget -Force
            Write-Host ("Guidelines: copied CLAUDE.md -> {0}" -f $cmTarget) -ForegroundColor Green
        }
    }

    $refFiles = Get-ChildItem -LiteralPath $cmSource -Filter "*.md" -File |
        Where-Object { $_.Name -ne "CLAUDE.md" }
    if ($refFiles) {
        $refTarget = Join-Path $claudeRoot "references"
        if ($DryRun) {
            Write-Host ("[DryRun] Copy {0} reference file(s) -> {1}" -f $refFiles.Count, $refTarget) -ForegroundColor Yellow
        }
        else {
            if (-not (Test-Path -LiteralPath $refTarget)) { New-Item -ItemType Directory -Path $refTarget -Force | Out-Null }
            foreach ($ref in $refFiles) {
                Copy-Item -LiteralPath $ref.FullName -Destination (Join-Path $refTarget $ref.Name) -Force
            }
            # Prune deployed references whose source was removed from claude/ (stale
            # copies would outlive their → pointers in CLAUDE.md).
            Get-ChildItem -LiteralPath $refTarget -Filter "*.md" -File |
                Where-Object { $refFiles.Name -notcontains $_.Name } |
                Remove-Item -Force
            Write-Host ("References: copied {0} file(s) -> {1}" -f $refFiles.Count, $refTarget) -ForegroundColor Green
        }
    }
}

# --- Distribute hook scripts -> ~/.claude/hooks/. Explicit list, not a glob:
#     scripts/ also holds non-hook helpers (diagnose templates) that must not
#     land in hooks/. Keeps repo and deployed hooks from drifting apart. ---
$hookScripts = @(
    "misc/modern-cli-guardrails/scripts/block-legacy-cli.ps1",
    "misc/git-guardrails-claude-code/scripts/block-dangerous-git.ps1"
)
$hooksTarget = Join-Path $claudeRoot "hooks"
$copiedHooks = 0
foreach ($rel in $hookScripts) {
    $src = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Error "Listed hook script not found: $src — fix the list or restore the file."
        exit 1
    }
    if ($DryRun) {
        Write-Host ("[DryRun] Copy hook {0} -> {1}" -f $rel, $hooksTarget) -ForegroundColor Yellow
    }
    else {
        if (-not (Test-Path -LiteralPath $hooksTarget)) { New-Item -ItemType Directory -Path $hooksTarget -Force | Out-Null }
        Copy-Item -LiteralPath $src -Destination $hooksTarget -Force
        $copiedHooks++
    }
}
if (-not $DryRun -and $copiedHooks -gt 0) {
    Write-Host ("Hooks: copied {0} script(s) -> {1}" -f $copiedHooks, $hooksTarget) -ForegroundColor Green
}

# --- Distribute user instructions to ZCode: claude/CLAUDE.md -> ~/.zcode/AGENTS.md.
#     ZCode auto-loads ~/.zcode/AGENTS.md the way Claude Code loads ~/.claude/CLAUDE.md;
#     without this step the two hosts drift apart. Skill deployment into ~/.zcode/skills
#     and ~/.agents/skills is managed outside this script (one live root per name is enough). ---
if ($cmMain -and (Test-Path -LiteralPath (Join-Path $HOME ".zcode"))) {
    $zcodeAgents = Join-Path $HOME ".zcode/AGENTS.md"
    if ($DryRun) { Write-Host ("[DryRun] Copy CLAUDE.md -> {0}" -f $zcodeAgents) -ForegroundColor Yellow }
    else {
        Copy-Item -LiteralPath $cmMain -Destination $zcodeAgents -Force
        Write-Host ("Guidelines: copied CLAUDE.md -> {0}" -f $zcodeAgents) -ForegroundColor Green
    }
}

# --- Keep ~/.agents/skills/ shared contract files in step with the repo (junctioned skills
#     there resolve `../ARTIFACT-FORMAT.md` textually, the same way they do in $Target). ---
$agentsSkills = Join-Path $HOME ".agents/skills"
if (Test-Path -LiteralPath $agentsSkills) {
    foreach ($shared in @("ARTIFACT-FORMAT.md", "verify-artifacts.py")) {
        $sharedSrc = Join-Path $root "engineering/$shared"
        if (-not (Test-Path -LiteralPath $sharedSrc)) { continue }
        $sharedDst = Join-Path $agentsSkills $shared
        if ($DryRun) { Write-Host ("[DryRun] Copy {0} -> {1}" -f $shared, $sharedDst) -ForegroundColor Yellow }
        else {
            Copy-Item -LiteralPath $sharedSrc -Destination $sharedDst -Force
            Write-Host ("Contract: copied {0} -> {1}" -f $shared, $sharedDst) -ForegroundColor Green
        }
    }
}

if ($DryRun) {
    Write-Host "Dry run done. Remove -DryRun to apply." -ForegroundColor Yellow
}
else {
    Write-Host ("Done: {0} links created." -f $linked) -ForegroundColor Cyan
    if ($backedUp -gt 0) {
        Write-Host ("Backed up {0} existing folders to: {1}" -f $backedUp, $backupDir) -ForegroundColor Yellow
    }
    Write-Host "Use /<name> in Claude Code. cosmos-setup is the project bootstrap entry."
}
