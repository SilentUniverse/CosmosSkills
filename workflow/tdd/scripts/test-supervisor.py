#!/usr/bin/env python3
"""Run one verifier with bounded output, timing, timeout, and an atomic receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ENGINEERING_ROOT = Path(__file__).resolve().parents[2]
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from workflow_contract import command_argv, effective_verifier, issue_binding, parse_ac_spec
from process_tree import ProcessTree


SCHEMA_VERSION = 1
SCOPES = ("preflight", "targeted", "module", "full", "build", "other")
SECRET_NAME = re.compile(
    r"(?:^|_)(?:APIKEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|AUTH|AUTHORIZATION)(?:$|_)",
    re.I,
)
NON_SECRET_NAMES = {"SSH_AUTH_SOCK"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _log_tail(path: Path, max_bytes: int = 4096, max_lines: int = 20) -> List[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(max(0, size - max_bytes))
            chunk = stream.read()
    except OSError:
        return []
    return chunk.decode("utf-8", errors="replace").splitlines()[-max_lines:]


def _secret_values(env: Mapping[str, str]) -> List[bytes]:
    values = set()
    for key, value in env.items():
        name = str(key).upper()
        text = str(value)
        if name in NON_SECRET_NAMES or not SECRET_NAME.search(name) or len(text) < 8:
            continue
        values.add(text.encode("utf-8"))
        values.update(
            part.encode("utf-8") for part in text.splitlines() if part
        )
    return sorted(values, key=len, reverse=True)


def _require_under(path: Path, directory: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay under {directory}") from exc
    return resolved


def _repo_root(cwd: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd.resolve()), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return cwd.resolve()
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else cwd.resolve()


def _sanitize_log(source: Path, target: Path, secrets: Sequence[bytes]) -> None:
    temporary = target.with_name(target.name + ".tmp.%d" % os.getpid())
    try:
        with source.open("rb") as incoming, temporary.open("wb") as outgoing:
            for line in incoming:
                for secret in secrets:
                    line = line.replace(secret, b"[REDACTED]")
                outgoing.write(line)
        os.replace(temporary, target)
        try:
            source.unlink()
        except FileNotFoundError:
            pass
    except OSError as exc:
        try:
            source.chmod(0o600)
        except OSError:
            pass
        raise OSError(
            f"log sanitization failed; raw evidence preserved at {source}: {exc}"
        ) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.%d" % os.getpid())
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _git_state(cwd: Path) -> Mapping[str, Any]:
    try:
        head = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            timeout=5,
        )
        status = subprocess.run(
            ["git", "-C", str(cwd), "status", "--porcelain=v1", "-z"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"head": None, "dirty": None, "dirty_digest": None}
    if head.returncode != 0 or status.returncode != 0:
        return {"head": None, "dirty": None, "dirty_digest": None}
    return {
        "head": head.stdout.decode("ascii", errors="replace").strip(),
        "dirty": bool(status.stdout),
        "dirty_digest": hashlib.sha256(status.stdout).hexdigest(),
    }


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    receipt: Path,
    log: Path,
    timeout: float,
    grace: float,
    scope: str,
    env: Optional[Mapping[str, str]] = None,
    binding: Optional[Mapping[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> Tuple[Mapping[str, Any], int]:
    if not argv:
        raise ValueError("command must not be empty")
    if timeout <= 0 or grace < 0:
        raise ValueError("timeout must be positive and grace must be non-negative")
    if scope not in SCOPES:
        raise ValueError("unsupported scope: %s" % scope)

    effective_env = dict(env) if env is not None else dict(os.environ)
    secrets = _secret_values(effective_env)
    if any(secret in str(argument).encode("utf-8") for secret in secrets for argument in argv):
        raise ValueError("command argv contains an environment secret; pass it through the environment")

    working_dir = cwd.resolve()
    log_path = log.resolve()
    receipt_path = receipt.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw_log_path = log_path.with_name(log_path.name + ".raw.%d" % os.getpid())
    started_at = _utc_now()
    started = time.monotonic()
    git = _git_state(working_dir)
    return_code: Optional[int] = None
    launch_error: Optional[str] = None
    timed_out = False
    termination = "none"

    orphaned = False
    raw_descriptor = os.open(raw_log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(raw_descriptor, "wb") as output:
        try:
            tree = ProcessTree(
                list(argv),
                cwd=str(working_dir),
                env=effective_env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            launch_error = "%s: %s" % (type(exc).__name__, exc)
            output.write((launch_error + "\n").encode("utf-8", errors="replace"))
        else:
            process = tree.process
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = tree.stop(grace)
                return_code = process.returncode
            finally:
                try:
                    if tree.alive():
                        orphaned = True
                        termination = tree.stop(grace)
                finally:
                    tree.close()

    _sanitize_log(raw_log_path, log_path, secrets)

    duration = time.monotonic() - started
    # 125 is this repo's own termination code (process_tree job-kill uses
    # TerminateJobObject(handle, 125); POSIX reports it as returncode < 0),
    # so nt rc==125 without a timeout is a tree the supervisor tore down.
    # Caveat: a validator that itself wraps `docker run` also exits 125 on
    # daemon errors — check its log before reading "crash" as our kill.
    if launch_error is not None or orphaned or (os.name == "nt" and return_code == 125 and not timed_out):
        outcome, supervisor_exit = "crash", 125
    elif timed_out:
        outcome, supervisor_exit = "timeout", 124
    elif return_code == 0:
        outcome, supervisor_exit = "pass", 0
    elif return_code is not None and return_code < 0:
        outcome, supervisor_exit = "crash", 125
    else:
        outcome = "fail"
        supervisor_exit = return_code if return_code and return_code < 124 else 1

    fraction = duration / timeout
    if timed_out:
        duration_class = "timeout"
    elif fraction >= 0.9:
        duration_class = "near-timeout"
    elif fraction >= 0.5:
        duration_class = "slow"
    else:
        duration_class = "normal"

    durable_root = repo_root.resolve() if binding is not None and repo_root is not None else None
    recorded_cwd = (
        working_dir.relative_to(durable_root).as_posix() or "."
        if durable_root is not None
        else str(working_dir)
    )
    recorded_log = (
        log_path.relative_to(durable_root).as_posix()
        if durable_root is not None
        else str(log_path)
    )
    data: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "argv_style": "windows" if os.name == "nt" else "posix",
        "scope": scope,
        "outcome": outcome,
        "argv": list(argv),
        "cwd": recorded_cwd,
        "started_at": started_at,
        "ended_at": _utc_now(),
        "duration_seconds": round(duration, 6),
        "duration_class": duration_class,
        "timeout_seconds": timeout,
        "exit_code": return_code,
        "log": recorded_log,
        "log_sha256": _sha256(log_path),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "git": git,
    }
    if termination != "none":
        data["termination"] = termination
        data["grace_seconds"] = grace
    if launch_error is not None:
        data["launch_error"] = launch_error
    if timed_out:
        data["log_tail"] = _log_tail(log_path)
    if binding is not None:
        data["issue"] = dict(binding)
    _atomic_json(receipt_path, data)
    return data, supervisor_exit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--grace", type=float, default=5.0)
    parser.add_argument("--scope", choices=SCOPES, required=True)
    parser.add_argument("--issue", type=Path)
    parser.add_argument("--verifier")
    parser.add_argument("--ac", help="comma/range AC subset bound to this receipt, e.g. 1,3-5")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        if bool(args.issue) != bool(args.verifier):
            raise ValueError("--issue and --verifier must be supplied together")
        selected_ac = parse_ac_spec(args.ac) if args.ac else None
        if selected_ac is not None and not args.issue:
            raise ValueError("--ac requires --issue and --verifier")
        binding = issue_binding(args.issue, args.verifier, selected_ac) if args.issue else None
        if binding is not None:
            issue_path = args.issue.resolve()
            repo_root = issue_path.parents[3]
            feature = str(binding["feature"])
            verifier = effective_verifier(
                repo_root, feature, issue_path.read_text(encoding="utf-8-sig")
            )
            expected_cwd = (repo_root / str(verifier["cwd"])).resolve()
            if args.cwd.resolve() != expected_cwd:
                raise ValueError(
                    f"--cwd must match verifier profile cwd: {expected_cwd}"
                )
            expected_argv = command_argv(verifier["commands"][args.verifier])
            if command != expected_argv:
                raise ValueError(f"command must match profile:{args.verifier}")
            _require_under(
                args.receipt,
                repo_root / ".scratch" / feature / "receipts",
                "--receipt",
            )
            _require_under(args.log, repo_root / ".scratch" / "tmp", "--log")
        else:
            repo_root = _repo_root(args.cwd)
            _require_under(args.receipt, repo_root / ".scratch", "--receipt")
            _require_under(args.log, repo_root / ".scratch" / "tmp", "--log")
        if args.receipt.resolve() == args.log.resolve():
            raise ValueError("--receipt and --log must be different paths")
        result, exit_code = run_command(
            command,
            cwd=args.cwd,
            receipt=args.receipt,
            log=args.log,
            timeout=args.timeout,
            grace=args.grace,
            scope=args.scope,
            binding=binding,
            repo_root=repo_root if binding is not None else None,
        )
    except (OSError, ValueError) as exc:
        print("test-supervisor: %s" % exc, file=sys.stderr)
        return 2
    print(
        "%s scope=%s exit=%s duration=%.3fs log=%s receipt=%s"
        % (
            result["outcome"],
            result["scope"],
            result["exit_code"],
            result["duration_seconds"],
            result["log"],
            args.receipt,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
