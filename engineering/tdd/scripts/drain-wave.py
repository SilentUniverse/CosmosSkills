#!/usr/bin/env python
# Wave arithmetic + dispatch ledger for /tdd -p drain (DRAIN.md step 1-3).
# Stdlib only. The model orchestrates; this script owns the wave-state mutation
# line: compute the wave, record the dispatch intent (with wave baseline) before
# any subagent starts, close dispatched issues on collect, and audit test-file
# ownership at close. Durability rule: an issue is schedulable only through this
# script; a dispatched issue with no ledger closure and no done status is a
# zombie (exit 3) — resolve by adopt-or-revert before scheduling anything.
#
#   drain-wave.py next <repo-root> [<feat>]     propose the next wave (read-only
#                                               except zombie auto-close of done slugs)
#   drain-wave.py dispatch <repo-root> <slug>...                record intent + baseline
#   drain-wave.py collect <repo-root> <slug>=<result>[,<slug>=<result>...]
#                                               result: green|red|blocked|conflict|aborted
#   drain-wave.py audit <repo-root> [<feat>]    test files no issue claims
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
            issues[slug] = (os.path.basename(fd), p, fm)
    return issues


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
    return data


def save_ledger(root, feat, data):
    p = ledger_path(root, feat)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, p)


def contract_sha256(path):
    """Hash aligned issue content; comments/evidence do not count as realignment."""
    with open(path, "r", encoding="utf-8") as stream:
        text = stream.read()
    marker = re.search(r"(?m)^## Comments\s*$", text)
    contract = text[:marker.start()] if marker else text
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def active_conflicts(root, issues):
    """Closed conflict results whose issue has not changed since collection."""
    active = {}
    for feat in sorted({value[0] for value in issues.values()}):
        data = load_ledger(root, feat)
        for wave in data["waves"]:
            digests = wave.get("conflict_contract_sha256", {})
            for slug, result in wave.get("closed", {}).items():
                if result != "conflict" or slug not in issues:
                    continue
                issue_feat, path, fm = issues[slug]
                if issue_feat != feat or fm.get("status") != "ready":
                    continue
                recorded = digests.get(slug)
                if not recorded or contract_sha256(path) == recorded:
                    active[(feat, slug)] = wave.get("wave", "?")
    return [(feat, wave, slug) for (feat, slug), wave in sorted(active.items())]


def report_conflicts(conflicts):
    print("drain-wave: receipt conflict requires /spec realignment:")
    for feat, wave, slug in conflicts:
        print("  %s (wave %s, ledger .scratch/%s/wave-ledger.json)" % (slug, wave, feat))
    print("the recorded issue content is unchanged; no next wave or explicit dispatch is allowed")


def git_baseline(root):
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if out.returncode != 0:
            return "(git status failed: %s)" % out.stderr.strip()[:200]
        return out.stdout.rstrip("\n")
    except OSError as e:
        return "(git unavailable: %s)" % e


def issues_touch(issues, slug):
    return as_list(issues[slug][2].get("touches"))


def issues_tests(issues, slug):
    return as_list(issues[slug][2].get("test_paths"))


def declared(fm):
    return bool(as_list(fm.get("touches"))) and bool(as_list(fm.get("test_paths")))


def collides(issues, a, b):
    for x in issues_touch(issues, a):
        for y in issues_touch(issues, b):
            if path_overlap(x, y):
                return True
    return bool(set(norm_path(p) for p in issues_tests(issues, a))
                & set(norm_path(p) for p in issues_tests(issues, b)))


def open_waves(data):
    return [w for w in data["waves"] if set(w["dispatched"]) - set(w.get("closed", {}))]


def settle_zombies(root, issues):
    """Auto-close dispatched slugs that are done on disk (trust disk); report the rest."""
    zombies = []
    auto = []
    scratch = os.path.join(root, ".scratch")
    feats = []
    if os.path.isdir(scratch):
        feats = [
            n for n in sorted(os.listdir(scratch))
            if os.path.isfile(os.path.join(scratch, n, "wave-ledger.json"))
        ]
    for feat in feats:
        data = load_ledger(root, feat)
        changed = False
        for w in open_waves(data):
            for slug in set(w["dispatched"]) - set(w.get("closed", {})):
                if slug in issues and issues[slug][2].get("status") == "done":
                    w.setdefault("closed", {})[slug] = "green"
                    changed = True
                    auto.append("%s (auto-closed: done on disk)" % slug)
                elif slug not in issues:
                    w.setdefault("closed", {})[slug] = "aborted"
                    changed = True
                    auto.append("%s (auto-closed: issue file gone)" % slug)
                else:
                    zombies.append((feat, w["wave"], slug))
        if changed:
            save_ledger(root, feat, data)
    return zombies, auto


