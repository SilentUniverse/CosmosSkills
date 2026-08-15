#!/usr/bin/env bash
# Human-in-the-loop reproduction loop.
# Copy this file to .scratch/tmp/hitl-<bug>.sh (never edit the template in place),
# edit the steps below, and run it.
# The agent runs the script; the user follows prompts in their terminal.
#
# Usage:
#   bash hitl-loop.template.sh
#
# Two helpers:
#   step "<instruction>"          → show instruction, wait for Enter
#   capture VAR "<question>"      → show question, read response into VAR
#
# At the end, captured values are printed as KEY=VALUE for the agent to parse.

set -euo pipefail

_captured=()

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _ || true   # Ctrl-D here: move on to the next prompt
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  # Ctrl-D (EOF) here means the user bailed — print what we have so far, don't lose it.
  if ! read -r -p "    > " answer; then
    printf '\n--- Captured (partial) ---\n'
    for _v in ${_captured[@]+"${_captured[@]}"}; do printf '%s=%s\n' "$_v" "${!_v}"; done
    exit 1
  fi
  printf -v "$var" '%s' "$answer"
  _captured+=("$var")
}

# --- edit below ---------------------------------------------------------

step "Open the app at http://localhost:3000 and sign in."

capture ERRORED "Click the 'Export' button. Did it throw an error? (y/n)"

capture ERROR_MSG "Paste the error message (or 'none'):"

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'ERRORED=%s\n' "$ERRORED"
printf 'ERROR_MSG=%s\n' "$ERROR_MSG"
