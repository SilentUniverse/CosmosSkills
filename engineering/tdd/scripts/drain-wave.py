#!/usr/bin/env python
# Wave arithmetic + dispatch ledger for /tdd -p drain (DRAIN.md step 1-3).
# Stdlib only. The model orchestrates; this script owns the wave-state mutation
# line: compute the wave, record the dispatch intent (with wave baseline) before
# any worker starts, commit a fully reconciled wave on collect, and audit test-file
# ownership at close. Durability rule: an issue is schedulable only through this
# script; any live dispatched issue without ledger closure is a zombie (exit 3),
# even when done on disk. Reconcile it before scheduling anything.
#
#   drain-wave.py next <repo-root> [<feat>]     propose the next wave (read-only)
#   drain-wave.py dispatch <repo-root> <slug>...                record intent + baseline
#   drain-wave.py collect <repo-root> <slug>=<result>[,<slug>=<result>...]
#                         result: green|red|blocked|aborted|conflict@evidence.json
#   drain-wave.py audit <repo-root> [<feat>]    test files no issue claims
#   drain-wave.py dismiss-conflict <repo-root> <feat> <slug> <evidence.json>
#   drain-wave.py selftest                       gate the gate: parse substrate +
#                                               refusal branches (tempdir fixtures)
#
# Exit: 0 ok, 1 violation, 2 usage, 3 zombies (recovery first), 4 nothing ready,
# 5 shared preflight receipt must be prepared before dispatch, 6 receipt conflict
# requires /spec realignment.
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

ENGINEERING_ROOT = Path(__file__).resolve().parents[2]
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from workflow_contract import issue_contract_digest, validate_v3_completion

RESULTS = ("green", "red", "blocked", "conflict", "aborted")
MAX_IN_FLIGHT = 4
SKIP_DIRS = {
    ".git", "node_modules", ".scratch", ".venv", "venv", "target",
    "dist", "build", "out", ".next", "__pycache__", "coverage", "lib",
}
TEST_FILE = re.compile(
    r"(\.spec\.[a-z]+$)|(\.test\.[a-z]+$)|(^test_[a-z0-9_]+\.[a-z]+$)|(_test\.[a-z]+$)"
)
FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
FLOW_LIST = re.compile(r"^\[\s*(.*)\s*\]$")
BLOCK_ITEM = re.compile(r"^\s+-\s+(.+)$")
DONE_HEAD = re.compile(r"^#{2,3}\s*\u5b8c\u6210(?:[^\w]|$)")
_PREFLIGHT_API = None


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class PreflightHelperMissing(RuntimeError):
    """Install defect: the sibling script is absent; no receipt can be read or written."""


