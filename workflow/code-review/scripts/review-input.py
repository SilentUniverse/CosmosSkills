#!/usr/bin/env python3
"""Pin working-tree review inputs into one bundle for /code-review axes.

Resolves HEAD, captures `git status --short` and the review diff, and embeds the
contents of in-scope untracked files (git diff omits them, so an empty tracked
diff does not prove an empty review). Scope comes from the reviewer's judgment:
`--paths` names the directories/files in scope; untracked files outside it are
listed as excluded rather than silently dropped. By default the diff is the
working tree against HEAD and in-scope untracked files are embedded; `--base <ref>`
reviews a committed range instead, resolving `<ref>...HEAD` plus the commit list
(capped at `MAX_COMMITS`) and listing untracked working files as out-of-range.
Both the diff and each embedded file are capped at `--max-bytes` (default 64 KiB)
with a truncation marker, so a stray binary, build artifact, or oversized diff
cannot balloon a subagent brief.

Output: one JSON object on stdout (or --output). Exit codes: 0 ok; 1 not a git
repository / git failure; 2 usage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _git(repo: Path, args: Sequence[str]) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )
    if process.returncode != 0:
        print(
            "review-input: git %s failed: %s"
            % (" ".join(args), (process.stderr or "").strip()),
            file=sys.stderr,
        )
        raise SystemExit(1)
    return process.stdout


def _status_entries(repo: Path) -> List[Dict[str, str]]:
    raw = _git(
        repo,
        ["-c", "core.quotepath=false", "status", "--porcelain=v1", "-z",
         "--untracked-files=all"],
    )
    tokens = raw.split("\0")
    entries: List[Dict[str, str]] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        token = tokens[index]
        xy, path = token[:2], token[3:]
        index += 1
        if xy and xy[0] in "CR":
            # Rename/copy entries carry the source path in the next NUL field.
            index += 1
        entries.append({"xy": xy, "path": path})
    return entries


def _in_scope(path: str, scopes: Sequence[str]) -> bool:
    if not scopes:
        return True
    for scope in scopes:
        if path == scope or path.startswith(scope.rstrip("/") + "/"):
            return True
    return False


def _cap_text(text: str, max_bytes: int, label: str) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="replace") + (
        "\n[review-input: %s truncated at %d of %d bytes]\n" % (label, max_bytes, len(raw))
    )


MAX_COMMITS = 200


def build_bundle(
    repo: Path,
    *,
    scopes: Sequence[str] = (),
    max_bytes: int = 65536,
    base: Optional[str] = None,
) -> Dict[str, Any]:
    repo = repo.resolve()
    head = _git(repo, ["rev-parse", "HEAD"]).strip()
    branch = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if base:
        resolved_base: Optional[str] = _git(repo, ["rev-parse", base]).strip()
        diff = _git(repo, ["diff", "%s...HEAD" % resolved_base])
        raw_commits = [line for line in _git(
            repo, ["log", "--oneline", "%s..HEAD" % resolved_base]
        ).splitlines() if line.strip()]
        # git log is newest-first; keep the most recent commits and flag the cut.
        commits = raw_commits[:MAX_COMMITS]
        commits_truncated = len(raw_commits) > MAX_COMMITS
    else:
        resolved_base = None
        diff = _git(repo, ["diff", "HEAD"])
        commits = []
        commits_truncated = False
    entries = _status_entries(repo)
    untracked: List[Dict[str, Any]] = []
    excluded: List[Dict[str, str]] = []
    for entry in entries:
        path = entry["path"]
        if entry["xy"] != "??":
            continue
        if base:
            # A committed-range review judges commits, not the working tree;
            # embedding stray untracked files would contaminate the axes.
            excluded.append({"path": path, "reason": "out-of-range"})
            continue
        if not _in_scope(path, scopes):
            excluded.append({"path": path, "reason": "out-of-scope"})
            continue
        raw = (repo / path).read_bytes()
        truncated = len(raw) > max_bytes
        # Review bundles feed prompts; normalize Windows CRLF to the LF that
        # `git diff` (and every other embedded line) uses. A truncation cut can
        # strand one \r after its \n — drop it, it is a slicing artifact.
        content = raw[:max_bytes].decode("utf-8", errors="replace").replace("\r\n", "\n")
        if truncated and content.endswith("\r"):
            content = content[:-1]
        if truncated:
            content += "\n[review-input: truncated at %d of %d bytes]\n" % (
                max_bytes, len(raw)
            )
        untracked.append(
            {"path": path, "bytes": len(raw), "truncated": truncated, "content": content}
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "branch": branch,
        "head": head,
        "status_short": [entry["xy"] + " " + entry["path"] for entry in entries],
        "base": resolved_base,
        "commits": commits,
        "commits_truncated": commits_truncated,
        "diff_head": _cap_text(diff, max_bytes, "diff"),
        "untracked": untracked,
        "excluded": excluded,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument(
        "--paths",
        default="",
        help="comma-separated in-scope directories/files for untracked contents",
    )
    parser.add_argument("--max-bytes", type=int, default=65536)
    parser.add_argument(
        "--base",
        default=None,
        help="review the committed range <base>...HEAD instead of the working tree",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo = args.repo_root
    if subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-dir"],
        capture_output=True, text=True, check=False,
    ).returncode != 0:
        print("review-input: not a git repository: %s" % repo, file=sys.stderr)
        return 1
    scopes = [item for item in args.paths.split(",") if item.strip()]
    bundle = build_bundle(
        repo, scopes=scopes, max_bytes=args.max_bytes, base=args.base
    )
    payload = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
