#!/usr/bin/env python3
"""Reuse supervised SPEC preflight results within one TDD drain batch.

The test supervisor executes the action and writes evidence. This script accepts only a passing,
integrity-checked preflight receipt for the exact cwd/action/fingerprint tuple.

Exit codes: 0 hit/recorded, 1 invalid receipt or input, 2 usage, 3 cache miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
PREFLIGHT = re.compile(r"^\s*-\s*P\d+\s+预检[：:]\s*`([^`]+)`\s*(?:→|->)\s*passed")


def _text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must not be empty")
    return value


def _normal_cwd(value: str) -> str:
    return os.path.normpath(_text(value, "cwd")).replace("\\", "/")


def _key(cwd: str, action: str, fingerprint: str) -> str:
    payload = json.dumps(
        {"action": action, "cwd": cwd, "fingerprint": fingerprint},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _declared_cwd(receipt: Path, cwd: str) -> Path:
    declared = Path(cwd)
    if declared.is_absolute():
        return declared.resolve()
    for parent in receipt.resolve().parents:
        if parent.name == ".scratch":
            return (parent.parent / declared).resolve()
    return declared.resolve()


def _execution(receipt: Path, cwd: str, action: str) -> Dict[str, Any]:
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{receipt}: invalid execution receipt: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"{receipt}: unsupported execution receipt schema")
    if data.get("scope") != "preflight" or data.get("outcome") != "pass":
        raise ValueError(f"{receipt}: preflight execution did not pass")
    if data.get("exit_code") != 0 or data.get("argv") != shlex.split(action):
        raise ValueError(f"{receipt}: execution does not match action")
    if Path(str(data.get("cwd", ""))).resolve() != _declared_cwd(receipt, cwd):
        raise ValueError(f"{receipt}: execution does not match cwd")
    log = Path(str(data.get("log", "")))
    if not log.is_file() or data.get("log_sha256") != _sha256(log):
        raise ValueError(f"{receipt}: execution log is missing or changed")
    return data


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported preflight receipt schema")
    if not isinstance(data.get("entries"), dict):
        raise ValueError(f"{path}: entries must be an object")
    return data


def _save(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.%d" % os.getpid())
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def _exclusive_writer(path: Path):
    """Cross-platform single-writer lock for the orchestrator receipt.

    A writer that crashed between O_EXCL and unlink would strand the lock forever,
    so a lock older than STALE_LOCK_SECONDS is treated as dead and taken over."""
    stale_after = 30
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + 5
    descriptor = None
    token = "%d:%d" % (os.getpid(), time.monotonic_ns())
    while descriptor is None:
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > stale_after:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise ValueError(f"{path}: timed out waiting for receipt writer lock")
            time.sleep(0.02)
    try:
        os.write(descriptor, token.encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        # Only remove a lock this writer still owns; a stolen-then-recreated lock
        # belongs to whoever took over.
        try:
            if lock.read_text(encoding="ascii") == token:
                lock.unlink()
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            pass


def _resolve_action(receipt: Path, action: str) -> str:
    if not action.startswith("profile:"):
        return action
    name = action[len("profile:"):].strip()
    profile = receipt.resolve().parent / "verifier.json"
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{receipt}: cannot resolve {action}: {profile} unreadable") from exc
    command = (data.get("commands") or {}).get(name)
    if not command:
        raise ValueError(f"{receipt}: verifier.json has no command '{name}'")
    return command


def record(
    path: Path,
    *,
    cwd: str,
    action: str,
    fingerprint: str,
    execution_receipt: Path,
) -> str:
    cwd = _normal_cwd(cwd)
    action = _text(action, "action")
    fingerprint = _text(fingerprint, "fingerprint")
    execution = _execution(execution_receipt, cwd, _resolve_action(path, action))
    key = _key(cwd, action, fingerprint)
    with _exclusive_writer(path):
        data = _load(path)
        data["entries"][key] = {
            "action": action,
            "checked_at": execution["ended_at"],
            "cwd": cwd,
            "duration_seconds": execution["duration_seconds"],
            "evidence": str(execution_receipt.resolve()),
            "fingerprint": fingerprint,
            "observed": "exit 0",
            "result": "passed",
        }
        _save(path, data)
    return key


def check(path: Path, *, cwd: str, action: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    cwd = _normal_cwd(cwd)
    action = _text(action, "action")
    fingerprint = _text(fingerprint, "fingerprint")
    data = _load(path)
    entry = data["entries"].get(_key(cwd, action, fingerprint))
    if not isinstance(entry, dict) or entry.get("result") != "passed":
        return None
    return entry


def _frontmatter(lines: Sequence[str]) -> Dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = FM_KEY.match(line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("\"'")
    return result


def _bullet(lines: Sequence[str], label: str) -> str:
    for line in lines:
        stripped = line.strip()
        for separator in ("：", ":"):
            prefix = f"- {label}{separator}"
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip().strip("`")
    return ""


def _verification(lines: Sequence[str]) -> Sequence[str]:
    result = []
    active = False
    for line in lines:
        if line.startswith("## "):
            if active:
                break
            active = "验证设计" in line
            continue
        if active:
            result.append(line)
    return result


def issue_preflight_rows(
    repo_root: Path,
    feature: Optional[str] = None,
    *,
    statuses: Sequence[str] = ("ready",),
) -> List[Mapping[str, Any]]:
    """Return executable P# tuples from selected live issues."""
    root = repo_root.resolve()
    scratch = root / ".scratch"
    features = [scratch / feature] if feature else sorted(
        path for path in scratch.iterdir() if path.is_dir()
    ) if scratch.is_dir() else []
    rows: List[Mapping[str, Any]] = []
    for feature_dir in features:
        issues_dir = feature_dir / "issues"
        if not issues_dir.is_dir():
            continue
        for issue in sorted(issues_dir.glob("*.md")):
            lines = issue.read_text(encoding="utf-8-sig").splitlines()
            card = _frontmatter(lines)
            if card.get("status") not in statuses:
                continue
            verification = _verification(lines)
            cwd = _bullet(verification, "工作目录")
            fingerprint = _bullet(verification, "环境指纹")
            if not cwd or not fingerprint:
                profile_path = feature_dir / "verifier.json"
                if str(card.get("contract_version", "")) != "3" or not profile_path.is_file():
                    continue
                try:
                    profile = json.loads(profile_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                cwd = cwd or str(profile.get("cwd", "") or "")
                fingerprint = fingerprint or str(profile.get("fingerprint", "") or "")
                if not cwd or not fingerprint:
                    continue
            for line in verification:
                match = PREFLIGHT.match(line)
                if match:
                    normal_cwd = _normal_cwd(cwd)
                    action = match.group(1).strip()
                    rows.append(
                        {
                            "feature": feature_dir.name,
                            "issue": issue.relative_to(root).as_posix(),
                            "slug": issue.stem,
                            "key": _key(normal_cwd, action, fingerprint),
                            "cwd": normal_cwd,
                            "action": action,
                            "fingerprint": fingerprint,
                            "receipt": (
                                scratch / feature_dir.name / "preflight-receipt.json"
                            ).relative_to(root).as_posix(),
                        }
                    )
    return rows


def duplicate_plan(
    repo_root: Path,
    feature: Optional[str] = None,
    *,
    rows: Optional[List[Mapping[str, Any]]] = None,
) -> Mapping[str, Any]:
    """Return only P# tuples reused by two or more ready issues in one feature.

    `rows` lets a caller that already ran `issue_preflight_rows` (e.g. a drain
    dispatch) skip the second scan of every ready card."""
    root = repo_root.resolve()
    groups: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for row in rows if rows is not None else issue_preflight_rows(root, feature):
        groups.setdefault((row["feature"], row["key"]), []).append(row)
    duplicates = []
    for (feat, _), rows in sorted(groups.items()):
        sample = rows[0]
        unique_issues = sorted(set(row["issue"] for row in rows))
        if len(unique_issues) < 2:
            continue
        receipt = root / sample["receipt"]
        hit = check(
            receipt,
            cwd=sample["cwd"],
            action=sample["action"],
            fingerprint=sample["fingerprint"],
        )
        duplicates.append(
            {
                "feature": feat,
                "key": sample["key"],
                "cwd": sample["cwd"],
                "action": sample["action"],
                "fingerprint": sample["fingerprint"],
                "issues": unique_issues,
                "receipt": sample["receipt"],
                "status": "hit" if hit else "miss",
            }
        )
    return {"schema_version": SCHEMA_VERSION, "duplicates": duplicates}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("record", "check"):
        command = commands.add_parser(name)
        command.add_argument("receipt", type=Path)
        command.add_argument("--cwd", required=True)
        command.add_argument("--action", required=True)
        command.add_argument("--fingerprint", required=True)
        if name == "record":
            command.add_argument("--execution-receipt", type=Path, required=True)
    plan = commands.add_parser("plan", help="list only duplicate ready-card preflight tuples")
    plan.add_argument("repo_root", type=Path)
    plan.add_argument("feature", nargs="?")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(duplicate_plan(args.repo_root, args.feature), ensure_ascii=False, indent=2))
            return 0
        if args.command == "record":
            key = record(
                args.receipt,
                cwd=args.cwd,
                action=args.action,
                fingerprint=args.fingerprint,
                execution_receipt=args.execution_receipt,
            )
            print(f"recorded: {key}")
            return 0
        entry = check(
            args.receipt,
            cwd=args.cwd,
            action=args.action,
            fingerprint=args.fingerprint,
        )
        if entry is None:
            print("cache-miss")
            return 3
        print(
            "cache-hit: observed=%s; evidence=%s; checked_at=%s"
            % (entry["observed"], entry["evidence"], entry["checked_at"])
        )
        return 0
    except ValueError as exc:
        print(f"preflight-receipt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
