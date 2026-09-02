#!/usr/bin/env python3
"""Run one verifier with bounded output, timing, timeout, and an atomic receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
SCOPES = ("preflight", "targeted", "module", "full", "build", "other")


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


def _soft_stop(process: subprocess.Popen) -> str:
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            return "ctrl-break"
        except (AttributeError, OSError):
            process.terminate()
            return "terminate"
    os.killpg(process.pid, signal.SIGTERM)
    return "sigterm"


def _hard_stop(process: subprocess.Popen) -> str:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
            return "taskkill"
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            return "kill"
    os.killpg(process.pid, signal.SIGKILL)
    return "sigkill"


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
) -> Tuple[Mapping[str, Any], int]:
    if not argv:
        raise ValueError("command must not be empty")
    if timeout <= 0 or grace < 0:
        raise ValueError("timeout must be positive and grace must be non-negative")
    if scope not in SCOPES:
        raise ValueError("unsupported scope: %s" % scope)

    working_dir = cwd.resolve()
    log_path = log.resolve()
    receipt_path = receipt.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    started = time.monotonic()
    git = _git_state(working_dir)
    return_code: Optional[int] = None
    launch_error: Optional[str] = None
    timed_out = False
    termination = "none"

    creation_flags = 0
    popen_options: Dict[str, Any] = {}
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_options["start_new_session"] = True

    with log_path.open("wb") as output:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=str(working_dir),
                env=dict(env) if env is not None else None,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
                **popen_options,
            )
        except OSError as exc:
            launch_error = "%s: %s" % (type(exc).__name__, exc)
            output.write((launch_error + "\n").encode("utf-8", errors="replace"))
        else:
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = _soft_stop(process)
                try:
                    return_code = process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    termination += "+" + _hard_stop(process)
                    return_code = process.wait()

    duration = time.monotonic() - started
    if launch_error is not None:
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

    data: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scope": scope,
        "outcome": outcome,
        "argv": list(argv),
        "command_text": shlex.join(list(argv)),
        "cwd": str(working_dir),
        "started_at": started_at,
        "ended_at": _utc_now(),
        "duration_seconds": round(duration, 6),
        "duration_class": duration_class,
        "timeout_seconds": timeout,
        "grace_seconds": grace,
        "exit_code": return_code,
        "termination": termination,
        "launch_error": launch_error,
        "log": str(log_path),
        "log_sha256": _sha256(log_path),
        "log_tail": _log_tail(log_path) if timed_out else [],
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "git": git,
    }
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
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result, exit_code = run_command(
            command,
            cwd=args.cwd,
            receipt=args.receipt,
            log=args.log,
            timeout=args.timeout,
            grace=args.grace,
            scope=args.scope,
        )
    except ValueError as exc:
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
