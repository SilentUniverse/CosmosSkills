# Claude Code PreToolUse hook — enforces CLAUDE.md §7 (modern CLI tooling) on Windows (PowerShell).
# Reads the tool-call JSON from stdin, inspects tool_input.command, and exits 2
# (with a message on stderr) if the command invokes a forbidden legacy tool.
#
# Failure-safe direction: malformed / empty input, or an explicit escape hatch,
# always exits 0 (allow). Only a confirmed match exits 2 (block).

$ErrorActionPreference = 'Stop'

$raw = [Console]::In.ReadToEnd()
try {
    $command = [string]($raw | ConvertFrom-Json).tool_input.command
} catch {
    # Malformed / empty input — don't block.
    exit 0
}

if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

# Escape hatch: allow when the command explicitly opts out.
if ($command -match '(?m)^\s*#\s*force-legacy' -or $env:ALLOW_LEGACY_CLI -eq '1') {
    exit 0
}

# Legacy tool -> modern replacement.
$map = [ordered]@{
    'grep' = 'rg'
    'find' = 'fd'
    'cat'  = 'bat (or the built-in Read tool)'
    'ls'   = 'eza'
    'sed'  = 'sd'
}

foreach ($old in $map.Keys) {
    # Match only in "command position": at the start of the command, or right
    # after a pipe / && / ; / (. The tool name must be followed by whitespace or
    # end-of-string so ripgrep, fdfind, pcre2grep, paths like src/cat/x, and the
    # quoted string "cat" are NOT treated as a match.
    $pattern = "(?:^|\||&&|;|\()\s*$old(?:\s|$)"
    if ($command -match $pattern) {
        [Console]::Error.WriteLine(
            "BLOCKED: '$old' is forbidden (CLAUDE.md " + [char]0xA7 + "7). Use '$($map[$old])' instead. " +
            "For routine search/read prefer the built-in Grep/Glob/Read tools. " +
            "If truly unavoidable, prefix the command with '# force-legacy' or set ALLOW_LEGACY_CLI=1.")
        exit 2
    }
}

exit 0
