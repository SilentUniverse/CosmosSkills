#!/usr/bin/env python3
"""Read engineering obligations and validate completion; the harness owns execution."""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path
ENGINEERING_ROOT = Path(__file__).resolve().parent
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from evidence import atomic_write, file_lock
from workflow_contract import effective_verifier, issue_contract_digest, parse_parent_pointer, validate_completion, verification_contract

PROFILE_NAME = re.compile(r"\bprofile:([A-Za-z][A-Za-z0-9_-]*)\b")
MAPPED_ACTION = re.compile(r"^(\s*-\s*#\d+\s*(?:→|->)\s*)`([^`]+)`")
ATTEMPT_HEAD = re.compile(r"^###\s+(?:尝试|失败|Attempt)(?:\s|—|-|$)", re.IGNORECASE)
CONTROL_DIRS = {"tmp", "batches", "wave-baselines", "workflow-runs", "evidence", "ci"}
_PROFILE_UNSET = object()

def scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == "[" and value[-1] == "]":
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [scalar(item) for item in inner.split(",") if item.strip()]
    return scalar(value)


def frontmatter(raw, path):
    lines = raw.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("%s: no YAML frontmatter" % path)
    data = {}
    for line in lines[1:]:
        if line == "---":
            return data
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = scalar(value)
    raise ValueError("%s: unclosed YAML frontmatter" % path)


def frontmatter_rich(raw, path):
    lines = raw.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("%s: no YAML frontmatter" % path)
    data = {}
    last_key = None
    for line in lines[1:]:
        if line == "---":
            return data
        if not line.strip():
            continue
        if line[:1].isspace():
            item = line.strip()
            if last_key is not None and item.startswith("- "):
                entry = data[last_key]
                if not isinstance(entry, list):
                    entry = data[last_key] = [entry] if entry else []
                entry.append(parse_value(item[2:]))
            continue
        if ":" not in line:
            last_key = None
            continue
        key, value = line.split(":", 1)
        last_key = key.strip()
        data[last_key] = parse_value(value)
    raise ValueError("%s: unclosed YAML frontmatter" % path)


def section_summary(raw):
    lines = raw.splitlines()
    active = False
    body = []
    for line in lines:
        if line.startswith("## 做什么"):
            active = True
            continue
        if active and (line.startswith("## ") or line.startswith("### ")):
            break
        if active and line.strip():
            body.append(line.strip())
    return " ".join(body[:3])


def compact_summary(raw, limit=160):
    value = section_summary(raw)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def safe_segment(value, label):
    value = str(value)
    if not value or value in (".", "..") or "/" in value or "\\" in value:
        raise ValueError("%s must be one directory/file stem" % label)
    return value


def feature_issue_dir(root, feature):
    root = Path(root).resolve()
    feature = safe_segment(feature, "feature")
    if feature in CONTROL_DIRS:
        raise ValueError("reserved workflow control directory: %s" % feature)
    scratch = (root / ".scratch").resolve()
    feature_dir = (scratch / feature).resolve()
    issue_dir = (feature_dir / "issues").resolve()
    try:
        feature_dir.relative_to(scratch)
        issue_dir.relative_to(feature_dir)
    except ValueError as exc:
        raise ValueError("feature issue directory must stay under .scratch") from exc
    return issue_dir


def section_lines(raw, heading, limit=3):
    lines = raw.splitlines()
    active = False
    body = []
    for line in lines:
        if line.startswith("## " + heading):
            active = True
            continue
        if active and line.startswith("## "):
            break
        if active and line.strip():
            body.append(line.strip())
    return body[:limit]


def section_body(raw, heading):
    return section_lines(raw, heading, limit=None)


def latest_attempt(raw, limit=8):
    """Project only the newest retry handoff from Comments, never the full history."""
    latest = []
    active = None
    for line in raw.splitlines():
        if line.startswith("### "):
            active = [line.strip()] if ATTEMPT_HEAD.match(line) else None
            if active is not None:
                latest = active
            continue
        if line.startswith("## "):
            active = None
            continue
        if active is not None and line.strip():
            active.append(line.strip())
    return latest[:limit]


