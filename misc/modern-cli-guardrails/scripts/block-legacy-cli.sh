#!/bin/bash
# Claude Code PreToolUse hook — enforces CLAUDE.md §7 (modern CLI tooling) on Unix / WSL.
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if the command invokes a forbidden legacy tool.
#
# Failure-safe direction: malformed / empty input, or an explicit escape hatch,
# always exits 0 (allow). Only a confirmed match exits 2 (block).

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Malformed / empty input — don't block.
if [ -z "$COMMAND" ]; then
  exit 0
fi

# Escape hatch: allow when the command explicitly opts out.
if [[ "$COMMAND" =~ ^[[:space:]]*#[[:space:]]*force-legacy ]] || [ "$ALLOW_LEGACY_CLI" = "1" ]; then
  exit 0
fi

# Legacy tool -> modern replacement (parallel arrays; order matters only for output).
LEGACY_TOOLS=("grep" "find" "cat" "ls" "sed")
MODERN_TOOLS=("rg" "fd" "bat (or the built-in Read tool)" "eza" "sd")

for i in "${!LEGACY_TOOLS[@]}"; do
  old="${LEGACY_TOOLS[$i]}"
  new="${MODERN_TOOLS[$i]}"
  # Match only in "command position": start of command, or right after | && ; (
  # followed by whitespace or end-of-string, so ripgrep / fdfind / pcre2grep /
  # paths like src/cat/x do NOT match.
  if echo "$COMMAND" | grep -qE "(^|\||&&|;|\()[[:space:]]*${old}([[:space:]]|$)"; then
    echo "BLOCKED: '$old' is forbidden (CLAUDE.md §7). Use '$new' instead. For routine search/read prefer the built-in Grep/Glob/Read tools. If truly unavoidable, prefix the command with '# force-legacy' or set ALLOW_LEGACY_CLI=1." >&2
    exit 2
  fi
done

exit 0
