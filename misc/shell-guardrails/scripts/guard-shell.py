#!/usr/bin/env python3
"""Claude Code / ZCode PreToolUse hook — one process, one parse, three tiers.

Reads the tool-call JSON from stdin, inspects tool_input.command, exits 2 with
a stderr message on the highest-priority hit, else 0. Single self-contained
stdlib file; runs on Windows (python) and Unix (python3) alike.

  Tier 1  destructive git operations        hard block, NO escape hatch
  Tier 2  POSIX paths to native executables hard block, NO escape hatch
          (Windows/MSYS only — gated on sys.platform/OSTYPE, so macOS/Linux
          commands like `python3 x.py /tmp/f` never hit it)
  Tier 3  legacy CLI (grep/find/sed)        block, '# force-legacy' escapes

The escape hatch ('# force-legacy' line or ALLOW_LEGACY_CLI=1) opts out of the
modern-CLI preference ONLY — the path-correctness tier stays in force.

Execution-domain model (bash semantics):
  - single-quoted text is always data (device/remote commands, prose);
  - double-quoted text is data EXCEPT $(...) and `...` interiors — those are
    host-evaluated substitutions and are scanned as commands;
  - `[[ ... ]]` interiors are data (regex/test operands) except substitutions;
  - `name=( ... )` array literal interiors are data, dropped from segments;
  - `name()` function declarations drop the name (declaration executes
    nothing; the { } body stays live text, matched only at command position);
  - case-construct zones: patterns are data, bodies are live — `case $x in
    grep|find) echo y;; esac` allows, `case $x in a) grep y f;; esac` blocks;
  - comments (word-start #) are dropped to end of line;
  - heredoc bodies are stripped before matching (<<- tab terminators included);
  - command position = the command word of a segment (basename-normalized, so
    /usr/bin/git counts), reachable through a prefix chain of keywords /
    wrappers / VAR=val / wrapper flag+value pairs. 'echo sudo git clean' and
    'adb shell sudo git clean' are never calls; 'command -v grep' only prints.
  - static quoted payloads of bash/sh/zsh -c and eval run on the host and are
    re-scanned (depth-capped); dynamic payloads (`eval "$cmd"`) stay fail-open.

Perf contract: necessary-condition prefilters run first — commands containing
no git / grep|find|sed / (on Windows/MSYS) POSIX-path token never reach the
parser.

Failure-safe: malformed input, missing stdin, or any internal error exits 0
(allow). GUARD_SHELL_DEBUG=1 surfaces the swallowed error for diagnosis.
All emitted text is ASCII on purpose (GBK console safety).
"""

import json
import os
import re
import sys

# ---------------------------------------------------------------- prefilters

# Heredoc bodies are data. The match starts AT '<<' (the opener-line command
# prefix stays live: `grep -q x <<EOF` still blocks) and ends with a lookahead
# on the terminator's newline (post-EOF text keeps its own line — gluing it
# onto the opener forges `python - cd /d/...` phantom segments).
# Substituting '\n' keeps the line structure intact.
HEREDOC_RE = re.compile(
    r'<<\s*-?\s*["\']?(\w+)["\']?[ \t]*\r?\n.*?^[ \t]*\1(?=\r?\n|$)',
    re.M | re.S)

# The (?:\.exe)? groups keep git.exe/grep.exe inside the prefilter — the tier
# heads strip the suffix via basename(), so without it those forms never parse.
GIT_RE = re.compile(r'(?<![\w.-])git(?:\.[eE][xX][eE])?(?![\w.-])')
LEGACY_RE = re.compile(r'(?<![\w.-])(grep|find|sed)(?:\.[eE][xX][eE])?(?![\w.-])')
POSIX_PRE_RE = re.compile(r'(^|[\s"\'(=|;&])/[A-Za-z]+([/\s"\'|)&;]|$)')
FORCE_RE = re.compile(r'(?m)^\s*#\s*force-legacy')

# --------------------------------------------------------- command-position

PREFIX_KEYWORDS = {'do', 'then', 'elif', 'else', 'fi', 'if', 'while', 'until',
                   'for', 'in', 'done', 'case', 'esac', 'function', 'select',
                   'coproc', '!', '{', '}', '[[', ']]'}
PREFIX_WRAPPERS = {'sudo', 'env', 'nohup', 'nice', 'timeout', 'time', 'xargs',
                   'stdbuf', 'watch', 'command', 'builtin', 'setsid', 'exec'}
