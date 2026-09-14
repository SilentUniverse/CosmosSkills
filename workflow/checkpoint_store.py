"""Content-addressed versions independent of the user's Git index and working tree."""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
from pathlib import Path


EXCLUDED = {".git", ".scratch", "node_modules", ".venv", "venv", "__pycache__"}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def checked_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("snapshot path must be a portable relative path")
    for part in value.split("/"):
        if (not part or part in (".", "..") or part[-1:] in (".", " ")
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ValueError("nonportable snapshot path: " + value)
    return value


def _excluded(path, kind="source"):
    excluded = EXCLUDED if kind == "source" else {".git", ".scratch"}
    return any(part in excluded for part in Path(path).parts)


def _aliases(known, name):
    parts = name.split("/")
    for index in range(1, len(parts) + 1):
        prefix = "/".join(parts[:index])
        alias = unicodedata.normalize("NFC", prefix).casefold()
        if alias in known and known[alias] != prefix:
            raise ValueError("case/Unicode snapshot path alias: " + name)
        known[alias] = prefix


def put(store, content):
    store = Path(store)
    digest = hashlib.sha256(content).hexdigest()
    directory = store / "blobs" / digest[:2]
    target = directory / digest[2:]
    if directory.resolve() != directory.absolute():
        raise ValueError("snapshot storage cannot traverse links")
    directory.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if get(store, digest) != content:
            raise ValueError("snapshot object collision")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=".object-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def get(store, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid snapshot digest")
    path = Path(store) / "blobs" / digest[:2] / digest[2:]
    if path.resolve() != path.absolute():
        raise ValueError("snapshot objects cannot traverse links")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("snapshot object changed: " + digest)
    return content


def _inventory(root, inputs, tracked=True, kind="source"):
    use_tracked = tracked
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                capture_output=True, timeout=10)
    except FileNotFoundError:
        result = None
    tracked = {}
    if use_tracked and result is not None and result.returncode == 0:
        if Path(os.fsdecode(result.stdout).strip()).resolve() != root:
            raise ValueError("snapshot root must be the Git repository root")
        rows = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"], timeout=10)
        for row in rows.split(b"\0"):
            if not row:
                continue
            metadata, raw_path = row.split(b"\t", 1)
            mode, _, stage = metadata.split()
            path = os.fsdecode(raw_path)
            if stage != b"0":
                raise ValueError("unresolved Git index conflict: " + path)
            if not _excluded(path):
                if mode == b"160000":
                    raise ValueError("submodule requires an explicit external input adapter: " + path)
                tracked[path] = mode.decode("ascii")
    if not tracked and not inputs:
        raise ValueError("snapshot needs tracked files or explicit inputs")
    for name in inputs:
        checked_path(name)
        if _excluded(name, kind):
            raise ValueError("workflow controls and dependencies are external inputs: " + name)
        path = root / name
        if not path.exists() and not path.is_symlink():
            raise ValueError("declared snapshot input is missing: " + name)
        if path.is_dir() and not path.is_symlink():
            for directory, names, files in os.walk(path, followlinks=False):
                names[:] = [n for n in names if not _excluded(n, kind)]
                for child in files + [n for n in names if (Path(directory) / n).is_symlink()]:
                    tracked.setdefault((Path(directory) / child).relative_to(root).as_posix(), None)
        else:
            tracked.setdefault(name, None)
    return tracked