def contract_digest(raw):
    contract = raw.split("\n## Comments", 1)[0]
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def issue_paths(root, feature):
    issue_dir = feature_issue_dir(root, feature)
    if not issue_dir.is_dir():
        raise ValueError("feature '%s' has no issue directory" % feature)
    paths = [path.resolve() for path in issue_dir.glob("*.md") if path.is_file()]
    archive = issue_dir / "archive"
    if archive.is_dir():
        archive = archive.resolve()
        try:
            archive.relative_to(issue_dir)
        except ValueError as exc:
            raise ValueError("issue archive must stay under its feature") from exc
        paths.extend(path.resolve() for path in archive.glob("*.md") if path.is_file())
    for path in paths:
        try:
            path.relative_to(issue_dir)
        except ValueError as exc:
            raise ValueError("issue path must stay under its feature") from exc
    return sorted(paths)


def issue_state(root, feature, path):
    raw = Path(path).read_text(encoding="utf-8-sig")
    data = frontmatter_rich(raw, path)
    if data.get("type") != "issue" or data.get("feature") != feature:
        raise ValueError("%s: issue identity does not match feature '%s'" % (path, feature))
    return raw, data


def issue_record(root, feature, path):
    raw, data = issue_state(root, feature, path)
    if data.get("status") != "done":
        return None
    relative = path.relative_to(root).as_posix()
    record = {
        "slug": path.stem,
        "category": data.get("category", "enhancement"),
        "refines": data.get("refines") or None,
        "summary": section_summary(raw),
        "path": relative,
        "digest": contract_digest(raw),
    }
    try:
        validate_completion(root, path, raw)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record["reason"] = str(exc)
    return record


def slug_order(slug):
    match = re.match(r"^(\d+)-", slug)
    return (int(match.group(1)) if match else -1, slug)


def inspect_feature(root, feature):
    root = Path(root).resolve()
    records = []
    seen = set()
    for path in issue_paths(root, feature):
        record = issue_record(root, feature, path)
        if record is None:
            continue
        if record["slug"] in seen:
            raise ValueError("duplicate issue slug '%s'" % record["slug"])
        seen.add(record["slug"])
        records.append(record)

    invalid = [record for record in records if "reason" in record]
    proven = [record for record in records if "reason" not in record]
    redos = {}
    for record in proven:
        if record["category"] == "redo" and record["refines"]:
            redos.setdefault(record["refines"], []).append(record)

    suppressed = set()
    for parent, replacements in redos.items():
        suppressed.add(parent)
        winner = max(replacements, key=lambda item: slug_order(item["slug"]))
        suppressed.update(item["slug"] for item in replacements if item is not winner)

    delivered = sorted(
        (record for record in proven if record["slug"] not in suppressed),
        key=lambda item: slug_order(item["slug"]),
    )
    source_material = "".join(
        "%s\0%s\n" % (record["slug"], record["digest"])
        for record in sorted(records, key=lambda item: item["slug"])
    )
    result = {
        "schema_version": 1,
        "feature": feature,
        "source_digest": hashlib.sha256(source_material.encode("utf-8")).hexdigest(),
        "source_count": len(records),
        "replaced": sorted(suppressed, key=slug_order),
        "delivered": delivered,
        "invalid": sorted(invalid, key=lambda item: slug_order(item["slug"])),
        "counts": {"done": len(proven), "delivered": len(delivered), "invalid": len(invalid)},
    }
    return result


def find_issue(root, feature, slug):
    issue_dir = feature_issue_dir(root, feature)
    slug = safe_segment(slug, "slug")
    if not issue_dir.is_dir():
        raise ValueError("feature '%s' has no issue directory" % feature)
    path = issue_dir / ("%s.md" % slug)
    if path.is_file():
        resolved = path.resolve()
        try:
            resolved.relative_to(issue_dir)
        except ValueError as exc:
            raise ValueError("issue path must stay under its feature") from exc
        return resolved
    raise ValueError("issue '%s' not found in feature '%s'" % (slug, feature))


