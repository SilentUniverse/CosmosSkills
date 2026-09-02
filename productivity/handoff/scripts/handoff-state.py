#!/usr/bin/env python3
"""Snapshot git state and locate the newest active handoff without rereading the tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


def _git(root: Path, args: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root)] + list(args),
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(message or "git command failed")
    return completed.stdout


def _is_handoff(path: str) -> bool:
    parts = Path(path).parts
    return bool(parts) and parts[0] == ".scratch" and parts[-1] == "handoff.md"


def _is_transient_cache(path: str) -> bool:
    parts = Path(path).parts
    return len(parts) >= 2 and parts[0] == ".scratch" and (
        parts[-1] in {"preflight-receipt.json", "wave-ledger.json"}
        or (len(parts) >= 3 and parts[-2] == "receipts" and parts[-1].endswith(".json"))
    )


def snapshot(root: Path) -> Mapping[str, Any]:
    repo = root.resolve()
    head = _git(repo, ["rev-parse", "--short", "HEAD"]).decode("ascii").strip()
    tracked = _git(
        repo,
        [
            "diff",
            "--binary",
            "HEAD",
            "--",
            ".",
            ":(exclude).scratch/handoff.md",
            ":(exclude,glob).scratch/*/handoff.md",
        ],
    )
    untracked = _git(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    digest = hashlib.sha256()
    digest.update(tracked)
    dirty_paths = []
    for raw in untracked.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape")
        if _is_handoff(relative) or _is_transient_cache(relative):
            continue
        dirty_paths.append(relative)
        digest.update(b"\0untracked\0" + raw + b"\0")
        path = repo / relative
        if path.is_file():
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    digest.update(block)
    status = _git(repo, ["status", "--porcelain=v1", "-z"])
    tracked_dirty = []
    for record in status.split(b"\0"):
        if len(record) < 4:
            continue
        relative = record[3:].decode("utf-8", errors="replace")
        if (
            _is_handoff(relative)
            or _is_transient_cache(relative)
            or relative.startswith(".scratch/tmp/")
        ):
            continue
        tracked_dirty.append(relative)
    paths = sorted(set(tracked_dirty + dirty_paths))
    return {
        "git_base": head,
        "worktree_digest": digest.hexdigest(),
        "dirty": bool(tracked or dirty_paths),
        "dirty_count": len(paths),
        "dirty_paths": paths,
    }


CAPSULES = ("active-work", "awaiting-alignment", "external-pending")


def _frontmatter(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def locate(root: Path, feature: Optional[str] = None) -> Mapping[str, Any]:
    repo = root.resolve()
    if feature:
        candidates = [repo / ".scratch" / feature / "handoff.md"]
    else:
        candidates = [repo / ".scratch" / "handoff.md"]
        candidates.extend(sorted((repo / ".scratch").glob("*/handoff.md")))
    active = []
    for path in candidates:
        if not path.is_file():
            continue
        frontmatter = _frontmatter(path)
        if frontmatter.get("type") == "handoff" and frontmatter.get("status") == "active":
            active.append((frontmatter.get("date", ""), path.stat().st_mtime_ns, path, frontmatter))
    if not active:
        return {"status": "none", "path": None}
    _, _, path, frontmatter = max(active, key=lambda row: (row[0], row[1]))
    capsule = frontmatter.get("capsule") or "active-work"
    if capsule not in CAPSULES:
        raise ValueError(
            "%s: capsule '%s' not in %s" % (path, capsule, "|".join(CAPSULES))
        )
    current = snapshot(repo)
    saved_base = frontmatter.get("git_base", "")
    saved_digest = frontmatter.get("worktree_digest", "")
    if saved_base != current["git_base"]:
        exists = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", saved_base + "^{commit}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        baseline = "head-diverged" if exists else "unknown-base"
    elif not saved_digest:
        baseline = "legacy-no-worktree-digest"
    elif saved_digest != current["worktree_digest"]:
        baseline = "worktree-diverged"
    else:
        baseline = "match"
    return {
        "status": "active",
        "path": str(path.relative_to(repo)),
        "feature": frontmatter.get("feature"),
        "capsule": capsule,
        "date": frontmatter.get("date"),
        "baseline": baseline,
        "saved_git_base": saved_base,
        "current_git_base": current["git_base"],
        "saved_worktree_digest": saved_digest or None,
        "current_worktree_digest": current["worktree_digest"],
        "dirty_count": current["dirty_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("repo_root", type=Path)
    find = commands.add_parser("locate")
    find.add_argument("repo_root", type=Path)
    find.add_argument("feature", nargs="?")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = snapshot(args.repo_root) if args.command == "snapshot" else locate(
            args.repo_root, args.feature
        )
    except (OSError, ValueError) as exc:
        print("handoff-state: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return 3 if args.command == "locate" and data["status"] == "none" else 0


if __name__ == "__main__":
    raise SystemExit(main())