def _observe(root, inventory):
    entries, aliases, contents = {}, {}, {}
    for name, git_mode in sorted(inventory.items()):
        checked_path(name)
        _aliases(aliases, name)
        path = root / name
        if path.parent.resolve() != path.parent:
            raise ValueError("snapshot input parent traverses a link: " + name)
        if path.name == ".env" or path.suffix in (".pem", ".key") or path.name.startswith(".env.") and path.name != ".env.example":
            raise ValueError("secret-bearing input requires external restoration: " + name)
        try:
            status = path.lstat()
        except FileNotFoundError:
            if git_mode is None:
                raise ValueError("snapshot input disappeared: " + name)
            entries[name] = {"kind": "deleted"}
            continue
        if stat.S_ISLNK(status.st_mode):
            target = os.readlink(path)
            try:
                resolved = path.resolve(strict=True).relative_to(root).as_posix()
            except (OSError, RuntimeError, ValueError):
                raise ValueError("snapshot link must resolve inside its inputs: " + name)
            if resolved not in inventory and not any(item.startswith(resolved + "/") for item in inventory):
                raise ValueError("snapshot link target is not captured: " + name)
            if Path(target).is_absolute() or "\\" in target:
                raise ValueError("snapshot link must be portable and relative: " + name)
            content = target.encode("utf-8")
            entry = {"kind": "symlink"}
        elif stat.S_ISREG(status.st_mode):
            content = path.read_bytes()
            if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                raise ValueError("Git LFS input is not materialized: " + name)
            entry = {"kind": "file", "executable": bool(status.st_mode & 0o111) if os.name != "nt" else git_mode == "100755"}
        else:
            raise ValueError("unsupported snapshot input kind: " + name)
        entry["blob"] = hashlib.sha256(content).hexdigest()
        contents[entry["blob"]] = content
        entries[name] = entry
    return entries, contents


def capture(root, store, inputs=(), tracked=True, kind="source"):
    if kind not in ("source", "artifact") or kind == "artifact" and tracked:
        raise ValueError("artifact capture requires explicit outputs")
    root, store = Path(root).resolve(), Path(store).resolve()
    inventory = _inventory(root, inputs, tracked=tracked, kind=kind)
    entries, contents = _observe(root, inventory)
    if _inventory(root, inputs, tracked=tracked, kind=kind) != inventory or _observe(root, inventory)[0] != entries:
        raise ValueError("snapshot inputs changed during capture")
    for content in contents.values():
        put(store, content)
    manifest = {"schema_version": 1, "kind": kind, "files": entries}
    return {"digest": put(store, encoded(manifest)), "manifest": manifest}


