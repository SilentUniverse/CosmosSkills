#!/usr/bin/env python3
"""Claude Code / ZCode PreToolUse hook — one process, one parse, three tiers.

Reads the tool-call JSON from stdin, inspects tool_input.command, exits 2 with
a stderr message on the highest-priority hit, else 0. Single self-contained
stdlib file; runs on Windows (python) and Unix (python3) alike.

  Tier 1  destructive git operations        hard block, NO escape hatch
  Tier 2  POSIX paths to native executables hard block, NO escape hatch
  Tier 3  legacy CLI (grep/find/sed)        block, '# force-legacy' escapes

The escape hatch ('# force-legacy' line or ALLOW_LEGACY_CLI=1) opts out of the
modern-CLI preference ONLY — the path-correctness tier stays in force.

Execution-domain model (bash semantics):
  - single-quoted text is always data (device/remote commands, prose);
  - double-quoted text is data EXCEPT $(...) and `...` interiors — those are
    host-evaluated substitutions and are scanned as commands;
  - name=( ... ) array literals are data; separators inside them do not split;
  - heredoc bodies are stripped before matching;
  - command position = the command word of a segment, reachable through a
    prefix chain of keywords / wrappers / VAR=val / wrapper flag+value.
    'echo sudo git push' and 'adb shell sudo git push' are never calls.

Perf contract: necessary-condition prefilters run first — commands containing
no git / grep|find|sed / POSIX-path token never reach the parser at all.

Failure-safe: malformed input, missing stdin, or any internal error exits 0
(allow). GUARD_SHELL_DEBUG=1 surfaces the swallowed error for diagnosis.
All emitted text is ASCII on purpose (GBK console safety).
"""

import json
import os
import re
import sys

# ---------------------------------------------------------------- prefilters

HEREDOC_RE = re.compile(
    r'^[^\r\n]*?<<\s*-?\s*["\']?(\w+)["\']?\r?\n.*?^[ \t]*\1(?:\r?\n|$)',
    re.M | re.S)

GIT_RE = re.compile(r'(?<![\w.-])git(?![\w.-])')
LEGACY_RE = re.compile(r'(?<![\w.-])(grep|find|sed)(?![\w.-])')
POSIX_PRE_RE = re.compile(r'(^|[\s"\'(=|;&])/[A-Za-z]+([/\s"\'|)&;]|$)')
FORCE_RE = re.compile(r'(?m)^\s*#\s*force-legacy')

# --------------------------------------------------------- command-position

PREFIX_KEYWORDS = {'do', 'then', 'else', '!', '{', 'if', 'while', 'until', 'case'}
PREFIX_WRAPPERS = {'sudo', 'env', 'nohup', 'nice', 'timeout', 'time', 'xargs',
                   'stdbuf', 'watch', 'command', 'builtin', 'setsid', 'exec'}
# Flags whose NEXT token is a value, not a command (env -u NAME, nice -n N...).
VALUE_FLAGS = {'-u', '-S', '--unset', '--split-string', '-n', '--adjustment',
               '-k', '--kill-after', '--signal', '-s', '--separator'}

VARVAL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
FLAG_RE = re.compile(r'^-.')
NUM_RE = re.compile(r'^\d+([.]\d+)?[smh]?$')


def command_word_index(tokens):
    """Index of the command word, or -1. A prefix chain must start at the
    segment head, so a git/grep behind adb/ssh/echo never reaches command
    position."""
    prev = ''
    pending_value = False
    for i, w in enumerate(tokens):
        if pending_value:
            pending_value = False
            continue
        if VARVAL_RE.match(w):
            continue
        if w in PREFIX_KEYWORDS or w in PREFIX_WRAPPERS:
            prev = w
            continue
        if prev and FLAG_RE.match(w):
            pending_value = w in VALUE_FLAGS
            continue
        if prev and NUM_RE.match(w):
            continue
        return i
    return -1


# ------------------------------------------------------------------ segments

