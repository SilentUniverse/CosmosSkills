#!/usr/bin/env python3
"""Select, publish, and consume an integrity-bound continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

WORKFLOW_ROOT = Path(__file__).resolve().parents[2]
if str(WORKFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_ROOT))
from workflow_runtime import reading, transaction, write_state


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
        parts[1] == "tmp" or parts[1].startswith(".workflow")
        or parts[-1] in {"preflight-receipt.json", "preflight-receipt.json.lock", "wave-ledger.json"}
        or (len(parts) >= 3 and parts[-2] == "receipts" and parts[-1].endswith(".json"))
    )


@reading
def snapshot(root: Path, handoff: Optional[Path] = None) -> Mapping[str, Any]:
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
    result = {
        "git_base": head,
        "worktree_digest": digest.hexdigest(),
        "dirty": bool(tracked or dirty_paths),
        "dirty_count": len(paths),
        "dirty_paths": paths,
    }
    if handoff is not None:
        path = target_path(repo, handoff)
        result.update(path=path.relative_to(repo).as_posix(), version=version(path))
    return result


def target_path(root, reference):
    root = Path(root).resolve()
    path = (root / reference).resolve()
    parts = path.relative_to(root).parts
    if not (len(parts) in (2, 3) and parts[0] == ".scratch" and parts[-1] == "handoff.md"):
        raise ValueError("target must be .scratch/[feature/]handoff.md")
    return path


def version(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def new(root, draft, feature=None, capsule="active-work"):
    root = Path(root).resolve()
    path = (root / draft).resolve()
    if capsule not in CAPSULES:
        raise ValueError("unknown handoff capsule")
    if path.exists():
        raise ValueError("draft already exists: %s" % draft)
    state = snapshot(root)
    slug = feature if feature not in (None, "", "null") else "null"
    target = ".scratch/handoff.md" if slug == "null" else ".scratch/%s/handoff.md" % slug
    target_file = target_path(root, target)
    if target_file.exists():
        raise ValueError(
            "handoff already exists at %s; update it in place instead of creating a draft" % target
        )
    content = (
        "---\n"
        "schema_version: 2\n"
        "type: handoff\n"
        "feature: %s\n"
        "capsule: %s\n"
        "git_base: %s\n"
        "worktree_digest: %s\n"
        "status: active\n"
        "date: %s\n"
        "---\n\n"
        "# Handoff: <topic>\n\n"
        "## Continue\n"
        "1. READ `<minimum exact paths>`\n"
        "2. RUN `<exact bounded command>`\n"
        "3. CONFIRM `<observable predicate>`; THEN `<next edit/decision>`\n\n"
        "## State\n"
        "<objective still owed + current node + pointers to authoritative artifacts/evidence>\n\n"
        "## Decisions\n"
        "- <decision, authorization, or invariant> — <scope and constraint a future agent must preserve>\n\n"
        "## Avoid\n"
        "- <failed or rejected path> — <evidence>\n"
        % (slug, capsule, state["git_base"], state["worktree_digest"], date.today().isoformat())
    )
    write_state(root, path, content)
    return {
        "path": path.relative_to(root).as_posix(),
        "target": target,
        "expected": version(target_file),
        "git_base": state["git_base"],
        "version": version(path),
    }


def publish(root, reference, expected, source):
    root = Path(root).resolve()
    path = target_path(root, reference)
    with transaction(root):
        if version(path) != expected:
            raise ValueError("handoff changed; preserve it and reconcile before publishing")
        raw = Path(source).read_text(encoding="utf-8-sig")
        fm = _frontmatter(Path(source), raw)
        if fm.get("type") != "handoff" or fm.get("status") != "active":
            raise ValueError("source must be an active handoff")
        if fm.get("capsule", "active-work") not in CAPSULES:
            raise ValueError("unknown handoff capsule")
        expected_feature = path.parent.name if path.parent != root / ".scratch" else "null"
        if fm.get("feature") != expected_feature:
            raise ValueError("handoff feature does not match its target")
        end = raw.find("\n---", 4)
        if end < 0:
            raise ValueError("handoff frontmatter is not closed")
        head, body = raw[:end], raw[end:]
        state = snapshot(root)
        if any(fm.get(key) != state[key] for key in ("git_base", "worktree_digest")):
            raise ValueError("handoff baseline changed while drafting; reconcile and snapshot again")
        for key, value in {"generation": uuid.uuid4().hex,
                           "git_base": state["git_base"],
                           "worktree_digest": state["worktree_digest"]}.items():
            line = "%s: %s" % (key, value)
            if re.search(r"(?m)^" + key + r":.*$", head):
                head = re.sub(r"(?m)^" + key + r":.*$", line, head)
            else:
                head += "\n" + line
        content = head + body
        write_state(root, path, content)
    return {"path": path.relative_to(root).as_posix(), "version": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def consume(root, reference, expected):
    root = Path(root).resolve()
    path = target_path(root, reference)
    with transaction(root):
        if expected == "absent" or version(path) != expected:
            raise ValueError("handoff changed; the selected version cannot be consumed")
        write_state(root, path, None)
    return {"path": path.relative_to(root).as_posix(), "status": "consumed"}


CAPSULES = ("active-work", "awaiting-alignment", "external-pending")


def _frontmatter(path: Path, raw: Optional[str] = None) -> Dict[str, str]:
    lines = (path.read_text(encoding="utf-8-sig") if raw is None else raw).splitlines()
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


@reading
def locate(root: Path, feature: Optional[str] = None, reference: Optional[Path] = None) -> Mapping[str, Any]:
    repo = root.resolve()
    if reference is not None:
        candidates = [target_path(repo, reference)]
    elif feature:
        if Path(feature).name != feature or feature in (".", "..") or "\\" in feature:
            raise ValueError("feature must be a single directory name")
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
    if len(active) > 1:
        return {
            "status": "ambiguous", "path": None,
            "candidates": [
                {"path": row[2].relative_to(repo).as_posix(), "feature": row[3].get("feature")}
                for row in active
            ],
        }
    _, _, path, frontmatter = active[0]
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
        "version": version(path),
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
    snap.add_argument("--path", type=Path)
    find = commands.add_parser("locate")
    find.add_argument("repo_root", type=Path)
    find.add_argument("feature", nargs="?")
    find.add_argument("--path", type=Path)
    make = commands.add_parser("new")
    make.add_argument("repo_root", type=Path)
    make.add_argument("draft", type=Path)
    make.add_argument("--feature", default=None)
    make.add_argument("--capsule", default="active-work", choices=CAPSULES)
    for name in ("publish", "consume"):
        change = commands.add_parser(name)
        change.add_argument("repo_root", type=Path)
        change.add_argument("path", type=Path)
        change.add_argument("--expected", required=True)
        if name == "publish":
            change.add_argument("--source", type=Path, required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            data = snapshot(args.repo_root, args.path)
        elif args.command == "locate":
            data = locate(args.repo_root, args.feature, args.path)
        elif args.command == "new":
            data = new(args.repo_root, args.draft, args.feature, args.capsule)
        elif args.command == "publish":
            data = publish(args.repo_root, args.path, args.expected, args.source)
        else:
            data = consume(args.repo_root, args.path, args.expected)
    except (OSError, ValueError) as exc:
        print("handoff-state: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return {"none": 3, "ambiguous": 4}.get(data.get("status"), 0)


if __name__ == "__main__":
    raise SystemExit(main())
