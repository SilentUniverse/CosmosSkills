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
PARENT_POINTER = re.compile(
    r"^Parent\s*[:：]\s*(PRD(?:-v\d+)?\.md)\s*[·•]\s*(S\d+)(?:\s*[·•]\s*(.+))?$"
)


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


def parse_parent_pointer(raw: str):
    pointers = []
    for line in _section(raw, "上级"):
        line = re.sub(r"^[-*]\s+", "", line.strip()).strip("`")
        if not re.match(r"^Parent\s*[:：]", line):
            continue
        match = PARENT_POINTER.fullmatch(line)
        if not match:
            raise ValueError("malformed Parent pointer; expected PRD.md · S# · R#/D#")
        refs = [token for token in re.split(r"[\s/·•、，,]+", match.group(3) or "") if token]
        if any(not re.fullmatch(r"[RD]\d+", token) for token in refs):
            raise ValueError("Parent refs must name R# or D#")
        pointers.append({"spec": match.group(1), "slice": match.group(2), "refs": refs})
    if len(pointers) > 1:
        raise ValueError("issue must have only one Parent design pointer")
    return pointers[0] if pointers else None


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


def _absolute_anywhere(value: str) -> bool:
    """Absolute on the recording platform: leading slash (POSIX/UNC) or a drive anchor.

    A receipt recorded on POSIX carries `/...` paths that Windows `Path.is_absolute`
    rejects (no drive); recognizing them keeps checkout-absolute evidence portable.
    """
    return value.startswith("/") or Path(value).is_absolute()