def cmd_next(root, feat):
    issues = load_issues(root, feat)
    if issues is None:
        return 1
    zombies, auto = settle_zombies(root, issues)
    for line in auto:
        print("ledger: %s" % line)
    if zombies:
        print("drain-wave: %d zombie(s) - dispatched but neither done nor closed:" % len(zombies))
        for f, w, slug in zombies:
            print("  %s (wave %d, ledger .scratch/%s/wave-ledger.json)" % (slug, w, f))
        print("recovery: adopt the on-disk code and finish the slice, or revert this issue's")
        print("edits to the wave baseline and leave it ready - then `collect` it. No new wave")
        print("until every zombie is closed (EDGE-CASES.md).")
        return 3
    conflicts = active_conflicts(root, issues)
    if conflicts:
        report_conflicts(conflicts)
        return 6
    if not issues:
        print("drain-wave: no issues found under .scratch/%s" % (feat or "*/issues"))
        return 4
    done = {s for s, (_, _, fm) in issues.items() if fm.get("status") == "done"}
    ready = {s for s, (_, _, fm) in issues.items() if fm.get("status") == "ready"}
    if not ready:
        print("drain-wave: nothing ready (%d done) - batch complete" % len(done))
        return 4
    blocked = []
    eligible = []
    for s in sorted(ready):
        deps = [d for d in as_list(issues[s][2].get("blocked_by")) if d]
        missing = [d for d in deps if d not in done]
        if missing:
            blocked.append((s, missing))
        else:
            eligible.append(s)
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
        solo_now = sorted(undeclared)[0]
        undeclared = [s for s in undeclared if s != solo_now]
    nf = feat if feat else "all features"
    print("drain-wave: %s - %d ready, %d done" % (nf, len(ready), len(done)))
    if solo_now:
        print("wave: %s (solo - undeclared, runs alone)" % solo_now)
    else:
        print("wave: %s" % (" ".join(wave) if wave else "(none this pass)"))
    if later:
        print("next waves (serialized): %s" % " ".join(later))
    if undeclared:
        print("solo (missing touches/test_paths - one per wave): %s" % " ".join(sorted(undeclared)))
    for s, missing in blocked:
        print("deferred: %s blocked by %s" % (s, ", ".join(missing)))
    return 0


def dispatch_receipt_hits(root, issues, slugs, ledgers):
    """Gate duplicate P# tuples and persist exact issue-to-key assignments."""
    api = preflight_api()
    root_path = Path(root)
    current_keys = {}
    rows = api.issue_preflight_rows(root_path)
    for row in rows:
        current_keys.setdefault(row["slug"], set()).add(row["key"])
    hits = {slug: [] for slug in slugs}

    # A previous wave can assign the same hit to an issue serialized into a later wave.
    # Accept it only while the issue still names that exact tuple and the receipt checks.
    for slug in slugs:
        feat = issues[slug][0]
        assignments = ledgers[feat].get("preflight_assignments", {}).get(slug, [])
        for assignment in assignments:
            if assignment.get("key") not in current_keys.get(slug, set()):
                continue
            entry = api.check(
                root_path / assignment.get("receipt", ""),
                cwd=assignment.get("cwd", ""),
                action=assignment.get("action", ""),
                fingerprint=assignment.get("fingerprint", ""),
            )
            if entry is not None:
                hits[slug].append(assignment["key"])

    plan = api.duplicate_plan(root_path, rows=rows)
    relevant = [
        duplicate
        for duplicate in plan["duplicates"]
        if any(Path(issue_path).stem in slugs for issue_path in duplicate["issues"])
    ]
    misses = [duplicate for duplicate in relevant if duplicate["status"] != "hit"]
    if misses:
        return None, misses

    for duplicate in relevant:
        assignment = {
            key: duplicate[key]
            for key in ("key", "cwd", "action", "fingerprint", "receipt")
        }
        feat = duplicate["feature"]
        by_issue = ledgers[feat].setdefault("preflight_assignments", {})
        for issue_path in duplicate["issues"]:
            slug = Path(issue_path).stem
            saved = by_issue.setdefault(slug, [])
            saved[:] = [item for item in saved if item.get("key") != duplicate["key"]]
            saved.append(dict(assignment))
            if slug in hits:
                hits[slug].append(duplicate["key"])
    return {slug: sorted(set(keys)) for slug, keys in hits.items() if keys}, []