def split_segments(text):
    """Quote- and substitution-aware segment split. Separators are unquoted
    | & ; newline, ( subshell, $(...) and `...` (also inside double quotes).
    Modes: T top, S single-quote, D double-quote, C $(...), B `...`,
    A array literal. Structural ( ) ` characters are dropped, so downstream
    token matching never sees glued noise like 'push)'."""
    segs = []
    buf = []
    modes = ['T']
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        m = modes[-1]
        if m == 'S':
            if c == "'":
                modes.pop()
            buf.append(c)
        elif m == 'A':
            # Array literal interior: data; separators do not split.
            if c == ')':
                modes.pop()
                buf.append(c)
            elif c == "'":
                modes.append('S')
                buf.append(c)
            elif c == '"':
                modes.append('D')
                buf.append(c)
            elif c == '\\' and nxt:
                buf.append(c)
                buf.append(nxt)
                i += 2
                continue
            elif c == '`':
                segs.append(''.join(buf))
                buf = []
                modes.append('B')
            elif c == '$' and nxt == '(':
                segs.append(''.join(buf))
                buf = []
                modes.append('C')
                i += 2
                continue
            else:
                buf.append(c)
        elif m == 'D':
            if c == '"':
                modes.pop()
                buf.append(c)
            elif c == '\\' and nxt:
                buf.append(c)
                buf.append(nxt)
                i += 2
                continue
            elif c == '`':
                # Host-evaluated substitution inside double quotes.
                segs.append(''.join(buf))
                buf = []
                modes.append('B')
            elif c == '$' and nxt == '(':
                segs.append(''.join(buf))
                buf = []
                modes.append('C')
                i += 2
                continue
            else:
                buf.append(c)
        else:
            # Modes T (top), C ($(...)), B (`...`): command text.
            if m == 'C' and c == ')':
                segs.append(''.join(buf))
                buf = []
                modes.pop()
            elif m == 'B' and c == '`':
                segs.append(''.join(buf))
                buf = []
                modes.pop()
            elif c == "'":
                modes.append('S')
                buf.append(c)
            elif c == '"':
                modes.append('D')
                buf.append(c)
            elif c == '\\' and nxt:
                buf.append(c)
                buf.append(nxt)
                i += 2
                continue
            elif c == '$' and nxt == '(':
                segs.append(''.join(buf))
                buf = []
                modes.append('C')
                i += 2
                continue
            elif c == '`':
                segs.append(''.join(buf))
                buf = []
                modes.append('B')
            elif c == '(':
                # name=( opens an array literal; a bare ( is a subshell and
                # just splits. Both drop the paren itself.
                if buf and buf[-1] == '=':
                    modes.append('A')
                    buf.append(c)
                else:
                    segs.append(''.join(buf))
                    buf = []
            elif c == ')':
                pass  # subshell closer in top mode: structural, dropped
            elif c in '|&;\n':
                segs.append(''.join(buf))
                buf = []
            else:
                buf.append(c)
        i += 1
    segs.append(''.join(buf))
    return [s for s in segs if s]


# --------------------------------------------------------------------- tiers

GIT_VALUE_FLAGS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}
NATIVE_RE = re.compile(r'^(?:python3?|py|pwsh|powershell|cmd|node|rg|fd|bat|jq|yq|sd)$')
POSIX_TOK_RE = re.compile(r'^/(?:tmp|[A-Za-z])(?:/|$)')
CMD_SWITCH_RE = re.compile(r'^/[A-Za-z]$')
REDIR_RE = re.compile(r'^(?:\d)?>{1,2}$|^<$')


def dangerous_git_hit(segments):
    for seg in segments:
        toks = seg.strip().split()
        if not toks:
            continue
        ci = command_word_index(toks)
        if ci < 0 or toks[ci] != 'git':
            continue
        # Value-taking flags drop themselves AND their value, so neither is
        # mistaken for the subcommand or a path operand (git -C . checkout x).
        after = []
        j = ci + 1
        while j < len(toks):
            if toks[j] in GIT_VALUE_FLAGS:
                j += 2
                continue
            after.append(toks[j])
            j += 1
        sub = next((t for t in after if not t.startswith('-')), None)
        if not sub:
            continue
        if sub == 'push':
            return 'git push'
        if sub == 'reset' and '--hard' in after:
            return 'git reset --hard'
        if sub == 'clean':
            f = [t for t in after
                 if len(t) > 1 and t.startswith('-') and 'f' in t.lstrip('-')]
            if f:
                return 'git clean (%s)' % f[0]
        if sub == 'branch' and ('-D' in after or
                                ('--delete' in after and '--force' in after)):
            return 'git branch -D'
        if sub == 'checkout' and '.' in after:
            return 'git checkout .'
        if sub == 'restore' and '.' in after:
            return 'git restore .'
    return None


