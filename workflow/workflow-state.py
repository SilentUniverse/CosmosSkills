#!/usr/bin/env python3
"""Project tracked issue state, not the product's complete behavior or user objective."""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

ENGINEERING_ROOT = Path(__file__).resolve().parent
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from workflow_contract import (
    effective_verifier,
    issue_contract_digest,
    load_verifier_profile,
    validate_v3_completion,
)
from workflow_runtime import (
    assignment, check_contract, load_baseline, reading, read_text, require_settled,
    transaction, write_state,
)


ISSUE_NAME = re.compile(r"^(\d+)-.+\.md$")
PROFILE_NAME = re.compile(r"\bprofile:([A-Za-z][A-Za-z0-9_-]*)\b")
MAPPED_ACTION = re.compile(r"^(\s*-\s*#\d+\s*(?:→|->)\s*)`([^`]+)`")
ATTEMPT_HEAD = re.compile(r"^###\s+(?:尝试|失败|Attempt)(?:\s|—|-|$)", re.IGNORECASE)


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
    raw = read_text(path, encoding="utf-8-sig")
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


@reading
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


_PROFILE_UNSET = object()


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


@reading
def issue_packet(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    raw, issue_data = issue_state(root, feature, path)
    return _issue_packet(root, feature, slug, path, raw, issue_data)


def current_dispatch(root, feature, states, payload=None):
    require_settled(root)
    ledger = root / ".scratch" / feature / "wave-ledger.json"
    if payload is None:
        try:
            payload = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("packets require one current open dispatch") from exc
    waves = [
        wave
        for wave in payload.get("waves", [])
        if set(wave.get("dispatched", [])) - set(wave.get("closed", {}))
    ]
    if len(waves) != 1:
        raise ValueError("packets require one current open dispatch")
    wave = waves[0]
    outstanding = set(wave.get("dispatched", [])) - set(wave.get("closed", {}))
    requested = {slug for slug, _, _, _ in states}
    if requested != outstanding:
        raise ValueError(
            "packets must project the complete current open dispatch; expected %s"
            % ", ".join(sorted(outstanding))
        )
    baseline = wave.get("baseline_sha256")
    contracts = wave.get("contracts")
    load_baseline(root, baseline, payload.get("baselines"))
    if not isinstance(contracts, dict):
        raise ValueError("current open dispatch has no contract bindings")
    for slug, _, raw, _ in states:
        if contracts.get(slug) != issue_contract_digest(raw):
            raise ValueError("issue '%s' changed after dispatch; reconcile before execution" % slug)
    return wave


@reading
def issue_packets(root, feature, slugs):
    """Project one wave without repeated process startup or persistent output."""
    slugs = list(slugs)
    if not slugs:
        raise ValueError("packets requires at least one slug")
    duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if duplicates:
        raise ValueError("duplicate packet slug(s): %s" % ", ".join(duplicates))
    root = Path(root).resolve()
    states = []
    for slug in slugs:
        path = find_issue(root, feature, slug)
        raw, issue_data = issue_state(root, feature, path)
        states.append((slug, path, raw, issue_data))
    return _packets(root, feature, states)


def _packets(root, feature, states, payload=None):
    binding = current_dispatch(root, feature, states, payload)
    dispatch = {"wave": binding.get("wave"), "baseline_sha256": binding["baseline_sha256"]}
    if binding.get("execution"):
        dispatch["execution"] = binding["execution"]
    profile = (
        load_verifier_profile(root, feature)
        if any(str(data.get("contract_version", "")) == "3" for _, _, _, data in states)
        else _PROFILE_UNSET
    )
    packets = [_issue_packet(root, feature, slug, path, raw, data, profile)
               for slug, path, raw, data in states]
    for packet in packets:
        if binding.get("execution") and "effective_verifier" in packet:
            if binding.get("verifier_sha256", {}).get(packet["slug"]) != packet["effective_verifier"]["effective_sha256"]:
                raise ValueError("verifier profile changed after dispatch; reconcile before execution")
    return {
        "schema_version": 1,
        "dispatch": dispatch,
        "packets": packets,
    }


@reading
def worker_briefs(root, feature, slugs=(), compact=False):
    """Render the mechanical half of each open-wave worker brief.

    One brief per outstanding slug: the packet projection, the receipt-hit
    tokens the feature wave ledger recorded for that slug, and the tests-so-far
    manifest (live done cards' declared `test_paths`, derived, never persisted).
    The brief contract itself stays single-sourced in the tdd skill's DRAIN.md;
    this projection removes hand-assembly without adding policy."""
    root = Path(root).resolve()
    ledger = root / ".scratch" / feature / "wave-ledger.json"
    try:
        payload = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("briefs require one current open dispatch") from exc
    open_waves = [
        wave
        for wave in payload.get("waves", [])
        if set(wave.get("dispatched", [])) - set(wave.get("closed", {}))
    ]
    if len(open_waves) != 1:
        raise ValueError("briefs require one current open dispatch")
    wave = open_waves[0]
    outstanding = sorted(
        set(wave.get("dispatched", [])) - set(wave.get("closed", {}))
    )
    selected = sorted(slugs) if slugs else outstanding
    unknown = [slug for slug in selected if slug not in outstanding]
    if unknown:
        raise ValueError(
            "slug(s) not in the current open dispatch: %s" % ", ".join(unknown)
        )
    consumers = payload.get("preflight_consumers")
    if not isinstance(consumers, dict):
        consumers = {}
    tests_so_far = []
    states = {}
    for path in issue_paths(root, feature):
        raw, data = issue_state(root, feature, path)
        if path.parent.name != "archive" and path.stem in outstanding:
            states[path.stem] = (path.stem, path, raw, data)
        if data.get("status") != "done":
            continue
        for item in data.get("test_paths", []) or []:
            if item not in tests_so_far:
                tests_so_far.append(item)
    missing = set(outstanding) - set(states)
    if missing:
        raise ValueError("dispatched issue(s) missing: %s" % ", ".join(sorted(missing)))
    projected = _packets(root, feature, [states[slug] for slug in outstanding], payload)
    by_slug = {item["slug"]: item for item in projected["packets"]}
    result = {
        "schema_version": 1,
        "dispatch": projected["dispatch"],
        "brief_rules": "tdd/DRAIN.md — worker brief contract",
        "briefs": [
            {
                "slug": slug,
                "packet": by_slug[slug],
                "receipt_hits": sorted(
                    "receipt-hit:%s" % key
                    for key, assigned in consumers.items()
                    if isinstance(assigned, list) and slug in assigned
                ),
                "tests_so_far": tests_so_far,
            }
            for slug in selected
        ],
    }
    if compact:
        shared = {
            "brief_rules": result.pop("brief_rules"),
            "tests_so_far": sorted(tests_so_far),
        }
        for brief in result["briefs"]:
            brief.pop("tests_so_far")
            brief.pop("slug")
            brief["shared_ref"] = "#/shared"
        return {"schema_version": 2, "shared": shared,
                "dispatch": result["dispatch"], "briefs": result["briefs"]}
    return result


def close_issue(root, feature, slug, execution=None):
    with transaction(root):
        path = find_issue(Path(root).resolve(), feature, slug)
        current = assignment(root, feature, slug, execution)
        raw, data = issue_state(Path(root).resolve(), feature, path)
        check_contract(current, slug, raw, data, root=root, feature=feature)
        result = _close_issue(root, feature, slug, path, raw, data)
        if current and current.get("mode") == "direct":
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                code = _wave_driver().cmd_collect(str(root), [slug + "=green"], execution, feature=feature)
            if code:
                raise ValueError(output.getvalue().strip())
        return result


def _wave_driver():
    spec = importlib.util.spec_from_file_location("workflow_wave", ENGINEERING_ROOT / "tdd/scripts/drain-wave.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_issue(root, feature, slug):
    root = Path(root).resolve()
    path = find_issue(root, feature, slug)
    output = io.StringIO()
    with transaction(root):
        raw, data = issue_state(root, feature, path)
        packet = _issue_packet(root, feature, slug, path, raw, data)
        with redirect_stdout(output), redirect_stderr(output):
            code = _wave_driver().cmd_dispatch(str(root), [slug], direct=True, feature=feature)
        if code:
            raise ValueError(output.getvalue().strip())
        execution = next(line.removeprefix("execution: ") for line in output.getvalue().splitlines()
                         if line.startswith("execution: "))
        current = assignment(root, feature, slug, execution)
        check_contract(current, slug, raw, data, root=root, feature=feature)
        if ("effective_verifier" in packet and current.get("verifier_sha256", {}).get(slug)
                != packet["effective_verifier"]["effective_sha256"]):
            raise ValueError("verifier profile changed while preparing the direct input")
        return {"packet": packet,
                "execution": current["execution"], "baseline_sha256": current["baseline_sha256"]}


def _close_issue(root, feature, slug, path, raw, data):
    root = Path(root).resolve()
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
    write_state(root, path, "".join(updated))
    result = {
        "feature": feature,
        "slug": slug,
        "status": "done",
    }
    ledger = root / ".scratch" / feature / "wave-ledger.json"
    if not (ledger.is_file() and not ledger_closed(ledger)):
        candidates = gc_feature(root, feature, apply=False)["candidates"]
        if candidates:
            result["gc_candidates"] = candidates
    return result


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 6)


@reading
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
    lines = [
        "# %s — 已追踪交付记录: %d · 来源 digest %s"
        % (state["feature"], state["source_count"], state["source_digest"])
    ]
    if not state["delivered"]:
        lines.append("- （无已交付行为）")
    for item in state["delivered"]:
        summary = item["summary"] or "（无行为摘要）"
        lines.append("- %s — %s [%s]" % (item["slug"], summary, item["path"]))
    return "\n".join(lines)


@reading
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
        except (OSError, ValueError) as exc:
            raise ValueError("cannot determine active executions from unreadable ledger: %s" % ledger) from exc
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
    lines = ["# 工作流前沿"]
    for state in states:
        count = state["counts"]
        lines.append(
            "%s: ready %d · blocked %d · done %d · zombie %d"
            % (
                state["feature"],
                count["ready"],
                count["blocked"],
                count["done"],
                count["zombie"],
            )
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


def ledger_has_active_conflict(path):
    """A dismissed conflict is rewritten to red; any retained conflict is still a barrier."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(
        result == "conflict"
        for wave in payload.get("waves", [])
        for result in wave.get("closed", {}).values()
    )


def ledger_baseline_refs(path):
    """Return referenced global baselines, or None when a ledger is unreadable."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {
        digest
        for wave in payload.get("waves", [])
        for digest in [wave.get("baseline_sha256")]
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
    }


def released_baseline_artifacts(root, removed_ledger):
    """Baselines owned by this ledger and no other retained feature ledger."""
    released = ledger_baseline_refs(removed_ledger)
    if not released:
        return []
    retained = set()
    for path in (root / ".scratch").glob("*/wave-ledger.json"):
        if path == removed_ledger:
            continue
        references = ledger_baseline_refs(path)
        if references is None:
            return []
        retained.update(references)
    directory = root / ".scratch" / "wave-baselines"
    return [
        directory / (digest + ".json")
        for digest in sorted(released - retained)
        if (directory / (digest + ".json")).is_file()
    ]


def gc_feature(root, feature, apply=False):
    if apply:
        with transaction(root):
            return _gc_feature(root, feature, apply=True)
    require_settled(root)
    return _gc_feature(root, feature)


@reading
def _gc_feature(root, feature, apply=False):
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
    active_conflict = ledger.is_file() and ledger_has_active_conflict(ledger)
    candidates = []
    if not ready and not open_wave and not active_conflict:
        for path in (feature_dir / "preflight-receipt.json", ledger):
            if path.is_file():
                candidates.append(path)
        if ledger in candidates:
            candidates.extend(released_baseline_artifacts(root, ledger))
    removed = []
    if apply:
        for path in candidates:
            path.unlink()
            removed.append(path.relative_to(root).as_posix())
    return {
        "feature": feature,
        "ready": ready,
        "open_wave": open_wave,
        "active_conflict": active_conflict,
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
    survey.add_argument(
        "--feature",
        action="append",
        default=None,
        help="limit the survey to this feature (repeatable); default is every feature",
    )
    gc = sub.add_parser("gc")
    gc.add_argument("root")
    gc.add_argument("feature")
    gc.add_argument("--apply", action="store_true")
    packet = sub.add_parser("packet")
    packet.add_argument("root")
    packet.add_argument("feature")
    packet.add_argument("slug")
    start = sub.add_parser("start")
    start.add_argument("root")
    start.add_argument("feature")
    start.add_argument("slug")
    packets = sub.add_parser("packets")
    packets.add_argument("root")
    packets.add_argument("feature")
    packets.add_argument("slugs", nargs="+")
    briefs = sub.add_parser("briefs")
    briefs.add_argument("root")
    briefs.add_argument("feature")
    briefs.add_argument("slugs", nargs="*")
    briefs.add_argument("--compact", action="store_true")
    close = sub.add_parser("close")
    close.add_argument("root")
    close.add_argument("feature")
    close.add_argument("slug")
    close.add_argument("--execution")
    stats_cmd = sub.add_parser("stats")
    stats_cmd.add_argument("root")
    return command


@reading
def survey_states(root, history=False, features=None):
    project = inspect_feature if history else feature_frontier
    names = list(features) if features else feature_names(root)
    return [project(root, feature) for feature in names]


def main(argv=None):
    # Stock Windows consoles default to the ANSI code page; never let an
    # un-encodable character kill a survey mid-run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = parser().parse_args((argv or sys.argv)[1:])
    try:
        if args.command == "inspect":
            state = inspect_feature(args.root, args.feature)
            output = json.dumps(state, ensure_ascii=False, indent=2) if args.format == "json" else render_human(state)
        elif args.command == "survey":
            states = survey_states(args.root, args.history, args.feature)
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
        elif args.command == "start":
            output = json.dumps(start_issue(args.root, args.feature, args.slug), ensure_ascii=False, separators=(",", ":"))
        elif args.command == "packets":
            output = json.dumps(
                issue_packets(args.root, args.feature, args.slugs),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif args.command == "briefs":
            output = json.dumps(
                worker_briefs(args.root, args.feature, args.slugs, compact=args.compact),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif args.command == "close":
            output = json.dumps(
                close_issue(args.root, args.feature, args.slug, args.execution), ensure_ascii=False, indent=2
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
