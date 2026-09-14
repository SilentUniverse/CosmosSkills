"""Local-host resource exclusion with health that survives the lock holder."""

import contextlib
import hashlib
import json
import os
import unicodedata
from pathlib import Path

from workflow_runtime import atomic_write, file_lock


def registry():
    return Path(os.environ.get("COSMOS_RESOURCE_ROOT", str(Path.home() / ".cosmos/resources"))).resolve()


def identity(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("resource ID must be a nonempty bounded string")
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _path(root, resource):
    return root / hashlib.sha256(identity(resource).encode("utf-8")).hexdigest()


def inspect(resources, root=None):
    root = Path(root).resolve() if root else registry()
    result = {}
    for resource in sorted({identity(value) for value in resources}):
        path = _path(root, resource).with_suffix(".json")
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("resource") != resource or data.get("state") not in ("available", "in_use", "recovery_required"):
                raise ValueError("invalid resource registry record")
            result[resource] = data
        else:
            result[resource] = {"resource": resource, "state": "available", "epoch": 0}
    return result


@contextlib.contextmanager
def operation(resources, owner, root=None, recovery=False, expected_owner=None):
    names = sorted({identity(value) for value in resources})
    grant = {"owner": owner, "resources": {}, "recovered": False}
    if not names:
        yield grant
        return
    root = Path(root).resolve() if root else registry()
    if root.exists() and root.is_symlink():
        raise ValueError("resource registry cannot be a link")
    with contextlib.ExitStack() as stack:
        for name in names:
            stack.enter_context(file_lock(_path(root, name).with_suffix(".lock")))
        current = inspect(names, root)
        if recovery and any(row["state"] != "available" and row.get("owner") != (expected_owner or owner)
                            for row in current.values()):
            raise ValueError("resource belongs to another unresolved run")
        if not recovery and any(row["state"] != "available" for row in current.values()):
            raise ValueError("resource recovery required; a free lock does not prove a healthy resource")
        for name, row in current.items():
            grant["resources"][name] = int(row["epoch"]) + 1
        try:
            for name, epoch in grant["resources"].items():
                atomic_write(_path(root, name).with_suffix(".json"), json.dumps(
                    {"resource": name, "epoch": epoch, "state": "in_use", "owner": owner}))
            yield grant
        finally:
            for name, epoch in grant["resources"].items():
                atomic_write(_path(root, name).with_suffix(".json"), json.dumps(
                    {"resource": name, "epoch": epoch,
                     "state": "available" if grant["recovered"] else "recovery_required", "owner": owner}))
