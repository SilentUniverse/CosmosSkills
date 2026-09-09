#!/bin/bash
# Claude Code PreToolUse hook — blocks destructive git commands on Unix / WSL.
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if a HOST-side git invocation is destructive.
#
# Matching is token-level (mirrors block-dangerous-git.ps1): the `git` at each
# segment's command position is examined with its subcommand and flags, after
# wrapper words and VAR=val prefixes. Quoted strings and heredoc bodies are
# data. No escape hatch, by design.
#
# Failure-safe: parse errors, missing jq, or unexpected failures exit 0.

COMMAND=$(cat | jq -r '.tool_input.command // empty' 2>/dev/null)

# Malformed / empty input (or jq missing) — don't block.
[ -z "$COMMAND" ] && exit 0

# jq on Windows emits CRLF: a trailing CR corrupts every last token and stops
# the heredoc delimiter from ever matching. Analysis text keeps LF only.
COMMAND=${COMMAND//$'\r'/}

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

# On Git Bash (MSYS) the executable lookup is case-insensitive, so GIT
# reaches git.exe; under WSL/Linux names stay exact. The corpus forces this
# with GUARD_SHELL_FORCE_MSYS when scoring the msys profile off-Windows.
FOLD=0
case "${OSTYPE:-}" in msys*|cygwin*) FOLD=1 ;; esac
[ "${GUARD_SHELL_FORCE_MSYS:-}" = "1" ] && FOLD=1

for t in "${SEGMENTS[@]}"; do
  # Command position (mirrors guard-shell.py): segment head, or the first
  # token after wrapper words / VAR=val / wrapper flag+value pairs. A bare
  # "git push" inside a quoted argument is data, never a call.
  read -ra TOK <<< "$t"
  n=${#TOK[@]}
  prev=""
  pending=0
  ci=-1
  for ((i = 0; i < n; i++)); do
    tok="${TOK[$i]}"
    if [ "$pending" = "1" ]; then pending=0; continue; fi
    case "$tok" in [A-Za-z_]*=*) continue ;; esac
    word="${tok//\"/}"
    word="${word//\'}"
    word="${word##*/}"
    case "$word" in
      *.[eE][xX][eE]) word="${word%.*}" ;;
    esac
    if [ "$FOLD" = "1" ]; then word="${word,,}"; fi
    if [ -n "$prev" ]; then
      case "$word" in
        -*)
          case "${prev}:${word}" in
            sudo:-u|sudo:-g|sudo:-p|sudo:--user|sudo:--group|\
env:-u|env:--unset|env:-S|env:--split-string|\
timeout:-k|timeout:--kill-after|timeout:--signal|timeout:-s|\
nice:-n|xargs:-I|xargs:-E|xargs:-n|xargs:-P|xargs:-s|xargs:-L|\
stdbuf:-o|stdbuf:-e|stdbuf:-i|watch:-n|watch:-g) pending=1 ;;
            command:-v|command:-V) ci=-2; break ;;
          esac
          continue ;;
        [0-9]*) continue ;;
      esac
    fi
    case "$word" in
      sudo|env|nohup|nice|timeout|time|xargs|stdbuf|watch|command|builtin|setsid|exec)
        prev="$word"; continue ;;
    esac
    ci=$i
    break
  done
  # command/builtin -v|-V only print a path — nothing executes.
  [ "$ci" = "-2" ] && continue
  [ "$ci" -lt 0 ] && continue
  [ "$word" = "git" ] || continue
  i=$ci
  # Cleaned tokens after `git`: value-taking flags drop themselves AND their
  # value, so neither is mistaken for the subcommand or a path operand.
  AFTER=()
  for ((j = i + 1; j < n; j++)); do
    t2="${TOK[$j]}"
    t2="${t2//\"/}"
    t2="${t2//\'}"
    case "$t2" in
      -C|-c|--git-dir|--work-tree|--namespace) j=$((j + 1)); continue ;;
    esac
    AFTER+=("$t2")
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
    checkout)
      for ((j = 0; j < m; j++)); do [ "${REST[$j]}" = "." ] && why="git checkout ."; done ;;
    restore)
      for ((j = 0; j < m; j++)); do [ "${REST[$j]}" = "." ] && why="git restore ."; done ;;
  esac
  if [ -n "$why" ]; then
    echo "BLOCKED: destructive git operation ($why). The user has reserved these operations for themselves; use the /commit workflow or ask the user to run it by hand." >&2
    exit 2
  fi
done

exit 0
