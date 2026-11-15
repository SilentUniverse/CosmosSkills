#!/usr/bin/env python
# Mechanical gate for ARTIFACT-FORMAT.md: .scratch/<feat>/FEATURE.md documents.
# A retired CODEBASE.md map or nested generated block gets a migration hint, never a violation.
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
BEGIN_GEN = re.compile(r"^<!--.*BEGIN GENERATED codebase")
LEGACY = re.compile(r"^(PRD(-v\d+)?\.md|issues|verifier\.json|spec-review\.json|spec-acceptances|spec-accepted\.md|experience-contract.*\.json|SUMMARY\.md)$")
MIGRATION = (
    "retired CODEBASE.md map artifacts (%s); migrate when next touched: "
    "1) move commands into the native entry (package.json, Makefile, justfile, pyproject) and "
    "AGENTS.md `## Commands`; 2) move invariants, including nested CLAUDE.md generated blocks, up the "
    "/correct ladder (architecture -> types -> check -> test -> AGENTS.md rule line); "
    "3) delete the retired files and blocks"
)

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
    has_cb = feature is None and os.path.isfile(os.path.join(root, "CODEBASE.md"))

    errors = []
    n_features = n_units = 0

    def err(msg):
        errors.append(msg)

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

    retired = ["CODEBASE.md"] if has_cb else []
    if feature is None and (has_scratch or has_cb):
        for nf_path, rel in nested_claude_files(root):
            with open(nf_path, "rb") as f:
                lines = f.read().decode("utf-8-sig", errors="replace").splitlines()
            if any(BEGIN_GEN.match(line) for line in lines):
                retired.append(rel + " generated block")
    if retired:
        print("verify-artifacts: hint: %s" % (MIGRATION % ", ".join(retired)))
    if not has_scratch:
        print("verify-artifacts: no .scratch/ under %s - nothing to check, clean." % root)
        return 0
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
        "verify-artifacts: OK%s - checked %d feature(s), %d unit(s)."
        % (" feature=%s" % feature if feature is not None else "", n_features, n_units)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
