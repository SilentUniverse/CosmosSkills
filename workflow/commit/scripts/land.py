#!/usr/bin/env python3
"""Land one verified topic commit: gh PR flow on GitHub, native Git elsewhere.

Input is an already-validated commit — the current (or --branch) topic branch
tip. The script never stages, scopes, or edits the caller's worktree; the
native engine lands through an isolated clean worktree. It is idempotent on
the verified head SHA: a re-run after a mid-sequence failure detects an
already merged PR or already published default branch and reports it instead
of repeating a step.

Engine `auto` uses gh when authenticated and the remote resolves as GitHub,
otherwise native. Exit codes: 0 landed (including already landed); 1 bad
input; 2 environment (no remote, detached HEAD, no usable engine); 3 head or
target mismatch needing resolution; 4 pending required checks; 5 verification
failed; 6 a git/gh step failed. One JSON object on stdout describes the run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


class LandError(Exception):
    def __init__(self, code: int, message: str, report: Mapping[str, Any]):
        super().__init__(message)
        self.code = code
        self.report = dict(report)


def _git(
    repo: Path, args: Sequence[str], *, check: bool = True
) -> subprocess.CompletedProcess:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and process.returncode != 0:
        detail = (process.stderr or "").strip() or (process.stdout or "").strip()
        raise LandError(6, "git %s failed: %s" % (" ".join(args), detail), {})
    return process


def _gh(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False, timeout=60
    )


def _current_branch(repo: Path) -> Optional[str]:
    process = _git(repo, ["symbolic-ref", "--short", "HEAD"], check=False)
    if process.returncode != 0:
        return None
    return process.stdout.strip() or None


def _remote_url(repo: Path, remote: str) -> str:
    return _git(repo, ["remote", "get-url", remote]).stdout.strip()


def _is_ancestor(repo: Path, ancestor: str, descendant_ref: str) -> bool:
    process = _git(
        repo, ["merge-base", "--is-ancestor", ancestor, descendant_ref], check=False
    )
    return process.returncode == 0


def _changed_paths(repo: Path, from_ref: str, to_ref: str) -> List[str]:
    output = _git(repo, ["diff", "--name-only", from_ref, to_ref]).stdout
    return [line for line in output.splitlines() if line.strip()]


def _blob_at(repo: Path, rev: str, path: str) -> Optional[str]:
    process = _git(repo, ["rev-parse", "%s:%s" % (rev, path)], check=False)
    return process.stdout.strip() if process.returncode == 0 else None


def _contains_changes(
    repo: Path, merge_base: str, topic_sha: str, target_ref: str
) -> bool:
    """True when every path the topic changed already matches it in target_ref.

    Content comparison rather than tree equality: an advanced default branch
    that already absorbed the topic (squash landing) still contains it even
    though the trees differ."""
    for path in _changed_paths(repo, merge_base, topic_sha):
        if _blob_at(repo, topic_sha, path) != _blob_at(repo, target_ref, path):
            return False
    return True


def _commit_message(repo: Path, sha: str) -> str:
    return _git(repo, ["log", "-1", "--format=%B", sha]).stdout.rstrip("\n")


def _default_branch_via_gh() -> Optional[str]:
    process = _gh(["repo", "view", "--json", "defaultBranchRef"])
    if process.returncode != 0:
        return None
    try:
        value = json.loads(process.stdout)["defaultBranchRef"]["name"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) and value else None


def _default_branch_native(repo: Path, remote: str) -> Optional[str]:
    process = _git(
        repo, ["symbolic-ref", "refs/remotes/%s/HEAD" % remote], check=False
    )
    if process.returncode == 0:
        ref = process.stdout.strip()
        prefix = "refs/remotes/%s/" % remote
        if ref.startswith(prefix):
            return ref[len(prefix):]
    process = _git(repo, ["remote", "show", remote], check=False)
    if process.returncode == 0:
        for line in process.stdout.splitlines():
            match = _REMOTE_HEAD_RE.search(line)
            if match:
                branch = match.group(1).strip()
                if branch and branch != "(unknown)":
                    return branch
    return None


_REMOTE_HEAD_RE = re.compile(r"HEAD branch:\s*(\S+)")


def _remote_topic_sha(repo: Path, remote: str, branch: str) -> Optional[str]:
    process = _git(
        repo, ["ls-remote", remote, "refs/heads/%s" % branch], check=False
    )
    line = process.stdout.strip().splitlines()[0] if process.stdout.strip() else ""
    return line.split("\t")[0] if line else None


def _pr_view(repo: Path, branch: str) -> Optional[Dict[str, Any]]:
    process = _gh(
        ["pr", "view", branch, "--json",
         "number,url,state,headRefOid,headRefName,baseRefName"]
    )
    if process.returncode != 0:
        return None
    try:
        data = json.loads(process.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _verify_pr_identity(pr: Mapping[str, Any], sha: str, base: str) -> None:
    if pr.get("headRefOid") != sha:
        raise LandError(
            3, "PR head %s is not the verified head %s" % (pr.get("headRefOid"), sha), {}
        )
    if pr.get("baseRefName") != base:
        raise LandError(
            3,
            "PR base %r is not the resolved default branch %r"
            % (pr.get("baseRefName"), base),
            {},
        )


def _merge_commit_of(branch: str) -> Optional[str]:
    view = _gh(["pr", "view", branch, "--json", "mergeCommit"])
    if view.returncode != 0:
        return None
    try:
        value = json.loads(view.stdout).get("mergeCommit") or {}
        return value.get("oid")
    except json.JSONDecodeError:
        return None


def land_gh(
    repo: Path,
    remote: str,
    branch: str,
    sha: str,
    base: str,
    report: Dict[str, Any],
) -> None:
    _ensure_topic_pushed(repo, remote, branch, sha)
    pr = _pr_view(repo, branch)
    if pr is not None:
        _verify_pr_identity(pr, sha, base)
        if pr.get("state") == "MERGED":
            report.update(
                landed=True,
                basis="merged-pr",
                pr=pr.get("url"),
                merge_commit=_merge_commit_of(branch),
            )
            report.setdefault("steps", []).append("already merged")
            _cleanup_remote_topic(repo, remote, branch, sha, report)
            return
        if pr.get("state") == "CLOSED":
            raise LandError(
                3,
                "PR %s is closed without merging; resolve or recreate it before landing"
                % pr.get("url"),
                {},
            )
    else:
        message = _commit_message(repo, sha)
        subject = message.splitlines()[0] if message else branch
        body = "\n".join(message.splitlines()[1:]).strip()
        create = _gh(
            ["pr", "create", "--base", base, "--head", branch,
             "--title", subject, "--body", body or subject]
        )
        if create.returncode != 0:
            raise LandError(
                6, "gh pr create failed: %s" % (create.stderr or "").strip(), {}
            )
        pr = _pr_view(repo, branch)
        if pr is None:
            raise LandError(6, "PR missing right after creation", {})
        _verify_pr_identity(pr, sha, base)
        report.setdefault("steps", []).append("created PR %s" % pr.get("url"))

    merge_args = ["pr", "merge", str(pr["number"]), "--squash",
                  "--match-head-commit", sha]
    merge = _gh(merge_args)
    if merge.returncode != 0:
        text = (merge.stderr or "") + (merge.stdout or "")
        if "match-head-commit" in text and ("unknown" in text.lower() or "usage" in text.lower()):
            merge = _gh(["pr", "merge", str(pr["number"]), "--squash"])
        if merge.returncode != 0:
            text = (merge.stderr or "") + (merge.stdout or "")
            lowered = text.lower()
            if "check" in lowered or "pending" in lowered or "required" in lowered:
                raise LandError(
                    4, "required checks pending: %s" % text.strip(), {"pr": pr.get("url")}
                )
            raise LandError(
                6, "gh pr merge failed: %s" % text.strip(), {"pr": pr.get("url")}
            )
    deadline = time.monotonic() + 90
    final: Optional[Dict[str, Any]] = None
    while time.monotonic() < deadline:
        final = _pr_view(repo, branch)
        if final and final.get("state") == "MERGED":
            break
        time.sleep(2)
    if not final or final.get("state") != "MERGED":
        raise LandError(
            6, "PR did not reach MERGED in time", {"pr": pr.get("url")}
        )
    if final.get("headRefOid") != sha:
        raise LandError(
            3, "PR merged a different head than verified", {"pr": pr.get("url")}
        )
    report.update(
        landed=True,
        basis="merged-pr",
        pr=final.get("url"),
        merge_commit=_merge_commit_of(branch),
    )
    report.setdefault("steps", []).append("verified MERGED")
    _cleanup_remote_topic(repo, remote, branch, sha, report)


def _ensure_topic_pushed(repo: Path, remote: str, branch: str, sha: str) -> None:
    if _remote_topic_sha(repo, remote, branch) == sha:
        return
    push = _git(
        repo, ["push", remote, "%s:refs/heads/%s" % (sha, branch)], check=False
    )
    if push.returncode != 0:
        raise LandError(
            6,
            "publishing topic branch failed: %s" % (push.stderr or "").strip(),
            {},
        )


def _cleanup_remote_topic(
    repo: Path, remote: str, branch: str, sha: str, report: Dict[str, Any]
) -> None:
    current = _remote_topic_sha(repo, remote, branch)
    if current is None:
        report.setdefault("cleanup", {})["remote_topic"] = "absent"
        return
    if current != sha:
        report.setdefault("cleanup", {})["remote_topic"] = "not at verified head; kept"
        return
    delete = _git(repo, ["push", remote, "--delete", branch], check=False)
    report.setdefault("cleanup", {})["remote_topic"] = (
        "deleted" if delete.returncode == 0 else "delete failed; kept"
    )


def _run_verify_command(worktree: Path, command: str, timeout: float) -> None:
    try:
        process = subprocess.run(
            command,
            cwd=str(worktree),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise LandError(5, "--verify-command timed out after %ss" % timeout, {})
    if process.returncode != 0:
        raise LandError(
            5,
            "--verify-command failed (%s): %s"
            % (process.returncode, (process.stderr or process.stdout).strip()[:2000]),
            {},
        )


def land_native(
    repo: Path,
    remote: str,
    branch: str,
    sha: str,
    base: str,
    verify_command: str,
    verify_timeout: float,
    report: Dict[str, Any],
) -> None:
    _git(repo, ["fetch", remote])
    remote_base_ref = "%s/%s" % (remote, base)
    old_remote = _git(repo, ["rev-parse", remote_base_ref]).stdout.strip()
    merge_base = _git(repo, ["merge-base", sha, remote_base_ref]).stdout.strip()
    topic_paths = set(_changed_paths(repo, merge_base, sha))

    if _is_ancestor(repo, sha, remote_base_ref):
        report.update(landed=True, basis="ancestor", default_published=old_remote)
        report.setdefault("steps", []).append("remote default already contains head")
        _cleanup_remote_topic(repo, remote, branch, sha, report)
        return
    if _contains_changes(repo, merge_base, sha, remote_base_ref):
        report.update(landed=True, basis="already-contained", default_published=old_remote)
        report.setdefault("steps", []).append("remote default already contains the change")
        _cleanup_remote_topic(repo, remote, branch, sha, report)
        return

    local_base_sha = _git(
        repo, ["rev-parse", "--verify", "refs/heads/%s" % base], check=False
    ).stdout.strip()
    if (
        local_base_sha
        and _is_ancestor(repo, old_remote, local_base_sha)
        and _is_ancestor(repo, sha, local_base_sha)
    ):
        push = _git(
            repo, ["push", remote, "%s:refs/heads/%s" % (local_base_sha, base)],
            check=False,
        )
        if push.returncode == 0:
            report.update(
                landed=True, basis="resume-push", default_published=local_base_sha
            )
            report.setdefault("steps", []).append("pushed previously merged local default")
            _advance_local_base(repo, base, local_base_sha, report)
            _cleanup_remote_topic(repo, remote, branch, sha, report)
            return

    worktree = Path(tempfile.mkdtemp(prefix="land-native-"))
    try:
        add = _git(repo, ["worktree", "add", "--detach", str(worktree), remote_base_ref], check=False)
        if add.returncode != 0:
            raise LandError(
                6, "isolated worktree unavailable: %s" % (add.stderr or "").strip(), {}
            )
        ff = _git(worktree, ["merge", "--ff-only", sha], check=False)
        if ff.returncode != 0:
            squash = _git(worktree, ["merge", "--squash", sha], check=False)
            if squash.returncode != 0:
                detail = (squash.stderr or "").strip() or (squash.stdout or "").strip()
                raise LandError(6, "squash merge failed: %s" % detail, {})
            message = _commit_message(repo, sha)
            commit = _git(worktree, ["commit", "-m", message], check=False)
            if commit.returncode != 0:
                detail = (commit.stderr or "").strip() or (commit.stdout or "").strip()
                raise LandError(6, "squash commit failed: %s" % detail, {})
            report.setdefault("steps", []).append("squash merge + commit")
        else:
            report.setdefault("steps", []).append("fast-forward merge")
        landed_sha = _git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
        if verify_command:
            _run_verify_command(worktree, verify_command, verify_timeout)
            report.setdefault("steps", []).append("verify command passed")
        push = _git(
            worktree, ["push", remote, "HEAD:refs/heads/%s" % base], check=False
        )
        if push.returncode != 0:
            raise LandError(
                6,
                "publishing default branch failed: %s" % (push.stderr or "").strip(),
                {"worktree": str(worktree)},
            )
    finally:
        _git(repo, ["worktree", "remove", "--force", str(worktree)], check=False)
        try:
            worktree.rmdir()
        except OSError:
            pass

    new_remote = _remote_topic_sha(repo, remote, base) or ""
    if not _is_ancestor(repo, old_remote, new_remote):
        raise LandError(5, "published default does not preserve prior default commits", {})
    if new_remote == sha:
        contains = True
    else:
        landed_paths = set(_changed_paths(repo, old_remote, new_remote))
        contains = topic_paths.issubset(landed_paths)
    if not contains:
        raise LandError(5, "published default does not contain the scoped change", {})
    report.update(landed=True, basis="native-push", default_published=new_remote)
    report.setdefault("steps", []).append("verified published default")
    _advance_local_base(repo, base, new_remote, report)
    _cleanup_remote_topic(repo, remote, branch, sha, report)


def _advance_local_base(
    repo: Path, base: str, new_remote: str, report: Dict[str, Any]
) -> None:
    current = _current_branch(repo)
    if current == base:
        report.setdefault("cleanup", {})["local_base"] = "checked out here; not moved"
        return
    local = _git(
        repo, ["rev-parse", "--verify", "refs/heads/%s" % base], check=False
    ).stdout.strip()
    if local and not _is_ancestor(repo, local, new_remote):
        report.setdefault("cleanup", {})["local_base"] = "diverged; left untouched"
        return
    moved = _git(repo, ["branch", "-f", base, new_remote], check=False)
    report.setdefault("cleanup", {})["local_base"] = (
        "advanced" if moved.returncode == 0 else "left untouched"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--branch")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base")
    parser.add_argument("--mode", choices=("auto", "gh", "native"), default="auto")
    parser.add_argument("--verify-command")
    parser.add_argument("--verify-timeout", type=float, default=600.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the resolved engine and planned actions; perform no mutation",
    )
    args = parser.parse_args(argv)

    repo = args.repo_root.resolve()
    report: Dict[str, Any] = {
        "engine": args.mode,
        "remote": args.remote,
        "head": None,
        "branch": None,
        "base": args.base,
        "landed": False,
        "steps": [],
    }
    try:
        if _git(repo, ["rev-parse", "--git-dir"], check=False).returncode != 0:
            raise LandError(1, "not a git repository: %s" % repo, {})
        branch = args.branch or _current_branch(repo)
        if branch is None:
            raise LandError(2, "detached HEAD; branch must be named", {})
        if _git(repo, ["remote", "get-url", args.remote], check=False).returncode != 0:
            raise LandError(2, "remote %r cannot be resolved" % args.remote, {})
        gh_default = None
        if args.mode != "native":
            gh_default = _default_branch_via_gh()
            if args.mode == "gh" and gh_default is None:
                raise LandError(2, "gh engine requested but gh is unusable", {})
        use_gh = gh_default is not None and (
            args.mode == "gh"
            or "github.com" in _remote_url(repo, args.remote).lower()
        )
        base = args.base or (gh_default if use_gh else None)
        if base is None:
            base = _default_branch_native(repo, args.remote)
        if base is None:
            raise LandError(
                2, "cannot resolve the default branch; pass --base", {}
            )
        if branch == base:
            raise LandError(1, "topic branch equals the default branch; nothing to land", {})
        sha = _git(
            repo, ["rev-parse", args.branch or "HEAD"]
        ).stdout.strip()
        report.update(branch=branch, head=sha, base=base)
        if args.dry_run:
            report["engine"] = "gh" if use_gh else "native"
            report["dry_run"] = True
            report["steps"] = (
                ["push topic", "create/reuse PR", "squash merge", "verify MERGED", "cleanup"]
                if use_gh
                else ["fetch", "isolated worktree", "ff-only or squash", "verify", "publish default"]
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if use_gh:
            report["engine"] = "gh"
            land_gh(repo, args.remote, branch, sha, base, report)
        else:
            report["engine"] = "native"
            land_native(
                repo, args.remote, branch, sha, base,
                args.verify_command or "", args.verify_timeout, report,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except LandError as exc:
        merged = dict(report)
        merged.update(exc.report)
        merged["error"] = str(exc)
        print(json.dumps(merged, ensure_ascii=False, indent=2))
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