def preflight_api():
    """Load the sibling helper without duplicating its receipt semantics."""
    global _PREFLIGHT_API
    if _PREFLIGHT_API is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preflight-receipt.py")
        if not os.path.isfile(path):
            raise PreflightHelperMissing(
                "preflight-receipt.py is missing next to drain-wave.py (%s); "
                "reinstall the tdd skill so both scripts arrive together" % path
            )
        spec = importlib.util.spec_from_file_location("cosmos_preflight_receipt", path)
        if spec is None or spec.loader is None:
            raise ValueError("cannot load preflight-receipt.py at %s" % path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PREFLIGHT_API = module
    return _PREFLIGHT_API


def read_lines(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig", errors="replace").splitlines()


def get_frontmatter(path):
    """Scalars -> str; flow/block lists -> list[str]. None if absent."""
    lines = read_lines(path)
    if len(lines) < 2 or lines[0].strip() != "---":
        return None
    fm = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        m = FM_KEY.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val == "":
                items = []
                j = i + 1
                while j < len(lines):
                    im = BLOCK_ITEM.match(lines[j])
                    if not im:
                        break
                    items.append(im.group(1).strip())
                    j += 1
                fm[key] = items if items else ""
                if items:
                    i = j - 1
            else:
                fm_list = FLOW_LIST.match(val)
                if fm_list:
                    inner = fm_list.group(1).strip()
                    fm[key] = (
                        [p.strip().strip("\"'") for p in inner.split(",")]
                        if inner
                        else []
                    )
                else:
                    fm[key] = val.strip("\"'")
        i += 1
    if i >= len(lines):
        return None
    return fm


def as_list(val):
    if val in (None, ""):
        return []
    return val if isinstance(val, list) else [val]


def norm_path(p):
    return p.replace("\\", "/").strip("/").lower()


def path_overlap(a, b):
    """True when two declared paths share a component prefix (dir contains file/subdir)."""
    ca = norm_path(a).split("/")
    cb = norm_path(b).split("/")
    n = min(len(ca), len(cb))
    return ca[:n] == cb[:n]


def has_done_record(path):
    try:
        return any(DONE_HEAD.match(s) for s in read_lines(path))
    except OSError:
        return False


def feature_dirs(root, feat):
    scratch = os.path.join(root, ".scratch")
    if feat:
        return [os.path.join(scratch, feat)] if os.path.isdir(os.path.join(scratch, feat)) else []
    if not os.path.isdir(scratch):
        return []
    return sorted(
        os.path.join(scratch, n)
        for n in os.listdir(scratch)
        if os.path.isdir(os.path.join(scratch, n))
    )


def load_issues(root, feat):
    """slug -> (feature, path, fm). Live issues only (never archive/)."""
    issues = {}
    for fd in feature_dirs(root, feat):
        i_dir = os.path.join(fd, "issues")
        if not os.path.isdir(i_dir):
            continue
        for n in sorted(os.listdir(i_dir)):
            p = os.path.join(i_dir, n)
            if not n.endswith(".md") or not os.path.isfile(p):
                continue
            slug = os.path.splitext(n)[0]
            if slug in issues and issues[slug][0] != os.path.basename(fd):
                print(
                    "drain-wave: duplicate slug '%s' in features '%s' and '%s' -"
                    " disambiguate by invoking with a single <feat>"
                    % (slug, issues[slug][0], os.path.basename(fd)),
                    file=sys.stderr,
                )
                return None
            fm = get_frontmatter(p)
            if fm is None:
                print("drain-wave: %s has no YAML frontmatter" % p, file=sys.stderr)
                return None
            if fm.get("status") == "done" and str(fm.get("contract_version", "")) == "3":
                try:
                    validate_v3_completion(Path(root), Path(p))
                except (OSError, UnicodeError, ValueError) as exc:
                    print(
                        "drain-wave: %s has invalid completion evidence: %s" % (p, exc),
                        file=sys.stderr,
                    )
                    return None
            issues[slug] = (os.path.basename(fd), p, fm)
    return issues


def load_archived_done(root, feat):
    """Return archived done slugs used only to satisfy dependency barriers."""
    done = set()
    owners = {}
    for fd in feature_dirs(root, feat):
        arch_dir = os.path.join(fd, "issues", "archive")
        if not os.path.isdir(arch_dir):
            continue
        feature = os.path.basename(fd)
        for name in sorted(os.listdir(arch_dir)):
            path = os.path.join(arch_dir, name)
            if not name.endswith(".md") or not os.path.isfile(path):
                continue
            slug = os.path.splitext(name)[0]
            fm = get_frontmatter(path)
            if fm is None or fm.get("status") != "done":
                print(
                    "drain-wave: archived issue '%s' must have status: done" % path,
                    file=sys.stderr,
                )
                return None
            if str(fm.get("contract_version", "")) == "3":
                try:
                    validate_v3_completion(Path(root), Path(path))
                except (OSError, UnicodeError, ValueError) as exc:
                    print(
                        "drain-wave: %s has invalid completion evidence: %s" % (path, exc),
                        file=sys.stderr,
                    )
                    return None
            if slug in owners and owners[slug] != feature:
                print(
                    "drain-wave: duplicate archived slug '%s' in features '%s' and '%s'"
                    % (slug, owners[slug], feature),
                    file=sys.stderr,
                )
                return None
            owners[slug] = feature
            done.add(slug)
    return done


def ledger_path(root, feat):
    return os.path.join(root, ".scratch", feat, "wave-ledger.json")


def load_ledger(root, feat):
    p = ledger_path(root, feat)
    if not os.path.isfile(p):
        return {"waves": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        print("drain-wave: %s unreadable - fix or delete it before continuing" % p, file=sys.stderr)
        sys.exit(1)
    data.setdefault("waves", [])
    baselines = data.get("baselines", {})
    if not isinstance(baselines, dict):
        baselines = {}
    for wave in data["waves"]:
        if "baseline" not in wave:
            continue
        snapshot = str(wave.pop("baseline"))
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        baselines.setdefault(digest, snapshot)
        wave["baseline_sha256"] = digest
    if baselines:
        data["baselines"] = baselines
    else:
        data.pop("baselines", None)
    return data


def save_ledger(root, feat, data):
    p = ledger_path(root, feat)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, p)


def contract_sha256(path):
    """Hash aligned issue content; comments/evidence do not count as realignment."""
    with open(path, "r", encoding="utf-8-sig") as stream:
        text = stream.read()
    marker = re.search(r"(?m)^## Comments\s*$", text)
    contract = text[:marker.start()] if marker else text
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def dispatch_contract_sha256(path):
    with open(path, "r", encoding="utf-8-sig") as stream:
        return issue_contract_digest(stream.read())


def load_conflict_evidence(root, feat, slug, issue_path, reference):
    """Validate one durable conflict report and return its ledger pointer."""
    if not reference:
        raise ValueError("conflict requires conflict evidence: <slug>=conflict@<receipt.json>")
    base = Path(root).resolve()
    path = (base / reference).resolve()
    receipts = (base / ".scratch" / feat / "receipts").resolve()
    try:
        path.relative_to(receipts)
    except ValueError as exc:
        raise ValueError("conflict evidence must stay under .scratch/%s/receipts" % feat) from exc
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("conflict evidence is not valid JSON: %s" % exc) from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
    ):
        raise ValueError("conflict evidence needs schema_version 1")
    expected = {
        "feature": feat,
        "slug": slug,
        "contract_sha256": contract_sha256(issue_path),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError("conflict evidence %s does not match %s" % (key, value))
    for key in ("command", "observed", "contract_clause", "evidence"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("conflict evidence requires non-empty %s" % key)
    return {
        "path": path.relative_to(base).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def recorded_conflict_digest(root, feat, slug, wave):
    """Read the contract digest from its evidence owner; accept old expanded ledgers."""
    reference = wave.get("conflict_evidence", {}).get(slug)
    if reference is None:
        return wave.get("conflict_contract_sha256", {}).get(slug)
    if not isinstance(reference, dict):
        return None
    try:
        base = Path(root).resolve()
        path = (base / str(reference.get("path", ""))).resolve()
        path.relative_to((base / ".scratch" / feat / "receipts").resolve())
        raw = path.read_bytes()
        if reference.get("sha256") != hashlib.sha256(raw).hexdigest():
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or payload.get("feature") != feat
        or payload.get("slug") != slug
    ):
        return None
    digest = payload.get("contract_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    legacy = wave.get("conflict_contract_sha256", {}).get(slug)
    return digest if legacy in (None, digest) else None


def active_conflicts(root):
    """Closed conflict results whose issue has not changed since collection."""
    active = {}
    scratch = os.path.join(root, ".scratch")
    features = []
    if os.path.isdir(scratch):
        features = [
            name for name in sorted(os.listdir(scratch))
            if os.path.isfile(os.path.join(scratch, name, "wave-ledger.json"))
        ]
    for feat in features:
        data = load_ledger(root, feat)
        for index, wave in enumerate(data["waves"]):
            for slug, result in wave.get("closed", {}).items():
                if result != "conflict":
                    continue
                recorded = recorded_conflict_digest(root, feat, slug, wave)
                realigned_retry = recorded and any(
                    slug in later.get("dispatched", [])
                    and isinstance(later.get("contracts"), dict)
                    and isinstance(later["contracts"].get(slug), str)
                    and later["contracts"][slug] != recorded
                    for later in data["waves"][index + 1:]
                )
                if realigned_retry:
                    continue
                path = os.path.join(root, ".scratch", feat, "issues", slug + ".md")
                if not os.path.isfile(path):
                    active[(feat, slug)] = wave.get("wave", "?")
                    continue
                fm = get_frontmatter(path)
                if (
                    fm is None
                    or fm.get("status") != "ready"
                    or not recorded
                    or contract_sha256(path) == recorded
                ):
                    active[(feat, slug)] = wave.get("wave", "?")
    return [(feat, wave, slug) for (feat, slug), wave in sorted(active.items())]


def report_conflicts(conflicts):
    print("drain-wave: receipt conflict requires /spec realignment:")
    for feat, wave, slug in conflicts:
        print("  %s (wave %s, ledger .scratch/%s/wave-ledger.json)" % (slug, wave, feat))
    print("the recorded issue content is unchanged; no next wave or explicit dispatch is allowed")
    print("a disproved report may use dismiss-conflict with contract-bound review evidence (DRAIN.md)")


def cmd_dismiss_conflict(root, feat, slug, evidence):
    """Correct one closed false-positive report without changing the issue contract."""
    try:
        if not feat or feat in (".", "..") or "/" in feat or "\\" in feat:
            raise ValueError("feature must be a directory name")
        base = Path(root).resolve()
        evidence_path = (base / evidence).resolve()
        evidence_path.relative_to(base / ".scratch" / feat / "receipts")
        raw = evidence_path.read_bytes()
        review = json.loads(raw.decode("utf-8"))
        if not isinstance(review, dict):
            raise ValueError("review must be a JSON object")
        if review.get("feature") != feat or review.get("slug") != slug:
            raise ValueError("review must identify this feature and issue")
        if review.get("classification") not in ("noise", "artifact_defect"):
            raise ValueError("only a disproved conflict may be dismissed")
        if any(not isinstance(review.get(key), str) or not review[key].strip()
               for key in ("reason", "evidence")):
            raise ValueError("review requires a reason and observed evidence")
        if type(review.get("wave")) is not int:
            raise ValueError("review must identify its wave number")
        issues = load_issues(root, feat)
        if not issues or slug not in issues or issues[slug][2].get("status") != "ready":
            raise ValueError("dismissal requires an existing ready issue")
        digest = contract_sha256(issues[slug][1])
        if review.get("contract_sha256") != digest:
            raise ValueError("review does not match the current issue contract")
        data = load_ledger(root, feat)
        if open_waves(data):
            raise ValueError("collect unfinished waves before dismissing a conflict")
        matches = [
            w for w in data["waves"]
            if w.get("wave") == review["wave"]
            and w.get("closed", {}).get(slug) == "conflict"
            and recorded_conflict_digest(root, feat, slug, w) == digest
        ]
        if len(matches) != 1:
            raise ValueError("review must match one recorded unchanged conflict")
    except (OSError, ValueError) as exc:
        print("drain-wave: conflict dismissal refused: %s" % exc, file=sys.stderr)
        return 1
    target = matches[0]
    target.setdefault("conflict_dismissals", {})[slug] = {
        "path": evidence_path.relative_to(base).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "dismissed_at": now_iso(),
    }
    target["closed"][slug] = "red"
    save_ledger(root, feat, data)
    print("drain-wave: dismissed false conflict for %s; issue remains ready" % slug)
    return 0


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def filesystem_baseline(root, issues, slugs):
    """Content identity for declared paths when Git is unavailable or not configured."""
    base = Path(root).resolve()
    declared_paths = sorted(
        {
            str(value).replace("\\", "/")
            for slug in slugs
            for value in issues_touch(issues, slug) + issues_tests(issues, slug)
            if str(value).strip()
        }
    )
    if not declared_paths:
        # An undeclared card is serialized, but still needs a useful crash/ownership baseline.
        declared_paths = ["."]
    files = {}
    missing = []
    for declared_path in declared_paths:
        candidate = (base / declared_path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError("declared baseline path escapes repo: %s" % declared_path) from exc
        if candidate.is_file():
            files[candidate.relative_to(base).as_posix()] = file_sha256(candidate)
        elif candidate.is_dir():
            for parent, dirs, names in os.walk(candidate):
                dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
                for name in sorted(names):
                    path = Path(parent) / name
                    if path.is_file():
                        files[path.relative_to(base).as_posix()] = file_sha256(path)
        else:
            missing.append(declared_path)
    return {
        "schema_version": 2,
        "kind": "filesystem",
        "files": files,
        "missing": missing,
    }


def workspace_baseline(root, issues, slugs):
    """Capture compact content identity for the dispatch workspace."""

    def run_git(arguments):
        return subprocess.run(
            ["git"] + arguments,
            cwd=root,
            capture_output=True,
        )

    try:
        inside = run_git(["rev-parse", "--is-inside-work-tree"])
    except OSError:
        return filesystem_baseline(root, issues, slugs)
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        return filesystem_baseline(root, issues, slugs)
    head = run_git(["rev-parse", "--verify", "HEAD"])
    head_value = head.stdout.decode("ascii", errors="replace").strip() if head.returncode == 0 else "unborn"
    pathspec = [".", ":(exclude).scratch", ":(exclude).scratch/**"]
    index_args = ["diff", "--cached", "--binary", "--no-ext-diff"]
    if head_value != "unborn":
        index_args.append("HEAD")
    index_args.extend(["--"] + pathspec)
    index_diff = run_git(index_args)
    worktree_diff = run_git(
        ["diff", "--binary", "--no-ext-diff", "--"] + pathspec
    )
    status = run_git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--"] + pathspec
    )
    failed = [
        (name, result)
        for name, result in (
            ("index diff", index_diff),
            ("worktree diff", worktree_diff),
            ("status", status),
        )
        if result.returncode != 0
    ]
    if failed:
        name, result = failed[0]
        message = result.stderr.decode("utf-8", errors="replace").strip()[:200]
        raise ValueError("git %s failed: %s" % (name, message))
    dirty_names = set()
    records = status.stdout.split(b"\0")
    index = 0
    while index < len(records) and records[index]:
        record = records[index]
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError("git status returned an invalid porcelain record")
        state = record[:2]
        dirty_names.add(record[3:])
        if b"R" in state or b"C" in state:
            index += 1
            if index >= len(records) or not records[index]:
                raise ValueError("git status returned an incomplete rename/copy record")
            dirty_names.add(records[index])
        index += 1

    dirty_paths = {}
    base = Path(root).resolve()
    for encoded in sorted(dirty_names):
        value = os.fsdecode(encoded)
        relative_path = Path(value)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("git reported a dirty path outside repo: %s" % value)
        relative = relative_path.as_posix()
        path = base / relative_path
        if path.is_symlink():
            target = os.readlink(path)
            dirty_paths[relative] = "symlink:" + hashlib.sha256(
                os.fsencode(target)
            ).hexdigest()
        elif path.is_file():
            dirty_paths[relative] = file_sha256(path)
        elif path.exists():
            dirty_paths[relative] = "directory"
        else:
            dirty_paths[relative] = "missing"
    return {
        "schema_version": 2,
        "kind": "git",
        "head": head_value,
        "index_diff_sha256": hashlib.sha256(index_diff.stdout).hexdigest(),
        "worktree_diff_sha256": hashlib.sha256(worktree_diff.stdout).hexdigest(),
        "dirty_paths": dirty_paths,
    }


def store_baseline(root, baseline):
    raw = (
        json.dumps(baseline, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    directory = Path(root) / ".scratch" / "wave-baselines"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + ".json")
    if path.is_file():
        if path.read_bytes() != raw:
            raise ValueError("baseline digest collision at %s" % path)
        return digest
    temporary = path.with_name(path.name + ".tmp.%d" % os.getpid())
    temporary.write_bytes(raw)
    os.replace(temporary, path)
    return digest


def issues_touch(issues, slug):
    return as_list(issues[slug][2].get("touches"))


def issues_tests(issues, slug):
    return as_list(issues[slug][2].get("test_paths"))


def issues_resources(issues, slug):
    return as_list(issues[slug][2].get("exclusive_resources"))


def declared(fm):
    return bool(as_list(fm.get("touches"))) and bool(as_list(fm.get("test_paths")))


def collides(issues, a, b):
    for x in issues_touch(issues, a):
        for y in issues_touch(issues, b):
            if path_overlap(x, y):
                return True
    for x in issues_tests(issues, a):
        for y in issues_tests(issues, b):
            if path_overlap(x, y):
                return True
    return bool(
        {str(value).strip().casefold() for value in issues_resources(issues, a) if str(value).strip()}
        & {str(value).strip().casefold() for value in issues_resources(issues, b) if str(value).strip()}
    )


def open_waves(data):
    return [w for w in data["waves"] if set(w["dispatched"]) - set(w.get("closed", {}))]


def find_zombies(root):
    """Return every dispatched assignment still awaiting the explicit wave commit."""
    zombies = []
    scratch = os.path.join(root, ".scratch")
    feats = []
    if os.path.isdir(scratch):
        feats = [
            n for n in sorted(os.listdir(scratch))
            if os.path.isfile(os.path.join(scratch, n, "wave-ledger.json"))
        ]
    for feat in feats:
        data = load_ledger(root, feat)
        for w in open_waves(data):
            for slug in set(w["dispatched"]) - set(w.get("closed", {})):
                zombies.append((feat, w["wave"], slug))
    return zombies


def chain_depths(issues):
    """Slug -> longest chain of ready issues transitively blocked by it."""
    ready = {s for s, (_, _, fm) in issues.items() if fm.get("status") == "ready"}
    dependents = {s: [] for s in ready}
    blockers = {s: [] for s in ready}
    for dependent in ready:
        for blocker in set(as_list(issues[dependent][2].get("blocked_by"))):
            if blocker in ready:
                dependents[blocker].append(dependent)
                blockers[dependent].append(blocker)

    # Reverse topological DP avoids Python's recursion limit. A cyclic region is
    # not propagated upstream; verify-artifacts reports the cycle itself.
    remaining = {s: len(dependents[s]) for s in ready}
    depth = {s: 1 for s in ready}
    leaves = [s for s in ready if remaining[s] == 0]
    while leaves:
        dependent = leaves.pop()
        for blocker in blockers[dependent]:
            depth[blocker] = max(depth[blocker], 1 + depth[dependent])
            remaining[blocker] -= 1
            if remaining[blocker] == 0:
                leaves.append(blocker)
    return depth


def plan_waves(issues, archived_done):
    done = {
        s for s, (_, _, fm) in issues.items() if fm.get("status") == "done"
    } | archived_done
    ready = {s for s, (_, _, fm) in issues.items() if fm.get("status") == "ready"}
    blocked = []
    eligible = []
    for s in sorted(ready):
        deps = [d for d in as_list(issues[s][2].get("blocked_by")) if d]
        missing = [d for d in deps if d not in done]
        if missing:
            blocked.append((s, missing))
        else:
            eligible.append(s)
    # With no duration estimates, prefer the issue unblocking the longest ready
    # dependency chain so capacity and collision deferrals unlock work early.
    depth = chain_depths(issues)
    eligible.sort(key=lambda s: (-depth.get(s, 1), s))
    undeclared = [s for s in eligible if not declared(issues[s][2])]
    packable = [s for s in eligible if s not in undeclared]
    wave = []
    for s in packable:
        if len(wave) >= MAX_IN_FLIGHT:
            break  # dispatch refuses >MAX_IN_FLIGHT; propose at most that
        if not any(collides(issues, s, w) for w in wave):
            wave.append(s)
    later = [s for s in packable if s not in wave]
    solo_now = None
    if not wave and undeclared:
        # no packable wave available - schedule one undeclared card alone (one per wave)
        solo_now = undeclared[0]
        undeclared = [s for s in undeclared if s != solo_now]
    return {
        "done": done,
        "ready": ready,
        "blocked": blocked,
        "wave": wave,
        "later": later,
        "undeclared": undeclared,
        "solo_now": solo_now,
    }


def cmd_next(root, feat):
    issues = load_issues(root, feat)
    if issues is None:
        return 1
    archived_done = load_archived_done(root, feat)
    if archived_done is None:
        return 1
    zombies = find_zombies(root)
    if zombies:
        print("drain-wave: %d zombie(s) - dispatched but not collected:" % len(zombies))
        for f, w, slug in zombies:
            print("  %s (wave %d, ledger .scratch/%s/wave-ledger.json)" % (slug, w, f))
        print("recovery: reconcile valid done evidence, finish the slice, or revert this issue's")
        print("edits to the wave baseline and leave it ready - then collect the whole wave. No new wave")
        print("until every zombie is closed (EDGE-CASES.md).")
        return 3
    conflicts = active_conflicts(root)
    if conflicts:
        report_conflicts(conflicts)
        return 6
    if not issues:
        print("drain-wave: no issues found under .scratch/%s" % (feat or "*/issues"))
        return 4
    plan = plan_waves(issues, archived_done)
    if not plan["ready"]:
        print("drain-wave: nothing ready (%d done) - batch complete" % len(plan["done"]))
        return 4
    nf = feat if feat else "all features"
    print("drain-wave: %s - %d ready, %d done" % (nf, len(plan["ready"]), len(plan["done"])))
    if plan["solo_now"]:
        print("wave: %s (solo - undeclared, runs alone)" % plan["solo_now"])
    else:
        print("wave: %s" % (" ".join(plan["wave"]) if plan["wave"] else "(none this pass)"))
    if plan["later"]:
        print("next waves (serialized): %s" % " ".join(plan["later"]))
    if plan["undeclared"]:
        print(
            "solo (missing touches/test_paths - one per wave): %s"
            % " ".join(sorted(plan["undeclared"]))
        )
    for s, missing in plan["blocked"]:
        print("deferred: %s blocked by %s" % (s, ", ".join(missing)))
    return 0


def cmd_step(root, feat, parallel=False):
    issues = load_issues(root, feat)
    if issues is None:
        return 1
    archived_done = load_archived_done(root, feat)
    if archived_done is None:
        return 1
    zombies = find_zombies(root)
    if zombies:
        print("action: finish-or-revert, reconcile, then collect the whole wave")
        for f, w, slug in zombies:
            print("zombie: %s (wave %d, ledger .scratch/%s/wave-ledger.json)" % (slug, w, f))
        print(
            "run: drain-wave.py collect <repo-root> "
            "<slug>=<green|red|blocked|aborted|conflict@evidence.json>[,...]"
            " - include every outstanding slug; no new wave until reconciliation (EDGE-CASES.md)"
        )
        return 3
    conflicts = active_conflicts(root)
    if conflicts:
        report_conflicts(conflicts)
        return 6
    if not issues:
        print("action: none - no issues found under .scratch/%s" % (feat or "*/issues"))
        return 4
    plan = plan_waves(issues, archived_done)
    if not plan["ready"]:
        print("action: close - nothing ready (%d done)" % len(plan["done"]))
        print(
            "run: drain-wave.py audit <repo-root> %s; close per FULL-SUITE.md via"
            " test-supervisor.py; then workflow-state.py gc <repo-root> <feat> --apply"
            % (feat or "<feat>")
        )
        return 4
    if plan["solo_now"]:
        wave = [plan["solo_now"]]
    else:
        wave = plan["wave"] if parallel else plan["wave"][:1]
    if wave:
        print("action: dispatch %s" % " ".join(wave))
        print("run: drain-wave.py dispatch <repo-root> %s" % " ".join(wave))
        return 0
    print("action: blocked - every ready issue is blocked or deferred")
    print("run: drain-wave.py next <repo-root> %s" % (feat or ""))
    return 1


def dispatch_receipt_hits(root, issues, slugs, ledgers):
    """Gate duplicate P# tuples and persist each key once with its issue consumers."""
    api = preflight_api()
    root_path = Path(root)
    current_rows = {}
    rows = []
    for feature in sorted({issues[slug][0] for slug in slugs}):
        rows.extend(api.issue_preflight_rows(root_path, feature))
    for row in rows:
        current_rows.setdefault(row["slug"], {})[row["key"]] = row
    hits = {slug: [] for slug in slugs}

    grouped_rows = {}
    for row in rows:
        grouped_rows.setdefault((row["feature"], row["key"]), []).append(row)
    relevant_keys = {
        identity
        for identity, group in grouped_rows.items()
        if len({row["issue"] for row in group}) >= 2
        and any(row["slug"] in slugs for row in group)
    }
    plan = api.duplicate_plan(
        root_path,
        rows=[
            row for row in rows
            if (row["feature"], row["key"]) in relevant_keys
        ],
    )
    planned = {
        (duplicate["feature"], duplicate["key"]): duplicate
        for duplicate in plan["duplicates"]
    }

    # Tuple fields belong to the card/profile and preflight cache. Normalize both
    # legacy issue->expanded/key maps and current key->consumers maps from live cards.
    for data in ledgers.values():
        consumers = {}
        stored_consumers = data.pop("preflight_consumers", {})
        if not isinstance(stored_consumers, dict):
            stored_consumers = {}
        for key, assigned_slugs in stored_consumers.items():
            if not isinstance(assigned_slugs, list):
                continue
            for slug in assigned_slugs:
                if isinstance(slug, str) and key in current_rows.get(slug, {}):
                    consumers.setdefault(key, set()).add(slug)
        legacy_assignments = data.pop("preflight_assignments", {})
        if not isinstance(legacy_assignments, dict):
            legacy_assignments = {}
        for slug, assignments in legacy_assignments.items():
            if not isinstance(assignments, list):
                continue
            for assignment in assignments:
                key = (
                    assignment
                    if isinstance(assignment, str)
                    else assignment.get("key") if isinstance(assignment, dict) else None
                )
                if key in current_rows.get(slug, {}):
                    consumers.setdefault(key, set()).add(slug)
        if consumers:
            data["preflight_consumers"] = {
                key: sorted(assigned_slugs)
                for key, assigned_slugs in sorted(consumers.items())
            }

    # A previous wave can assign the same hit to an issue serialized into a later wave.
    # Accept it only while the issue still names that exact tuple and the receipt checks.
    for slug in slugs:
        feat = issues[slug][0]
        consumers = ledgers[feat].get("preflight_consumers", {})
        for key, assigned_slugs in consumers.items():
            if slug not in assigned_slugs:
                continue
            row = current_rows.get(slug, {}).get(key)
            if row is None:
                continue
            duplicate = planned.get((feat, key))
            valid = duplicate is not None and duplicate["status"] == "hit"
            if duplicate is None:
                valid = api.check(
                    root_path / row["receipt"],
                    cwd=row["cwd"],
                    action=row["action"],
                    fingerprint=row["fingerprint"],
                    verifier_digest=row.get("verifier_digest", ""),
                    readiness_digest=row.get("readiness_digest", ""),
                ) is not None
            if valid:
                hits[slug].append(key)

    relevant = plan["duplicates"]
    misses = [duplicate for duplicate in relevant if duplicate["status"] != "hit"]
    if misses:
        return None, misses

    for duplicate in relevant:
        feat = duplicate["feature"]
        consumers = ledgers[feat].setdefault("preflight_consumers", {})
        assigned_slugs = set(consumers.get(duplicate["key"], []))
        for issue_path in duplicate["issues"]:
            slug = Path(issue_path).stem
            assigned_slugs.add(slug)
            if slug in hits:
                hits[slug].append(duplicate["key"])
        consumers[duplicate["key"]] = sorted(assigned_slugs)
    return {slug: sorted(set(keys)) for slug, keys in hits.items() if keys}, []


def cmd_dispatch(root, slugs):
    issues = load_issues(root, None)
    if issues is None:
        return 1
    archived_done = load_archived_done(root, None)
    if archived_done is None:
        return 1
    if not slugs:
        print("drain-wave: dispatch needs at least one slug", file=sys.stderr)
        return 2
    duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if duplicates:
        print(
            "drain-wave: duplicate dispatch slug(s): %s" % ", ".join(duplicates),
            file=sys.stderr,
        )
        return 1
    if len(slugs) > MAX_IN_FLIGHT:
        print(
            "drain-wave: %d issues > cap %d - dispatch in batches of <=%d, each landing first"
            % (len(slugs), MAX_IN_FLIGHT, MAX_IN_FLIGHT),
            file=sys.stderr,
        )
        return 1
    done = {
        s for s, (_, _, fm) in issues.items() if fm.get("status") == "done"
    } | archived_done
    for s in slugs:
        if s not in issues:
            print("drain-wave: unknown slug '%s'" % s, file=sys.stderr)
            return 1
        fm = issues[s][2]
        if fm.get("status") != "ready":
            print("drain-wave: %s is '%s', not ready" % (s, fm.get("status")), file=sys.stderr)
            return 1
        missing = [d for d in as_list(fm.get("blocked_by")) if d and d not in done]
        if missing:
            print(
                "drain-wave: barrier violation - %s blocked by unfinished %s"
                % (s, ", ".join(missing)),
                file=sys.stderr,
            )
            return 1
    undeclared = [s for s in slugs if not declared(issues[s][2])]
    if len(slugs) > 1 and undeclared:
        print(
            "drain-wave: explicit multi-card dispatch requires touches and test_paths; "
            "run undeclared card(s) alone: %s" % ", ".join(sorted(undeclared)),
            file=sys.stderr,
        )
        return 1
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if collides(issues, a, b):
                print(
                    "drain-wave: %s and %s declare overlapping touches/test_paths/exclusive_resources -"
                    " serialize into successive waves" % (a, b),
                    file=sys.stderr,
                )
                return 1
    zombies = find_zombies(root)
    if zombies:
        print(
            "drain-wave: open wave with unresolved issue(s) - reconcile and collect it first;"
            " if the run crashed, `next` prints the recovery contract",
            file=sys.stderr,
        )
        return 3
    conflicts = active_conflicts(root)
    if conflicts:
        report_conflicts(conflicts)
        return 6
    scratch = os.path.join(root, ".scratch")
    if os.path.isdir(scratch):
        # global wave barrier: one open wave at a time, across features
        for n in sorted(os.listdir(scratch)):
            if os.path.isfile(os.path.join(scratch, n, "wave-ledger.json")):
                if open_waves(load_ledger(root, n)):
                    print(
                        "drain-wave: feature '%s' still has an open wave - reconcile and collect it first" % n,
                        file=sys.stderr,
                    )
                    return 1
    by_feat = {}
    for s in slugs:
        by_feat.setdefault(issues[s][0], []).append(s)
    ledgers = {}
    for feat in by_feat:
        ledgers[feat] = load_ledger(root, feat)
    try:
        receipt_hits, misses = dispatch_receipt_hits(root, issues, slugs, ledgers)
    except PreflightHelperMissing as exc:
        print("drain-wave: preflight helper unusable: %s" % exc, file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        # Corrupt/unreadable receipt data: delete it and re-record, not a reinstall.
        print("drain-wave: preflight receipt is invalid: %s" % exc, file=sys.stderr)
        return 1
    if misses:
        print(
            "drain-wave: shared preflight must be replayed once before this wave",
            file=sys.stderr,
        )
        print(
            "preflight-required: %s"
            % json.dumps(
                {"duplicates": misses},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        print(
            "run each action through test-supervisor.py with scope=preflight, then use "
            "preflight-receipt.py record --execution-receipt and retry dispatch",
            file=sys.stderr,
        )
        return 5
    try:
        baseline_sha256 = store_baseline(root, workspace_baseline(root, issues, slugs))
    except (OSError, ValueError) as exc:
        print("drain-wave: cannot capture reliable wave baseline: %s" % exc, file=sys.stderr)
        return 1
    for feat, group in sorted(by_feat.items()):
        data = ledgers[feat]
        num = max((w["wave"] for w in data["waves"]), default=0) + 1
        data["waves"].append(
            {
                "wave": num,
                "at": now_iso(),
                "dispatched": sorted(group),
                "baseline_sha256": baseline_sha256,
                "contracts": {
                    slug: dispatch_contract_sha256(issues[slug][1])
                    for slug in sorted(group)
                },
                "closed": {},
            }
        )
        save_ledger(root, feat, data)
        print("drain-wave: wave %d dispatched (%s) -> .scratch/%s/wave-ledger.json" % (num, ", ".join(sorted(group)), feat))
    if receipt_hits:
        briefs = {}
        for slug, keys in sorted(receipt_hits.items()):
            for key in keys:
                briefs.setdefault("receipt-hit:%s" % key, []).append(slug)
        print(
            "briefs: %s"
            % json.dumps(briefs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
    print("baseline recorded; execution may start")
    return 0


def cmd_collect(root, pairs):
    issues = load_issues(root, None)
    if issues is None:
        return 1
    plan = []  # (feat, slug, result, conflict evidence); validate, then one write pass
    seen = set()
    for pair in pairs:
        if "=" not in pair:
            print("drain-wave: bad pair '%s' (want slug=result)" % pair, file=sys.stderr)
            return 2
        slug, reported = pair.split("=", 1)
        if slug in seen:
            print("drain-wave: duplicate collect slug '%s'" % slug, file=sys.stderr)
            return 1
        seen.add(slug)
        conflict_reference = ""
        if reported.startswith("conflict@"):
            result = "conflict"
            conflict_reference = reported[len("conflict@"):]
        else:
            result = reported
        if result not in RESULTS:
            print("drain-wave: result '%s' not in %s" % (result, "|".join(RESULTS)), file=sys.stderr)
            return 2
        if slug not in issues:
            print("drain-wave: unknown slug '%s'" % slug, file=sys.stderr)
            return 1
        if issues[slug][2].get("status") == "done" and result != "green":
            print(
                "drain-wave: %s is done on disk but reported '%s' - reconcile before collect"
                % (slug, result),
                file=sys.stderr,
            )
            return 1
        if result == "green" and issues[slug][2].get("status") != "done":
            print(
                "drain-wave: %s reported green but is '%s' on disk - set the completion"
                " record and status: done before collect"
                % (slug, issues[slug][2].get("status")),
                file=sys.stderr,
            )
            return 1
        if result == "green" and str(issues[slug][2].get("contract_version", "")) == "3":
            try:
                validate_v3_completion(Path(root), Path(issues[slug][1]))
            except (OSError, UnicodeError, ValueError) as exc:
                print(
                    "drain-wave: %s has invalid completion evidence: %s" % (slug, exc),
                    file=sys.stderr,
                )
                return 1
        conflict_evidence = None
        if result == "conflict":
            try:
                conflict_evidence = load_conflict_evidence(
                    root,
                    issues[slug][0],
                    slug,
                    issues[slug][1],
                    conflict_reference,
                )
            except (OSError, ValueError) as exc:
                print("drain-wave: %s" % exc, file=sys.stderr)
                return 1
        plan.append((issues[slug][0], slug, result, conflict_evidence))
    ledgers = {}
    hits = {}
    replayed = set()
    for feat, slug, result, _ in plan:
        data = ledgers.setdefault(feat, load_ledger(root, feat))
        hit = None
        for w in reversed(open_waves(data)):
            if slug in w["dispatched"]:
                hit = w
                break
        if hit is None:
            if any(slug in w.get("closed", {}) for w in data["waves"]):
                # A prior collect run recorded this slug and closed its wave before
                # dying; re-running the same reconciliation must not refuse on it.
                replayed.add(slug)
                continue
            print(
                "drain-wave: %s has no open dispatch in .scratch/%s/wave-ledger.json" % (slug, feat),
                file=sys.stderr,
            )
            return 1
        if slug in hit.get("closed", {}):
            print("drain-wave: %s was already collected in its open wave" % slug, file=sys.stderr)
            return 1
        hits[slug] = hit
    if replayed:
        plan = [entry for entry in plan if entry[1] not in replayed]
    outstanding = set()
    scratch = os.path.join(root, ".scratch")
    if os.path.isdir(scratch):
        for feature in sorted(os.listdir(scratch)):
            if not os.path.isfile(os.path.join(scratch, feature, "wave-ledger.json")):
                continue
            data = ledgers.get(feature) or load_ledger(root, feature)
            for open_wave in open_waves(data):
                outstanding.update(
                    set(open_wave["dispatched"]) - set(open_wave.get("closed", {}))
                )
    missing = sorted(outstanding - set(hits))
    if missing:
        print(
            "drain-wave: collect the remaining wave results together; missing: %s"
            % ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    if not plan:
        print("drain-wave: reported results were already collected; nothing to do")
        return 0
    for feat, data in sorted(ledgers.items()):
        names = ", ".join(slug for f, slug, _, _ in plan if f == feat)
        if not names:
            continue
        touched = set()
        for f, slug, result, conflict_evidence in plan:
            if f == feat:
                hits[slug].setdefault("closed", {})[slug] = result
                if result == "conflict":
                    hits[slug].setdefault("conflict_evidence", {})[slug] = conflict_evidence
                touched.add(id(hits[slug]))
        for w in data["waves"]:
            if id(w) in touched and not (set(w["dispatched"]) - set(w.get("closed", {}))):
                w["closed_at"] = now_iso()
        save_ledger(root, feat, data)
        print("drain-wave: collected %s -> .scratch/%s/wave-ledger.json" % (names, feat))
    return 0


def cmd_audit(root, feat):
    issues = load_issues(root, feat)
    if issues is None:
        return 1
    owned = set()
    scan_dirs = set()
    for _, _, fm in issues.values():
        for p in as_list(fm.get("test_paths")):
            if p:
                owned.add(norm_path(p))
        for p in as_list(fm.get("touches")):
            if p:
                scan_dirs.add(norm_path(p))
    unowned = []
    for d in sorted(scan_dirs):
        base = os.path.join(root, d.replace("/", os.sep))
        stack = [base]
        while stack:
            cur = stack.pop()
            try:
                entries = os.listdir(cur)
            except OSError:
                continue
            for n in entries:
                p = os.path.join(cur, n)
                try:
                    is_dir = os.path.isdir(p)
                except OSError:
                    continue
                if is_dir:
                    if n in SKIP_DIRS:
                        continue
                    stack.append(p)
                elif TEST_FILE.search(n) and any(n.endswith(ext) for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".cs", ".rb", ".php", ".kt", ".swift")):
                    rel = norm_path(os.path.relpath(p, root))
                    if rel not in owned:
                        unowned.append(rel)
    if unowned:
        print("drain-wave: %d test file(s) claimed by no issue's test_paths:" % len(unowned))
        for rel in sorted(set(unowned)):
            print("  %s" % rel)
        print("assign each to an issue (sanctioned test_paths append) or open a cleanup issue")
        print("before the closing review - unreviewed tests must not ride the batch.")
        return 1
    print("drain-wave: audit clean - every test file under touches is claimed")
    return 0


def cmd_selftest():
    """Gate the gate: parse substrate, wave cap, zombie block, collect refusals.
    Fixtures live in a tempdir; nothing outside it is read or written."""
    bad = []

    def check(name, ok):
        print("%s %s" % ("ok  " if ok else "FAIL", name))
        if not ok:
            bad.append(name)

    def run_silent(fn, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return fn(*args)

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.abspath(tmp)
        i_dir = os.path.join(root, ".scratch", "sf", "issues")
        os.makedirs(i_dir)

        def issue(name, touches, tests):
            body = ["---", "status: ready", "touches:"]
            body += ["  - %s" % t for t in touches]
            body.append("test_paths:")
            body += ["  - %s" % t for t in tests]
            body += ["---", "# x"]
            with open(os.path.join(i_dir, name), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(body) + "\n")

        for i in range(1, 7):
            issue("%02d-p%d.md" % (i, i), ("pkg-%d" % i,), ("pkg-%d/t%d.spec.ts" % (i, i),))
        with open(os.path.join(i_dir, "07-flow.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nstatus: ready\ntouches: [pkg-7]\ntest_paths: [pkg-7/t7.spec.ts]\n---\n# x\n")
        issue("08-ov.md", ("pkg-7/sub",), ("pkg-7/t8.spec.ts",))
        issue("09-tp.md", ("pkg-9",), ("pkg-7/t7.spec.ts",))

        fm = get_frontmatter(os.path.join(i_dir, "01-p1.md"))
        check("frontmatter: scalar", fm.get("status") == "ready")
        check("frontmatter: block list", fm.get("touches") == ["pkg-1"])
        fm7 = get_frontmatter(os.path.join(i_dir, "07-flow.md"))
        check(
            "frontmatter: flow list",
            fm7.get("touches") == ["pkg-7"] and fm7.get("test_paths") == ["pkg-7/t7.spec.ts"],
        )
        check("path_overlap: dir contains path", path_overlap("pkg-1", "pkg-1/x.ts"))
        check("path_overlap: disjoint", not path_overlap("pkg-1", "pkg-2"))
        imap = load_issues(root, "sf")
        check("collides: touches prefix", collides(imap, "07-flow", "08-ov"))
        check("collides: shared test file", collides(imap, "07-flow", "09-tp"))

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd_next(root, "sf")
        wave = [l for l in buf.getvalue().splitlines() if l.startswith("wave: ")]
        slugs = wave[0][len("wave: "):].split() if wave else []
        check("next: wave capped at %d" % MAX_IN_FLIGHT, code == 0 and len(slugs) == MAX_IN_FLIGHT)
        check("dispatch: records the wave", run_silent(cmd_dispatch, root, slugs) == 0)
        check("next: open wave blocks as zombies", run_silent(cmd_next, root, "sf") == 3)
        check("collect: green refused while ready", run_silent(cmd_collect, root, [slugs[0] + "=green"]) == 1)
        done = os.path.join(i_dir, slugs[0] + ".md")
        with open(done, "r", encoding="utf-8") as f:
            raw = f.read()
        with open(done, "w", encoding="utf-8", newline="\n") as f:
            f.write(raw.replace("status: ready", "status: done"))
        check("collect: partial wave refused", run_silent(cmd_collect, root, [slugs[0] + "=green"]) == 1)
        check("collect: red refused once done", run_silent(cmd_collect, root, [slugs[0] + "=red"]) == 1)
        check("collect: bad result refused", run_silent(cmd_collect, root, [slugs[1] + "=pink"]) == 2)
        done2 = os.path.join(i_dir, slugs[1] + ".md")
        with open(done2, "r", encoding="utf-8") as f:
            raw2 = f.read()
        with open(done2, "w", encoding="utf-8", newline="\n") as f:
            f.write(raw2.replace("status: ready", "status: done"))
        check(
            "zombie: done-on-disk still needs reconciliation",
            run_silent(cmd_next, root, "sf") == 3
            and load_ledger(root, "sf")["waves"][-1]["closed"] == {},
        )
        conflict_path = Path(root) / ".scratch" / "sf" / "receipts" / "conflict.json"
        conflict_path.parent.mkdir(parents=True)
        conflict_issue = Path(i_dir) / (slugs[2] + ".md")
        conflict_path.write_text(
            json.dumps({
                "schema_version": 1,
                "feature": "sf",
                "slug": slugs[2],
                "contract_sha256": contract_sha256(conflict_issue),
                "command": "selftest",
                "observed": "exit 1",
                "contract_clause": "AC #1",
                "evidence": "selftest fixture",
            }),
            encoding="utf-8",
        )
        check(
            "collect: one reconciled batch closes the wave",
            run_silent(
                cmd_collect,
                root,
                [
                    slugs[0] + "=green",
                    slugs[1] + "=green",
                    slugs[2] + "=conflict@" + conflict_path.relative_to(root).as_posix(),
                    slugs[3] + "=red",
                ],
            ) == 0,
        )
        led = load_ledger(root, "sf")["waves"][-1]
        check("collect: ledger records green", led.get("closed", {}).get(slugs[0]) == "green")
        check("next: unchanged conflict blocks the batch", run_silent(cmd_next, root, "sf") == 6)
        check("dispatch: unchanged conflict blocks bypass", run_silent(cmd_dispatch, root, ["05-p5"]) == 6)
        conflict_path = os.path.join(i_dir, slugs[2] + ".md")
        with open(conflict_path, "a", encoding="utf-8", newline="\n") as f:
            f.write("# realigned\n")
        check("next: changed issue releases conflict barrier", run_silent(cmd_next, root, "sf") == 0)

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.abspath(tmp)
        i_dir = os.path.join(root, ".scratch", "cp", "issues")
        os.makedirs(i_dir)

        def card(name, touches, test, blocked=""):
            body = ["---", "status: ready"]
            if blocked:
                body.append("blocked_by: [%s]" % blocked)
            body += ["touches: [%s]" % touches, "test_paths: [%s]" % test, "---", "# x"]
            with open(os.path.join(i_dir, name), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(body) + "\n")

        # 01 collides with 02 on alpha/; 02 unblocks the 03 -> 04 chain.
        card("01-solo.md", "alpha", "alpha/t1.spec.ts")
        card("02-head.md", "alpha", "alpha/t2.spec.ts")
        card("03-mid.md", "beta", "beta/t3.spec.ts", blocked="02-head")
        card("04-leaf.md", "gamma", "gamma/t4.spec.ts", blocked="03-mid")
        imap = load_issues(root, "cp")
        depth = chain_depths(imap)
        check(
            "chain: depth counts ready dependents",
            depth.get("02-head") == 3 and depth.get("01-solo") == 1,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd_next(root, "cp")
        wave_lines = [l for l in buf.getvalue().splitlines() if l.startswith("wave: ")]
        check(
            "next: collision serializes longest dependency chain first",
            code == 0 and bool(wave_lines)
            and "02-head" in wave_lines[0] and "01-solo" not in wave_lines[0],
        )
        out = io.StringIO()
        with redirect_stdout(out):
            code = cmd_step(root, "cp", parallel=False)
        check(
            "step: serial mode also takes the chain head",
            code == 0 and "dispatch 02-head" in out.getvalue(),
        )
        undeclared = {
            "01-leaf": ("cp", "", {"status": "ready"}),
            "02-head": ("cp", "", {"status": "ready"}),
            "03-mid": ("cp", "", {"status": "ready", "blocked_by": ["02-head"]}),
            "04-tail": ("cp", "", {"status": "ready", "blocked_by": ["03-mid"]}),
        }
        check(
            "chain: undeclared solo uses dependency priority",
            plan_waves(undeclared, set())["solo_now"] == "02-head",
        )

    if bad:
        print("drain-wave: selftest FAILED (%d check(s))" % len(bad))
        return 1
    print("drain-wave: selftest ok")
    return 0


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    usage = (
        "usage: drain-wave.py step <repo-root> [<feat>] [-p|--parallel] | next <repo-root> [<feat>] | "
        "dispatch <repo-root> <slug>... | "
        "collect <repo-root> <slug>=<result|conflict@evidence.json>[,...] | audit <repo-root> [<feat>] | "
        "dismiss-conflict <repo-root> <feat> <slug> <evidence.json> | selftest"
    )
    cmd = argv[1] if len(argv) >= 2 else None
    if cmd == "selftest":
        return cmd_selftest()
    if len(argv) < 3:
        print(usage, file=sys.stderr)
        return 2
    root = os.path.abspath(argv[2])
    if not os.path.isdir(root):
        print("drain-wave: no such directory '%s'" % root, file=sys.stderr)
        return 2
    if cmd == "step":
        step_args = argv[3:]
        parallel = "-p" in step_args or "--parallel" in step_args
        step_args = [value for value in step_args if value not in ("-p", "--parallel")]
        feat = step_args[0] if len(step_args) == 1 else None
        if len(step_args) > 1:
            print(usage, file=sys.stderr)
            return 2
        return cmd_step(root, feat, parallel=parallel)
    if cmd == "next":
        feat = argv[3] if len(argv) == 4 else None
        if len(argv) > 4:
            print(usage, file=sys.stderr)
            return 2
        return cmd_next(root, feat)
    if cmd == "dispatch":
        return cmd_dispatch(root, argv[3:])
    if cmd == "collect":
        pairs = [p.strip() for arg in argv[3:] for p in arg.split(",") if p.strip()]
        return cmd_collect(root, pairs)
    if cmd == "dismiss-conflict":
        if len(argv) != 6:
            print(usage, file=sys.stderr)
            return 2
        return cmd_dismiss_conflict(root, argv[3], argv[4], argv[5])
    if cmd == "audit":
        feat = argv[3] if len(argv) == 4 else None
        if len(argv) > 4:
            print(usage, file=sys.stderr)
            return 2
        return cmd_audit(root, feat)
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
