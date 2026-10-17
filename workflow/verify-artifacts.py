#!/usr/bin/env python
# Mechanical gate for ARTIFACT-FORMAT.md: .scratch/<feat>/FEATURE.md documents and the CODEBASE.md map.
# Stdlib only. Exit: 0 clean, 1 violations, 2 usage.
# Invoke: python verify-artifacts.py [<repo-root>] [--feature <feat>]
# If the `python` interpreter is missing, python3 verify-artifacts.py [<repo-root>]
# Do not retry python3 after a non-zero gate exit (that is a contract violation).
#
import os
import re
import sys
from pathlib import Path

ENGINEERING_ROOT = Path(__file__).resolve().parent
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
import feature_doc

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".scratch",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "out",
    ".next",
    "__pycache__",
}
ROSTER_ILLEGAL = re.compile(r'[<>:"|?*{}]')
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
BEGIN_GEN = re.compile(r"^<!--.*BEGIN GENERATED codebase")
END_GEN = re.compile(r"^<!--.*END GENERATED codebase")
GIT_BASE = re.compile(r"^git_base:\s*\S+")
FEN_QU = "\u5206\u533a"  # roster heading word 分区
LEGACY = re.compile(r"^(PRD(-v\d+)?\.md|issues|verifier\.json|spec-review\.json|spec-acceptances|spec-accepted\.md|experience-contract.*\.json|SUMMARY\.md)$")

BAD_UTF8 = set()


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig", errors="replace")
    if "\ufffd" in text:
        BAD_UTF8.add(path)
    return text


def read_lines(path):
    return read_text(path).splitlines()


