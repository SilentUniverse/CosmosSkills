#!/usr/bin/env python3
"""Shared machine contract for lean verifier profiles and completion evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
AC_CHECKBOX = re.compile(r"^\s*-\s*\[[ xX]\]\s+\S")
DEVIATION = re.compile(
    r"^\s*-\s*偏差\s+(fingerprint|command)\.([A-Za-z][A-Za-z0-9_-]*)[：:]\s*(.+?)\s*$"
)
DEVIATION_PREFIX = re.compile(r"^\s*-\s*偏差[ \t]+")
PROFILE_ACTION = re.compile(r"^profile:([A-Za-z][A-Za-z0-9_-]*)$")
AC_ACTION = re.compile(r"^\s*-\s*#(\d+)\s*(?:→|->)\s*`([^`]+)`")
DONE_HEAD = re.compile(r"^#{2,3}\s*完成(?:[^\w]|$)")


def _frontmatter(raw: str, path: Path) -> Dict[str, str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: no YAML frontmatter")
    result: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        match = FM_KEY.match(line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("\"'")
    raise ValueError(f"{path}: unclosed YAML frontmatter")


def _section(raw: str, heading_word: str) -> List[str]:
    result: List[str] = []
    active = False
    for line in raw.splitlines():
        if line.startswith("## "):
            if active:
                break
            active = heading_word in line
            continue
        if active:
            result.append(line)
    return result


def _bullet(lines: Sequence[str], label: str) -> str:
    for line in lines:
        stripped = line.strip()
        for separator in ("：", ":"):
            prefix = f"- {label}{separator}"
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip().strip("`")
    return ""


def _bullet_values(lines: Sequence[str], label: str) -> List[str]:
    values = []
    for line in lines:
        stripped = line.strip()
        for separator in ("：", ":"):
            prefix = f"- {label}{separator}"
            if stripped.startswith(prefix):
                values.append(stripped[len(prefix):].strip().strip("`"))
                break
    return values


def _completion(raw: str) -> List[str]:
    block = None
    for line in raw.splitlines():
        if DONE_HEAD.match(line):
            block = []
            continue
        if block is not None:
            if line.startswith("#"):
                break
            block.append(line)
    return block or []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def issue_contract_digest(raw: str) -> str:
    """Hash the immutable issue contract; status and Comments are execution state."""
    contract = raw.split("\n## Comments", 1)[0]
    lines = contract.splitlines(keepends=True)
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    for index, line in enumerate(lines[1:], start=1):
        if in_frontmatter and line.strip() == "---":
            break
        if in_frontmatter and line.startswith("status:"):
            ending = line[len(line.rstrip("\r\n")):]
            lines[index] = "status: <execution-state>" + ending
            break
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _pairs(value: str, label: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in re.split(r"[;；]", value):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"{label} entry needs key=value: {item!r}")
        key, entry = item.split("=", 1)
        key, entry = key.strip(), entry.strip()
        if not key or not entry or key in result:
            raise ValueError(f"{label} has invalid or duplicate key: {key!r}")
        result[key] = entry
    return result


def _pair_text(values: Mapping[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in values.items())


def _windows_command_argv(command: str) -> List[str]:
    """Parse the Windows command-line quoting accepted by CreateProcess/CommandLineToArgvW."""
    argv: List[str] = []
    index = 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index == len(command):
            break
        argument: List[str] = []
        quoted = False
        while index < len(command):
            if command[index] in " \t" and not quoted:
                break
            if command[index] == "\\":
                start = index
                while index < len(command) and command[index] == "\\":
                    index += 1
                count = index - start
                if index < len(command) and command[index] == '"':
                    argument.extend("\\" * (count // 2))
                    if count % 2:
                        argument.append('"')
                        index += 1
                    else:
                        quoted = not quoted
                        index += 1
                else:
                    argument.extend("\\" * count)
                continue
            if command[index] == '"':
                quoted = not quoted
                index += 1
                continue
            argument.append(command[index])
            index += 1
        if quoted:
            raise ValueError("unclosed quote in Windows verifier command")
        argv.append("".join(argument))
    return argv


def command_argv(command: Any, style: str | None = None) -> List[str]:
    """Return the exact argv for a profile command on the receipt's platform."""
    if isinstance(command, list):
        if not command or any(not isinstance(value, str) or not value for value in command):
            raise ValueError("verifier command argv must contain non-empty strings")
        return list(command)
    if not isinstance(command, str) or not command.strip():
        raise ValueError("verifier command must be a non-empty string or argv array")
    style = style or ("windows" if os.name == "nt" else "posix")
    if style == "windows":
        return _windows_command_argv(command)
    if style == "posix":
        return shlex.split(command)
    raise ValueError(f"unsupported argv style: {style!r}")


