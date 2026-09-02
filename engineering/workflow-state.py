#!/usr/bin/env python3
"""Read feature state without materializing a second source of truth."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


ISSUE_NAME = re.compile(r"^(\d+)-.+\.md$")


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


def contract_digest(raw):
    contract = raw.split("\n## Comments", 1)[0]
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def issue_paths(root, feature):
    issue_dir = Path(root) / ".scratch" / feature / "issues"
    if not issue_dir.is_dir():
        raise ValueError("feature '%s' has no issue directory" % feature)
    paths = [path for path in issue_dir.glob("*.md") if path.is_file()]
    archive = issue_dir / "archive"
    if archive.is_dir():
        paths.extend(path for path in archive.glob("*.md") if path.is_file())
    return sorted(paths)


def issue_record(root, feature, path):
    raw = path.read_text(encoding="utf-8")
    data = frontmatter(raw, path)
    if data.get("status") != "done":
        return None
    if data.get("type") != "issue" or data.get("feature") != feature:
        raise ValueError("%s: done issue identity does not match feature '%s'" % (path, feature))
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
    issue_dir = Path(root) / ".scratch" / feature / "issues"
    if not issue_dir.is_dir():
        raise ValueError("feature '%s' has no issue directory" % feature)
    path = issue_dir / ("%s.md" % slug)
    if path.is_file():
        return path
    raise ValueError("issue '%s' not found in feature '%s'" % (slug, feature))


def issue_packet(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw = path.read_text(encoding="utf-8")
    data = {key: value for key, value in frontmatter_rich(raw, path).items()}
    return {
        "schema_version": 1,
        "slug": slug,
        "feature": feature,
        "status": data.get("status"),
        "category": data.get("category", "enhancement"),
        "refines": data.get("refines") or None,
        "blocked_by": data.get("blocked_by", []),
        "test_paths": data.get("test_paths", []),
        "touches": data.get("touches", []),
        "summary": section_summary(raw),
        "context": section_lines(raw, "相关面"),
        "digest": contract_digest(raw),
        "source": path.relative_to(root).as_posix(),
    }


def _verify_v3_receipt(root, raw, slug):
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("- receipt:"):
            continue
        relative = s[len("- receipt:"):].split("；")[0].split(";")[0].strip().strip("` ")
        parts = relative.replace("\\", "/").split("/")
        if (
            not relative.endswith(".json")
            or len(parts) < 4
            or parts[0] != ".scratch"
            or parts[2] != "receipts"
            or ".." in parts
        ):
            raise ValueError(
                "issue '%s' receipt path must stay under .scratch/<feat>/receipts/: %s"
                % (slug, relative)
            )
        path = root.joinpath(*parts)
        if not path.is_file():
            raise ValueError("issue '%s' receipt missing: %s" % (slug, relative))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError("issue '%s' receipt not valid JSON: %s" % (slug, exc))
        if payload.get("outcome") != "pass":
            raise ValueError(
                "issue '%s' receipt outcome %r != pass" % (slug, payload.get("outcome"))
            )
        return
    raise ValueError("issue '%s' contract v3 record has no receipt line" % slug)


def close_issue(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw = path.read_text(encoding="utf-8")
    data = frontmatter(raw, path)
    if data.get("status") != "ready":
        raise ValueError(
            "issue '%s' is '%s'; close requires status: ready" % (slug, data.get("status"))
        )
    if "### 完成" not in raw:
        raise ValueError("issue '%s' has no ### 完成 record" % slug)
    if data.get("contract_version") == "3":
        _verify_v3_receipt(root, raw, slug)
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
        raw = path.read_text(encoding="utf-8")
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
        if path.parent.name == "archive":
            continue
        raw = path.read_text(encoding="utf-8")
        if frontmatter(raw, path).get("status") == "ready":
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
            states = [inspect_feature(args.root, feature) for feature in feature_names(args.root)]
            if args.format == "json":
                output = json.dumps(states, ensure_ascii=False, indent=2)
            else:
                output = "\n\n".join(render_human(state) for state in states) or "（无 feature state）"
        elif args.command == "packet":
            output = json.dumps(
                issue_packet(args.root, args.feature, args.slug), ensure_ascii=False, indent=2
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