def get_frontmatter(path, lines=None):
    """Scalar frontmatter keys; None if absent or unterminated."""
    if lines is None:
        lines = read_lines(path)
    if len(lines) < 2 or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = FM_KEY.match(line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return None


def nested_claude_files(root):
    out = []
    stack = [root]
    root_abs = os.path.abspath(root)
    while stack:
        d = stack.pop()
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            p = os.path.join(d, name)
            try:
                is_dir = os.path.isdir(p)
            except OSError:
                continue
            if is_dir:
                if name in SKIP_DIRS:
                    continue
                stack.append(p)
            elif name == "CLAUDE.md":
                rel = os.path.relpath(p, root_abs).replace("\\", "/")
                if rel != "CLAUDE.md":
                    out.append((p, rel))
    out.sort(key=lambda x: x[1])
    return out


def main(argv):
    # Stock Windows consoles/pipes default to the ANSI code page; never let an
    # un-encodable path or message kill the report mid-list.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    BAD_UTF8.clear()
    args = list(argv[1:])
    if args in (["--help"], ["-h"]):
        print("usage: python verify-artifacts.py [<repo-root>] [--feature <feat>]")
        return 0
    feature = None
    if "--feature" in args:
        index = args.index("--feature")
        if index + 1 >= len(args) or args[index + 1].startswith("--"):
            print("verify-artifacts: --feature requires a feature slug", file=sys.stderr)
            return 2
        feature = args[index + 1]
        del args[index:index + 2]
    if len(args) > 1 or any(arg.startswith("--") for arg in args):
        print(
            "verify-artifacts: usage: python verify-artifacts.py [<repo-root>] [--feature <feat>]",
            file=sys.stderr,
        )
        return 2
    root = os.path.abspath(args[0] if args else os.getcwd())
    scratch = os.path.join(root, ".scratch")
    has_scratch = os.path.isdir(scratch)
    cb_path = os.path.join(root, "CODEBASE.md")
    has_cb = feature is None and os.path.isfile(cb_path)

    errors = []
    n_features = n_units = n_cb_blocks = 0

    def err(msg):
        errors.append(msg)

    budget = 40
    roster_paths = {}
    if has_cb:
        fm = get_frontmatter(cb_path)
        if fm is None:
            err("%s: no YAML frontmatter" % cb_path)
        else:
            if fm.get("type") != "codebase":
                err("%s: type '%s' != codebase" % (cb_path, fm.get("type", "")))
            if not ISO_DATE.match(str(fm.get("generated", ""))):
                err("%s: generated not ISO YYYY-MM-DD" % cb_path)
            b = str(fm.get("budget", ""))
            if re.match(r"^\d+$", b):
                budget = int(b)
        cb_lines = read_lines(cb_path)
        fm_end = -1
        if len(cb_lines) >= 2 and cb_lines[0].strip() == "---":
            for i in range(1, len(cb_lines)):
                if cb_lines[i].strip() == "---":
                    fm_end = i
                    break
        in_roster = False
        body_count = 0
        for i in range(fm_end + 1, len(cb_lines)):
            line = cb_lines[i]
            if line.startswith("## "):
                in_roster = ("roster" in line) or (FEN_QU in line)
                body_count += 1
                continue
            if line.strip() == "":
                continue
            if in_roster and re.match(r"^\s*-", line):
                m = re.match(r"^\s*-\s+`([^`]+)", line)
                if m:
                    roster_paths[m.group(1).rstrip("/")] = True
                continue
            body_count += 1
        if body_count > budget:
            err(
                "%s: root body %d lines (excl. roster) > budget %d - relocate -> condense -> raise "
                "(raise carries justification in the change; set 'budget:' in frontmatter to adopt current size)"
                % (cb_path, body_count, budget)
            )
        for p in list(roster_paths.keys()):
            if ROSTER_ILLEGAL.search(p):
                err(
                    "%s: roster path '%s' uses placeholder/glob syntax - write a real existing directory "
                    "(one representative path per pattern)" % (cb_path, p)
                )
                continue
            dir_path = os.path.join(root, p.replace("/", os.sep))
            try:
                ok = os.path.isdir(dir_path)
            except (OSError, ValueError):
                ok = False
            if not ok:
                err("%s: roster path '%s' is not an existing directory" % (cb_path, p))

    if feature is not None:
        if (
            not feature
            or feature in (".", "..")
            or "/" in feature
            or "\\" in feature
            or os.path.basename(feature) != feature
        ):
            print("verify-artifacts: feature must be one directory name")
            return 1
        feature_path = os.path.realpath(os.path.join(scratch, feature))
        if (
            not os.path.isfile(os.path.join(feature_path, feature_doc.FILE))
            or os.path.dirname(feature_path) != os.path.realpath(scratch)
        ):
            print("verify-artifacts: feature '%s' not found under %s" % (feature, scratch))
            return 1
    if not has_scratch and not has_cb:
        print("verify-artifacts: no .scratch/ and no CODEBASE.md under %s - nothing to check, clean." % root)
        return 0

    for nf_path, rel in (nested_claude_files(root) if feature is None else []):
        nf_lines = read_lines(nf_path)
        begins = sum(1 for x in nf_lines if BEGIN_GEN.match(x))
        ends = sum(1 for x in nf_lines if END_GEN.match(x))
        if begins == 0:
            continue
        if begins != ends:
            err("%s: BEGIN/END GENERATED marker count mismatch (%d/%d)" % (nf_path, begins, ends))
            continue
        in_block = False
        has_base = False
        content = 0
        bi = 0
        for s in nf_lines:
            if BEGIN_GEN.match(s):
                in_block = True
                bi += 1
                has_base = False
                content = 0
                n_cb_blocks += 1
                continue
            if END_GEN.match(s):
                if not has_base:
                    err("%s: block %d missing git_base:" % (nf_path, bi))
                if content > 8:
                    err(
                        "%s: block %d has %d content lines > 8 - relocate -> condense -> raise"
                        % (nf_path, bi, content)
                    )
                in_block = False
                continue
            if not in_block:
                continue
            if GIT_BASE.match(s):
                has_base = True
                continue
            if s.strip() != "":
                content += 1
        if not has_cb:
            err("%s: generated block exists but root CODEBASE.md is missing" % nf_path)

    names = feature_doc.feature_names(root) if feature is None else [feature]
    if has_scratch:
        for entry in sorted(os.listdir(scratch)):
            directory = os.path.join(scratch, entry)
            if feature is not None and entry != feature or not os.path.isdir(directory):
                continue
            legacy = sorted(name for name in os.listdir(directory) if LEGACY.match(name))
            if legacy:
                err("%s: legacy planning artifacts (%s); move their live content into FEATURE.md and delete them"
                    % (directory, ", ".join(legacy)))
    for name in names:
        try:
            doc = feature_doc.load(root, name)
        except ValueError as exc:
            err("%s: %s" % (os.path.join(scratch, name), exc))
            continue
        n_features += 1
        n_units += len(doc.units)
        read_text(str(doc.path))
        location = doc.path
        for unit_id, message in feature_doc.problems(doc):
            err("%s: %s%s" % (location, unit_id + " " if unit_id else "", message))
        for unit in doc.units:
            if unit.status == "done" and unit.completion is not None:
                problem = feature_doc.completion_problem(doc, unit)
                if problem:
                    err("%s: %s completion proof is invalid: %s" % (location, unit.id, problem))

    for p in sorted(BAD_UTF8):
        err("%s: not valid UTF-8" % p)

    if errors:
        print("verify-artifacts: %d violation(s)" % len(errors))
        for e in errors:
            print("  %s" % e)
        return 1
    print(
        "verify-artifacts: OK%s - checked %d feature(s), %d unit(s), %d codebase block(s)."
        % (" feature=%s" % feature if feature is not None else "", n_features, n_units, n_cb_blocks)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