def cmd_dispatch(root, slugs):
    issues = load_issues(root, None)
    if issues is None:
        return 1
    if not slugs:
        print("drain-wave: dispatch needs at least one slug", file=sys.stderr)
        return 2
    if len(slugs) > MAX_IN_FLIGHT:
        print(
            "drain-wave: %d issues > cap %d - dispatch in batches of <=%d, each landing first"
            % (len(slugs), MAX_IN_FLIGHT, MAX_IN_FLIGHT),
            file=sys.stderr,
        )
        return 1
    done = {s for s, (_, _, fm) in issues.items() if fm.get("status") == "done"}
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
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if collides(issues, a, b):
                print(
                    "drain-wave: %s and %s declare overlapping touches/test_paths -"
                    " serialize into successive waves" % (a, b),
                    file=sys.stderr,
                )
                return 1
    zombies, auto = settle_zombies(root, issues)
    if zombies:
        print(
            "drain-wave: open wave with unresolved issue(s) - collect them first;"
            " if the run crashed, `next` prints the recovery contract",
            file=sys.stderr,
        )
        return 3
    conflicts = active_conflicts(root, issues)
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
                        "drain-wave: feature '%s' still has an open wave - collect it first" % n,
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
            % json.dumps({"duplicates": misses}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        print(
            "run each action in its declared cwd without installing anything, then use "
            "preflight-receipt.py record and retry dispatch",
            file=sys.stderr,
        )
        return 5
    baseline = git_baseline(root)
    for feat, group in sorted(by_feat.items()):
        data = ledgers[feat]
        num = max((w["wave"] for w in data["waves"]), default=0) + 1
        group_hits = {
            slug: receipt_hits[slug]
            for slug in sorted(group)
            if slug in receipt_hits
        }
        data["waves"].append(
            {
                "wave": num,
                "at": now_iso(),
                "dispatched": sorted(group),
                "baseline": baseline,
                "receipt_hits": group_hits,
                "closed": {},
            }
        )
        save_ledger(root, feat, data)
        print("drain-wave: wave %d dispatched (%s) -> .scratch/%s/wave-ledger.json" % (num, ", ".join(sorted(group)), feat))
        for slug in sorted(group_hits):
            for key in group_hits[slug]:
                print("brief: %s receipt-hit:%s" % (slug, key))
    print("baseline recorded; subagents may start")
    return 0


def cmd_collect(root, pairs):
    issues = load_issues(root, None)
    if issues is None:
        return 1
    plan = []  # (feat, slug, result); validation first, then one write pass
    for pair in pairs:
        if "=" not in pair:
            print("drain-wave: bad pair '%s' (want slug=result)" % pair, file=sys.stderr)
            return 2
        slug, result = pair.split("=", 1)
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
        plan.append((issues[slug][0], slug, result))
    ledgers = {}
    hits = {}
    for feat, slug, result in plan:
        data = ledgers.setdefault(feat, load_ledger(root, feat))
        hit = None
        for w in reversed(open_waves(data)):
            if slug in w["dispatched"]:
                hit = w
                break
        if hit is None:
            print(
                "drain-wave: %s has no open dispatch in .scratch/%s/wave-ledger.json" % (slug, feat),
                file=sys.stderr,
            )
            return 1
        hits[slug] = hit
    for feat, data in sorted(ledgers.items()):
        touched = set()
        for f, slug, result in plan:
            if f == feat:
                hits[slug].setdefault("closed", {})[slug] = result
                if result == "conflict":
                    hits[slug].setdefault("conflict_contract_sha256", {})[slug] = contract_sha256(
                        issues[slug][1]
                    )
                touched.add(id(hits[slug]))
        for w in data["waves"]:
            if id(w) in touched and not (set(w["dispatched"]) - set(w.get("closed", {}))):
                w["closed_at"] = now_iso()
        save_ledger(root, feat, data)
        names = ", ".join(slug for f, slug, _ in plan if f == feat)
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
        check("collect: green accepted once done", run_silent(cmd_collect, root, [slugs[0] + "=green"]) == 0)
        check("collect: red refused once done", run_silent(cmd_collect, root, [slugs[0] + "=red"]) == 1)
        check("collect: bad result refused", run_silent(cmd_collect, root, [slugs[1] + "=pink"]) == 2)
        led = load_ledger(root, "sf")["waves"][-1]
        check("collect: ledger records green", led.get("closed", {}).get(slugs[0]) == "green")
        done2 = os.path.join(i_dir, slugs[1] + ".md")
        with open(done2, "r", encoding="utf-8") as f:
            raw2 = f.read()
        with open(done2, "w", encoding="utf-8", newline="\n") as f:
            f.write(raw2.replace("status: ready", "status: done"))
        check(
            "zombie: done-on-disk auto-closes",
            run_silent(cmd_next, root, "sf") == 3
            and load_ledger(root, "sf")["waves"][-1]["closed"].get(slugs[1]) == "green",
        )
        check(
            "collect: conflict and ordinary red close the wave",
            run_silent(
                cmd_collect,
                root,
                [slugs[2] + "=conflict", slugs[3] + "=red"],
            ) == 0,
        )
        check("next: unchanged conflict blocks the batch", run_silent(cmd_next, root, "sf") == 6)
        check("dispatch: unchanged conflict blocks bypass", run_silent(cmd_dispatch, root, ["05-p5"]) == 6)
        conflict_path = os.path.join(i_dir, slugs[2] + ".md")
        with open(conflict_path, "a", encoding="utf-8", newline="\n") as f:
            f.write("# realigned\n")
        check("next: changed issue releases conflict barrier", run_silent(cmd_next, root, "sf") == 0)

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
        "usage: drain-wave.py next <repo-root> [<feat>] | dispatch <repo-root> <slug>... | "
        "collect <repo-root> <slug>=<result>[,...] | audit <repo-root> [<feat>] | selftest"
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
