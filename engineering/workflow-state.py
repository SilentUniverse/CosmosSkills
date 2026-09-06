#!/usr/bin/env python3
"""Read feature state without materializing a second source of truth."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ENGINEERING_ROOT = Path(__file__).resolve().parent
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from workflow_contract import effective_verifier, issue_contract_digest, validate_v3_completion


ISSUE_NAME = re.compile(r"^(\d+)-.+\.md$")
PROFILE_NAME = re.compile(r"\bprofile:([A-Za-z][A-Za-z0-9_-]*)\b")
MAPPED_ACTION = re.compile(r"^(\s*-\s*#\d+\s*(?:→|->)\s*)`([^`]+)`")


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
        if active and line.startswith("## "):
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
    raw = path.read_text(encoding="utf-8-sig")
    data = frontmatter_rich(raw, path)
    if data.get("type") != "issue" or data.get("feature") != feature:
        raise ValueError("%s: issue identity does not match feature '%s'" % (path, feature))
    if data.get("status") == "done" and data.get("contract_version") == "3":
        validate_v3_completion(Path(root).resolve(), path, raw)
    return raw, data


def issue_record(root, feature, path):
    raw, data = issue_state(root, feature, path)
    if data.get("status") != "done":
        return None
    relative = path.relative_to(root).as_posix()
    return {
        "slug": path.stem,
        "category": data.get("category", "enhancement"),
        "refines": data.get("refines") or None,
        "summary": section_summary(raw),
        "path": relative,
        "digest": contract_digest(raw),
    }


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

    redos = {}
    for record in records:
        if record["category"] == "redo" and record["refines"]:
            redos.setdefault(record["refines"], []).append(record)

    suppressed = set()
    for parent, replacements in redos.items():
        suppressed.add(parent)
        winner = max(replacements, key=lambda item: slug_order(item["slug"]))
        suppressed.update(item["slug"] for item in replacements if item is not winner)

    delivered = sorted(
        (record for record in records if record["slug"] not in suppressed),
        key=lambda item: slug_order(item["slug"]),
    )
    source_material = "".join(
        "%s\0%s\n" % (record["slug"], record["digest"])
        for record in sorted(records, key=lambda item: item["slug"])
    )
    return {
        "schema_version": 1,
        "feature": feature,
        "source_digest": hashlib.sha256(source_material.encode("utf-8")).hexdigest(),
        "source_count": len(records),
        "replaced": sorted(suppressed, key=slug_order),
        "delivered": delivered,
    }


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


def issue_packet(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw, issue_data = issue_state(root, feature, path)
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
        "parent": section_body(raw, "上级"),
        "objective": section_body(raw, "做什么"),
        "acceptance": section_body(raw, "验收标准"),
        "verification": verification,
        "context": section_body(raw, "相关面"),
        "dependencies": section_body(raw, "前置依赖"),
        "digest": contract_digest(raw),
        "contract_sha256": issue_contract_digest(raw),
        "source": path.relative_to(root).as_posix(),
    }
    if str(data.get("contract_version", "")) == "3":
        verifier = dict(effective_verifier(root, feature, raw))
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
        referenced.update(verifier.get("completion_commands", []))
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


def close_issue(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw, data = issue_state(root, feature, path)
    if data.get("status") != "ready":
        raise ValueError(
            "issue '%s' is '%s'; close requires status: ready" % (slug, data.get("status"))
        )
    if "### 完成" not in raw:
        raise ValueError("issue '%s' has no ### 完成 record" % slug)
    if data.get("contract_version") == "3":
        validate_v3_completion(root, path, raw)
    lines = raw.splitlines(keepends=True)
    updated = []
    scanning = False
    replaced = False
    for index, line in enumerate(lines):
        if index == 0 and line.rstrip("\r\n") == "---":
            scanning = True
            updated.append(line)
            continue
        if scanning:
            if line.rstrip("\r\n") == "---":
                scanning = False
            elif line.startswith("status:"):
                ending = line[len(line.rstrip("\r\n")):]
                updated.append("status: done" + ending)
                replaced = True
                continue
        updated.append(line)
    if not replaced:
        raise ValueError("issue '%s' frontmatter has no status field" % slug)
    temporary = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        stream.write("".join(updated))
    os.replace(temporary, path)
    gc = gc_feature(root, feature, apply=False)
    return {
        "feature": feature,
        "slug": slug,
        "status": "done",
        "gc_candidates": gc["candidates"],
    }


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
    return {
        "schema_version": 1,
        "timing": timing,
        "cards": cards,
        "card_bytes": card_bytes,
    }


def render_human(state):
    lines = ["# %s — current reality" % state["feature"]]
    lines.append("source: %d done issue(s), digest %s" % (state["source_count"], state["source_digest"]))
    if not state["delivered"]:
        lines.append("- （无已交付行为）")
    for item in state["delivered"]:
        summary = item["summary"] or "（无行为摘要）"
        lines.append("- %s — %s [%s]" % (item["slug"], summary, item["path"]))
    return "\n".join(lines)


def feature_frontier(root, feature):
    root = Path(root).resolve()
    issue_dir = feature_issue_dir(root, feature)
    live = []
    done = set()
    if not issue_dir.is_dir():
        raise ValueError("feature '%s' has no issue directory" % feature)
    for path in issue_paths(root, feature):
        raw, data = issue_state(root, feature, path)
        if path.parent.name == "archive":
            if data.get("status") == "done":
                done.add(path.stem)
            continue
        status = data.get("status")
        if status == "done":
            done.add(path.stem)
        live.append((path, raw, data))
    ready = []
    blocked = []
    for path, raw, data in live:
        if data.get("status") != "ready":
            continue
        dependencies = [value for value in data.get("blocked_by", []) if value]
        missing = [value for value in dependencies if value not in done]
        item = {
            "slug": path.stem,
            "summary": compact_summary(raw),
            "blocked_by": missing,
        }
        (blocked if missing else ready).append(item)
    zombies = []
    ledger = root / ".scratch" / feature / "wave-ledger.json"
    if ledger.is_file():
        try:
            payload = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        for wave in payload.get("waves", []):
            for slug in sorted(set(wave.get("dispatched", [])) - set(wave.get("closed", {}))):
                zombies.append({"slug": slug, "wave": wave.get("wave")})
    zombie_slugs = {item["slug"] for item in zombies}
    ready = [item for item in ready if item["slug"] not in zombie_slugs]
    blocked = [item for item in blocked if item["slug"] not in zombie_slugs]
    return {
        "feature": feature,
        "counts": {
            "ready": len(ready),
            "blocked": len(blocked),
            "done": len(done),
            "zombie": len(zombies),
        },
        "ready": ready,
        "blocked": blocked,
        "zombies": zombies,
    }


def render_survey(states):
    if not states:
        return "（无 feature state）"
    lines = ["# workflow frontier"]
    for state in states:
        count = state["counts"]
        lines.append(
            "%s: ready=%d blocked=%d done=%d zombie=%d"
            % (state["feature"], count["ready"], count["blocked"], count["done"], count["zombie"])
        )
        for item in state["ready"]:
            lines.append("- ready %s — %s" % (item["slug"], item["summary"] or "（无摘要）"))
        for item in state["blocked"]:
            lines.append("- blocked %s ← %s" % (item["slug"], ", ".join(item["blocked_by"])))
        for item in state["zombies"]:
            lines.append("- zombie %s (wave %s)" % (item["slug"], item["wave"]))
    return "\n".join(lines)


def feature_names(root):
    scratch = Path(root) / ".scratch"
    if not scratch.is_dir():
        return []
    return sorted(
        path.name for path in scratch.iterdir()
        if path.is_dir() and (path / "issues").is_dir()
    )


def ledger_closed(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for wave in payload.get("waves", []):
        if set(wave.get("dispatched", [])) - set(wave.get("closed", {})):
            return False
    return True


def gc_feature(root, feature, apply=False):
    root = Path(root).resolve()
    feature_dir = root / ".scratch" / feature
    ready = False
    for path in issue_paths(root, feature):
        _, data = issue_state(root, feature, path)
        if path.parent.name == "archive":
            continue
        if data.get("status") == "ready":
            ready = True
            break
    ledger = feature_dir / "wave-ledger.json"
    open_wave = ledger.is_file() and not ledger_closed(ledger)
    candidates = []
    if not ready and not open_wave:
        for path in (feature_dir / "preflight-receipt.json", ledger):
            if path.is_file():
                candidates.append(path)
    removed = []
    if apply:
        for path in candidates:
            path.unlink()
            removed.append(path.relative_to(root).as_posix())
    return {
        "feature": feature,
        "ready": ready,
        "open_wave": open_wave,
        "candidates": [path.relative_to(root).as_posix() for path in candidates],
        "removed": removed,
    }


def parser():
    command = argparse.ArgumentParser(prog="workflow-state.py")
    sub = command.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("root")
    inspect.add_argument("feature")
    inspect.add_argument("--format", choices=("json", "human"), default="human")
    survey = sub.add_parser("survey")
    survey.add_argument("root")
    survey.add_argument("--format", choices=("json", "human"), default="human")
    survey.add_argument("--history", action="store_true")
    gc = sub.add_parser("gc")
    gc.add_argument("root")
    gc.add_argument("feature")
    gc.add_argument("--apply", action="store_true")
    packet = sub.add_parser("packet")
    packet.add_argument("root")
    packet.add_argument("feature")
    packet.add_argument("slug")
    close = sub.add_parser("close")
    close.add_argument("root")
    close.add_argument("feature")
    close.add_argument("slug")
    stats_cmd = sub.add_parser("stats")
    stats_cmd.add_argument("root")
    return command


def main(argv=None):
    args = parser().parse_args((argv or sys.argv)[1:])
    try:
        if args.command == "inspect":
            state = inspect_feature(args.root, args.feature)
            output = json.dumps(state, ensure_ascii=False, indent=2) if args.format == "json" else render_human(state)
        elif args.command == "survey":
            if args.history:
                states = [inspect_feature(args.root, feature) for feature in feature_names(args.root)]
            else:
                states = [feature_frontier(args.root, feature) for feature in feature_names(args.root)]
            if args.format == "json":
                output = json.dumps(states, ensure_ascii=False, indent=2)
            else:
                output = (
                    "\n\n".join(render_human(state) for state in states) or "（无 feature state）"
                    if args.history
                    else render_survey(states)
                )
        elif args.command == "packet":
            output = json.dumps(
                issue_packet(args.root, args.feature, args.slug),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif args.command == "close":
            output = json.dumps(
                close_issue(args.root, args.feature, args.slug), ensure_ascii=False, indent=2
            )
        elif args.command == "stats":
            output = json.dumps(stats(args.root), ensure_ascii=False, indent=2)
        else:
            output = json.dumps(gc_feature(args.root, args.feature, args.apply), ensure_ascii=False, indent=2)
    except (OSError, UnicodeError, ValueError) as exc:
        print("workflow-state: %s" % exc, file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