def load(store, source_digest):
    manifest = json.loads(get(store, source_digest).decode("utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("kind") not in ("source", "artifact") or not isinstance(manifest.get("files"), dict):
        raise ValueError("invalid source manifest")
    aliases, prefixes = {}, {}
    for name, entry in manifest["files"].items():
        checked_path(name)
        _aliases(prefixes, name)
        alias = unicodedata.normalize("NFC", name).casefold()
        if alias in aliases:
            raise ValueError("case/Unicode snapshot path alias")
        aliases[alias] = name
        if not isinstance(entry, dict) or _excluded(name, manifest["kind"]) or entry.get("kind") not in ("file", "symlink", "deleted"):
            raise ValueError("invalid source entry")
        if entry["kind"] == "file" and type(entry.get("executable")) is not bool:
            raise ValueError("invalid snapshot mode")
        if entry["kind"] != "deleted":
            get(store, entry["blob"])
    for name in aliases:
        if any(parent in aliases for parent in ("/".join(name.split("/")[:index]) for index in range(1, len(name.split("/"))))):
            raise ValueError("snapshot entry cannot be another entry's parent")
    return manifest


def verify(store, digest, directory):
    root = Path(directory).resolve()
    manifest = load(store, digest)
    inventory = {name: "100755" if entry.get("executable") else "100644" for name, entry in manifest["files"].items()}
    if _observe(root, inventory)[0] != manifest["files"]:
        raise ValueError("materialized inputs changed")


def overlay(store, digest, directory):
    directory = Path(directory).resolve()
    manifest = load(store, digest)
    if manifest["kind"] != "artifact":
        raise ValueError("only declared build artifacts can be restored over source")
    temporary = directory.parent / (".artifact-" + digest)
    materialize(store, digest, temporary)
    try:
        for name, entry in manifest["files"].items():
            if entry["kind"] == "deleted":
                raise ValueError("artifact cannot delete an input")
            target = directory / name
            if target.exists() or target.is_symlink() or target.parent.resolve() != target.parent:
                raise ValueError("build artifact overlaps source or another artifact: " + name)
        for name in manifest["files"]:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary / name, target)
    finally:
        shutil.rmtree(temporary)
    verify(store, digest, directory)


def materialize(store, source_digest, destination):
    store, destination = Path(store).resolve(), Path(destination).absolute()
    if destination.is_symlink():
        raise ValueError("preview destination exists as a link")
    destination = destination.parent.resolve() / destination.name
    manifest = load(store, source_digest)
    if destination.exists():
        raise ValueError("preview destination exists or traverses a link; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".preview-", dir=destination.parent))
    try:
        for name, entry in manifest["files"].items():
            if entry["kind"] != "file":
                continue
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(get(store, entry["blob"]))
            path.chmod(0o755 if entry["executable"] else 0o644)
        for name, entry in manifest["files"].items():
            if entry["kind"] == "symlink":
                path = staging / name
                path.parent.mkdir(parents=True, exist_ok=True)
                target = get(store, entry["blob"]).decode("utf-8")
                if Path(target).is_absolute() or "\\" in target:
                    raise ValueError("invalid snapshot symlink")
                resolved = (path.parent / target).resolve()
                resolved.relative_to(staging)
                path.symlink_to(target, target_is_directory=resolved.is_dir())
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"source_digest": source_digest, "directory": str(destination)}


def difference(store, before, after):
    old, new = load(store, before)["files"], load(store, after)["files"]
    return [{"path": path, "before": old.get(path), "after": new.get(path)}
            for path in sorted(set(old) | set(new)) if old.get(path) != new.get(path)]


def proof_store(root, feature):
    checked_path(feature)
    path = Path(root).resolve() / '.scratch' / feature / 'receipts' / 'managed'
    if path.resolve() != path:
        raise ValueError('proof storage cannot traverse links')
    return path


def publish_proof(root, reference, proof_ref, proof, plan, state, checks):
    import workflow_batch as batch
    import workflow_managed as managed
    from workflow_runtime import read_text, write_state
    destination = proof_store(root, reference.split('/')[0])
    objects = destination / 'objects'
    put(objects, encoded(proof))
    member = state['members'][reference]
    contract = get(managed.store(root), member['contract_ref'])
    put(objects, contract)
    receipts, logs = {}, set()
    for check in checks:
        run_id = proof['checks'][check]
        run = batch._json(batch._path(root, state['batch_id']) / 'runs' / (run_id + '.json'))
        receipt = managed._document(root, run['receipt_ref'])
        receipts[check] = {'receipt_ref': put(objects, encoded(receipt)), 'job': plan['jobs'][check]}
        for stage in receipt['stages']:
            logs.add(stage['log_ref'])
        if receipt.get('application'):
            logs.add(receipt['application']['log_ref'])
    for digest in logs:
        put(objects, get(managed.store(root), digest))
    dependencies, decision_events, external = {}, {}, {}
    external_objects = set()
    upstream_proofs = dict(proof.get('upstream', {}))
    for dep in proof.get('external_proofs', {}):
        evidence_ref = member['external_evidence'][dep]
        evidence = json.loads(get(managed.store(root), evidence_ref))
        contract_ref = evidence['contract_ref']
        for digest in (evidence_ref, contract_ref):
            put(objects, get(managed.store(root), digest))
            external_objects.add(digest)
        external[dep] = evidence_ref
        for completion in (evidence['completion'] or {}).get('receipts', []):
            if completion.get('kind') == 'issue_proof':
                upstream_ref = hashlib.sha256(encoded(completion)).hexdigest()
                if not (proof_store(root, dep.split('/')[0]) / (upstream_ref + '.json')).is_file():
                    from workflow_jobs import validate_receipt
                    upstream_state, upstream_plan = batch.load_batch(root, completion['batch_id'])
                    if upstream_state['member_proofs'].get(dep) != upstream_ref:
                        raise ValueError('external managed proof cannot be exported from its current batch')
                    for run_id in completion['checks'].values():
                        validate_receipt(root, upstream_state, upstream_plan, run_id)
                    publish_proof(root, dep, upstream_ref, completion, upstream_plan, upstream_state, list(completion['checks']))
                upstream_proofs[dep] = upstream_ref
    for dep, upstream in upstream_proofs.items():
        if not upstream:
            continue
        upstream_store = proof_store(root, dep.split('/')[0])
        pointer = json.loads(read_text(upstream_store / (upstream + '.json'), encoding='utf-8'))
        upstream_bundle = json.loads(get(upstream_store / 'objects', pointer['bundle_ref']))
        for digest in [pointer['bundle_ref']] + upstream_bundle['objects']:
            put(objects, get(upstream_store / 'objects', digest))
        dependencies[dep] = pointer['bundle_ref']
    for value in proof.get('decisions', {}).values():
        if value:
            decision_id = value['decision_id']
            digest = state['decisions'][decision_id]
            decision_events[decision_id] = put(objects, get(managed.store(root), digest))
    closure = {proof_ref, member['contract_ref']} | logs | {row['receipt_ref'] for row in receipts.values()} | set(decision_events.values()) | external_objects
    for digest in dependencies.values():
        closure.add(digest)
        closure.update(json.loads(get(objects, digest))['objects'])
    bundle = {'schema_version': 1, 'kind': 'portable_issue_proof' , 'proof_ref': proof_ref,
              'contract_ref': member['contract_ref'], 'receipts': receipts, 'logs': sorted(logs),
              'requirements': plan['requirements'], 'manual_checks': plan.get('manual_checks', {}),
              'source_digest': proof['source_digest'], 'historical_only': True, 'dependencies': dependencies,
              'external_dependencies': external,
              'decision_events': decision_events, 'decision_contracts': plan.get('decisions', {}), 'objects': sorted(closure)}
    bundle_ref = put(objects, encoded(bundle))
    write_state(root, destination / (proof_ref + '.json'), encoded({'bundle_ref': bundle_ref}).decode('utf-8'))
    read_proof(root, reference, proof_ref, contract.decode('utf-8'))
    return bundle_ref


def read_proof(root, reference, proof_ref, raw):
    from workflow_contract import execution_contract_digest
    destination = proof_store(root, reference.split('/')[0])
    if not re.fullmatch(r'[0-9a-f]{64}', proof_ref):
        raise ValueError('invalid portable proof reference')
    pointer = destination / (proof_ref + '.json')
    from workflow_runtime import read_text
    try:
        pointer_text = read_text(pointer, encoding='utf-8')
    except FileNotFoundError:
        return None
    if pointer.resolve() != pointer:
        raise ValueError('portable proof pointer traverses a link')
    objects = destination / 'objects'
    bundle = json.loads(get(objects, json.loads(pointer_text)['bundle_ref']))
    for digest in bundle.get('objects', []):
        get(objects, digest)
    proof = json.loads(get(objects, proof_ref))
    contract = get(objects, bundle['contract_ref']).decode('utf-8')
    if (bundle.get('kind') != 'portable_issue_proof' or bundle['proof_ref'] != proof_ref
            or proof.get('member') != reference or proof['behavior_digest'] != execution_contract_digest(raw)
            or execution_contract_digest(contract) != proof['behavior_digest']):
        raise ValueError('portable proof does not match the retained contract')
    if set(bundle.get('external_dependencies', {})) != set(proof.get('external_proofs', {})):
        raise ValueError('portable proof lost external dependency evidence')
    for dep, evidence_ref in bundle.get('external_dependencies', {}).items():
        evidence = json.loads(get(objects, evidence_ref))
        external_raw = get(objects, evidence['contract_ref']).decode('utf-8')
        identity = hashlib.sha256(encoded({'contract': execution_contract_digest(external_raw),
                                          'proof': evidence['completion']})).hexdigest()
        if identity != proof['external_proofs'][dep]:
            raise ValueError('portable external completion changed')
        for completion in (evidence['completion'] or {}).get('receipts', []):
            if completion.get('kind') == 'issue_proof':
                dependency_ref = bundle.get('dependencies', {}).get(dep)
                if not dependency_ref or json.loads(get(objects, dependency_ref))['proof_ref'] != hashlib.sha256(encoded(completion)).hexdigest():
                    raise ValueError('portable external managed proof lost its object closure')
    covered = set()
    for check, row in bundle['receipts'].items():
        receipt = json.loads(get(objects, row['receipt_ref']))
        if (not receipt['passed'] or receipt['candidate_ref'] != proof['source_digest']
                or receipt['check_id'] != check or receipt['run_id'] != proof['checks'][check]
                or receipt['verifier_digest'] != hashlib.sha256(encoded(row['job'])).hexdigest()):
            raise ValueError('portable proof lacks the matching executed check')
        for stage in receipt['stages']:
            if hashlib.sha256(get(objects, stage['log_ref'])).hexdigest() != stage['process']['log_sha256']:
                raise ValueError('portable log does not match actual execution')
        if receipt.get('application'):
            get(objects, receipt['application']['log_ref'])
            if receipt['application'].get('terminal') is not True:
                raise ValueError('portable application evidence is not terminal')
        covered.update(row['job']['ac_map'].get(reference, []))
    if covered != set(proof['ac']) or set(bundle['receipts']) != set(proof['checks']):
        raise ValueError('portable proof does not cover the complete contract')
    for digest in bundle['logs']:
        get(objects, digest)
    return proof


def artifact_registry(root, feature):
    checked_path(feature)
    if '/' in feature or feature.startswith('.') or feature in ('batches', 'wave-baselines', 'tmp'):
        raise ValueError('artifact registry needs a feature owner')
    path = Path(root).resolve() / '.scratch' / feature / 'artifacts.json'
    if path.resolve() != path:
        raise ValueError('artifact registry cannot traverse links')
    return path


def _file_identity(root, relative):
    path = Path(root).resolve() / checked_path(relative)
    if path.resolve() != path or path.is_symlink() or not path.is_file():
        raise ValueError('only owned regular files without link traversal are GC candidates')
    value = path.stat()
    return {'device': value.st_dev, 'inode': value.st_ino, 'size': value.st_size,
            'mtime_ns': value.st_mtime_ns, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _registry(root, feature):
    path = artifact_registry(root, feature)
    from workflow_runtime import read_text
    try:
        value = json.loads(read_text(path, encoding='utf-8'))
    except FileNotFoundError:
        value = {'schema_version': 1, 'files': {}}
    if value.get('schema_version') != 1 or not isinstance(value.get('files'), dict):
        raise ValueError('artifact ownership registry is invalid')
    value.setdefault('claims', {})
    return path, value


def register_artifact(root, feature, record, tracked_paths=None, registry_state=None, known_paths=None):
    from workflow_runtime import transaction, write_state
    if (not isinstance(record, dict) or not record.get('owner') or not record.get('purpose')
            or record.get('lifecycle') not in ('temporary', 'asset', 'evidence', 'delivery')
            or not isinstance(record.get('references', []), list)):
        raise ValueError('artifact needs its producer, purpose, lifecycle and consumers')
    relative = checked_path(record['path'])
    allowed = '.scratch/' + feature + '/'
    managed_run = relative.startswith('.scratch/batches/') and '/run-data/' in relative
    if not relative.startswith(allowed) and not managed_run:
        raise ValueError('GC only owns declared feature or managed execution directories; move disposable probes there at creation')
    if not managed_run and any(part in ('issues', 'receipts', 'node_modules', '.venv', 'venv') for part in Path(relative).parts):
        raise ValueError('historical cards, durable proofs and dependency directories are not transient GC')
    if tracked_paths is None:
        tracked_paths = tracked_artifacts(root)
    if relative in tracked_paths:
        raise ValueError('tracked artifacts require a normal reviewed code change')
    identity = _file_identity(root, relative)
    with transaction(root):
        path, registry = registry_state or _registry(root, feature)
        known = known_paths if known_paths is not None else {}
        if known_paths is None:
            for key in registry['files']:
                _aliases(known, key)
        _aliases(known, relative)
        record = dict(record, references=sorted(set(record.get('references', [])) | set(registry['claims'].get(relative, []))))
        previous = registry['files'].get(relative)
        if previous and previous['lifecycle'] != 'temporary' and record['lifecycle'] == 'temporary':
            raise ValueError('durable artifact cannot be downgraded to disposable scratch')
        if previous and previous['owner'] != record['owner']:
            raise ValueError('artifact is owned by another execution')
        if previous and previous.get('references') and set(previous['references']) - set(record.get('references', [])):
            raise ValueError('registration cannot silently release existing consumers')
        registry['files'][relative] = {**record, 'path': relative, 'identity': identity,
                                       'released': False, 'references': record.get('references', []), 'deleted': False}
        if registry_state is None:
            write_state(root, path, encoded(registry).decode('utf-8'))
        return registry['files'][relative]


def release_artifacts(root, feature, owner, consumer=None):
    from workflow_runtime import transaction, write_state
    with transaction(root):
        path, registry = _registry(root, feature)
        for row in registry['files'].values():
            if row['owner'] != owner:
                continue
            if consumer:
                row['references'] = [ref for ref in row['references'] if ref != consumer]
            else:
                row['released'] = True
        write_state(root, path, encoded(registry).decode('utf-8'))
        return {'owner': owner, 'released': True, 'consumer': consumer}


def collect_artifacts(root, feature, apply=False):
    from workflow_runtime import atomic_write, transaction, write_state
    import workflow_batch as batch
    root = Path(root).resolve()
    with transaction(root):
        path, registry = _registry(root, feature)
        removed, retained, candidates, recovered, total = [], [], [], [], 0
        journal_path = path.with_name('gc-deletions.json')
        if journal_path.is_symlink() or journal_path.parent.resolve() != journal_path.parent:
            raise ValueError('GC journal cannot traverse a link')
        intents = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {}
        tracked_paths = tracked_artifacts(root) if registry['files'] else set()
        active_owners = set()
        ledger = root / '.scratch' / feature / 'wave-ledger.json'
        if ledger.exists():
            data = json.loads(ledger.read_text(encoding='utf-8'))
            for wave in data['waves']:
                if set(wave['dispatched']) - set(wave.get('closed', {})):
                    active_owners.add(wave.get('execution'))
        for relative, row in registry['files'].items():
            if row.get('deleted'):
                continue
            reason = None
            if relative in tracked_paths:
                reason = 'file is tracked by Git'
            elif row['lifecycle'] != 'temporary' or row.get('references'):
                reason = 'retained consumer or durable asset'
            elif not row['released'] or row['owner'] in active_owners:
                reason = 'producer has not released this file'
            elif relative.startswith('.scratch/batches/'):
                parts = relative.split('/')
                run = batch._json(batch._path(root, parts[2]) / 'runs' / (parts[4] + '.json'))
                if run['status'] != 'terminal' or not run.get('receipt_ref'):
                    reason = 'managed process or terminal evidence is unresolved'
            target = root / relative
            if reason is None:
                try:
                    if _file_identity(root, relative) != row['identity']:
                        reason = 'file identity or content changed'
                except (OSError, ValueError):
                    if (intents.get(relative) == {'identity': row['identity'], 'owner': row['owner']}
                            and not target.exists() and not target.is_symlink()):
                        if apply:
                            row['deleted'] = True
                            recovered.append(relative)
                        continue
                    reason = 'file is missing or not an owned regular file'
            if reason:
                retained.append({'path': relative, 'reason': reason})
            else:
                candidates.append(relative)
        if apply and (candidates or recovered):
            # The unlink intent must be durable even if the surrounding state transaction aborts.
            intents = {name: value for name, value in intents.items() if not registry['files'].get(name, {}).get('deleted')}
            intents.update({name: {'identity': registry['files'][name]['identity'], 'owner': registry['files'][name]['owner']} for name in candidates})
            atomic_write(journal_path, encoded(intents).decode('utf-8'))
            for relative in candidates:
                row, target = registry['files'][relative], root / relative
                try:
                    if _file_identity(root, relative) != row['identity']:
                        raise ValueError('file changed before deletion')
                    target.unlink()
                except (OSError, ValueError) as exc:
                    retained.append({'path': relative, 'reason': str(exc)})
                    continue
                row['deleted'] = True
                removed.append(relative)
                total += row['identity']['size']
                parent = target.parent
                boundary = root / '.scratch' / feature
                if boundary in parent.parents:
                    while parent != boundary:
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            write_state(root, path, encoded(registry).decode('utf-8'))
        return {'candidates': candidates, 'removed': removed, 'removed_bytes': total,
                'recovered_deletions': recovered, 'retained': retained}


def tracked_artifacts(root):
    try:
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, timeout=10)
    except FileNotFoundError:
        if (Path(root) / '.git').exists():
            raise ValueError('Git tracking evidence unavailable; retain temporary files')
        return set()
    if result.returncode and (Path(root) / '.git').exists():
        raise ValueError('Git tracking evidence failed; retain temporary files')
    return set(result.stdout.decode('utf-8').split('\0')) if result.returncode == 0 else set()