def _issue_packet(root, feature, slug, path, raw, issue_data, profile=_PROFILE_UNSET):
    data = dict(issue_data)
    verification = section_body(raw, "验证设计")
    packet = {
        "schema_version": 1,
        "slug": slug,
        "feature": feature,
        "status": data.get("status"),
        "category": data.get("category", "enhancement"),
        "refines": data.get("refines") or None,
        "blocked_by": data.get("blocked_by", []),
        "test_paths": data.get("test_paths", []),
        "touches": data.get("touches", []),
        "exclusive_resources": data.get("exclusive_resources", []),
        "parent": section_body(raw, "上级"),
        "objective": section_body(raw, "做什么"),
        "acceptance": section_body(raw, "验收标准"),
        "verification": verification,
        "context": section_body(raw, "相关面"),
        "contract_sha256": issue_contract_digest(raw),
        "source": path.relative_to(root).as_posix(),
    }
    parent_ref = parse_parent_pointer(raw)
    if parent_ref:
        packet["parent_ref"] = parent_ref
    if data.get("contract_version"):
        packet["contract_version"] = data["contract_version"]
    if data.get("experience_review"):
        packet["experience_review"] = data["experience_review"]
    manual_verification = section_body(raw, "手动验证")
    if manual_verification:
        packet["manual_verification"] = manual_verification
    attempt = latest_attempt(raw)
    if attempt:
        packet["latest_attempt"] = attempt
    if str(data.get("contract_version", "")) == "3":
        verifier = dict(
            effective_verifier(root, feature, raw)
            if profile is _PROFILE_UNSET
            else effective_verifier(root, feature, raw, profile)
        )
        verifier.pop("ac_commands", None)
        action_counts = {}
        for line in verification:
            match = MAPPED_ACTION.match(line)
            if match and not match.group(2).startswith("profile:"):
                action_counts[match.group(2)] = action_counts.get(match.group(2), 0) + 1
        aliases = {}
        compact = []
        for line in verification:
            stripped = line.strip()
            if stripped.startswith("- profile:") or stripped.startswith("- 偏差 "):
                continue
            match = MAPPED_ACTION.match(line)
            if match and action_counts.get(match.group(2), 0) > 1:
                action = match.group(2)
                alias = aliases.setdefault(action, "card_%d" % (len(aliases) + 1))
                line = line[: match.start(2)] + "packet:" + alias + line[match.end(2):]
            compact.append(line)
        referenced = {
            name for line in compact for name in PROFILE_NAME.findall(line)
        }
        verifier["completion_commands"] = [
            name for name in verifier.get("completion_commands", []) if name in referenced
        ]
        commands = {
            name: command
            for name, command in verifier["commands"].items()
            if name in referenced
        }
        verifier["commands"] = commands
        packet["verification"] = compact
        packet["effective_verifier"] = verifier
        if aliases:
            packet["packet_commands"] = {alias: action for action, alias in aliases.items()}
    return packet


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 6)


