#!/bin/bash
# Claude Code PreToolUse hook — blocks destructive git commands on Unix / WSL.
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if a HOST-side git invocation is destructive.
#
# Matching is token-level (mirrors block-dangerous-git.ps1): every `git` word
# in each host-side segment is examined with its subcommand and flags. Quoted
# strings and heredoc bodies are data. No escape hatch, by design.
#
# Failure-safe: parse errors, missing jq, or unexpected failures exit 0.

COMMAND=$(cat | jq -r '.tool_input.command // empty' 2>/dev/null)

# Malformed / empty input (or jq missing) — don't block.
[ -z "$COMMAND" ] && exit 0

# Strip heredoc bodies: data, not commands.
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

# Quote-aware split: separators inside '...'/"..." belong to the quoted string.
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

for t in "${SEGMENTS[@]}"; do
  # Tokenize on whitespace; examine every `git` word with its subcommand + flags.
  read -ra TOK <<< "$t"
  n=${#TOK[@]}
  for ((i = 0; i < n; i++)); do
    # Only a `git` in command position counts: segment-initial, or right after
    # a known wrapper. A bare "git push" inside a quoted argument is data.
    if [ "${TOK[$i]}" = "git" ]; then
      if [ "$i" -gt 0 ]; then
        case "${TOK[$((i - 1))]}" in
          sudo|env|nohup|nice|timeout|xargs) ;;
          *) continue ;;
        esac
      fi
    else
      continue
    fi
    # Cleaned tokens after `git`: value-taking flags drop themselves AND their
    # value, so neither is mistaken for the subcommand or a path operand.
    AFTER=()
    for ((j = i + 1; j < n; j++)); do
      case "${TOK[$j]}" in
        -C|-c|--git-dir|--work-tree|--namespace) j=$((j + 1)); continue ;;
      esac
      AFTER+=("${TOK[$j]}")
    done
    m=${#AFTER[@]}
    sub=""
    for ((j = 0; j < m; j++)); do
      case "${AFTER[$j]}" in -*) continue ;; *) sub="${AFTER[$j]}"; break ;; esac
    done
    [ -z "$sub" ] && continue
    REST=("${AFTER[@]}")
    why=""
    case "$sub" in
      push)     why="git push" ;;
      reset)
        for ((j = 0; j < m; j++)); do [ "${REST[$j]}" = "--hard" ] && why="git reset --hard"; done ;;
      clean)
        for ((j = 0; j < m; j++)); do
          tok="${REST[$j]}"
          [[ "$tok" == -* && "${#tok}" -gt 1 && "${tok//-/}" == *f* ]] && why="git clean ($tok)"
        done ;;
      branch)
        has_del=0; has_force=0
        for ((j = 0; j < m; j++)); do
          [ "${REST[$j]}" = "-D" ] && why="git branch -D"
          [ "${REST[$j]}" = "--delete" ] && has_del=1
          [ "${REST[$j]}" = "--force" ] && has_force=1
        done
        [ "$has_del" = "1" ] && [ "$has_force" = "1" ] && why="git branch -D" ;;
      checkout)
        for ((j = 0; j < m; j++)); do [ "${REST[$j]}" = "." ] && why="git checkout ."; done ;;
      restore)
        for ((j = 0; j < m; j++)); do [ "${REST[$j]}" = "." ] && why="git restore ."; done ;;
    esac
    if [ -n "$why" ]; then
      echo "BLOCKED: destructive git operation ($why). The user has reserved these operations for themselves — use the /commit workflow or ask the user to run it by hand." >&2
      exit 2
    fi
  done
done

exit 0
