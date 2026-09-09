#!/usr/bin/env python3
"""Reuse supervised SPEC preflight results within one TDD drain batch.

The test supervisor executes the action and writes evidence. This script accepts only a passing,
integrity-checked receipt for the exact cwd/resolved-action/fingerprint/readiness/profile tuple.

`run` executes and records every duplicate-plan cache miss serially through the supervisor;
only passing executions become cache entries, and failures are reported per tuple.

Exit codes: 0 hit/recorded (run: every miss recorded), 1 invalid receipt or input (run: at
least one tuple failed), 2 usage, 3 cache miss.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ENGINEERING_ROOT = Path(__file__).resolve().parents[2]
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from workflow_contract import (
    command_argv,
    effective_verifier,
    load_verifier_profile,
    resolve_action,
)


from workflow_runtime import file_lock


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


def _normal_fingerprint(value: str) -> str:
    text = _text(value, "fingerprint")
    entries = []
    for item in re.split(r"[;；]", text):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            return re.sub(r"\s+", " ", text)
        key, entry = item.split("=", 1)
        entries.append((key.strip(), re.sub(r"\s+", " ", entry.strip())))
    return "; ".join("%s=%s" % pair for pair in sorted(entries))


def _readiness_digest(prerequisites: str, prepare: str) -> str:
    normalized_prerequisites = (
        _normal_fingerprint(prerequisites) if prerequisites.strip() else ""
    )
    payload = json.dumps(
        {
            "prerequisites": normalized_prerequisites,
            "prepare": re.sub(r"\s+", " ", prepare.strip()),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _key(
    cwd: str,
    action: str,
    fingerprint: str,
    verifier_digest: str = "",
    readiness_digest: str = "",
) -> str:
    payload = {
        "action": action,
        "cwd": cwd,
        "fingerprint": _normal_fingerprint(fingerprint),
        "verifier_digest": verifier_digest,
    }
    if readiness_digest:
        payload["readiness_digest"] = readiness_digest
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data.get("schema_version") != 1
    ):
        raise ValueError(f"{receipt}: unsupported execution receipt schema")
    if data.get("scope") != "preflight" or data.get("outcome") != "pass":
        raise ValueError(f"{receipt}: preflight execution did not pass")
    if data.get("exit_code") != 0 or data.get("argv") != command_argv(
        action, data.get("argv_style")
    ):
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
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data.get("schema_version") != SCHEMA_VERSION
    ):
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
    with file_lock(path.with_name(path.name + ".lock")):
        yield


def _resolve_action(receipt: Path, action: str) -> Tuple[str, bool]:
    if not action.startswith("profile:"):
        return action, False
    name = action[len("profile:"):].strip()
    profile = receipt.resolve().parent / "verifier.json"
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{receipt}: cannot resolve {action}: {profile} unreadable") from exc
    command = (data.get("commands") or {}).get(name)
    if not command:
        raise ValueError(f"{receipt}: verifier.json has no command '{name}'")
    return command, True


def record(
    path: Path,
    *,
    cwd: str,
    action: str,
    fingerprint: str,
    execution_receipt: Path,
    verifier_digest: str = "",
    readiness_digest: str = "",
) -> str:
    cwd = _normal_cwd(cwd)
    action = _text(action, "action")
    fingerprint = _text(fingerprint, "fingerprint")
    resolved_action, profile_action = _resolve_action(path, action)
    if profile_action and not verifier_digest:
        raise ValueError("profile action requires --verifier-digest from plan/dispatch")
    if readiness_digest and not re.fullmatch(r"[0-9a-f]{64}", readiness_digest):
        raise ValueError("readiness digest must be a 64-character SHA-256")
    _execution(execution_receipt, cwd, resolved_action)
    key = _key(cwd, resolved_action, fingerprint, verifier_digest, readiness_digest)
    execution_receipt = execution_receipt.resolve()
    with _exclusive_writer(path):
        data = _load(path)
        data["entries"][key] = {
            "evidence": str(execution_receipt),
            "evidence_sha256": _sha256(execution_receipt),
        }
        _save(path, data)
    return key


def check(
    path: Path,
    *,
    cwd: str,
    action: str,
    fingerprint: str,
    verifier_digest: str = "",
    readiness_digest: str = "",
) -> Optional[Dict[str, Any]]:
    cwd = _normal_cwd(cwd)
    action = _text(action, "action")
    fingerprint = _text(fingerprint, "fingerprint")
    resolved_action, profile_action = _resolve_action(path, action)
    if profile_action and not verifier_digest:
        raise ValueError("profile action requires --verifier-digest from plan/dispatch")
    if readiness_digest and not re.fullmatch(r"[0-9a-f]{64}", readiness_digest):
        raise ValueError("readiness digest must be a 64-character SHA-256")
    data = _load(path)
    entry = data["entries"].get(
        _key(cwd, resolved_action, fingerprint, verifier_digest, readiness_digest)
    )
    # Missing result is the compact schema: only passing executions are stored.
    # Accept legacy explicit `passed`, but never accept another value.
    if not isinstance(entry, dict) or entry.get("result") not in (None, "passed"):
        return None
    evidence = Path(str(entry.get("evidence", "")))
    try:
        if not evidence.is_file():
            return None
        expected_digest = entry.get("evidence_sha256")
        if expected_digest is not None and expected_digest != _sha256(evidence):
            return None
        _execution(evidence, cwd, resolved_action)
    except (OSError, ValueError):
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
        profile = None
        for issue in sorted(issues_dir.glob("*.md")):
            issue_raw = issue.read_text(encoding="utf-8-sig")
            lines = issue_raw.splitlines()
            card = _frontmatter(lines)
            if card.get("status") not in statuses:
                continue
            verification = _verification(lines)
            cwd = _bullet(verification, "工作目录")
            fingerprint = _bullet(verification, "环境指纹")
            prerequisites = _bullet(verification, "前置条件")
            prepare = _bullet(verification, "准备动作")
            verifier = None
            if str(card.get("contract_version", "")) == "3":
                try:
                    if profile is None:
                        profile = load_verifier_profile(root, feature_dir.name)
                    verifier = effective_verifier(
                        root, feature_dir.name, issue_raw, profile
                    )
                except (OSError, ValueError) as exc:
                    raise ValueError(f"{issue}: {exc}") from exc
                cwd = cwd or str(verifier["cwd"])
                fingerprint = fingerprint or str(verifier["fingerprint"])
            if not cwd or not fingerprint:
                continue
            for line in verification:
                match = PREFLIGHT.match(line)
                if match:
                    normal_cwd = _normal_cwd(cwd)
                    declared_action = match.group(1).strip()
                    action = resolve_action(verifier, declared_action) if verifier else declared_action
                    verifier_digest = str(verifier["effective_sha256"]) if verifier else ""
                    readiness_digest = (
                        "" if verifier else _readiness_digest(prerequisites, prepare)
                    )
                    rows.append(
                        {
                            "feature": feature_dir.name,
                            "issue": issue.relative_to(root).as_posix(),
                            "slug": issue.stem,
                            "key": _key(
                                normal_cwd,
                                action,
                                fingerprint,
                                verifier_digest,
                                readiness_digest,
                            ),
                            "cwd": normal_cwd,
                            "action": action,
                            "declared_action": declared_action,
                            "fingerprint": fingerprint,
                            "verifier_digest": verifier_digest,
                            "readiness_digest": readiness_digest,
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
            verifier_digest=sample.get("verifier_digest", ""),
            readiness_digest=sample.get("readiness_digest", ""),
        )
        duplicate = {
            "feature": feat,
            "key": sample["key"],
            "cwd": sample["cwd"],
            "action": sample["action"],
            "fingerprint": sample["fingerprint"],
            "issues": unique_issues,
            "receipt": sample["receipt"],
            "status": "hit" if hit else "miss",
        }
        declared_action = sample.get("declared_action", sample["action"])
        if declared_action != sample["action"]:
            duplicate["declared_action"] = declared_action
        verifier_digest = sample.get("verifier_digest", "")
        if verifier_digest:
            duplicate["verifier_digest"] = verifier_digest
        readiness_digest = sample.get("readiness_digest", "")
        if readiness_digest:
            duplicate["readiness_digest"] = readiness_digest
        duplicates.append(duplicate)
    return {"schema_version": SCHEMA_VERSION, "duplicates": duplicates}


def _supervisor_run_command():
    """Import test-supervisor lazily; only `run` pays for the sibling lookup."""
    spec = importlib.util.spec_from_file_location(
        "test_supervisor_module", Path(__file__).resolve().parent / "test-supervisor.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("cannot load test-supervisor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_command


def run_planned(
    repo_root: Path,
    feature: Optional[str] = None,
    *,
    timeout: float = 600.0,
    grace: float = 5.0,
    keys: Optional[List[str]] = None,
) -> Mapping[str, Any]:
    """Execute every duplicate-plan cache miss serially and record passing runs.

    Each miss runs through test-supervisor with scope=preflight. Only a passing
    execution becomes a cache entry; a failing, timing-out, or crashing tuple is
    reported in the verdicts and never recorded. Independent tuples still run,
    and one failure never upgrades another tuple's evidence.
    """
    root = repo_root.resolve()
    supervisor_run = _supervisor_run_command()
    verdicts: List[Dict[str, Any]] = []
    duplicates = duplicate_plan(root, feature)["duplicates"]
    if keys is not None:
        missing = set(keys) - {row["key"] for row in duplicates}
        if missing:
            raise ValueError("requested preflight tuple changed; retry dispatch before execution")
        duplicates = [row for row in duplicates if row["key"] in keys]
    for miss in duplicates:
        if miss["status"] != "miss":
            verdicts.append(
                {
                    "feature": miss["feature"],
                    "key": miss["key"],
                    "action": miss["action"],
                    "issues": miss["issues"],
                    "status": "hit",
                }
            )
            continue
        cwd = Path(miss["cwd"])
        if not cwd.is_absolute():
            cwd = root / cwd
        receipt = (
            root / ".scratch" / miss["feature"] / "receipts"
            / ("preflight-%s.json" % miss["key"][:16])
        )
        log = root / ".scratch" / "tmp" / ("preflight-%s-%s.log" % (miss["feature"], miss["key"][:16]))
        result, _ = supervisor_run(
            command_argv(miss["action"], "windows" if os.name == "nt" else "posix"),
            cwd=cwd,
            receipt=receipt,
            log=log,
            timeout=timeout,
            grace=grace,
            scope="preflight",
        )
        verdict: Dict[str, Any] = {
            "feature": miss["feature"],
            "key": miss["key"],
            "action": miss["action"],
            "issues": miss["issues"],
            "status": "recorded" if result["outcome"] == "pass" else "failed",
            "outcome": result["outcome"],
            "exit_code": result["exit_code"],
            "log": result["log"],
            "execution_receipt": str(receipt),
        }
        if result["outcome"] == "pass":
            record(
                root / miss["receipt"],
                cwd=miss["cwd"],
                action=miss["action"],
                fingerprint=miss["fingerprint"],
                execution_receipt=receipt,
                verifier_digest=miss.get("verifier_digest", ""),
                readiness_digest=miss.get("readiness_digest", ""),
            )
        verdicts.append(verdict)
    return {
        "schema_version": SCHEMA_VERSION,
        "verdicts": verdicts,
        "recorded": sum(1 for item in verdicts if item["status"] == "recorded"),
        "failed": sum(1 for item in verdicts if item["status"] == "failed"),
        "hit": sum(1 for item in verdicts if item["status"] == "hit"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("record", "check"):
        command = commands.add_parser(name)
        command.add_argument("receipt", type=Path)
        command.add_argument("--cwd", required=True)
        command.add_argument("--action", required=True)
        command.add_argument("--fingerprint", required=True)
        command.add_argument("--verifier-digest", default="")
        command.add_argument("--readiness-digest", default="")
        if name == "record":
            command.add_argument("--execution-receipt", type=Path, required=True)
    plan = commands.add_parser("plan", help="list only duplicate ready-card preflight tuples")
    plan.add_argument("repo_root", type=Path)
    plan.add_argument("feature", nargs="?")
    run = commands.add_parser(
        "run", help="execute and record every duplicate-plan cache miss serially"
    )
    run.add_argument("repo_root", type=Path)
    run.add_argument("feature", nargs="?")
    run.add_argument("--timeout", type=float, default=600.0)
    run.add_argument("--grace", type=float, default=5.0)
    run.add_argument("--key", action="append", help="run only these dispatch-requested tuple keys")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(duplicate_plan(args.repo_root, args.feature), ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            report = run_planned(
                args.repo_root, args.feature, timeout=args.timeout, grace=args.grace, keys=args.key
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["failed"] == 0 else 1
        if args.command == "record":
            key = record(
                args.receipt,
                cwd=args.cwd,
                action=args.action,
                fingerprint=args.fingerprint,
                execution_receipt=args.execution_receipt,
                verifier_digest=args.verifier_digest,
                readiness_digest=args.readiness_digest,
            )
            print(f"recorded: {key}")
            return 0
        entry = check(
            args.receipt,
            cwd=args.cwd,
            action=args.action,
            fingerprint=args.fingerprint,
            verifier_digest=args.verifier_digest,
            readiness_digest=args.readiness_digest,
        )
        if entry is None:
            print("cache-miss")
            return 3
        print("cache-hit: evidence=%s" % entry["evidence"])
        return 0
    except ValueError as exc:
        print(f"preflight-receipt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
