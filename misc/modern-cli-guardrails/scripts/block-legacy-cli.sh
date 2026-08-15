#!/bin/bash
# Claude Code PreToolUse hook — enforces CLAUDE.md §7 (modern CLI tooling) on Unix / WSL.
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if a HOST-side segment of the command invokes a
# forbidden legacy tool.
#
# Matching: only the first word of each segment is checked, so a tool name in
# argument position — `adb shell ls`, `docker exec ctr ls`, `wsl ls` — never
# blocks, and quoted strings plus heredoc bodies are data, not commands. So
# `adb shell "ls; grep x"` passes while `adb logcat -d | grep x` blocks (that
# grep runs on the host).
#
# Failure-safe direction: parse errors, missing jq, unexpected failures, or an
# explicit escape hatch exit 0 (allow). Only a confirmed host-side match exits 2.

COMMAND=$(cat | jq -r '.tool_input.command // empty' 2>/dev/null)

# Malformed / empty input (or jq missing) — don't block.
[ -z "$COMMAND" ] && exit 0

# Escape hatch: any line starting with '# force-legacy' opts the whole command
# out (line-anchored, matching the .ps1's (?m) semantics — bash =~ ^ only
# anchors the first line).
while IFS= read -r _hline; do
  [[ "$_hline" =~ ^[[:space:]]*#[[:space:]]*force-legacy ]] && exit 0
done <<< "$COMMAND"
[ "$ALLOW_LEGACY_CLI" = "1" ] && exit 0

# Drop heredoc bodies: lines between <<'EOF' and the matching delimiter are
# DATA (commit messages, file content), not commands. Delimiter must end the
# line; a body on the same line as other commands ("<<EOF | grep x") is not a
# heredoc for stripping purposes.
STRIPPED=""
heredoc=0
delim=""
re_heredoc="^.*<<-?[[:space:]]*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?[[:space:]]*$"
while IFS= read -r line || [ -n "$line" ]; do
  if [ "$heredoc" = "1" ]; then
    [ "$line" = "$delim" ] && heredoc=0
    continue
  fi
  STRIPPED+="$line"$'\n'
  if [[ "$line" =~ $re_heredoc ]]; then
    delim="${BASH_REMATCH[1]}"
    heredoc=1
  fi
done <<< "$COMMAND"

# Split into segments, quote-aware: a separator inside '...'/"..." belongs to
# the quoted string (the device command in adb shell "..."), not to the host
# shell. Unquoted | & ; ( and newlines split. Segments are collected in an
# ARRAY — a real newline inside a quoted argument stays inside that segment
# and must never become a segment boundary.
declare -a SEGMENTS=()
quote=""
seg=""
len=${#STRIPPED}
i=0
while [ "$i" -lt "$len" ]; do
  c=${STRIPPED:$i:1}
  if [ -n "$quote" ]; then
    if [ "$c" = '\' ] && [ "$quote" = '"' ] && [ $((i + 1)) -lt "$len" ]; then
      seg+="$c"${STRIPPED:$((i + 1)):1}
      i=$((i + 2))
      continue
    fi
    [ "$c" = "$quote" ] && quote=""
    seg+="$c"
  else
    case "$c" in
      "'"|'"')
        quote="$c"
        seg+="$c" ;;
      '\')
        seg+="$c"
        [ $((i + 1)) -lt "$len" ] && seg+=${STRIPPED:$((i + 1)):1}
        i=$((i + 2))
        continue ;;
      '|'|'&'|';'|'('|$'\n')
        SEGMENTS+=("$seg")
        seg="" ;;
      *)
        seg+="$c" ;;
    esac
  fi
  i=$((i + 1))
done
SEGMENTS+=("$seg")

re_legacy="^(grep|find|ls|sed)([^[:alnum:]_./-].*)?$"
for t in "${SEGMENTS[@]}"; do
  t="${t#"${t%%[![:space:]]*}"}"   # trim leading whitespace
  [ -z "$t" ] && continue
  if [[ "$t" =~ $re_legacy ]]; then
    old="${t%%[!a-z]*}"
    case "$old" in
      grep) new=rg ;; find) new=fd ;; ls) new=eza ;; sed) new=sd ;;
    esac
    echo "BLOCKED: '$old' is forbidden on the host shell (CLAUDE.md section 7). Use '$new' instead. For routine search/read prefer the built-in Grep/Glob/Read tools. If truly unavoidable, put '# force-legacy' on its own line first, or set ALLOW_LEGACY_CLI=1." >&2
    exit 2
  fi
done

exit 0