def stats(root):
    root = Path(root).resolve()
    durations = {}
    for receipts_dir in sorted(root.glob(".scratch/*/receipts")):
        for path in sorted(receipts_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            duration = payload.get("duration_seconds")
            if isinstance(duration, (int, float)):
                durations.setdefault(str(payload.get("scope", "?")), []).append(float(duration))
    timing = {
        scope: {
            "count": len(values),
            "p50": percentile(values, 0.5),
            "p95": percentile(values, 0.95),
        }
        for scope, values in sorted(durations.items())
    }
    cards = {"v2": 0, "v3": 0}
    card_bytes = {"v2": 0, "v3": 0}
    for path in sorted(root.glob(".scratch/*/issues/*.md")):
        raw = path.read_text(encoding="utf-8-sig")
        try:
            data = frontmatter(raw, path)
        except ValueError:
            continue
        key = "v3" if str(data.get("contract_version", "")) == "3" else "v2"
        cards[key] += 1
        card_bytes[key] += len(raw.encode("utf-8"))
    completion = {"done": 0, "invalid": 0}
    invalid = []
    for feature in feature_names(root):
        projection = inspect_feature(root, feature)
        for key in completion:
            completion[key] += projection["counts"][key]
        invalid.extend(dict(item, feature=feature) for item in projection["invalid"])
    return {
        "schema_version": 1,
        "timing": timing,
        "cards": cards,
        "card_bytes": card_bytes,
        "completion": completion,
        "invalid": invalid,
    }


def issue_packet(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw, data = issue_state(root, feature, path)
    return _issue_packet(root, feature, slug, path, raw, data)


def issue_packets(root, feature, slugs):
    if len(slugs) != len(set(slugs)):
        raise ValueError("duplicate packet slug")
    return [issue_packet(root, feature, slug) for slug in slugs]


def _spec_gate(root, feature, raw):
    directory = Path(root) / ".scratch" / feature
    if not parse_parent_pointer(raw) and not (directory / "spec-review.json").exists():
        return []
    path = Path(__file__).resolve().parent / "spec" / "scripts" / "spec-review.py"
    spec = importlib.util.spec_from_file_location("cosmos_spec_review", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if parse_parent_pointer(raw):
        module.parent_contract(directory, raw)
    problem = module.acceptance_barrier(directory, [("card", raw)])
    return [problem] if problem else []


def _admission(root, feature, path, raw, data):
    if data.get("status") != "ready":
        raise ValueError("engineering admission requires a ready card")
    verification_contract(root, path, raw)
    dependencies = data.get("blocked_by", [])
    if not isinstance(dependencies, list) or any(not isinstance(value, str) for value in dependencies):
        raise ValueError("blocked_by must be a list of issue slugs")
    if dependencies:
        paths = issue_paths(root, feature)
        for slug in sorted(set(dependencies)):
            safe_segment(slug, "dependency")
            matches = [candidate for candidate in paths if candidate.stem == slug]
            if len(matches) != 1:
                raise ValueError("dependency needs exactly one retained card: " + slug)
            dependency = matches[0]
            dep_raw, dep_data = issue_state(root, feature, dependency)
            if dep_data.get("status") != "done":
                raise ValueError("unfinished dependency: " + slug)
            try:
                validate_completion(root, dependency, dep_raw)
            except (OSError, ValueError) as exc:
                raise ValueError("dependency '%s' has no valid completion proof: %s" % (slug, exc)) from exc
    problems = _spec_gate(root, feature, raw)
    if problems:
        raise ValueError("; ".join(problems))


def start_issue(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw, data = issue_state(root, feature, path)
    _admission(root, feature, path, raw, data)
    return {"admitted": True, "packet": _issue_packet(root, feature, slug, path, raw, data)}


def _set_status(raw, status, reason=None):
    lines = raw.splitlines(keepends=True)
    inside = False
    changed = False
    result = []
    for index, line in enumerate(lines):
        if line.strip() == "---":
            inside = index == 0
        if inside and line.startswith("pending_reason:"):
            continue
        if inside and line.startswith("status:"):
            line = "status: " + status + "\n"
            if reason:
                line += "pending_reason: " + json.dumps(reason, ensure_ascii=False) + "\n"
            changed = True
        result.append(line)
    if not changed:
        raise ValueError("card has no status")
    return "".join(result)


def close_issue(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    with file_lock(path.with_suffix(".lock")):
        raw, data = issue_state(root, feature, path)
        if data.get("status") != "ready":
            raise ValueError("close requires status: ready")
        _admission(root, feature, path, raw, data)
        validate_completion(root, path, raw)
        atomic_write(path, _set_status(raw, "done"))
    return {"feature": feature, "slug": slug, "status": "done"}


def park_issue(root, feature, slug, reason):
    if not reason.strip():
        raise ValueError("park needs an engineering reason")
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    with file_lock(path.with_suffix(".lock")):
        raw, data = issue_state(root, feature, path)
        if data.get("status") not in ("ready", "pending"):
            raise ValueError("completed history cannot be parked")
        atomic_write(path, _set_status(raw, "pending", reason.strip()))
    return {"feature": feature, "slug": slug, "status": "pending", "pending_reason": reason.strip()}


def feature_names(root):
    scratch = Path(root) / ".scratch"
    return sorted(p.name for p in scratch.iterdir()
                  if p.name not in CONTROL_DIRS and (p / "issues").is_dir()) if scratch.is_dir() else []


def feature_frontier(root, feature):
    root = Path(root).resolve()
    ready, blocked, done, invalid = [], [], [], []
    for path in issue_paths(root, feature):
        raw, data = issue_state(root, feature, path)
        if data.get("status") == "done":
            record = issue_record(root, feature, path)
            if "reason" in record:
                invalid.append(record)
            else:
                done.append(path.stem)
        elif path.parent.name != "archive":
            item = {"slug": path.stem, "summary": compact_summary(raw)}
            if data.get("status") == "ready":
                try:
                    start_issue(root, feature, path.stem)
                    ready.append(item)
                except ValueError as exc:
                    blocked.append(dict(item, blocked_by=[str(exc)]))
            else:
                blocked.append(dict(item, blocked_by=[data.get("pending_reason", "pending engineering decision")]))
    return {"feature": feature,
            "counts": {"ready": len(ready), "blocked": len(blocked), "done": len(done), "invalid": len(invalid)},
            "ready": ready, "blocked": blocked, "done": sorted(done), "invalid": invalid}


def survey_states(root, history=False, features=None):
    return [(inspect_feature if history else feature_frontier)(root, f)
            for f in (features if features else feature_names(root))]


def render_human(state):
    rows = ["# " + state["feature"]]
    for item in state.get("delivered", state.get("ready", [])):
        rows.append("- %s — %s" % (item["slug"], item["summary"]))
    for item in state.get("blocked", []):
        rows.append("- %s: %s" % (item["slug"], "; ".join(item["blocked_by"])))
    for item in state.get("invalid", []):
        rows.append("- %s — 完成证明无效: %s" % (item["slug"], item["reason"]))
    if "counts" in state:
        rows.append(json.dumps(state["counts"], ensure_ascii=False))
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "survey", "packet", "packets", "start", "close", "park", "stats"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
        if name not in ("survey", "stats"):
            cmd.add_argument("feature")
        if name in ("packet", "start", "close", "park"):
            cmd.add_argument("slug")
        if name == "packets":
            cmd.add_argument("slugs", nargs="+")
        if name == "park":
            cmd.add_argument("--reason", required=True)
        if name in ("survey", "inspect"):
            cmd.add_argument("--format", choices=("json", "human"), default="human")
        if name == "survey":
            cmd.add_argument("--history", action="store_true")
            cmd.add_argument("--feature", action="append")
    if argv and str(argv[0]).endswith("workflow-state.py"):
        argv = argv[1:]
    args = parser.parse_args(argv)
    try:
        if args.command == "survey":
            result = survey_states(args.root, args.history, args.feature)
        elif args.command == "inspect":
            result = inspect_feature(args.root, args.feature)
        elif args.command == "stats":
            result = stats(args.root)
        elif args.command == "packets":
            result = issue_packets(args.root, args.feature, args.slugs)
        else:
            method = {"packet": issue_packet, "start": start_issue, "close": close_issue, "park": park_issue}[args.command]
            result = method(args.root, args.feature, args.slug, *([args.reason] if args.command == "park" else []))
        if getattr(args, "format", "json") == "human":
            print("\n\n".join(render_human(row) for row in result) if isinstance(result, list) else render_human(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print("workflow-state: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