# Flags whose NEXT token is a value, not a command — per wrapper, because the
# same short flag means different things elsewhere (sudo -s is a switch while
# timeout -s SIGNAL takes a value).
WRAPPER_VALUE_FLAGS = {
    'sudo': {'-u', '-g', '-p', '--user', '--group'},
    'env': {'-u', '--unset', '-S', '--split-string'},
    'timeout': {'-k', '--kill-after', '--signal', '-s'},
    'nice': {'-n', '--adjustment'},
    'xargs': {'-I', '-E', '-n', '-P', '-s', '-L'},
    'stdbuf': {'-o', '-e', '-i'},
    'watch': {'-n', '-g'},
}

VARVAL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
FLAG_RE = re.compile(r'^-.')
NUM_RE = re.compile(r'^\d+([.]\d+)?[smh]?$')
IDENT_RE = re.compile(r'^[A-Za-z_]\w*$')


def basename(w):
    # backslash separators and a trailing .exe are Windows realities the
    # tier heads must normalize away (C:\Python312\python.exe == python)
    b = w.replace('\\', '/').rsplit('/', 1)[-1]
    if b.lower().endswith('.exe'):
        b = b[:-4]
    return b


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
        b = basename(w)
        if b in PREFIX_KEYWORDS or b in PREFIX_WRAPPERS:
            prev = b
            continue
        if prev:
            if FLAG_RE.match(w):
                # command/builtin -v|-V only print a path — nothing executes
                if prev in ('command', 'builtin') and w in ('-v', '-V'):
                    return -1
                pending_value = w in WRAPPER_VALUE_FLAGS.get(prev, ())
                continue
            if NUM_RE.match(w):
                continue
        return i
    return -1


# ------------------------------------------------------------------ segments

def split_segments(text):
    """Quote- and substitution-aware segment split. Separators are unquoted
    | & ; newline, ( subshell, $(...) and `...` (also inside double quotes).
    Modes: T top, S single-quote, D double-quote, C $(...), B `...`,
    A array literal, K [[ ]] test interior. Structural ( ) ` characters are
    dropped, so downstream token matching never sees glued noise like 'clean)'.
    Comments, array interiors, [[ ]] operands and case patterns are dropped
    as data; a case pattern's ) and ;; toggle pattern->body->pattern zones."""
    segs = []
    buf = []
    modes = ['T']
    zone = 0            # 0 normal, 1 case header, 2 case pattern, 3 case body
    word = []           # unquoted identifier chars feeding the zone machine
    adepth = 0          # array-literal paren depth
    aquote = ''         # quote seen inside an array literal
    lastc = ''
    i, n = 0, len(text)

    def flush_word():
        nonlocal zone
        w = ''.join(word)
        del word[:]
        if not w:
            return
        if w == 'case' and zone in (0, 3):
            zone = 1
        elif zone == 1 and w == 'in':
            zone = 2
            segs.append(''.join(buf))
            del buf[:]
        elif w == 'esac' and zone:
            zone = 0

    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        m = modes[-1]
        if m == 'S':
            if c == "'":
                modes.pop()
            buf.append(c)
        elif m == 'A':
            # Array literal interior: data, dropped. Track quotes so a paren
            # inside 'a)b' cannot close the literal early.
            if aquote:
                if c == aquote:
                    aquote = ''
            elif c in '\'"':
                aquote = c
            elif c == '(':
                adepth += 1
            elif c == ')':
                adepth -= 1
                if adepth == 0:
                    modes.pop()
                    buf.append(' ')
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
                segs.append(''.join(buf))
                del buf[:]
                modes.append('B')
            elif c == '$' and nxt == '(':
                segs.append(''.join(buf))
                del buf[:]
                modes.append('C')
                i += 2
                continue
            else:
                buf.append(c)
        elif m == 'K':
            # [[ ]] interior: test operands are data; substitutions still
            # execute on the host and get their own live segments.
            if c == ']' and nxt == ']':
                modes.pop()
                buf.append(' ')
                i += 2
                lastc = ']'
                continue
            if c == '`':
                segs.append(''.join(buf))
                del buf[:]
                modes.append('B')
            elif c == '$' and nxt == '(':
                segs.append(''.join(buf))
                del buf[:]
                modes.append('C')
                i += 2
                continue
        elif m == 'C':
            if c == ')':
                segs.append(''.join(buf))
                del buf[:]
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
                del buf[:]
                modes.append('C')
                i += 2
                continue
            elif c == '`':
                segs.append(''.join(buf))
                del buf[:]
                modes.append('B')
            elif c in '|&;\n':
                segs.append(''.join(buf))
                del buf[:]
            else:
                buf.append(c)
        elif m == 'B':
            if c == '`':
                modes.pop()
                segs.append(''.join(buf))
                del buf[:]
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
            elif c in '|&;\n':
                segs.append(''.join(buf))
                del buf[:]
            else:
                buf.append(c)
        else:
            # Mode T (top): command text, plus the case-construct zone machine.
            if zone == 2:
                # case pattern: data. ) opens the body as a live segment.
                if c == ')':
                    zone = 3
                    segs.append(''.join(buf))
                    del buf[:]
                elif c.isalnum() or c == '_':
                    word.append(c)
                else:
                    flush_word()
            elif c == '#' and (not buf or buf[-1] in ' \t' or lastc in ' \t\n'):
                # word-start comment: drop to end of line (data)
                nl = text.find('\n', i)
                i = n if nl == -1 else nl
            elif c == '[' and nxt == '[' and (not buf or buf[-1] in ' \t'):
                flush_word()
                modes.append('K')
                i += 2
                lastc = '['
                continue
            elif c == "'":
                flush_word()
                modes.append('S')
                buf.append(c)
            elif c == '"':
                flush_word()
                modes.append('D')
                buf.append(c)
            elif c == '`':
                flush_word()
                segs.append(''.join(buf))
                del buf[:]
                modes.append('B')
            elif c == '\\' and nxt:
                flush_word()
                buf.append(c)
                buf.append(nxt)
                i += 2
                continue
            elif c == '$' and nxt == '(':
                flush_word()
                segs.append(''.join(buf))
                del buf[:]
                modes.append('C')
                i += 2
                continue
            elif c == '(':
                flush_word()
                stripped = ''.join(buf).rstrip()
                if stripped and IDENT_RE.match(stripped) and nxt == ')':
                    # name() function declaration: drop the name, keep body live
                    del buf[:]
                    i += 2
                    lastc = ')'
                    continue
                if buf and buf[-1] == '=':
                    modes.append('A')
                    adepth = 1
                    aquote = ''
                    buf.append(c)
                else:
                    segs.append(''.join(buf))
                    del buf[:]
            elif c == ')':
                flush_word()
                # subshell closer in top mode: structural, dropped
            elif c in '|&;':
                flush_word()
                if c == ';' and zone == 3 and lastc == ';':
                    zone = 2
                elif c == ';' and zone == 1:
                    pass
                else:
                    segs.append(''.join(buf))
                    del buf[:]
            elif c == '\n':
                flush_word()
                segs.append(''.join(buf))
                del buf[:]
            else:
                if c.isalnum() or c == '_':
                    word.append(c)
                else:
                    flush_word()
                buf.append(c)
        i += 1
        lastc = c
    flush_word()
    segs.append(''.join(buf))
    return [s for s in segs if s.strip()]


