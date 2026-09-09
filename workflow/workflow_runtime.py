"""Serialize local workflow state changes without time-based lock takeover."""

import contextlib
import functools
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path


_held = threading.local()


def load_baseline(root, digest, legacy=None):
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("dispatch has no valid baseline binding")
    path = Path(root) / ".scratch/wave-baselines" / (digest + ".json")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        if isinstance(legacy, dict) and digest in legacy:
            return None
        raise ValueError("dispatch baseline artifact is missing")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("baseline changed after dispatch")
    data = json.loads(raw.decode("utf-8"))
    if (not isinstance(data, dict) or data.get("schema_version") != 2
            or data.get("kind") not in ("git", "filesystem")):
        raise ValueError("dispatch baseline is invalid")
    return data


def assignment(root, feature, slug, execution=None):
    path = _target(Path(root).resolve(), ".scratch/%s/wave-ledger.json" % feature)
    try:
        payload = json.loads(read_text(path))
    except FileNotFoundError:
        payload = {"waves": []}
    active = [wave for wave in payload["waves"]
              if slug in wave.get("dispatched", []) and slug not in wave.get("closed", {})]
    if len(active) > 1:
        raise ValueError("multiple open executions for %s" % slug)
    current = active[0] if active else None
    if current and current.get("execution"):
        if execution != current["execution"]:
            raise ValueError("execution does not match the current assignment for %s" % slug)
    elif execution is not None:
        raise ValueError("execution has no current assignment for %s" % slug)
    return current


def check_contract(current, slug, raw, data, *, root=None, feature=None):
    if not current or not current.get("execution"):
        return
    from workflow_contract import issue_contract_digest, execution_contract_digest

    if str(data.get("contract_version", "")) == "3":
        from workflow_contract import effective_verifier
        expected = current.get("verifier_sha256", {}).get(slug)
        if (not expected or root is None or feature is None
                or effective_verifier(Path(root), feature, raw)["effective_sha256"] != expected):
            raise ValueError("verifier profile changed during execution: %s" % slug)
    if current.get("contracts", {}).get(slug) == issue_contract_digest(raw):
        return
    if current.get("behavior_contracts", {}).get(slug) != execution_contract_digest(raw):
        raise ValueError("behavior contract changed during execution: %s" % slug)
    before = set(current.get("test_paths", {}).get(slug, []))
    after = set(data.get("test_paths", []) or [])
    if not before.issubset(after):
        raise ValueError("test ownership cannot shrink during execution")
    allowed = list(data.get("touches", []) or []) + list(before)
    def contains(base, path):
        base, path = str(base).replace("\\", "/").rstrip("/"), str(path).replace("\\", "/")
        if ".." in path.split("/") or path.startswith("/") or ":" in path:
            return False
        return path == base or path.startswith(base + "/")
    if any(not any(contains(base, path) for base in allowed) for path in after - before):
        raise ValueError("new test path lies outside admitted ownership; reconcile before writing")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def atomic_write(path, content):
    path = Path(path)
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _target(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root / ".scratch"):
        raise ValueError("workflow transaction target must stay under .scratch")
    return path


def _prepare(root, changes):
    if not isinstance(changes, dict):
        raise ValueError("invalid pending workflow transaction")
    prepared = []
    for relative, change in changes.items():
        if not isinstance(relative, str) or not isinstance(change, dict):
            raise ValueError("invalid workflow transaction entry")
        path = _target(root, relative)
        if set(change) != {"before", "content"}:
            raise ValueError("invalid workflow transaction fields")
        content, before = change["content"], change["before"]
        if content is not None and not isinstance(content, str):
            raise ValueError("invalid workflow transaction content")
        if before is not None and (not isinstance(before, str) or len(before) != 64):
            raise ValueError("invalid workflow transaction digest")
        after = hashlib.sha256(content.encode("utf-8")).hexdigest() if content is not None else None
        current = _digest(path)
        if current == after:
            continue
        if current != before:
            raise ValueError("pending workflow transaction conflicts with %s" % relative)
        prepared.append((path, content))
    return prepared


def _apply(root, changes):
    for path, content in _prepare(root, changes):
        atomic_write(path, content)


def read_text(path, encoding="utf-8"):
    """Read the current transaction's staged text, or the committed file."""
    path = Path(path).resolve()
    for root, changes in getattr(_held, "roots", {}).items():
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            change = changes.get(relative)
            if change is not None:
                if change["content"] is None:
                    raise FileNotFoundError(str(path))
                return change["content"]
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                _held.versions[root].setdefault(relative, None)
                raise
            _held.versions[root].setdefault(relative, hashlib.sha256(raw).hexdigest())
            return raw.decode(encoding)
    return path.read_text(encoding=encoding)


def write_state(root, path, content):
    root = Path(root).resolve()
    path = Path(path).resolve()
    relative = path.relative_to(root).as_posix()
    _target(root, relative)
    with transaction(root):
        changes = _held.roots[root]
        if relative in changes:
            before = changes[relative]["before"]
        elif relative in _held.versions[root]:
            before = _held.versions[root][relative]
        else:
            before = _digest(path)
        changes[relative] = {"before": before, "content": content}


def require_settled(root):
    if (Path(root) / ".scratch" / ".workflow-pending.json").exists():
        raise ValueError("interrupted workflow publication; retry the mutating operation to recover")


@contextlib.contextmanager
def file_lock(path, shared=False):
    path = Path(path)
    if shared and not path.exists():
        yield
        if path.exists():
            raise ValueError("workflow state changed during read; retry the projection")
        return
    if not shared:
        path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the inode: unlinking an unlocked file can split simultaneous lockers.
    with path.open("rb" if shared else "a+b") as stream:
        if not shared and stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                mode = msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK
                msvcrt.locking(stream.fileno(), mode, 1)
            else:
                import fcntl
                mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                fcntl.flock(stream.fileno(), mode | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("workflow state is busy; retry after the current operation") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def read_snapshot(root):
    root = Path(root).resolve()
    readers = getattr(_held, "readers", set())
    if root in getattr(_held, "roots", {}) or root in readers:
        yield
        return
    with file_lock(root / ".scratch" / ".workflow.lock", shared=True):
        require_settled(root)
        _held.readers = readers | {root}
        try:
            yield
        finally:
            _held.readers = readers


def reading(function):
    @functools.wraps(function)
    def wrapped(root, *args, **kwargs):
        with read_snapshot(root):
            return function(root, *args, **kwargs)
    return wrapped


@contextlib.contextmanager
def transaction(root):
    root = Path(root).resolve()
    active = getattr(_held, "roots", {})
    if root in active:
        yield
        return
    if root in getattr(_held, "readers", set()):
        raise ValueError("cannot mutate workflow state during a read-only projection")
    directory = root / ".scratch"
    with file_lock(directory / ".workflow.lock"):
        changes = {}
        versions = getattr(_held, "versions", {})
        _held.versions = versions.copy()
        _held.versions[root] = {}
        _held.roots = active.copy()
        _held.roots[root] = changes
        try:
            pending = directory / ".workflow-pending.json"
            if pending.exists():
                _apply(root, json.loads(pending.read_text(encoding="utf-8")))
                pending.unlink()
            yield
            if len(changes) > 1:
                _prepare(root, changes)
                atomic_write(pending, json.dumps(changes, ensure_ascii=False, sort_keys=True))
                _apply(root, changes)
                pending.unlink()
            elif changes:
                _apply(root, changes)
        finally:
            _held.roots = active
            _held.versions = versions
