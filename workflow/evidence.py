#!/usr/bin/env python3
"""Fixed candidates and deterministic evidence. Never launch or supervise a test."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HEX = re.compile(r"[0-9a-f]{64}")
SECRET = re.compile(r"(?:^|_)(?:APIKEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|AUTH|AUTHORIZATION)(?:$|_)", re.I)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            h.update(block)
    return h.hexdigest()


@contextlib.contextmanager
def file_lock(path):
    """Short-lived exclusion for one engineering file, with no owner or recovery ledger."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("lock cannot be a symlink")
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if not stream.read(1):
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path, content):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("engineering record cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_record(path, value):
    value = dict(value)
    value.pop("digest", None)
    value["digest"] = digest(value)
    content = encoded(value) + b"\n"
    path = Path(path)
    with file_lock(path.with_name(path.name + ".lock")):
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("immutable record already exists with different content: " + str(path))
        else:
            atomic_write(path, content)
    return value


def read_record(path, kind=None):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("digest") != digest({k: v for k, v in value.items() if k != "digest"}):
        raise ValueError("record digest mismatch: " + str(path))
    if kind and value.get("kind") != kind:
        raise ValueError("unexpected evidence kind")
    expected_version = 2 if value.get("kind") == "check_receipt" else 1
    if type(value.get("schema_version")) is not int or value["schema_version"] != expected_version:
        raise ValueError("unsupported evidence schema")
    return value


def relative(value):
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or any(p in ("", "..") for p in text.split("/")) or ":" in text:
        raise ValueError("expected repository-relative path: " + text)
    return path.as_posix()


def local(root, value):
    root = Path(root).resolve()
    path = root / relative(value)
    if path.resolve() != path or not path.resolve().is_relative_to(root):
        raise ValueError("evidence paths must stay in the repository without links")
    return path


def reference(root, path):
    path = Path(os.path.abspath(path))
    if path.resolve() != path:
        raise ValueError("evidence paths cannot contain links")
    return path.relative_to(Path(root).resolve()).as_posix()


def git(root, *args, input=None):
    result = subprocess.run(["git", "-C", str(root), *args], input=input, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def manifest(root, paths):
    result = {}
    for name in paths:
        name = relative(name)
        path = local(root, name)
        if not path.is_file():
            raise ValueError("retained input is not a file: " + name)
        result[name] = sha(path)
    return result


def validate_manifest(root, files):
    if not isinstance(files, dict) or manifest(root, files) != files:
        raise ValueError("retained input or artifact changed")


def retain_files(root, paths, record_path):
    """Copy exactly the named bytes beside their immutable record, without a registry."""
    record_path = local(root, reference(root, record_path))
    files, retained = {}, {}
    for name in sorted(set(relative(p) for p in paths)):
        source = local(root, name)
        if not source.is_file():
            raise ValueError("retained input is not a file: " + name)
        content = source.read_bytes()
        expected = hashlib.sha256(content).hexdigest()
        asset = record_path.parent / (record_path.name + ".assets") / expected / Path(name).name
        asset = local(root, reference(root, asset))
        with file_lock(asset.with_name(asset.name + ".lock")):
            if asset.exists():
                if asset.read_bytes() != content:
                    raise ValueError("retained asset changed: " + str(asset))
            else:
                atomic_write(asset, content)
        files[name], retained[name] = expected, reference(root, asset)
    return files, retained


def validate_retained(root, files, retained):
    if not isinstance(files, dict) or not isinstance(retained, dict) or files.keys() != retained.keys():
        raise ValueError("retained input/artifact manifest is incomplete")
    for name, expected in files.items():
        relative(name)
        if not isinstance(expected, str) or not HEX.fullmatch(expected) or sha(local(root, retained[name])) != expected:
            raise ValueError("retained input or artifact changed: " + name)


def output_files(root, paths, allow_missing=False):
    files = set()
    for name in paths:
        path = local(root, name)
        if path.is_file():
            files.add(relative(name))
        elif path.is_dir():
            for child in path.rglob("*"):
                child = local(root, reference(root, child))
                if child.is_file():
                    files.add(reference(root, child))
        else:
            if not allow_missing:
                raise ValueError("declared output is missing: " + name)
    if not allow_missing and any(not any(_selected(name, [declared]) for name in files) for declared in paths):
        raise ValueError("declared outputs contain no files")
    return sorted(files)


def source_manifest(root, tree):
    source = {}
    for row in git(root, "ls-tree", "-rz", tree).split(b"\0"):
        if not row:
            continue
        metadata, raw_name = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = relative(raw_name.decode("utf-8"))
        if name.startswith(".scratch/"):
            continue
        if kind != "blob":
            raise ValueError("submodule needs a project-specific fixed input contract: " + name)
        source[name] = {"mode": mode, "oid": oid}
    return source


def validate_candidate(root, path):
    fixed = read_record(path, "candidate")
    commit, tree = fixed.get("commit"), fixed.get("tree")
    spec_text, spec_digest = fixed.get("spec_text"), fixed.get("spec_digest")
    oid = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
    if (not {"commit", "tree", "spec_text", "spec_digest"}.issubset(fixed)
            or not isinstance(tree, str) or not re.fullmatch(oid, tree)
            or commit is not None and (not isinstance(commit, str) or not re.fullmatch(oid, commit)
                or git(root, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit
                or git(root, "rev-parse", "--verify", commit + "^{tree}").decode().strip() != tree)
            or commit is None and git(root, "rev-parse", "--verify", tree + "^{tree}").decode().strip() != tree
            or source_manifest(root, tree) != fixed["source"]
            or (spec_text is None and spec_digest is not None)
            or (spec_text is not None and (not isinstance(spec_text, str)
                or hashlib.sha256(spec_text.encode("utf-8")).hexdigest() != spec_digest))):
        raise ValueError("fixed candidate source or Spec changed")
    validate_retained(root, fixed["inputs"], fixed["retained_inputs"])
    return fixed


def candidate(root, ref, spec, inputs, out):
    root = Path(root).resolve()
    out = local(root, reference(root, out))
    resolved = git(root, "rev-parse", "--verify", ref + "^{}").decode().strip()
    kind = git(root, "cat-file", "-t", resolved).decode().strip()
    if kind not in ("commit", "tree"):
        raise ValueError("candidate ref must identify a Git commit or tree")
    commit = resolved if kind == "commit" else None
    tree = git(root, "rev-parse", resolved + "^{tree}").decode().strip()
    source = source_manifest(root, tree)
    text, spec_digest = None, None
    if spec is not None:
        spec_path = Path(spec).resolve()
        text = spec_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        spec_digest = hashlib.sha256(text.encode()).hexdigest()
        state_path = spec_path.parent / "spec-review.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        accepted = (spec_path.parent / "spec-accepted.md").read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if state.get("accepted_digest") != spec_digest or accepted != text:
            raise ValueError("candidate needs the exact accepted Spec bytes")
    files, retained = retain_files(root, inputs, out)
    value = {"schema_version": 1, "kind": "candidate", "commit": commit, "tree": tree,
             "source": source, "spec_digest": spec_digest, "spec_text": text,
             "inputs": files, "retained_inputs": retained}
    # Git retains the source object; Cosmos does not maintain another source object store.
    git(root, "update-ref", "refs/cosmos/candidates/" + digest(value), resolved)
    return write_record(out, value)


def _selected(name, paths):
    return not paths or "." in paths or any(name == p or name.startswith(p.rstrip("/") + "/") for p in paths)


def validate_output_locations(root, definition, records):
    for record in records:
        record = Path(record)
        zones = (record, record.with_suffix(".log"), record.with_suffix(".exit"),
                 record.with_name(record.name + ".assets"))
        for zone in zones:
            name = reference(root, zone)
            if any(_selected(name, [output]) or _selected(output, [name]) for output in definition["outputs"]):
                raise ValueError("declared outputs overlap their own engineering evidence")


def observe_inputs(root, fixed, definition):
    paths = [relative(p) for p in definition.get("inputs", [])]
    outputs = [relative(p) for p in definition.get("outputs", [])]
    expected = {name: item for name, item in fixed["source"].items() if _selected(name, paths)}
    if not expected:
        raise ValueError("check has no declared source inputs")
    if outputs and any(_selected(name, outputs) for name in expected):
        raise ValueError("outputs overlap fixed source inputs")
    observed = {}
    for name, item in expected.items():
        path = Path(root).resolve() / relative(name)
        if path.parent.resolve() != path.parent or not path.parent.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError("source path is linked or escapes checkout")
        if item["mode"] == "120000":
            if not path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
                raise ValueError("candidate symlink changed or escapes checkout: " + name)
            content = os.readlink(path).encode("utf-8")
            algorithm = "sha256" if len(item["oid"]) == 64 else "sha1"
            oid = hashlib.new(algorithm, b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        else:
            if path.is_symlink() or not path.is_file():
                raise ValueError("candidate input missing or linked: " + name)
            content = path.read_bytes()
            if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError("LFS inputs need materialized project evidence")
            if os.name != "nt" and bool(path.stat().st_mode & 0o111) != (item["mode"] == "100755"):
                raise ValueError("candidate executable mode changed: " + name)
            # Git applies the checkout's native clean/EOL filters. The actual bytes
            # remain in the input identity, so different materializations do not hit.
            oid = git(root, "hash-object", "--path=" + name, "--stdin", input=content).decode().strip()
        if oid != item["oid"]:
            raise ValueError("checkout differs from fixed candidate: " + name)
        observed[name] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": item["mode"], "oid": oid}
    extra = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0")
    for name in extra:
        if (name and not name.startswith(".scratch/") and _selected(name, paths)
                and name not in expected and name not in fixed["inputs"] and not (outputs and _selected(name, outputs))):
            raise ValueError("unfixed tracked or untracked input: " + name)
    validate_manifest(root, fixed["inputs"])
    return {"source": observed, "external": fixed["inputs"]}


def _definition(value):
    if not isinstance(value, dict):
        raise ValueError("check definition must be an object")
    allowed = {"argv", "cwd", "environment", "scope", "inputs", "outputs", "measurement_context"}
    if set(value) - allowed:
        raise ValueError("unknown check definition fields: " + ", ".join(sorted(set(value) - allowed)))
    argv = value.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
        raise ValueError("check needs exact argv")
    secrets = [v for k, v in os.environ.items() if SECRET.search(k) and k != "SSH_AUTH_SOCK" and len(v) >= 8]
    if any(secret in arg for arg in argv for secret in secrets):
        raise ValueError("pass secrets through environment, not argv")
    env = value.get("environment")
    if not isinstance(env, dict) or not env:
        raise ValueError("declare the relevant runtime/dependency/environment identity")
    cwd = relative(value.get("cwd", "."))
    scope = value.get("scope", "targeted")
    if scope not in ("preflight", "targeted", "module", "full", "build", "other"):
        raise ValueError("invalid check scope")
    for name in ("inputs", "outputs"):
        if not isinstance(value.get(name, []), list) or any(not isinstance(p, str) for p in value.get(name, [])):
            raise ValueError("check " + name + " must be an array of paths")
    return {"argv": argv, "cwd": cwd, "environment": env, "scope": scope,
            "inputs": sorted(relative(p) for p in value.get("inputs", [])),
            "outputs": sorted(relative(p) for p in value.get("outputs", [])),
            "measurement_context": value.get("measurement_context")}


def prepare(root, candidate_path, definition_path, out):
    root = Path(root).resolve()
    fixed = validate_candidate(root, candidate_path)
    definition = _definition(json.loads(Path(definition_path).read_text(encoding="utf-8")))
    validate_output_locations(root, definition, (candidate_path, out))
    before = observe_inputs(root, fixed, definition)
    context_path = local(root, reference(root, out))
    log = context_path.with_suffix(".log")
    exit_file = context_path.with_suffix(".exit")
    if any(p.exists() for p in (context_path, log, exit_file)):
        raise ValueError("use a fresh attempt path; never overwrite attempts")
    if not local(root, definition["cwd"]).is_dir():
        raise ValueError("check cwd does not exist")
    value = write_record(context_path, {"schema_version": 1, "kind": "check_input",
        "candidate": reference(root, candidate_path), "candidate_digest": fixed["digest"],
        "definition": definition, "input_digest": digest(before),
        "check_digest": digest({"definition": definition, "inputs": before}),
        "log": reference(root, log), "exit_file": reference(root, exit_file), "prepared_at": time.time()})
    command = " ".join(shlex.quote(x) for x in definition["argv"])
    quoted_log, quoted_exit = shlex.quote(str(log)), shlex.quote(str(exit_file))
    shell = "if [ -e " + quoted_exit + " ] || [ -L " + quoted_exit + " ]; then exit 73; fi; "
    shell += "(set -C; : > " + quoted_log + ") || exit 73; "
    shell += "cosmos_check_exit=0; (cd " + shlex.quote(str(local(root, definition["cwd"]))) + " && " + command + ")"
    shell += " >> " + quoted_log + " 2>&1 || cosmos_check_exit=$?; "
    shell += "(set -C; printf '%s\\n' \"$cosmos_check_exit\" > " + quoted_exit + ") || exit 73; exit \"$cosmos_check_exit\""
    quote = lambda s: "'" + str(s).replace("'", "''") + "'"
    powershell = "$ErrorActionPreference = 'Stop'; $PSNativeCommandUseErrorActionPreference = $false; "
    powershell += "if (Test-Path -LiteralPath " + quote(exit_file) + ") { throw 'Attempt already completed' }; "
    powershell += "$cosmosLog = [IO.File]::Open(" + quote(log) + ", [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None); $cosmosLog.Dispose(); "
    powershell += "Set-Location -LiteralPath " + quote(local(root, definition["cwd"])) + "; $LASTEXITCODE = $null"
    powershell += "; & " + " ".join(quote(x) for x in definition["argv"])
    powershell += " *>&1 | Out-File -LiteralPath " + quote(log) + " -Encoding utf8 -Append -ErrorAction Stop"
    powershell += "; $cosmosCheckExit = $LASTEXITCODE; if ($null -eq $cosmosCheckExit) { throw 'No native exit result' }; "
    powershell += "$cosmosExit = [IO.File]::Open(" + quote(exit_file) + ", [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None); "
    powershell += "try { $cosmosBytes = [Text.Encoding]::UTF8.GetBytes([string]$cosmosCheckExit); $cosmosExit.Write($cosmosBytes, 0, $cosmosBytes.Length) } finally { $cosmosExit.Dispose() }; exit $cosmosCheckExit"
    return {"context": str(context_path), "check_digest": value["check_digest"],
            "posix_command": shell, "powershell_command": powershell,
            "execution": "Run the exact command through the harness; its timeout/cancellation policy remains required."}


def seal(root, context_path, out, duration=None):
    root = Path(root).resolve()
    out = local(root, reference(root, out))
    context = read_record(context_path, "check_input")
    fixed = validate_candidate(root, local(root, context["candidate"]))
    if fixed["digest"] != context["candidate_digest"]:
        raise ValueError("candidate changed")
    definition = _definition(context["definition"])
    validate_output_locations(root, definition, (local(root, context["candidate"]), context_path, out))
    log = local(root, context["log"])
    exit_file = local(root, context["exit_file"])
    if min(log.stat().st_mtime, exit_file.stat().st_mtime) < context["prepared_at"] - 1:
        raise ValueError("result predates its prepared inputs")
    exit_content = exit_file.read_bytes()
    text = exit_content.decode("utf-8-sig").strip()
    if not re.fullmatch(r"-?\d+", text):
        raise ValueError("native exit file is incomplete")
    code = int(text)
    after = observe_inputs(root, fixed, definition)
    if digest(after) != context["input_digest"] or context["check_digest"] != digest({"definition": definition, "inputs": after}):
        raise ValueError("check inputs changed during execution")
    if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                                 or not math.isfinite(duration) or duration < 0):
        raise ValueError("invalid measured duration")
    content = log.read_bytes()
    for name, secret in os.environ.items():
        if SECRET.search(name) and name != "SSH_AUTH_SOCK" and len(secret) >= 8:
            for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
                content = content.replace(secret.encode(encoding), "<redacted>".encode(encoding))
    retained = out.with_suffix(".log")
    retained_exit = out.with_suffix(".exit")
    if retained == out or retained_exit == out:
        raise ValueError("receipt path must differ from its retained log and exit files")
    if retained == log or retained_exit == exit_file:
        raise ValueError("retained evidence must not overwrite raw execution output")
    for destination, body in ((retained, content), (retained_exit, exit_content)):
        destination = local(root, reference(root, destination))
        with file_lock(destination.with_name(destination.name + ".lock")):
            if destination.exists():
                if destination.read_bytes() != body:
                    raise ValueError("retained result already exists")
            else:
                atomic_write(destination, body)
    files, retained_outputs = retain_files(root, output_files(root, definition["outputs"], allow_missing=code != 0), out)
    return write_record(out, {"schema_version": 2, "kind": "check_receipt",
        "candidate_digest": fixed["digest"], "spec_digest": fixed["spec_digest"],
        "check_digest": context["check_digest"], "input_digest": context["input_digest"],
        "definition": definition, "input_identity": after,
        "context": reference(root, context_path), "context_digest": context["digest"],
        "argv": definition["argv"], "cwd": definition["cwd"], "scope": definition["scope"],
        "runtime": definition["environment"], "measurement_context": definition["measurement_context"],
        "outcome": "pass" if code == 0 else "fail", "exit_code": code,
        "duration_seconds": duration, "log": reference(root, retained), "log_sha256": sha(retained),
        "outputs": files, "retained_outputs": retained_outputs,
        "exit_file": reference(root, retained_exit), "exit_sha256": hashlib.sha256(exit_content).hexdigest()})


def validate_receipt(root, path, expected_candidate=None):
    root = Path(root).resolve()
    path = local(root, reference(root, path))
    receipt = read_record(path, "check_receipt")
    definition = _definition(receipt["definition"])
    if (receipt["check_digest"] != digest({"definition": definition, "inputs": receipt["input_identity"]})
            or receipt["input_digest"] != digest(receipt["input_identity"])
            or receipt["argv"] != definition["argv"] or receipt["cwd"] != definition["cwd"]
            or receipt["scope"] != definition["scope"] or receipt["runtime"] != definition["environment"]
            or receipt["measurement_context"] != definition["measurement_context"]):
        raise ValueError("receipt input/command binding changed")
    context = read_record(local(root, receipt["context"]), "check_input")
    if (context["digest"] != receipt["context_digest"] or context["check_digest"] != receipt["check_digest"]
            or context["input_digest"] != receipt["input_digest"] or _definition(context["definition"]) != definition):
        raise ValueError("receipt lost its prepared inputs")
    fixed = validate_candidate(root, local(root, context["candidate"]))
    if (fixed["digest"] != receipt["candidate_digest"] or context["candidate_digest"] != fixed["digest"]
            or fixed["spec_digest"] != receipt["spec_digest"]):
        raise ValueError("receipt candidate binding changed")
    selected = {name: item for name, item in fixed["source"].items() if _selected(name, definition["inputs"])}
    observed = receipt["input_identity"]["source"]
    if (not selected or not isinstance(observed, dict) or selected.keys() != observed.keys()
            or receipt["input_identity"]["external"] != fixed["inputs"]):
        raise ValueError("receipt input closure changed")
    for name, expected in selected.items():
        actual = observed[name]
        if (not isinstance(actual, dict) or actual.get("mode") != expected["mode"] or actual.get("oid") != expected["oid"]
                or not isinstance(actual.get("sha256"), str) or not HEX.fullmatch(actual["sha256"])):
            raise ValueError("receipt source identity changed: " + name)
    for key, hash_key in (("log", "log_sha256"), ("exit_file", "exit_sha256")):
        if sha(local(root, receipt[key])) != receipt[hash_key]:
            raise ValueError("receipt evidence missing or changed: " + key)
    if (not isinstance(receipt["exit_code"], int) or isinstance(receipt["exit_code"], bool)
            or int(local(root, receipt["exit_file"]).read_text(encoding="utf-8-sig").strip()) != receipt["exit_code"]):
        raise ValueError("receipt exit result changed")
    duration = receipt["duration_seconds"]
    if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                                 or not math.isfinite(duration) or duration < 0):
        raise ValueError("invalid measured duration")
    if receipt["outcome"] != ("pass" if receipt["exit_code"] == 0 else "fail"):
        raise ValueError("receipt outcome does not match native exit")
    validate_retained(root, receipt["outputs"], receipt["retained_outputs"])
    if (receipt["outputs"] and not definition["outputs"]
            or any(not _selected(name, definition["outputs"]) for name in receipt["outputs"])
            or receipt["outcome"] == "pass" and any(
                not any(_selected(name, [declared]) for name in receipt["outputs"]) for declared in definition["outputs"])):
        raise ValueError("receipt outputs differ from their declaration")
    if expected_candidate and receipt["candidate_digest"] != expected_candidate:
        raise ValueError("receipt belongs to another candidate")
    return receipt


def _applies_to_candidate(root, receipt, fixed):
    if receipt["candidate_digest"] == fixed["digest"]:
        return True
    paths = receipt["definition"]["inputs"]
    if not paths:
        return False
    context = read_record(local(root, receipt["context"]), "check_input")
    previous = validate_candidate(root, local(root, context["candidate"]))
    old_source = {name: item for name, item in previous["source"].items() if _selected(name, paths)}
    new_source = {name: item for name, item in fixed["source"].items() if _selected(name, paths)}
    return old_source == new_source and previous["inputs"] == fixed["inputs"]


def _known_receipts(root, paths, check_digests):
    """Query existing records; selected paths never hide another known attempt."""
    root = Path(root).resolve()
    explicit = {local(root, reference(root, path)) for path in paths}
    candidates = set(explicit)
    for directory in {path.parent for path in explicit}:
        candidates.update(directory.glob("*.json"))
    scratch = root / ".scratch"
    if scratch.is_dir() and not scratch.is_symlink():
        candidates.update(scratch.rglob("*.json"))
    result = {}
    for path in sorted(candidates):
        try:
            path = local(root, reference(root, path))
            header = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if path in explicit:
                raise
            continue
        if not isinstance(header, dict) or header.get("kind") != "check_receipt":
            if path in explicit:
                raise ValueError("expected a check receipt: " + str(path))
            continue
        if header.get("check_digest") in check_digests:
            item = validate_receipt(root, path)
            if item["check_digest"] in check_digests:
                result[reference(root, path)] = item
    return result


def _reject_known_failures(root, paths, proofs):
    known = _known_receipts(root, paths, {proof["check_digest"] for proof in proofs})
    if any(item["outcome"] != "pass" for item in known.values()):
        raise ValueError("known failed attempt conflicts with the selected passing check; diagnose the conflicting evidence")


def validate_artifact_bindings(files, proofs, fixed):
    proven = {name: {value} for name, value in fixed["inputs"].items()}
    for proof in proofs:
        for name, value in proof["outputs"].items():
            proven.setdefault(name, set()).add(value)
        for name, value in proof["input_identity"]["source"].items():
            proven.setdefault(name, set()).add(value["sha256"])
    for name, value in files.items():
        if value not in proven.get(name, set()):
            raise ValueError("review artifact is not bound to the selected verification evidence: " + name)


def reuse(root, context_path, receipts):
    context = read_record(context_path, "check_input")
    fixed = validate_candidate(root, local(root, context["candidate"]))
    if context["candidate_digest"] != fixed["digest"]:
        raise ValueError("reuse context candidate changed")
    definition = _definition(context["definition"])
    current = observe_inputs(root, fixed, definition)
    if (context["input_digest"] != digest(current)
            or context["check_digest"] != digest({"definition": definition, "inputs": current})):
        raise ValueError("prepared reuse inputs changed")
    for path in receipts:
        validate_receipt(root, path)
    matches = _known_receipts(root, receipts, {context["check_digest"]})
    outcomes = {item["outcome"] for item in matches.values()}
    eligible = any(_applies_to_candidate(root, item, fixed) for item in matches.values() if item["outcome"] == "pass")
    if len(outcomes) > 1:
        status = "conflict"
    elif outcomes == {"fail"}:
        status = "known-failure"
    elif outcomes == {"pass"} and eligible:
        status = "hit"
    else:
        status = "miss"
    return {"status": status, "receipts": sorted(matches)}


def review(root, candidate_path, receipts, artifacts, scope, out):
    fixed = validate_candidate(root, candidate_path)
    if not scope.strip() or not receipts:
        raise ValueError("review needs an explicit scope and verification evidence")
    proofs, checked = {}, []
    for path in receipts:
        item = validate_receipt(root, path)
        if item["outcome"] != "pass" or not _applies_to_candidate(root, item, fixed):
            raise ValueError("required check did not pass for this candidate's declared input closure")
        proofs[reference(root, path)] = item["digest"]
        checked.append(item)
    _reject_known_failures(root, receipts, checked)
    files, retained = retain_files(root, artifacts, out)
    validate_artifact_bindings(files, checked, fixed)
    value = {"schema_version": 1, "kind": "candidate_review", "candidate": reference(root, candidate_path),
             "candidate_digest": fixed["digest"], "spec_digest": fixed["spec_digest"],
             "scope": scope, "receipts": proofs, "artifacts": files, "retained_artifacts": retained}
    return write_record(local(root, reference(root, out)), value)


def validate_review(root, path, reject_conflicts=True):
    record = read_record(path, "candidate_review")
    fixed = validate_candidate(root, local(root, record["candidate"]))
    if fixed["digest"] != record["candidate_digest"] or fixed["spec_digest"] != record["spec_digest"]:
        raise ValueError("review candidate mismatch")
    if not isinstance(record.get("scope"), str) or not record["scope"].strip() or not record["receipts"]:
        raise ValueError("review scope or verification is missing")
    checked = []
    for name, expected in record["receipts"].items():
        proof = validate_receipt(root, local(root, name))
        if proof["digest"] != expected or proof["outcome"] != "pass" or not _applies_to_candidate(root, proof, fixed):
            raise ValueError("review verification changed")
        checked.append(proof)
    if reject_conflicts:
        _reject_known_failures(root, [local(root, name) for name in record["receipts"]], checked)
    validate_retained(root, record["artifacts"], record["retained_artifacts"])
    validate_artifact_bindings(record["artifacts"], checked, fixed)
    return record


def record_decision(root, review_path, event, destination):
    record = validate_review(root, review_path)
    if (not isinstance(event, dict) or event.get("review_digest") != record["digest"]
            or event.get("action") not in ("approve", "request_changes")
            or not isinstance(event.get("event_id"), str) or not event["event_id"]):
        raise ValueError("invalid or stale human decision")
    return write_record(local(root, reference(root, destination)), {"schema_version": 1, "kind": "human_decision",
        "review": reference(root, review_path), "review_digest": record["digest"],
        "candidate_digest": record["candidate_digest"], "spec_digest": record["spec_digest"],
        "event": event})


def validate_decision(root, path):
    decision = read_record(path, "human_decision")
    record = validate_review(root, local(root, decision["review"]), reject_conflicts=False)
    if (decision["review_digest"] != record["digest"] or decision["candidate_digest"] != record["candidate_digest"]
            or decision["spec_digest"] != record["spec_digest"] or decision["event"]["review_digest"] != record["digest"]
            or decision["event"].get("action") not in ("approve", "request_changes")
            or not isinstance(decision["event"].get("event_id"), str) or not decision["event"]["event_id"]):
        raise ValueError("decision identity mismatch")
    return decision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("candidate", "prepare", "seal", "validate", "reuse", "review"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
        if name == "candidate":
            cmd.add_argument("--ref", "--commit", dest="ref", required=True)
            cmd.add_argument("--spec", type=Path)
            cmd.add_argument("--input", action="append", default=[])
        if name in ("prepare", "review"):
            cmd.add_argument("--candidate", type=Path, required=True)
        if name == "prepare":
            cmd.add_argument("--definition", type=Path, required=True)
        if name in ("seal", "reuse"):
            cmd.add_argument("--context", type=Path, required=True)
        if name == "seal":
            cmd.add_argument("--duration", type=float, help="only an actual runner measurement; unknown by default")
        if name == "validate":
            cmd.add_argument("path", type=Path)
        if name in ("reuse", "review"):
            cmd.add_argument("--receipt", type=Path, action="append", default=[])
        if name == "review":
            cmd.add_argument("--artifact", action="append", default=[])
            cmd.add_argument("--scope", required=True)
        if name not in ("validate", "reuse"):
            cmd.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "candidate":
            result = candidate(args.root, args.ref, args.spec, args.input, args.out)
        elif args.command == "prepare":
            result = prepare(args.root, args.candidate, args.definition, args.out)
        elif args.command == "seal":
            result = seal(args.root, args.context, args.out, args.duration)
        elif args.command == "reuse":
            result = reuse(args.root, args.context, args.receipt)
        elif args.command == "review":
            result = review(args.root, args.candidate, args.receipt, args.artifact, args.scope, args.out)
        else:
            record = read_record(args.path)
            kind = record["kind"]
            if kind == "check_receipt":
                result = validate_receipt(args.root, args.path)
            elif kind == "candidate_review":
                result = validate_review(args.root, args.path)
            elif kind == "human_decision":
                result = validate_decision(args.root, args.path)
            elif kind == "candidate":
                result = validate_candidate(args.root, args.path)
            else:
                raise ValueError("unsupported validation kind")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in ("miss", "conflict", "known-failure") else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "invalid", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