# --------------------------------------------------------------------- tiers

GIT_VALUE_FLAGS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}
NATIVE_RE = re.compile(r'^(?:python3?|py|pwsh|powershell|cmd|node|rg|fd|bat|jq|yq|sd)$')
POSIX_TOK_RE = re.compile(r'^/(?:tmp|[A-Za-z])(?:/|$)')
CMD_SWITCH_RE = re.compile(r'^/[A-Za-z]$')
REDIR_RE = re.compile(r'^(?:\d)?>{1,2}$|^<$')

# adb/fastboot are native executables too: on Git Bash, MSYS rewrites any
# leading-/ argument into a Windows path before the device sees it, so an
# unquoted device path is a guaranteed runtime failure.
ADB_HEADS = {'adb', 'fastboot'}
DEVICE_PATH_RE = re.compile(
    r'^/(?:sdcard|storage|data|system|vendor|etc|proc|sys|dev|sbin|bin)(?:/|$)')
NO_PATHCONV_RE = re.compile(r'^MSYS2?_NO_PATHCONV=')
DQ_SPAN_RE = re.compile(r'"[^"]*"')
SQ_SPAN_RE = re.compile(r"'[^']*'")

LOCAL_SHELLS = {'bash', 'sh', 'zsh', 'dash', 'ksh'}


def dangerous_git_hit(segments):
    for seg in segments:
        toks = seg.strip().split()
        if not toks:
            continue
        ci = command_word_index(toks)
        if ci < 0 or basename(toks[ci]) != 'git':
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


def winpath_hits(segments):
    """First tier-2 violation as (kind, token): 'native' = POSIX path token
    handed to a native Windows executable, 'adb' = unquoted Android device
    path handed to adb/fastboot (MSYS mangles it before the device sees it).
    Quoted spans after adb are the device command — data, not argv — and a
    MSYS_NO_PATHCONV prefix disables path conversion, so both stay allowed."""
    for seg in segments:
        toks = seg.strip().split()
        if not toks:
            continue
        ci = command_word_index(toks)
        if ci < 0:
            continue
        head = basename(toks[ci])
        if head in ADB_HEADS:
            if any(NO_PATHCONV_RE.match(t) for t in toks[:ci]):
                continue
            unquoted = SQ_SPAN_RE.sub(' ', DQ_SPAN_RE.sub(' ', seg))
            for tok in unquoted.split():
                tok = tok.strip('\'"')
                if DEVICE_PATH_RE.match(tok):
                    return ('adb', tok)
            continue
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
                return ('native', tok)
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
        if basename(toks[ci]) in ('grep', 'find', 'sed'):
            return basename(toks[ci])
    return None