def _profile_cwd(root: Path, value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("contract v3 profile cwd must be repo-relative")
    resolved = (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("contract v3 profile cwd must stay inside the repo") from exc
    return relative.as_posix() or "."


def effective_verifier(root: Path, feature: str, issue_raw: str) -> Mapping[str, Any]:
    """Resolve one v3 card against its profile and strict, machine-readable deviations."""
    root = Path(root).resolve()
    verification = _section(issue_raw, "验证设计")
    profile_ref = _bullet(verification, "profile")
    if profile_ref != "verifier.json":
        raise ValueError("contract v3 profile must be `verifier.json`")
    profile_path = root / ".scratch" / feature / "verifier.json"
    try:
        raw_profile = profile_path.read_bytes()
        profile = json.loads(raw_profile.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"contract v3 profile file unreadable: {profile_path}: {exc}") from exc
    schema_version = profile.get("schema_version", 1) if isinstance(profile, dict) else None
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise ValueError("contract v3 profile needs schema_version 1 or 2")
    card = _frontmatter(issue_raw, Path(f".scratch/{feature}/issues/<card>.md"))
    verifier_schema = card.get("verifier_schema", "")
    if schema_version == 2 and verifier_schema != "2":
        raise ValueError("contract v3 schema-2 profile requires card verifier_schema: 2")
    if schema_version == 1 and verifier_schema not in ("", "1"):
        raise ValueError(
            f"contract v3 card verifier_schema {verifier_schema!r} != profile schema 1"
        )
    commands = profile.get("commands")
    if not isinstance(commands, dict) or not commands or not all(
        isinstance(key, str) and key and isinstance(value, str) and value.strip()
        for key, value in commands.items()
    ):
        raise ValueError("contract v3 profile needs non-empty string commands")
    completion_commands = profile.get("completion_commands", [])
    cwd_value = str(profile.get("cwd", "." if schema_version == 1 else "")).strip()
    fingerprint_text = str(profile.get("fingerprint", "")).strip()
    prerequisites = str(profile.get("prerequisites", "")).strip()
    prepare = str(profile.get("prepare", "")).strip()
    if schema_version == 2 and not all((cwd_value, fingerprint_text, prerequisites, prepare)):
        raise ValueError("contract v3 profile needs cwd, fingerprint, prerequisites, and prepare")
    cwd = _profile_cwd(root, cwd_value)
    duplicated = [
        label
        for label in ("工作目录", "环境指纹", "前置条件", "准备动作")
        if _bullet(verification, label)
    ]
    if duplicated:
        raise ValueError(
            "contract v3 card duplicates profile fields: %s" % ", ".join(duplicated)
        )
    fingerprint = _pairs(fingerprint_text, "fingerprint")
    missing = [key for key in ("git", "lock", "runtime", "tools", "services") if key not in fingerprint]
    if missing:
        raise ValueError("contract v3 profile fingerprint missing keys: %s" % ", ".join(missing))
    prerequisites_map = _pairs(prerequisites, "prerequisites") if schema_version == 2 else None
    if prerequisites_map is not None:
        missing = [
            key for key in ("fixtures", "services", "permissions", "network")
            if key not in prerequisites_map
        ]
        if missing:
            raise ValueError(
                "contract v3 profile prerequisites missing keys: %s" % ", ".join(missing)
            )
        if "无" not in prepare and "result=" not in prepare:
            raise ValueError("contract v3 profile prepare needs result= or explicit 无")
    effective_commands = dict(commands)
    seen = set()
    for line in verification:
        if not DEVIATION_PREFIX.match(line):
            continue
        match = DEVIATION.match(line)
        if not match:
            raise ValueError(f"invalid v3 deviation syntax: {line.strip()!r}")
        kind, key, value = match.groups()
        marker = (kind, key)
        if marker in seen:
            raise ValueError(f"duplicate v3 deviation: {kind}.{key}")
        seen.add(marker)
        value = value.strip().strip("`")
        target = fingerprint if kind == "fingerprint" else effective_commands
        if kind == "fingerprint" and key not in target:
            raise ValueError(f"v3 deviation references unknown {kind}.{key}")
        if not value:
            raise ValueError(f"v3 deviation {kind}.{key} must not be empty")
        target[key] = value
    if schema_version == 2:
        if (
            not isinstance(completion_commands, list)
            or not completion_commands
            or any(not isinstance(name, str) or not name for name in completion_commands)
            or len(completion_commands) != len(set(completion_commands))
            or any(name not in effective_commands for name in completion_commands)
        ):
            raise ValueError(
                "contract v3 profile schema 2 needs unique completion_commands resolved by commands"
            )
    effective: Dict[str, Any] = {
        "schema_version": schema_version,
        "cwd": cwd,
        "fingerprint": _pair_text(fingerprint),
        "prerequisites": (
            _pair_text(prerequisites_map) if prerequisites_map is not None else prerequisites
        ),
        "prepare": prepare,
        "commands": effective_commands,
        "completion_commands": completion_commands,
    }
    encoded = json.dumps(
        effective, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    effective["effective_sha256"] = hashlib.sha256(encoded).hexdigest()
    for action_name in re.findall(r"\bprofile:([A-Za-z][A-Za-z0-9_-]*)\b", "\n".join(verification)):
        if action_name not in effective_commands:
            raise ValueError(f"verifier profile has no command '{action_name}'")
    ac_count = sum(1 for line in _section(issue_raw, "验收标准") if AC_CHECKBOX.match(line))
    ac_commands: Dict[int, str] = {}
    for line in verification:
        match = AC_ACTION.match(line)
        if not match:
            continue
        ac_id, action = int(match.group(1)), match.group(2).strip()
        if ac_id in ac_commands:
            raise ValueError(f"duplicate contract v3 AC mapping: #{ac_id}")
        profile_action = PROFILE_ACTION.fullmatch(action)
        if schema_version == 2:
            if not profile_action:
                raise ValueError(
                    f"contract v3 schema-2 AC #{ac_id} must map to one profile:NAME command"
                )
            name = profile_action.group(1)
            if name not in completion_commands:
                raise ValueError(
                    f"contract v3 AC #{ac_id} maps to non-completion command {name!r}"
                )
            ac_commands[ac_id] = name
    if schema_version == 2:
        extra_maps = sorted(set(ac_commands) - set(range(1, ac_count + 1)))
        if extra_maps:
            raise ValueError(
                "contract v3 schema-2 AC map references missing AC: %s"
                % ", ".join("#%d" % value for value in extra_maps)
            )
        missing_maps = sorted(set(range(1, ac_count + 1)) - set(ac_commands))
        if missing_maps:
            raise ValueError(
                "contract v3 schema-2 AC missing profile command map: %s"
                % ", ".join("#%d" % value for value in missing_maps)
            )
    effective["ac_commands"] = ac_commands
    return effective


def resolve_action(verifier: Mapping[str, Any], action: str) -> str:
    match = PROFILE_ACTION.match(action.strip())
    if not match:
        return action.strip()
    name = match.group(1)
    command = verifier.get("commands", {}).get(name)
    if not command:
        raise ValueError(f"verifier profile has no command '{name}'")
    return str(command)


def parse_ac_spec(value: str) -> List[int]:
    result = set()
    for token in value.split(","):
        token = token.strip()
        if re.fullmatch(r"\d+", token):
            result.add(int(token))
        elif re.fullmatch(r"\d+-\d+", token):
            low, high = (int(part) for part in token.split("-", 1))
            if low > high:
                raise ValueError(f"invalid AC range: {token}")
            result.update(range(low, high + 1))
        elif token:
            raise ValueError(f"invalid AC selector: {token}")
    return sorted(result)


def issue_binding(
    issue_path: Path,
    verifier_name: str,
    ac: Sequence[int] | None = None,
) -> Mapping[str, Any]:
    """Build the receipt binding before execution while the card is still ready."""
    issue_path = Path(issue_path).resolve()
    if issue_path.parent.name != "issues" or issue_path.parent.parent.parent.name != ".scratch":
        raise ValueError("--issue must be .scratch/<feat>/issues/<slug>.md")
    feature = issue_path.parent.parent.name
    root = issue_path.parent.parent.parent.parent
    raw = issue_path.read_text(encoding="utf-8-sig")
    data = _frontmatter(raw, issue_path)
    if data.get("type") != "issue" or data.get("feature") != feature:
        raise ValueError("--issue identity does not match its feature directory")
    if data.get("contract_version") != "3" or data.get("status") != "ready":
        raise ValueError("--issue binding requires a ready contract v3 card")
    verifier = effective_verifier(root, feature, raw)
    if verifier_name not in verifier["commands"]:
        raise ValueError(f"verifier profile has no command '{verifier_name}'")
    if verifier["schema_version"] == 2 and verifier_name not in verifier["completion_commands"]:
        raise ValueError(f"verifier '{verifier_name}' is not a completion command")
    ac_count = sum(1 for line in _section(raw, "验收标准") if AC_CHECKBOX.match(line))
    if ac_count == 0:
        raise ValueError("--issue has no checkbox AC")
    requested_ac = list(ac if ac is not None else range(1, ac_count + 1))
    if any(type(value) is not int for value in requested_ac):
        raise ValueError("--ac must contain integers")
    selected_ac = sorted(set(requested_ac))
    if not selected_ac or any(value < 1 or value > ac_count for value in selected_ac):
        raise ValueError("--ac must select existing AC")
    mismatched = [
        value for value in selected_ac
        if verifier["schema_version"] == 2
        and verifier["ac_commands"].get(value) != verifier_name
    ]
    if mismatched:
        raise ValueError(
            "verifier %r is not mapped by AC: %s"
            % (verifier_name, ", ".join("#%d" % value for value in mismatched))
        )
    return {
        "feature": feature,
        "slug": issue_path.stem,
        "contract_sha256": issue_contract_digest(raw),
        "ac": selected_ac,
        "cwd": verifier["cwd"],
        "verifier": verifier_name,
        "verifier_schema": verifier["schema_version"],
        "verifier_sha256": verifier["effective_sha256"],
    }


def validate_v3_completion(root: Path, issue_path: Path, raw: str | None = None) -> Mapping[str, Any]:
    """Verify that bound passing receipts jointly prove this exact card."""
    root = Path(root).resolve()
    issue_path = Path(issue_path).resolve()
    raw = raw if raw is not None else issue_path.read_text(encoding="utf-8-sig")
    data = _frontmatter(raw, issue_path)
    feature = data.get("feature", "")
    slug = issue_path.stem
    expected_ac = list(
        range(1, sum(1 for line in _section(raw, "验收标准") if AC_CHECKBOX.match(line)) + 1)
    )
    if not expected_ac:
        raise ValueError(f"issue '{slug}' has no checkbox AC")
    verifier = effective_verifier(root, feature, raw)
    receipt_refs = _bullet_values(_completion(raw), "receipt")
    if not receipt_refs:
        raise ValueError(f"issue '{slug}' contract v3 record has no receipt line")
    covered = set()
    payloads = []
    for receipt_ref in receipt_refs:
        relative = receipt_ref.split("；", 1)[0].split(";", 1)[0].strip().strip("`")
        parts = relative.replace("\\", "/").split("/")
        if (
            not relative.endswith(".json")
            or len(parts) < 4
            or parts[:3] != [".scratch", feature, "receipts"]
            or any(part in ("", ".", "..") for part in parts)
        ):
            raise ValueError(
                f"issue '{slug}' receipt path must stay under .scratch/{feature}/receipts/: {relative}"
            )
        receipt_path = root.joinpath(*parts)
        try:
            receipt_path = receipt_path.resolve()
            receipt_path.relative_to((root / ".scratch" / feature / "receipts").resolve())
        except ValueError as exc:
            raise ValueError(
                f"issue '{slug}' receipt path must stay under .scratch/{feature}/receipts/: {relative}"
            ) from exc
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"issue '{slug}' receipt missing: {relative}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"issue '{slug}' receipt not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"issue '{slug}' receipt must be a JSON object")
        binding = payload.get("issue")
        legacy_unbound = verifier["schema_version"] == 1 and "issue" not in payload
        if legacy_unbound:
            if payload.get("outcome") != "pass":
                raise ValueError(
                    "issue '%s' legacy receipt outcome %r != pass"
                    % (slug, payload.get("outcome"))
                )
            receipt_ac = set()
            for claim in re.findall(r"\bAC\s*([0-9,\-]+)", receipt_ref):
                receipt_ac.update(parse_ac_spec(claim))
            receipt_ac = sorted(receipt_ac)
            if not receipt_ac or any(value not in expected_ac for value in receipt_ac):
                raise ValueError(f"issue '{slug}' legacy receipt has invalid AC claim")
        else:
            if (
                type(payload.get("schema_version")) is not int
                or payload.get("schema_version") != 1
            ):
                raise ValueError(f"issue '{slug}' receipt needs schema_version 1")
            if verifier["schema_version"] == 2:
                if payload.get("scope") not in ("targeted", "module", "full", "build", "other"):
                    raise ValueError(f"issue '{slug}' completion receipt has invalid scope")
            elif payload.get("scope") == "preflight":
                raise ValueError(f"issue '{slug}' completion cannot use a preflight receipt")
            if (
                payload.get("outcome") != "pass"
                or type(payload.get("exit_code")) is not int
                or payload.get("exit_code") != 0
            ):
                raise ValueError(
                    "issue '%s' receipt outcome %r/exit %r != pass/0"
                    % (slug, payload.get("outcome"), payload.get("exit_code"))
                )
            if not isinstance(binding, dict):
                raise ValueError(f"issue '{slug}' receipt has no issue binding")
            expected = {
                "feature": feature,
                "slug": slug,
                "contract_sha256": issue_contract_digest(raw),
                "cwd": verifier["cwd"],
                "verifier_schema": verifier["schema_version"],
            }
            for key, value in expected.items():
                if binding.get(key) != value:
                    raise ValueError(
                        f"issue '{slug}' receipt binding {key} {binding.get(key)!r} != {value!r}"
                    )
            receipt_ac = binding.get("ac")
            if (
                not isinstance(receipt_ac, list)
                or not receipt_ac
                or any(type(value) is not int for value in receipt_ac)
                or receipt_ac != sorted(set(receipt_ac))
                or any(value not in expected_ac for value in receipt_ac)
            ):
                raise ValueError(f"issue '{slug}' receipt binding ac is invalid: {receipt_ac!r}")
            name = binding.get("verifier")
            if binding.get("verifier_sha256") != verifier["effective_sha256"]:
                raise ValueError(f"issue '{slug}' receipt verifier profile changed")
            if name not in verifier["commands"]:
                raise ValueError(f"issue '{slug}' receipt names unknown verifier {name!r}")
            if verifier["schema_version"] == 2 and name not in verifier["completion_commands"]:
                raise ValueError(f"issue '{slug}' receipt verifier {name!r} is not a completion command")
            mismatched = [
                value for value in receipt_ac
                if verifier["schema_version"] == 2
                and verifier["ac_commands"].get(value) != name
            ]
            if mismatched:
                raise ValueError(
                    "issue '%s' receipt verifier %r is not mapped by AC: %s"
                    % (slug, name, ", ".join("#%d" % value for value in mismatched))
                )
            argv_style = payload.get("argv_style")
            if verifier["schema_version"] == 2 and argv_style not in ("posix", "windows"):
                raise ValueError(f"issue '{slug}' schema-2 receipt needs argv_style")
            expected_argv = command_argv(verifier["commands"][name], argv_style)
            if payload.get("argv") != expected_argv:
                raise ValueError(f"issue '{slug}' receipt argv does not match profile:{name}")
            cwd_value = payload.get("cwd")
            if not isinstance(cwd_value, str) or not cwd_value.strip():
                raise ValueError(f"issue '{slug}' receipt cwd is missing")
            payload_cwd = Path(cwd_value)
            if data.get("status") == "ready" or not payload_cwd.is_absolute():
                if not payload_cwd.is_absolute():
                    payload_cwd = root / payload_cwd
                expected_cwd = (root / verifier["cwd"]).resolve()
                if payload_cwd.resolve() != expected_cwd:
                    raise ValueError(f"issue '{slug}' receipt cwd does not match verifier profile")
            if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("log_sha256", ""))):
                raise ValueError(f"issue '{slug}' receipt log_sha256 is invalid")
            log_path = Path(str(payload.get("log", "")))
            local_log = None
            if not log_path.is_absolute():
                local_log = root / log_path
            else:
                try:
                    log_path.resolve().relative_to((root / ".scratch" / "tmp").resolve())
                    local_log = log_path
                except ValueError:
                    normalized_parts = log_path.as_posix().split("/")
                    if not any(
                        normalized_parts[index:index + 2] == [".scratch", "tmp"]
                        for index in range(len(normalized_parts) - 1)
                    ):
                        raise ValueError(
                            f"issue '{slug}' receipt log must identify .scratch/tmp/"
                        )
            if local_log is not None:
                try:
                    local_log.resolve().relative_to((root / ".scratch" / "tmp").resolve())
                except ValueError as exc:
                    raise ValueError(f"issue '{slug}' receipt log must stay under .scratch/tmp/") from exc
            if data.get("status") == "ready" and (
                local_log is None
                or not local_log.is_file()
                or payload.get("log_sha256") != _sha256(local_log)
            ):
                raise ValueError(f"issue '{slug}' receipt log is missing or changed")
            if (
                data.get("status") != "ready"
                and local_log is not None
                and local_log.exists()
                and (not local_log.is_file() or payload.get("log_sha256") != _sha256(local_log))
            ):
                raise ValueError(f"issue '{slug}' receipt log is missing or changed")
        covered.update(receipt_ac)
        payloads.append(payload)
    if covered != set(expected_ac):
        missing = sorted(set(expected_ac) - covered)
        raise ValueError(
            "issue '%s' completion receipts do not cover AC: %s"
            % (slug, ", ".join("#%d" % value for value in missing))
        )
    return {"receipts": payloads, "ac": expected_ac}