def issue_contract_digest(raw: str) -> str:
    """Hash the immutable issue contract; status and Comments are execution state.

    Line endings are normalized so a digest written through a text-mode reader and
    revalidated through a byte-mode reader agree on every platform.
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
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


def execution_contract_digest(raw: str) -> str:
    """Separate appendable test ownership from the immutable behavior contract."""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    result = []
    in_frontmatter, tests = False, False
    for index, line in enumerate(lines):
        if line.strip() == "---":
            in_frontmatter = index == 0
            tests = False
        elif in_frontmatter and line.startswith("test_paths:"):
            tests = True
            continue
        elif tests:
            if line[:1].isspace():
                continue
            tests = False
        result.append(line)
    return issue_contract_digest("".join(result))


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
    if "git" in values:
        preferred = ("git", "lock", "runtime", "tools", "services")
    elif "fixtures" in values:
        preferred = ("fixtures", "services", "permissions", "network")
    else:
        preferred = ()
    keys = [key for key in preferred if key in values]
    keys.extend(sorted(key for key in values if key not in preferred))
    return "; ".join(f"{key}={values[key]}" for key in keys)


def _windows_command_argv(command: str) -> List[str]:
    """Parse Windows command-line quoting, plus single-quote grouping for POSIX-style shells.

    Double quotes keep CreateProcess/CommandLineToArgvW semantics (backslash escapes
    before `"`). Single quotes group literally with no escapes, matching the POSIX
    shells that drive these commands on Windows (Git Bash, MSYS); on stock cmd nobody
    quotes paths with `'`, so accepting both keeps every substrate's receipts valid.
    """
    argv: List[str] = []
    index = 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index == len(command):
            break
        argument: List[str] = []
        quote = ""
        while index < len(command):
            if command[index] in " \t" and not quote:
                break
            if command[index] == "'" and quote != '"':
                quote = "" if quote == "'" else "'"
                index += 1
                continue
            if command[index] == "\\" and quote != "'":
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
                        quote = "" if quote == '"' else '"'
                        index += 1
                else:
                    argument.extend("\\" * count)
                continue
            if command[index] == '"' and quote != "'":
                quote = "" if quote == '"' else '"'
                index += 1
                continue
            argument.append(command[index])
            index += 1
        if quote:
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


_PROFILE_UNSET = object()


def load_verifier_profile(root: Path, feature: str) -> Any:
    """Read one feature profile for reuse across a batch of card projections."""
    root = Path(root).resolve()
    profile_path = root / ".scratch" / feature / "verifier.json"
    try:
        raw_profile = profile_path.read_bytes()
        return json.loads(raw_profile.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"contract v3 profile file unreadable: {profile_path}: {exc}") from exc


def effective_verifier(
    root: Path,
    feature: str,
    issue_raw: str,
    profile: Any = _PROFILE_UNSET,
) -> Mapping[str, Any]:
    """Resolve one v3 card against its profile and strict, machine-readable deviations."""
    root = Path(root).resolve()
    verification = _section(issue_raw, "验证设计")
    profile_ref = _bullet(verification, "profile")
    if profile_ref != "verifier.json":
        raise ValueError("contract v3 profile must be `verifier.json`")
    if profile is _PROFILE_UNSET:
        profile = load_verifier_profile(root, feature)
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
        completion_commands = sorted(completion_commands)
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


def verification_contract(root, issue_path, raw=None):
    """Resolve the complete AC-to-command contract without executing a check."""
    from evidence import relative
    root, issue_path = Path(root).resolve(), Path(issue_path)
    raw = raw if raw is not None else issue_path.read_text(encoding="utf-8-sig")
    data = _frontmatter(raw, issue_path)
    if data.get("contract_version", "") not in ("", "1", "2", "3"):
        raise ValueError("engineering contract_version must be 1, 2, or 3")
    expected_ac = set(range(1, sum(bool(AC_CHECKBOX.match(line)) for line in _section(raw, "验收标准")) + 1))
    if not expected_ac:
        raise ValueError("engineering contract needs checkbox AC")
    lines = _section(raw, "验证设计")
    if data.get("contract_version") == "3":
        verifier = dict(effective_verifier(root, data.get("feature", ""), raw))
    else:
        cwd = _bullet(lines, "工作目录")
        if not cwd:
            raise ValueError("engineering contract needs an explicit 工作目录")
        fingerprint, prerequisites, prepare = (_bullet(lines, field) for field in ("环境指纹", "前置条件", "准备动作"))
        if data.get("contract_version") == "2" and data.get("status") != "done":
            if not all((fingerprint, prerequisites, prepare)):
                raise ValueError("contract v2 needs 环境指纹, 前置条件, and 准备动作")
            for text, label, required in (
                (fingerprint, "fingerprint", {"git", "lock", "runtime", "tools", "services"}),
                (prerequisites, "prerequisites", {"fixtures", "services", "permissions", "network"}),
            ):
                missing = required - set(_pairs(text, label))
                if missing:
                    raise ValueError("contract v2 %s missing keys: %s" % (label, ", ".join(sorted(missing))))
            if "无" not in prepare and "result=" not in prepare:
                raise ValueError("contract v2 prepare needs result= or explicit 无")
        verifier = {"cwd": relative(cwd), "commands": {}, "fingerprint": fingerprint,
                    "prerequisites": prerequisites, "prepare": prepare}
    mappings = {}
    for line in lines:
        match = AC_ACTION.match(line)
        if not match:
            continue
        index, action = int(match.group(1)), match.group(2).strip()
        if index in mappings:
            raise ValueError("duplicate AC command mapping: #%d" % index)
        profile = PROFILE_ACTION.fullmatch(action)
        if profile:
            name = profile.group(1)
            if name not in verifier["commands"]:
                raise ValueError("AC mapping names an unavailable profile command: " + name)
        else:
            name = action
            verifier["commands"][name] = action
        command_argv(verifier["commands"][name])
        mappings[index] = name
    if set(mappings) != expected_ac:
        raise ValueError("engineering contract needs exactly one explicit command mapping for every AC")
    verifier["ac_commands"] = mappings
    declared_environment(verifier)
    return verifier


def declared_environment(verifier):
    contract = {}
    for key in ("fingerprint", "prerequisites"):
        if verifier.get(key):
            values = _pairs(verifier[key], key)
            if key == "fingerprint":
                values.pop("git", None)
            contract[key] = values
    if verifier.get("prepare"):
        contract["prepare"] = verifier["prepare"]
    return contract


def _ac_claim(reference):
    result = set()
    for claim in re.findall(r"\bAC\s*([0-9,\-]+)", reference):
        result.update(parse_ac_spec(claim))
    return result


def _reference_path(root, reference):
    from evidence import local
    name = reference.split("；", 1)[0].split(";", 1)[0].strip().strip("`")
    return local(root, name)


def _validate_legacy_completion(root, issue_path, raw, verifier, expected_ac, references):
    """Historical receipts unlock dependencies only while their actual proof remains available."""
    from evidence import local
    covered, payloads = set(), []
    data = _frontmatter(raw, issue_path)
    for reference in references:
        path = _reference_path(root, reference)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("historical receipt is missing or invalid: " + str(path)) from exc
        if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
            raise ValueError("historical receipt needs schema_version 1")
        if (payload.get("scope") not in ("targeted", "module", "full", "build", "other")
                or payload.get("outcome") != "pass" or type(payload.get("exit_code")) is not int or payload["exit_code"] != 0):
            raise ValueError("historical receipt needs a passing non-preflight native exit")
        binding = payload.get("issue")
        ac = _ac_claim(reference)
        if binding is not None:
            if not isinstance(binding, dict) or any(binding.get(key) != value for key, value in {
                "feature": data.get("feature"), "slug": issue_path.stem, "contract_sha256": issue_contract_digest(raw),
            }.items()):
                raise ValueError("historical receipt issue binding changed")
            bound_ac = binding.get("ac")
            if not isinstance(bound_ac, list) or any(type(index) is not int for index in bound_ac):
                raise ValueError("historical receipt AC binding is invalid")
            if ac and ac != set(bound_ac):
                raise ValueError("historical receipt AC claim differs from binding")
            ac = set(bound_ac)
        if not ac or not ac.issubset(expected_ac):
            raise ValueError("historical receipt needs valid AC coverage")
        for index in ac:
            command = verifier["commands"][verifier["ac_commands"][index]]
            if payload.get("argv") != command_argv(command, payload.get("argv_style")):
                raise ValueError("historical receipt command does not prove the mapped AC")
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            raise ValueError("historical receipt cwd is missing")
        if (Path(cwd) if Path(cwd).is_absolute() else root / cwd).resolve() != (root / verifier["cwd"]).resolve():
            raise ValueError("historical receipt cwd differs from the engineering contract")
        log = payload.get("log")
        if not isinstance(log, str) or not log:
            raise ValueError("historical receipt log is missing")
        if Path(log).is_absolute():
            try:
                log = Path(log).resolve().relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError("historical receipt log is outside this repository") from exc
        log_path = local(root, log)
        if not log_path.is_file() or payload.get("log_sha256") != _sha256(log_path):
            raise ValueError("historical receipt log is missing or changed")
        covered.update(ac)
        payloads.append(payload)
    if covered != set(expected_ac):
        raise ValueError("historical receipts do not cover every AC")
    return {"receipts": payloads, "ac": expected_ac}


def validate_completion(root, issue_path, raw=None):
    """Validate new fixed evidence or retained proof on an already completed historical card."""
    root, issue_path = Path(root).resolve(), Path(issue_path).resolve()
    raw = raw if raw is not None else issue_path.read_text(encoding="utf-8-sig")
    data = _frontmatter(raw, issue_path)
    verifier = verification_contract(root, issue_path, raw)
    expected_ac = sorted(verifier["ac_commands"])
    completion = _completion(raw)
    if not completion:
        raise ValueError("close requires a ### 完成 record with machine evidence")
    evidence_refs = _bullet_values(completion, "evidence")
    if evidence_refs:
        return validate_evidence_completion(root, raw, verifier, expected_ac, evidence_refs)
    if data.get("status") != "done":
        raise ValueError("new completion requires schema 2 evidence; legacy proof is read-only history")
    if data.get("contract_version") == "3":
        result = validate_v3_completion(root, issue_path, raw)
        # Bound schema-1 history additionally proves its retained evidence through the
        # legacy reader; unbound old-minimum receipts carry no such proof to check.
        if _bullet_values(completion, "managed-proof") or result.get("unbound"):
            return result
    references = _bullet_values(completion, "receipt")
    if not references:
        raise ValueError("historical completion has no retained machine evidence")
    return _validate_legacy_completion(root, issue_path, raw, verifier, expected_ac, references)


def validate_v3_completion(
    root: Path,
    issue_path: Path,
    raw: str | None = None,
    profile: Any = _PROFILE_UNSET,
) -> Mapping[str, Any]:
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
    verifier = (
        effective_verifier(root, feature, raw)
        if profile is _PROFILE_UNSET
        else effective_verifier(root, feature, raw, profile)
    )
    managed_refs = _bullet_values(_completion(raw), "managed-proof")
    if managed_refs:
        if len(managed_refs) != 1 or not re.fullmatch(r"[0-9a-f]{64}", managed_refs[0]):
            raise ValueError("managed completion needs exactly one immutable proof reference")
        from historical_proof import validate_managed_proof
        proof = validate_managed_proof(root, feature + "/" + slug, managed_refs[0], raw)
        if set(proof["ac"]) != set(expected_ac):
            raise ValueError("managed completion does not cover this card's AC")
        return {"receipts": [proof], "ac": expected_ac}
    evidence_refs = _bullet_values(_completion(raw), "evidence")
    if evidence_refs:
        return validate_evidence_completion(root, raw, verifier, expected_ac, evidence_refs)
    receipt_refs = _bullet_values(_completion(raw), "receipt")
    if not receipt_refs:
        raise ValueError(f"issue '{slug}' contract v3 record has no receipt line")
    covered = set()
    payloads = []
    unbound = True
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
        unbound = unbound and legacy_unbound
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
            cwd_portable_absolute = _absolute_anywhere(cwd_value)
            if data.get("status") == "ready" or not cwd_portable_absolute:
                if not cwd_portable_absolute:
                    payload_cwd = root / payload_cwd
                expected_cwd = (root / verifier["cwd"]).resolve()
                if payload_cwd.resolve() != expected_cwd:
                    raise ValueError(f"issue '{slug}' receipt cwd does not match verifier profile")
            if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("log_sha256", ""))):
                raise ValueError(f"issue '{slug}' receipt log_sha256 is invalid")
            log_text = str(payload.get("log", ""))
            log_path = Path(log_text)
            local_log = None
            if not _absolute_anywhere(log_text):
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
    return {"receipts": payloads, "ac": expected_ac, "unbound": unbound}


def validate_evidence_completion(root, raw, verifier, expected_ac, references):
    """Map shared, immutable checks to this card without adding the card to the check key."""
    from evidence import local, read_record, validate_candidate, validate_receipt, _applies_to_candidate, _reject_known_failures
    targets = _bullet_values(_completion(raw), "candidate")
    if len(targets) > 1:
        raise ValueError("completion needs at most one explicit candidate")
    target = validate_candidate(root, local(root, targets[0])) if targets else None
    covered, payloads, candidates, paths = set(), [], set(), []
    for reference in references:
        name = reference.split("；", 1)[0].split(";", 1)[0].strip().strip("`")
        path = local(root, name)
        try:
            receipt = validate_receipt(root, path)
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError("completion evidence is missing or malformed: " + str(path)) from exc
        if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 2
                or receipt["outcome"] != "pass" or receipt["scope"] == "preflight"):
            raise ValueError("completion needs a passing non-preflight check")
        if target is not None and not _applies_to_candidate(root, receipt, target):
            raise ValueError("completion check does not apply to the selected candidate's input closure")
        observed = receipt["definition"]["environment"].get("contract", {})
        if not isinstance(observed, dict) or any(observed.get(key) != value for key, value in declared_environment(verifier).items()):
            raise ValueError("check environment differs from the engineering contract")
        ac = _ac_claim(reference)
        if not ac or not ac.issubset(expected_ac):
            raise ValueError("evidence reference needs valid AC selectors")
        if receipt["cwd"] != verifier["cwd"]:
            raise ValueError("check cwd differs from the engineering contract")
        for index in ac:
            name = verifier.get("ac_commands", {}).get(index)
            if name is None:
                raise ValueError("shared evidence requires an explicit command for each AC")
            command = verifier["commands"][name]
            if receipt["argv"] not in [command_argv(command, style) for style in ("posix", "windows")]:
                raise ValueError("check command does not prove the mapped AC")
        parent = parse_parent_pointer(raw)
        if parent:
            context = read_record(local(root, receipt["context"]), "check_input")
            candidate = target if target is not None else read_record(local(root, context["candidate"]), "candidate")
            if not isinstance(candidate["spec_text"], str):
                raise ValueError("Parent-bound completion requires a candidate with an accepted Spec")
            import importlib.util
            import sys
            source = Path(__file__).resolve().parent / "spec" / "scripts" / "spec-review.py"
            spec = importlib.util.spec_from_file_location("cosmos_completion_spec", source)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            feature = _frontmatter(raw, Path("card"))["feature"]
            contract = module.parent_contract(Path(root) / ".scratch" / feature, raw)
            model = module.parse_model(candidate["spec_text"])
            if module.validate_model(model) or not module._design_matches(contract["model"], model, contract["needed"]):
                raise ValueError("candidate Spec does not cover this card's accepted design")
        candidates.add(receipt["candidate_digest"])
        covered.update(ac)
        payloads.append(receipt)
        paths.append(path)
    if covered != set(expected_ac) or (target is None and len(candidates) != 1):
        raise ValueError("completion needs all AC proven against one fixed candidate")
    if _frontmatter(raw, Path("card")).get("status") != "done":
        _reject_known_failures(root, paths, payloads)
    return {"receipts": payloads, "ac": expected_ac}