def native_posix_path_hit(segments):
    for seg in segments:
        toks = seg.strip().split()
        if not toks:
            continue
        ci = command_word_index(toks)
        if ci < 0:
            continue
        head = toks[ci]
        if not NATIVE_RE.match(head):
            continue
        # cmd-headed segments: bare single-letter tokens (/a, /b) are cmd/dir
        # switches, never paths — keeps `cmd //c dir /a /b <path>` allowed.
        cmd_switches_ok = head == 'cmd'
        prev_redirect = False
        for tok in toks[ci + 1:]:
            # Redirect targets are resolved by bash, not the native process.
            is_redir = bool(REDIR_RE.match(tok))
            if (not prev_redirect and not is_redir
                    and not (cmd_switches_ok and CMD_SWITCH_RE.match(tok))
                    and POSIX_TOK_RE.match(tok)):
                return tok
            prev_redirect = is_redir
    return None


def legacy_cli_hit(segments):
    for seg in segments:
        toks = seg.strip().split()
        if not toks:
            continue
        ci = command_word_index(toks)
        if ci < 0:
            continue
        if toks[ci] in ('grep', 'find', 'sed'):
            return toks[ci]
    return None


# ---------------------------------------------------------------------- main

MSG_GIT = ("BLOCKED: destructive git operation ({why}). The user has reserved "
           "these operations for themselves — use the /commit workflow or ask "
           "the user to run it by hand.")
MSG_PATH = ("BLOCKED: POSIX path '{tok}' handed to a native Windows "
            "executable. Native processes only understand Windows absolute "
            "paths. Temp files: use $env:TEMP (from bash: cygpath -w $TEMP); "
            "other paths: convert with cygpath -w first. This is a "
            "correctness rule; '# force-legacy' does not bypass it.")
MSG_LEGACY = {
    'grep': 'rg', 'find': 'fd', 'sed': 'sd',
}


def main():
    try:
        # stdin arrives as UTF-8 JSON; decode explicitly, not by console
        # codepage (Windows GBK default would mangle non-ASCII payloads).
        raw = sys.stdin.buffer.read().decode('utf-8', 'replace')
        data = json.loads(raw)
        command = (data.get('tool_input') or {}).get('command') or ''
    except Exception:
        sys.exit(0)  # malformed / empty input — don't block

    if not command.strip():
        sys.exit(0)

    escape = bool(FORCE_RE.search(command)) or \
        os.environ.get('ALLOW_LEGACY_CLI') == '1'

    try:
        stripped = HEREDOC_RE.sub('', command)
        need_git = bool(GIT_RE.search(stripped))
        need_legacy = (not escape) and bool(LEGACY_RE.search(stripped))
        need_path = bool(POSIX_PRE_RE.search(stripped))
        if not (need_git or need_legacy or need_path):
            sys.exit(0)

        segs = split_segments(stripped)

        if need_git:
            why = dangerous_git_hit(segs)
            if why:
                sys.stderr.write(MSG_GIT.format(why=why))
                sys.exit(2)

        if need_path:
            tok = native_posix_path_hit(segs)
            if tok:
                sys.stderr.write(MSG_PATH.format(tok=tok))
                sys.exit(2)

        if need_legacy:
            old = legacy_cli_hit(segs)
            if old:
                sys.stderr.write(
                    "BLOCKED: '%s' is forbidden on the host shell (CLAUDE.md "
                    "section 7). Use '%s' instead. For routine search/read "
                    "prefer the built-in Grep/Glob/Read tools. If truly "
                    "unavoidable, put '# force-legacy' on its own line first, "
                    "or set ALLOW_LEGACY_CLI=1." % (old, MSG_LEGACY[old]))
                sys.exit(2)

        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        if os.environ.get('GUARD_SHELL_DEBUG'):
            import traceback
            traceback.print_exc()
        sys.exit(0)  # any unexpected failure — don't block


if __name__ == '__main__':
    main()
