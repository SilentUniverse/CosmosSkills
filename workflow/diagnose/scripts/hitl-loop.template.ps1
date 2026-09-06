# Human-in-the-loop reproduction loop (Windows / PowerShell).
# Copy this file to .scratch/tmp/hitl-<bug>.ps1 (never edit the template in place),
# edit the steps below, and run it:
#   pwsh -NoProfile -File .scratch/tmp/hitl-<bug>.ps1
# The agent runs the script; the user follows prompts in their terminal.
#
# Two helpers:
#   Step    "<instruction>"        -> show instruction, wait for Enter
#   Capture "VAR" "<question>"      -> show question, read response into a variable
#
# At the end, captured values are printed as KEY=VALUE for the agent to parse.

$ErrorActionPreference = 'Stop'
$captured = [ordered]@{}

function Step([string]$instruction) {
    Write-Host "`n>>> $instruction"
    Read-Host "    [Enter when done]" | Out-Null
}

function Capture([string]$name, [string]$question) {
    Write-Host "`n>>> $question"
    $answer = Read-Host "    >"
    $script:captured[$name] = $answer
}

# --- edit below ---------------------------------------------------------

try {
    Step "Open the app at http://localhost:3000 and sign in."

    Capture "ERRORED" "Click the 'Export' button. Did it throw an error? (y/n)"

    Capture "ERROR_MSG" "Paste the error message (or 'none'):"
}

# --- edit above ---------------------------------------------------------

# finally runs on normal exit AND on Ctrl-C — partial captures are never lost.
finally {
    Write-Host "`n--- Captured ---"
    foreach ($key in $captured.Keys) {
        Write-Host "$key=$($captured[$key])"
    }
}