def payload_segments(segments, depth, want_path=False):
    """Static quoted payloads of bash/sh/zsh -c and eval run on this host:
    re-split and re-scan them (depth-capped). Dynamic payloads stay fail-open.
    want_path keeps tier 2 covered too — without it, `bash -c 'python x.py
    /tmp/f'` would slip past the no-escape path tier."""
    if depth >= 2:
        return []
    extra = []
    for seg in segments:
        toks = seg.split()
        ci = command_word_index(toks)
        if ci < 0:
            continue
        head = basename(toks[ci])
        args = toks[ci + 1:]
        if head in LOCAL_SHELLS and len(args) >= 2 and args[0] == '-c':
            payload = ' '.join(args[1:])
        elif head == 'eval' and args:
            payload = ' '.join(args)
        else:
            continue
        payload = payload.strip()
        if len(payload) >= 2 and payload[0] == payload[-1] and payload[0] in '\'"':
            payload = payload[1:-1]
        if not (GIT_RE.search(payload) or LEGACY_RE.search(payload)
                or (want_path and POSIX_PRE_RE.search(payload))):
            continue
        inner = split_segments(payload)
        extra.extend(inner)
        extra.extend(payload_segments(inner, depth + 1, want_path))
    return extra


# ---------------------------------------------------------------------- main

MSG_GIT = ("BLOCKED: destructive git operation ({why}). The user has reserved "
           "these operations for themselves — use the /commit workflow or ask "
           "the user to run it by hand.")
MSG_PATH = ("BLOCKED: POSIX path '{tok}' handed to a native Windows "
            "executable. Native processes only understand Windows absolute "
            "paths. Temp files: use $env:TEMP (from bash: cygpath -w $TEMP); "
            "other paths: convert with cygpath -w first. This is a "
            "correctness rule; '# force-legacy' does not bypass it.")
MSG_ADB = ("BLOCKED: device path '{tok}' passed unquoted to adb on Git Bash - "
           "MSYS rewrites leading-/ arguments into Windows paths before the "
           "device sees them, so the command fails at runtime. Quote the "
           "whole device command (adb shell \"dump /sdcard/x\"), use // on "
           "pull/push remote paths (adb pull //sdcard/x out/), or prefix "
           "MSYS_NO_PATHCONV=1 and give local paths in Windows form. "
           "See ~/.claude/references/android-adb.md.")
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

    # Tier 2 only exists in the Windows/MSYS world. OSTYPE, when present, is
    # the shell truth (msys/cygwin = Git Bash, anything else = a Unix-domain
    # shell like WSL where /tmp is valid); without OSTYPE — the hook spawns
    # via cmd.exe — sys.platform is the fallback. GUARD_SHELL_FORCE_MSYS
    # enables it for testing. On macOS/Linux a /tmp argument to python3 is
    # perfectly valid and must never block.
    _ostype = os.environ.get('OSTYPE', '')
    if _ostype:
        is_msys = _ostype.startswith(('msys', 'cygwin'))
    else:
        is_msys = sys.platform in ('win32', 'cygwin', 'msys')
    if os.environ.get('GUARD_SHELL_FORCE_MSYS') == '1':
        is_msys = True

    try:
        stripped = HEREDOC_RE.sub('\n', command)
        need_git = bool(GIT_RE.search(stripped))
        need_legacy = (not escape) and bool(LEGACY_RE.search(stripped))
        need_path = is_msys and bool(POSIX_PRE_RE.search(stripped))
        if not (need_git or need_legacy or need_path):
            sys.exit(0)

        segs = split_segments(stripped)
        segs += payload_segments(segs, 0, want_path=need_path)

        if need_git:
            why = dangerous_git_hit(segs)
            if why:
                sys.stderr.write(MSG_GIT.format(why=why))
                sys.exit(2)

        if need_path:
            hit = winpath_hits(segs)
            if hit:
                kind, tok = hit
                msg = MSG_ADB if kind == 'adb' else MSG_PATH
                sys.stderr.write(msg.format(tok=tok))
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
        if os.environ.get('GUARD_SHELL_DEBUG') == '1':
            import traceback
            traceback.print_exc()
        sys.exit(0)  # any unexpected failure — don't block


if __name__ == '__main__':
    main()
