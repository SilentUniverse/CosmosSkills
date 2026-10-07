#!/usr/bin/env python
# Deterministic spec review surface: parses R/D/S anchors from a feature PRD,
# renders the human Full/Delta review HTML, and runs the one-shot localhost
# review bridge. Stdlib only; no model calls. Exit: 0 ok, 1 violation/timeout,
# 2 usage.
# Invoke: python spec-review.py <render|review|validate> <repo-root> <feature> [options]
# If the `python` interpreter is missing, python3 spec-review.py ...; never retry
# python3 after a non-zero exit (that is a contract violation).
#
import argparse
import hashlib
import hmac
import html
import json
import re
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ENGINEERING_ROOT = Path(__file__).resolve().parents[2]
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
from evidence import atomic_write, file_lock, write_record

REVIEW_STATE = "spec-review.json"
R_BULLET = re.compile(r"^\s*[-*]\s+(R\d+)\s*[—\-–]\s*(.+)$")
BEFORE_LINE = re.compile(r"^\s+Before\s*[:：]\s*(.+)$", re.IGNORECASE)
D_HEAD = re.compile(r"^#{2,4}\s+(D\d+)\s*[—\-–:>]?\s*(.*)$")
REFS_LINE = re.compile(r"^\s*Refs\s*[:：]\s*(.*)$", re.IGNORECASE)
META_LINE = re.compile(
    r"^\s*(Refs\s*[:：]|Door\s*[:：]|Blast\s+radius\s*[:：]|Review\s*[:：])", re.IGNORECASE
)
META_DOOR = re.compile(r"Door\s*[:：]\s*(one-way|two-way)", re.IGNORECASE)
META_BLAST = re.compile(r"Blast\s+radius\s*[:：]\s*([^\s;；]+)", re.IGNORECASE)
META_HUMAN = re.compile(r"Review\s*[:：]\s*human\s*$", re.IGNORECASE)
S_ROW = re.compile(r"^\|\s*(S\d+)\s*([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
S_CANDIDATE = re.compile(r"^\|\s*S\d+")
WHY_LINE = re.compile(r"^\s*(Why|理由|依据)\s*[:：]", re.IGNORECASE)
TEST_ROW = re.compile(r"^\|\s*(R\d+)\s*\|")
C_BULLET = re.compile(r"^\s*[-*]\s+(C\d+)\s*[—\-–]\s*(.+)$")
SCOPE_LINE = re.compile(r"^\s*[-*]\s+(IN|OUT)\s*[:：]\s*(.+)$", re.IGNORECASE)
PRD_NAME = re.compile(r"^PRD(-v\d+)?\.md$")
ID_TOKEN = re.compile(r"^(R|D|S)(\d+)$")
NOTE_TOKEN = re.compile(r"^(C|K|Q)\d+$")
REVIEW_TOKENS = ("key", "routine", "verification")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SUBMIT_CAP = 65536
ACCEPTED_SNAPSHOT = "spec-accepted.md"
SECTION_LABELS = {"section:problem": "问题", "section:solution": "预期结果",
                  "section:scope": "范围", "section:acceptance": "端到端验收",
                  "section:context": "补充约束与正文", "section:change": "修订理由"}


def valid_item_id(value):
    return isinstance(value, str) and (re.fullmatch(r"[RDSCKQ]\d+", value) is not None
                                      or value in SECTION_LABELS)


def normalized_text(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def prd_digest(path):
    return hashlib.sha256(normalized_text(path).encode("utf-8")).hexdigest()


def item_hash(kind, item_id, canonical):
    material = "%s\n%s\n%s" % (kind, item_id, canonical)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def h2_sections(text):
    """Map of '## ' heading text -> body lines (deeper headings stay in the body)."""
    sections = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def find_section(sections, word):
    for heading, body in sections.items():
        if word in heading:
            return body
    return None


def ref_tokens(value):
    return [token for token in re.split(r"[\s,，、;；]+", (value or "").strip()) if token]


class Model(object):
    """Parsed R/D/S anchors. Empty families are legal (draft PRDs)."""

    def __init__(self):
        self.requirements = []   # {"id", "text"}
        self.decisions = []      # {"id", "title", "lines", "refs", "door", "blast", "human"}
        self.slices = []         # {"id", "label", "outcome", "covers", "depends", "review"}
        self.test_rows = []      # {"id", "cells"}
        self.scope_in = []       # in-scope lines
        self.scope_out = []      # out-of-scope lines (范围 OUT, or 不在本次范围内 fallback)
        self.contracts = []      # {"id", "text"}
        self.risks = []          # bullet texts (风险)
        self.questions = []      # bullet texts (尚未明确)
        self.controls = {key: "" for key in SECTION_LABELS}
        self.slice_candidates = 0
        self.has_ids = False
        self.problems = []

    def item_ids(self):
        return (
            [item["id"] for item in self.requirements]
            + [item["id"] for item in self.decisions]
            + [item["id"] for item in self.slices]
        )

    def item_texts(self):
        table = dict(self.controls)
        for item in self.requirements:
            rows = [" | ".join(row["cells"]) for row in self.test_rows if row["id"] == item["id"]]
            table[item["id"]] = "\n".join([item["text"], item.get("before", "")] + rows)
        for item in self.decisions:
            table[item["id"]] = "\n".join(line.rstrip() for line in item["lines"]).strip()
        for item in self.slices:
            table[item["id"]] = " | ".join(
                [item["id"], item["label"], item["outcome"], " ".join(item["covers"]),
                 " ".join(item["depends"]), item["review"]]
            )
        table.update({item["id"]: item["text"] for item in self.contracts})
        for prefix, lines in (("K", self.risks), ("Q", self.questions)):
            table.update({"%s%d" % (prefix, n): value for n, value in enumerate(lines, 1)})
        return table

    def hashes(self):
        return {key: item_hash(key.split(":")[0] if ":" in key else key[0], key, value)
                for key, value in self.item_texts().items()}

    def refs_of(self, item_id):
        for item in self.decisions:
            if item["id"] == item_id:
                return set(item["refs"])
        for item in self.slices:
            if item["id"] == item_id:
                return set(item["covers"]) | set(item["depends"])
        return set()


def parse_model(text):
    sections = h2_sections(text)
    model = Model()

    scenarios = find_section(sections, "用户场景")
    if scenarios:
        for line in scenarios:
            match = R_BULLET.match(line)
            if match:
                model.requirements.append({"id": match.group(1),
                                           "text": match.group(2).strip(),
                                           "before": ""})
                continue
            before = BEFORE_LINE.match(line)
            if before:
                if not model.requirements or model.requirements[-1]["before"]:
                    model.problems.append("Before must appear once after its R#")
                else:
                    model.requirements[-1]["before"] = before.group(1).strip()

    decisions = find_section(sections, "实现决策")
    if decisions:
        current = None
        for line in decisions:
            head = D_HEAD.match(line)
            if head:
                current = {
                    "id": head.group(1),
                    "title": head.group(2).strip(),
                    "lines": [line.rstrip()],
                    "refs": [],
                    "door": "",
                    "blast": "",
                    "human": False,
                }
                model.decisions.append(current)
                continue
            if current is None:
                continue
            current["lines"].append(line.rstrip())
            if not META_LINE.match(line):
                continue
            refs = REFS_LINE.match(line)
            if refs:
                if current.get("refs_seen"):
                    model.problems.append("%s repeats Refs; use one declaration" % current["id"])
                current["refs_seen"] = True
                current["refs"] = ref_tokens(refs.group(1))
            door = META_DOOR.search(line)
            if door and not current["door"]:
                current["door"] = door.group(1).lower()
            blast = META_BLAST.search(line)
            if blast and not current["blast"]:
                current["blast"] = blast.group(1).strip()
            if META_HUMAN.match(line):
                current["human"] = True

    slices = find_section(sections, "实施切片")
    if slices:
        for line in slices:
            if S_CANDIDATE.match(line):
                model.slice_candidates += 1
            match = S_ROW.match(line)
            if not match:
                continue
            depends = ref_tokens(match.group(5))
            model.slices.append({
                "id": match.group(1),
                "label": match.group(2).strip(),
                "outcome": match.group(3).strip(),
                "covers": ref_tokens(match.group(4)),
                "depends": [] if depends == ["-"] else depends,
                "review": match.group(6).strip().lower() or "routine",
            })

    testing = find_section(sections, "测试决策")
    if testing:
        for line in testing:
            match = TEST_ROW.match(line)
            if not match or re.match(r"^\|[\s:-]+\|", line):
                continue
            model.test_rows.append({
                "id": match.group(1),
                "cells": [cell.strip() for cell in line.strip().strip("|").split("|")],
            })

    scope = find_section(sections, "范围")
    if scope:
        for line in scope:
            match = SCOPE_LINE.match(line)
            if not match:
                continue
            if match.group(1).upper() == "IN":
                model.scope_in.append(match.group(2).strip())
            else:
                model.scope_out.append(match.group(2).strip())
    if not model.scope_out:
        out_section = find_section(sections, "不在本次范围内")
        model.scope_out = [
            re.sub(r"^[-*]\s+", "", line.strip())
            for line in out_section or [] if line.strip()
        ]

    contracts = find_section(sections, "不变量")
    if contracts:
        for line in contracts:
            match = C_BULLET.match(line)
            if match:
                model.contracts.append({"id": match.group(1), "text": match.group(2).strip()})

    for word, target in (("风险", model.risks), ("尚未明确", model.questions)):
        section = find_section(sections, word)
        for line in section or []:
            stripped = re.sub(r"^[-*]\s+", "", line.strip())
            if stripped:
                target.append(stripped)

    prefix = text.split("\n## ", 1)[0] if not text.startswith("## ") else ""
    if prefix.startswith("---\n"):
        header, _, prefix = prefix[4:].partition("\n---")
        prefix = "\n".join(line for line in header.splitlines()
                           if not re.match(r"^(version|supersedes|created):", line)) + prefix
    residual = [prefix]
    for heading, lines in sections.items():
        if lines is scenarios:
            lines = [line for line in lines if not R_BULLET.match(line) and not BEFORE_LINE.match(line)]
        elif lines is decisions:
            first = next((n for n, line in enumerate(lines) if D_HEAD.match(line)), len(lines))
            lines = lines[:first]
        elif lines is slices:
            lines = [line for line in lines if not S_ROW.match(line)]
        elif lines is testing:
            lines = [line for line in lines if not TEST_ROW.match(line)]
        elif lines is contracts:
            lines = [line for line in lines if not C_BULLET.match(line)]
        elif lines is find_section(sections, "风险") or lines is find_section(sections, "尚未明确"):
            continue
        else:
            key = next((key for word, key in (("问题", "section:problem"), ("方案", "section:solution"),
                        ("范围", "section:scope"), ("端到端验证", "section:acceptance"),
                        ("取代理由", "section:change")) if word in heading), None)
            if key:
                model.controls[key] += "\n" + heading + "\n" + "\n".join(lines).strip()
                continue
        residual.extend([heading] + [line.rstrip() for line in lines if line.strip()])
    model.controls["section:context"] = "\n".join(residual).strip()

    model.has_ids = bool(model.requirements or model.decisions or model.slices)
    return model


def cyclic_ids(graph):
    remaining = {key: [dep for dep in deps if dep in graph] for key, deps in graph.items()}
    changed = True
    while changed:
        changed = False
        for key in list(remaining):
            if not [dep for dep in remaining[key] if dep in remaining]:
                del remaining[key]
                changed = True
    return sorted(remaining)


def validate_model(model):
    """Hard problems gate render/validate; advisory warnings do not (model_warnings)."""
    problems = list(model.problems)
    for family in (model.requirements, model.decisions, model.slices, model.contracts):
        seen = set()
        for item in family:
            if item["id"] in seen:
                problems.append("duplicate id %s" % item["id"])
            seen.add(item["id"])
    if not model.has_ids:
        return problems
    requirement_ids = {item["id"] for item in model.requirements}
    decision_ids = {item["id"] for item in model.decisions}
    slice_ids = {item["id"] for item in model.slices}
    if model.slice_candidates != len(model.slices):
        problems.append(
            "实施切片: %d of %d slice row(s) failed to parse; expected "
            "'| S# [label] | outcome | covers | depends | review |'" % (
                model.slice_candidates - len(model.slices), model.slice_candidates)
        )
    for item in model.decisions:
        for token in item["refs"]:
            match = ID_TOKEN.match(token)
            if not match or match.group(1) != "R":
                problems.append("%s refs %r must reference R#" % (item["id"], token))
            elif token not in requirement_ids:
                problems.append("%s references undeclared %s" % (item["id"], token))
    for item in model.slices:
        for token in item["covers"]:
            if token not in requirement_ids and token not in decision_ids:
                problems.append("%s covers undeclared %s" % (item["id"], token))
        for token in item["depends"]:
            match = ID_TOKEN.match(token)
            if not match or match.group(1) != "S":
                problems.append("%s depends %r must reference S#" % (item["id"], token))
            elif token not in slice_ids:
                problems.append("%s depends on undeclared %s" % (item["id"], token))
        if item["review"] not in REVIEW_TOKENS:
            problems.append(
                "%s review %r not in %s" % (item["id"], item["review"], "|".join(REVIEW_TOKENS))
            )
    for row in model.test_rows:
        if row["id"] not in requirement_ids:
            problems.append("测试决策 references undeclared %s" % row["id"])
    for cyclic in cyclic_ids({item["id"]: item["depends"] for item in model.slices}):
        problems.append("%s is in (or depends on) a Depends cycle" % cyclic)
    return problems


def model_warnings(model):
    if not model.has_ids:
        return []
    covered = {row["id"] for row in model.test_rows}
    return [
        "%s has no 测试决策 row" % item["id"]
        for item in model.requirements
        if item["id"] not in covered
    ]


def classify_delta(model, old_items):
    """Item-level classification against the previous rendered hashes."""
    fresh = model.hashes()
    result = {"ADDED": [], "MODIFIED": [], "REMOVED": [], "AFFECTED": [], "UNCHANGED": []}
    for item_id, digest in sorted(fresh.items()):
        if item_id not in old_items:
            result["ADDED"].append(item_id)
        elif old_items[item_id] != digest:
            result["MODIFIED"].append(item_id)
        else:
            result["UNCHANGED"].append(item_id)
    result["REMOVED"] = sorted(set(old_items) - set(fresh))
    changed = set(result["ADDED"] + result["MODIFIED"] + result["REMOVED"])
    global_change = any(not ID_TOKEN.fullmatch(key) and key != "section:change" for key in changed)
    affected = set()
    while True:
        added = {key for key in result["UNCHANGED"] if key not in affected
                 and ((global_change and ID_TOKEN.fullmatch(key))
                      or model.refs_of(key) & (changed | affected))}
        if not added:
            break
        affected.update(added)
    result["AFFECTED"] = sorted(affected)
    result["UNCHANGED"] = [i for i in result["UNCHANGED"] if i not in affected]
    return result


def resolve_head_prd(feature_dir):
    """The single live PRD (not superseded by any sibling). Error on 0 or many."""
    files = sorted(
        name for name in os.listdir(feature_dir)
        if PRD_NAME.match(name) and os.path.isfile(os.path.join(feature_dir, name))
    )
    if not files:
        raise ValueError("no PRD.md/PRD-vN.md under %s" % feature_dir)
    superseded = set()
    for name in files:
        match = re.search(
            r"^supersedes:\s*(\S+)",
            normalized_text(os.path.join(feature_dir, name)),
            re.MULTILINE,
        )
        if match:
            superseded.add(match.group(1).strip())
    live = [name for name in files if name not in superseded]
    if len(live) != 1:
        raise ValueError("PRD chain must leave exactly one live head, found: %s" % ", ".join(live))
    return live[0]


def state_problems(state):
    if not isinstance(state, dict):
        return ["spec-review.json must be a JSON object"]
    problems = []
    if type(state.get("schema_version")) is not int or state.get("schema_version") != 1:
        problems.append("spec-review.json schema_version must be 1")
    for key in ("spec", "accepted_spec"):
        value = state.get(key)
        if (key == "spec" or value is not None) and (not isinstance(value, str) or not PRD_NAME.fullmatch(value)):
            problems.append("spec-review.json %s must name PRD.md/PRD-vN.md" % key)
    for key in ("accepted_digest", "last_rendered_digest"):
        value = state.get(key)
        if value is not None and (not isinstance(value, str) or not HEX64.fullmatch(value)):
            problems.append("spec-review.json %s must be null or a 64-character SHA-256" % key)
    for key in ("accepted_items", "last_rendered_items"):
        value = state.get(key)
        if value is None:
            continue
        if not isinstance(value, dict) or (key == "accepted_items" and not value):
            problems.append("spec-review.json %s must be %san object" % (key, "non-empty " if key == "accepted_items" else ""))
        elif any(not valid_item_id(item) or not isinstance(digest, str) or not HEX64.fullmatch(digest)
                 for item, digest in value.items()):
            problems.append("spec-review.json %s contains a malformed entry" % key)
    return problems


def load_state(feature_dir):
    path = os.path.join(feature_dir, REVIEW_STATE)
    if not os.path.isfile(path):
        return {}
    try:
        state = json.loads(normalized_text(path))
    except ValueError as exc:
        raise ValueError("%s is not valid JSON: %s" % (path, exc))
    problems = state_problems(state)
    if problems:
        raise ValueError("; ".join(problems))
    return state


def save_state(feature_dir, state):
    atomic_write(Path(feature_dir) / REVIEW_STATE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def render_state(model, prd_name, digest, previous):
    """Next spec-review.json: keep the acceptance half, refresh the rendered half."""
    return {
        "schema_version": 1,
        "spec": prd_name,
        "last_rendered_digest": digest,
        "last_rendered_items": model.hashes(),
        "accepted_digest": previous.get("accepted_digest"),
        "accepted_spec": previous.get("accepted_spec"),
        "accepted_items": previous.get("accepted_items"),
    }


def accepted_snapshot_path(feature_dir, state):
    """Resolve the accepted snapshot: the digest-named archive, or the legacy alias."""
    accepted = state.get("accepted_digest")
    if isinstance(accepted, str) and HEX64.fullmatch(accepted):
        archive = Path(feature_dir) / "spec-acceptances" / (accepted + ".md")
        if archive.is_file():
            return archive
    return Path(feature_dir) / ACCEPTED_SNAPSHOT


def record_acceptance(state, feature_dir, prd_path, digest, model):
    """Pin the accepted bytes: digest, item ledger, and a durable snapshot file.

    The digest-named archive stores the normalized PRD text so its own prd_digest equals
    accepted_digest; editing it in place is detectable by any gate.
    """
    state["accepted_digest"] = digest
    state["accepted_spec"] = os.path.basename(prd_path)
    state["accepted_items"] = model.hashes()
    text = normalized_text(prd_path)
    archive = Path(feature_dir) / "spec-acceptances" / (digest + ".md")
    if archive.exists() and archive.read_text(encoding="utf-8") != text:
        raise ValueError("accepted Spec archive changed")
    atomic_write(archive, text)
    return state


def acceptance_problems(feature_dir, state, prd_name, digest):
    """Acceptance binding shared by validation and execution admission."""
    accepted = state.get("accepted_digest")
    if not isinstance(accepted, str) or not HEX64.match(accepted):
        return ["%s has no recorded human acceptance" % prd_name]
    problems = []
    snapshot = accepted_snapshot_path(feature_dir, state)
    if snapshot.is_file():
        if prd_digest(snapshot) != accepted:
            problems.append("accepted snapshot no longer matches accepted_digest")
    elif state.get("accepted_items") is not None:
        problems.append("acceptance ledger exists but the accepted snapshot is missing")
    if accepted != digest:
        problems.append(
            "accepted_digest %s… != current %s digest %s…; re-review before materializing"
            % (accepted[:12], prd_name, digest[:12])
        )
    return problems


def parent_contract(feature_dir, raw):
    workflow_root = str(Path(__file__).resolve().parents[2])
    if workflow_root not in sys.path:
        sys.path.insert(0, workflow_root)
    from workflow_contract import parse_parent_pointer
    pointer = parse_parent_pointer(raw)
    if pointer is None:
        return None
    source = Path(feature_dir) / pointer["spec"]
    if source.resolve().parent != Path(feature_dir).resolve() or not source.is_file():
        raise ValueError("Parent PRD must exist inside its feature: %s" % pointer["spec"])
    model = parse_model(normalized_text(source))
    problems = validate_model(model)
    if problems:
        raise ValueError("Parent PRD is invalid: %s" % "; ".join(problems))
    slices = {item["id"]: item for item in model.slices}
    if pointer["slice"] not in slices:
        raise ValueError("Parent references undeclared %s" % pointer["slice"])
    refs = set(pointer["refs"])
    if not set(slices[pointer["slice"]]["covers"]) <= refs:
        raise ValueError("Parent refs must cover the named slice's Covers")
    if not refs <= set(model.item_ids()):
        raise ValueError("Parent references undeclared R#/D#")
    needed = refs | {pointer["slice"]}
    while True:
        expanded = needed | set().union(*(model.refs_of(key) for key in needed))
        if expanded == needed:
            break
        needed = expanded
    return {"pointer": pointer, "model": model, "needed": needed}


def _design_matches(source, accepted, needed):
    source_hashes, accepted_hashes = source.hashes(), accepted.hashes()
    controls = {key for key in set(source_hashes) | set(accepted_hashes)
                if not ID_TOKEN.fullmatch(key) and key != "section:change"}
    return all(source_hashes.get(key) == accepted_hashes.get(key) for key in needed | controls)


def acceptance_barrier(feature_dir, issues=None):
    """None when dispatch may proceed; only absence of review state skips the gate."""
    feature_dir = Path(feature_dir)
    if not (feature_dir / REVIEW_STATE).exists():
        return None
    try:
        state = load_state(feature_dir)
        prd_name = resolve_head_prd(feature_dir)
        digest = prd_digest(feature_dir / prd_name)
        problems = acceptance_problems(
            feature_dir, state, prd_name, digest
        )
        if issues is not None:
            snapshot = accepted_snapshot_path(feature_dir, state)
            accepted_digest = state.get("accepted_digest")
            integrity = acceptance_problems(feature_dir, state, prd_name, accepted_digest)
            recorded_source = state.get("accepted_spec")
            if recorded_source and (not isinstance(recorded_source, str) or not PRD_NAME.fullmatch(recorded_source)
                    or prd_digest(feature_dir / recorded_source) != accepted_digest):
                integrity.append("accepted source PRD changed; preserve it and write a superseding PRD")
            if not integrity:
                accepted = parse_model(normalized_text(snapshot)) if snapshot.is_file() else None
                candidate = parse_model(normalized_text(feature_dir / prd_name))
                strict_parent = "section:context" in (state.get("accepted_items") or {})
                scoped = validate_model(candidate)
                for name, raw in issues:
                    parent = parent_contract(feature_dir, raw)
                    if parent is None:
                        if strict_parent or digest != accepted_digest:
                            scoped.append("%s: a valid Parent design pointer is required; /spec must bind unassigned open cards to their PRD slice, preserving refines and done history" % name)
                        continue
                    if accepted is None:
                        if digest != accepted_digest:
                            scoped.append("%s: accepted snapshot is required for scoped acceptance" % name)
                        continue
                    if not _design_matches(parent["model"], accepted, parent["needed"]):
                        scoped.append("%s: Parent design is outside accepted anchors or global constraints" % name)
                    elif not _design_matches(candidate, accepted, parent["needed"]):
                        scoped.append("%s: pending PRD changes affect its design or global constraints" % name)
                problems = scoped
            else:
                problems = integrity
    except (OSError, ValueError) as exc:
        problems = ["cannot verify acceptance binding: %s" % exc]
    if not problems:
        return None
    return (
        "%s; run spec-review.py validate <repo-root> <feature> --require-accepted "
        "and resolve the reported acceptance binding before dispatch" % "; ".join(problems)
    )


CSS = """*{box-sizing:border-box}
.compare{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;font-size:15px;line-height:1.7}
.topnav{flex-wrap:wrap}
body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;color:#1c2733;background:#eef2f6;font-size:18px;line-height:1.8}
main{padding:0 28px 48px}
.topnav{position:sticky;top:0;z-index:10;display:flex;gap:18px;align-items:center;background:#fffffff2;backdrop-filter:blur(6px);border-bottom:1px solid #d5dde5;padding:12px 0;font-size:15.5px}
.topnav .brand{font-weight:700;color:#2b5c8a}
.topnav a{color:#5a6b7b;text-decoration:none}
.topnav a b{color:#a23b3b}
h1{font-size:26px;margin:16px 0 2px;display:flex;align-items:center}
h2{font-size:19.5px;margin:36px 0 14px;padding-bottom:6px;border-bottom:2px solid #d5dde5}
h3{font-size:16.5px;margin:18px 0 8px;color:#5a6b7b;font-weight:600}
.badge{display:inline-block;font-size:13px;padding:2px 10px;border-radius:10px;background:#dce8f5;margin-left:8px;font-weight:400}
.badge.delta{background:#f5e3c8}
.hero{background:#fff;border:1px solid #d5dde5;border-radius:10px;padding:16px 18px;margin-top:14px}
.counts{margin:4px 0 0;color:#345;font-size:16px}
.counts.delta{color:#8a6d1a}
.card.contract{border-left:4px solid #2b5c8a}
.card.note{border-left:4px solid #8a6d1a}
.cards{display:grid;gap:16px;grid-template-columns:1fr;align-items:stretch}
@media(min-width:1000px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{background:#fff;border:1px solid #d5dde5;border-radius:10px;padding:15px 20px;display:flex;flex-direction:column}
.card.decide{border-left:4px solid #a23b3b}
.card.decide.keyslice{border-left-color:#8a6d1a}
.card .title{font-weight:600;font-size:18px}
.card .meta{font-size:14.5px;color:#5a6b7b;margin-top:6px}
.q{font-size:19.5px;font-weight:700;line-height:1.5;margin:0 0 2px}
.q .door,.q .risk{margin-left:6px;font-size:12.5px}
.body{margin-top:10px;line-height:1.9;font-size:17.5px}
.body p{margin:0 0 12px}
.body p:last-child{margin-bottom:0}
.body ul{margin:0 0 12px;padding-left:22px}
.body li{margin:0 0 6px}
.body ul:last-child{margin-bottom:0}
.door{color:#a23b3b;font-weight:600}.risk{color:#8a6d1a}
a.ref{display:inline-block;font-size:14px;padding:1px 8px;border-radius:9px;background:#dce8f5;color:#2b5c8a;text-decoration:none;margin-right:4px}
.scopecols{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.scopecols>div>b{display:block;font-size:13px;color:#5a6b7b;margin-bottom:6px}
.scopecols .in,.scopecols .out{margin:4px 0}
.scopecols .in{color:#2c6e49}.scopecols .out{color:#8a5a2b}
table{border-collapse:collapse;width:100%;background:#fff;font-size:16px;border:1px solid #d5dde5}
th,td{border:0;border-bottom:1px solid #e3e9ef;padding:10px 12px;text-align:left;vertical-align:top}
th{font-size:13.5px;color:#5a6b7b;border-bottom:2px solid #d5dde5}
tr:last-child td{border-bottom:0}
textarea{width:100%;min-height:72px;font-family:ui-monospace,monospace;font-size:13.5px;padding:8px;border:1px solid #d5dde5;border-radius:8px}
.comment textarea{min-height:60px;font-family:inherit;font-size:16.5px}
.comment{margin-top:auto;padding-top:12px}
.before{color:#8a5a2b}.after{color:#2c6e49;font-weight:600}
#feedback-text{min-height:110px}
button{margin-top:10px;padding:7px 20px;border-radius:8px;border:1px solid #2b5c8a;background:#2b5c8a;color:#fff;cursor:pointer;font-size:14px}
button:disabled{opacity:.5}
.foot{margin-top:30px;font-size:13.5px;color:#5a6b7b}
.state{font-size:13px;padding:1px 7px;border-radius:9px;margin-right:6px}
.state.MODIFIED,.state.AFFECTED{background:#f5e3c8}.state.ADDED{background:#d9ecd9}
.state.REMOVED{background:#f2d4d4}.state.UNCHANGED{background:#e8edf2}
.muted{color:#5a6b7b;font-size:15px}
"""


def state_badge(mode, delta, item_id):
    if mode != "delta":
        return ""
    for state in ("ADDED", "MODIFIED", "REMOVED", "AFFECTED", "UNCHANGED"):
        if item_id in delta.get(state, []):
            label = {"ADDED": "新增", "MODIFIED": "调整", "REMOVED": "移除",
                     "AFFECTED": "关联变化", "UNCHANGED": "沿用"}[state]
            return '<span class="state %s">%s</span>' % (state, label)
    return ""


def review_items(model):
    """The decision area: direction decisions (`Review: human`) plus one-way contract doors."""
    posed, seen = [], set()
    for item in model.decisions:
        if item["human"]:
            posed.append(item)
            seen.add(item["id"])
    for item in model.decisions:
        if item["door"] == "one-way" and item["id"] not in seen:
            posed.append(item)
            seen.add(item["id"])
    return posed


def decision_body(item):
    """(summary paragraph, remaining lines) with machine-readable meta lines removed."""
    body = [line for line in item["lines"][1:] if not META_LINE.match(line)]
    start = 0
    while start < len(body) and not body[start].strip():
        start += 1
    end = start
    while end < len(body) and body[end].strip():
        end += 1
    return body[start:end], body[end:]


HARD_ENDERS = "。；？！"
ASCII_ENDERS = ".;?!"
SOFT_ENDERS = "，、→"
SOFT_LIMIT = 90


def _break_points(line, enders, space_gated=False, parens=True, code=True):
    """Split offsets after ender chars, outside backtick spans (and parentheses)."""
    points, in_code, depth = [], False, 0
    for index, ch in enumerate(line):
        if code and ch == "`":
            in_code = not in_code
            continue
        if code and in_code:
            continue
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif (depth == 0 or not parens) and ch in enders:
            if space_gated and ch in ASCII_ENDERS:
                nxt = line[index + 1] if index + 1 < len(line) else ""
                if nxt and not nxt.isspace():
                    continue
            points.append(index + 1)
    return points


def _cut(line, points):
    parts, start = [], 0
    for stop in points:
        parts.append(line[start:stop])
        start = stop
    parts.append(line[start:])
    return parts


def split_sentences(line):
    """Hard breaks at sentence enders; over-long sentences also break at ，、."""
    out = []
    for piece in _cut(line, _break_points(line, HARD_ENDERS + ASCII_ENDERS, space_gated=True)):
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > SOFT_LIMIT:
            soft = [part.strip() for part in
                    _cut(piece, _break_points(piece, SOFT_ENDERS, parens=False, code=False))
                    if part.strip()]
            out.extend(soft if len(soft) > 1 else [piece])
        else:
            out.append(piece)
    return out


def paragraphs_html(lines, by_line=False):
    """One <p> per sentence (or per source line with by_line); bullet blocks become <ul>."""
    blocks, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    parts = []
    for block in blocks:
        if all(re.match(r"^[-*]\s+", item) for item in block):
            parts.append("<ul>%s</ul>" % "".join(
                "<li>%s</li>" % html.escape(re.sub(r"^[-*]\s+", "", item))
                for item in block))
        else:
            for line in block:
                if by_line:
                    parts.append("<p>%s</p>" % html.escape(line))
                    continue
                for sentence in split_sentences(line):
                    parts.append("<p>%s</p>" % html.escape(sentence))
    return "".join(parts)


def item_comment(item_id, placeholder="有异议写在这里；留空即同意"):
    """One always-visible box: text is feedback, empty is silent approval."""
    return (
        '<div class="comment" data-id="%s">'
        '<textarea placeholder="%s"></textarea></div>' % (item_id, placeholder)
    )


def decision_card(item, mode, delta, hashes, pose=False, number=0, previous=None):
    """pose=True adds the decision question and feedback box; all bodies remain visible."""
    badge = state_badge(mode, delta, item["id"])
    refs = "".join('<a class="ref" href="#%s">%s</a>' % (r, r) for r in item["refs"])
    chips = []
    if item["door"] == "one-way":
        chips.append('<span class="door">难以撤回</span>')
    if item["blast"]:
        chips.append('<span class="risk">%s</span>' % html.escape(item["blast"]))
    meta = ""
    if refs or chips:
        meta = '<div class="meta">%s</div>' % " ".join([refs] + chips)
    head = "%s%s %s" % (badge, html.escape(item["id"]), html.escape(item["title"]))
    anchor = "%s · %s" % (item["id"], hashes.get(item["id"], "")[:12])
    first, rest = decision_body(item)
    previous_body = ""
    if previous is not None and mode == "delta" and item["id"] in delta["MODIFIED"]:
        old_first, old_rest = decision_body(previous)
        previous_body = '<div class="before"><b>已接受的决定</b>%s</div><b>本次决定</b>' % paragraphs_html(old_first + old_rest)
        if (previous["human"], previous["door"]) != (item["human"], item["door"]):
            previous_body = '<p>人工确认或撤回条件有变化，请核对原有边界是否仍被保留。</p>' + previous_body
    if pose:
        mark = "%s%d. " % (badge, number) if number else badge
        return (
            '<div class="card decide" title="%s">'
            '<div class="q">%s%s %s %s</div>'
            '<div class="body">%s</div>%s%s</div>'
            % (anchor, mark, html.escape(item["id"]), html.escape(item["title"]),
               " ".join(chips), previous_body + paragraphs_html(first + rest), meta,
               item_comment(item["id"]))
        )
    summary_chips = (" " + " ".join(chips)) if chips else ""
    return (
        '<div class="card" title="%s"><div class="title">%s%s</div>'
        '<div class="body">%s</div>%s</div>'
        % (anchor, head, summary_chips, paragraphs_html(first + rest), meta)
    )


def behavior_card(row, mode, delta, before="", requirement="", previous=None):
    cells = row["cells"]
    scenario = cells[1] if len(cells) > 1 else row["id"]
    observable = cells[3] if len(cells) > 3 else ""
    parts = []
    if previous is not None and mode == "delta" and row["id"] in delta["MODIFIED"]:
        parts.append('<p class="before">已接受：%s</p>' % html.escape(previous["text"]))
        if previous.get("before", "") != before:
            parts.append('<p class="before">原现状：%s</p><p>现状：%s</p>' % (
                html.escape(previous.get("before") or "未记录"), html.escape(before or "已移除现状说明")))
        if previous.get("observable", "") != observable:
            parts.append('<p class="before">原验收观察：%s</p>' % html.escape(previous.get("observable") or "未记录"))
            if not observable:
                parts.append('<p>本次验收观察：尚未定义。</p>')
    elif before:
        parts.append('<p class="before">现状：%s</p>' % html.escape(before))
    if requirement:
        parts.append('<p class="after">预期：%s</p>' % html.escape(requirement))
    if observable and observable != requirement:
        parts.append('<p>验收观察：%s</p>' % html.escape(observable))
    change = '<div class="body">%s</div>' % "".join(parts)
    return (
        '<div class="card" id="%s"><div class="title">%s%s</div>%s</div>'
        % (row["id"], state_badge(mode, delta, row["id"]), html.escape(scenario), change)
    )


def contract_card(item):
    return (
        '<div class="card contract"><div class="title">%s</div>'
        '<div class="body">%s</div></div>'
        % (html.escape(item["id"]), paragraphs_html([item["text"]]))
    )


def note_card(prefix, number, text, answerable=False):
    head = "%s%d" % (prefix, number)
    box = ""
    if answerable:
        box = item_comment(head, "你的回答（可选）")
    return (
        '<div class="card note"><div class="title">%s</div>'
        '<div class="body">%s</div>%s</div>'
        % (head, paragraphs_html([text]), box)
    )


def review_html(feature, prd_name, prd_text, digest, model, delta, mode, bridge, token="", url="",
                baseline=None, baseline_label="上次展示"):
    sections = h2_sections(prd_text)
    hashes = model.hashes()
    decide_items = review_items(model)
    decide_ids = {item["id"] for item in decide_items}
    if mode == "delta":
        previously_reviewed = {item["id"] for item in review_items(baseline)} if baseline else set(delta["MODIFIED"])
        decide_items += [item for item in model.decisions
                         if item["id"] in previously_reviewed and item["id"] not in decide_ids]
        decide_ids = {item["id"] for item in decide_items}
    previous_decisions = {item["id"]: item for item in baseline.decisions} if baseline else {}
    previous_observations = {row["id"]: row["cells"][3] if len(row["cells"]) > 3 else ""
                             for row in baseline.test_rows} if baseline else {}
    previous_requirements = {item["id"]: dict(item, observable=previous_observations.get(item["id"], ""))
                             for item in baseline.requirements} if baseline else {}
    tested_ids = {row["id"] for row in model.test_rows}
    behavior_rows = list(model.test_rows) + [
        {"id": item["id"], "cells": [item["id"], item["id"], "", ""]}
        for item in model.requirements if item["id"] not in tested_ids]
    scope_notes = [line for line in find_section(sections, "范围") or []
                   if line.strip() and not SCOPE_LINE.match(line)
                   and re.sub(r"^[-*]\s+", "", line.strip()) not in model.scope_out]
    acceptance = find_section(sections, "端到端验证") or []
    acceptance = [line for line in acceptance if line.strip() and line.strip() != "（无）"]
    problem = [line for line in (find_section(sections, "问题") or []) if line.strip()]
    outcome = [line for line in (find_section(sections, "方案") or []) if line.strip()]
    counts = []
    if decide_items:
        counts.append("%d 项决策" % len(decide_items))
    if behavior_rows:
        counts.append("%d 项行为" % len(behavior_rows))
    if model.contracts:
        counts.append("%d 条不变量" % len(model.contracts))
    if model.risks or model.questions:
        counts.append("%d 条风险/疑问" % (len(model.risks) + len(model.questions)))
    out = []
    add = out.append
    add('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    add("<title>%s — spec review</title><style>%s</style></head><body><main>" % (
        html.escape(feature), CSS))
    add('<nav class="topnav"><span class="brand">%s · %s Review</span>' % (
        html.escape(feature), "Delta" if mode == "delta" else "Full"))
    add('<a href="#problem">问题</a>')
    if model.scope_in or model.scope_out or scope_notes:
        add('<a href="#scope">范围</a>')
    if model.test_rows or model.requirements:
        add('<a href="#behavior">行为 %d</a>' % len(behavior_rows))
    if model.contracts:
        add('<a href="#contracts">不变量 %d</a>' % len(model.contracts))
    if acceptance:
        add('<a href="#acceptance">验收</a>')
    if model.risks:
        add('<a href="#notes">风险 %d</a>' % len(model.risks))
    if decide_items or model.questions:
        add('<a href="#decide"><b>填写 %d</b></a>'
            % (len(decide_items) + len(model.questions)))
    add('<a href="#submit"><b>提交</b></a>')
    add("</nav>")
    add('<section class="hero"><h1>%s<span class="badge %s">%s Review</span></h1>' % (
        html.escape(feature),
        "delta" if mode == "delta" else "",
        "Delta" if mode == "delta" else "Full"))
    add('<p class="counts">%s</p>' % html.escape(" · ".join(counts) or "（无锚点）"))
    if mode == "delta":
        changed = set(delta["ADDED"] + delta["MODIFIED"] + delta["REMOVED"])
        add('<p class="counts delta">本次调整 %d 项行为，%d 项决定需要复核。</p>' % (
            sum(key.startswith("R") for key in changed), len(decide_ids & (changed | set(delta["AFFECTED"])))))
        add('<p class="muted">对照：%s。先看变化与影响，再到页尾集中填写意见。</p>' % html.escape(baseline_label))
    add("</section>")
    if mode == "delta":
        boundary_changes = [key for kind in ("ADDED", "MODIFIED", "REMOVED") for key in delta[kind]
                            if key != "section:change" and not ID_TOKEN.fullmatch(key)]
        if boundary_changes:
            add('<h2 id="changes">需要留意的边界变化</h2>')
        current_text = model.item_texts()
        previous_text = baseline.item_texts() if baseline else {}
        for kind in ("ADDED", "MODIFIED", "REMOVED"):
            for key in delta[kind]:
                if key not in boundary_changes:
                    continue
                add('<div class="card"><div class="title">%s%s</div>' % (
                    state_badge(mode, delta, key), html.escape(SECTION_LABELS.get(key, key))))
                add('<div class="scopecols">')
                if kind != "ADDED":
                    add('<div><b>%s</b><pre class="compare">%s</pre></div>' % (
                        html.escape(baseline_label), html.escape(previous_text.get(key, "旧正文未保留；请核对源版本。"))))
                if kind != "REMOVED":
                    add('<div><b>本次</b><pre class="compare">%s</pre></div>' % html.escape(current_text.get(key, "")))
                add('</div></div>')
        if not any(delta[key] for key in ("ADDED", "MODIFIED", "REMOVED", "AFFECTED")):
            add('<p>没有待审内容变化。</p>')
    if mode == "delta" and delta["REMOVED"]:
        removed = [key for key in delta["REMOVED"] if key.startswith(("R", "D"))]
        if removed:
            add('<h2>本次移除</h2>')
            for key in removed:
                if key in previous_requirements:
                    body = [previous_requirements[key]["text"]]
                elif key in previous_decisions:
                    first, rest = decision_body(previous_decisions[key])
                    body = [previous_decisions[key]["title"]] + first + rest
                else:
                    body = ["旧正文未保留，请核对移除的原有约束。"]
                add('<div class="card"><div class="title">%s</div>%s</div>' % (html.escape(key), paragraphs_html(body)))
    add('<h2 id="problem">要解决的问题</h2>')
    if problem:
        add('<div class="card"><div class="title">问题</div><div class="body">%s</div></div>'
            % paragraphs_html(problem))
    if outcome:
        add('<div class="card"><div class="title">预期结果</div><div class="body">%s</div></div>'
            % paragraphs_html(outcome))
    if model.scope_in or model.scope_out or scope_notes:
        add('<h2 id="scope">范围</h2><div class="card scopecard"><div class="scopecols">')
        add('<div><b>IN</b>%s</div>' % "".join(
            '<div class="in">✓ %s</div>' % html.escape(line) for line in model.scope_in))
        add('<div><b>OUT</b>%s</div>' % "".join(
            '<div class="out">— %s</div>' % html.escape(line) for line in model.scope_out))
        add("</div></div>")
        if scope_notes:
            add('<div class="card">%s</div>' % paragraphs_html(scope_notes))
    if model.test_rows or model.requirements:
        add('<h2 id="behavior">行为 · %d</h2><div class="cards">' % len(behavior_rows))
        requirement_of = {item["id"]: item for item in model.requirements}
        for row in behavior_rows:
            requirement = requirement_of.get(row["id"], {})
            body = behavior_card(row, mode, delta, requirement.get("before", ""), requirement.get("text", ""),
                                 previous_requirements.get(row["id"]))
            add(body)
        add("</div>")
    if model.contracts:
        add('<h2 id="contracts">必须守住的边界 · %d</h2><div class="cards">' % len(model.contracts))
        for item in model.contracts:
            add(contract_card(item))
        add("</div>")
    if acceptance:
        add('<h2 id="acceptance">如何判断交付合格</h2>')
        add('<div class="card"><div class="body">%s</div></div>'
            % paragraphs_html(acceptance, by_line=True))
    if model.risks:
        add('<h2 id="notes">风险</h2><div class="cards">')
        for number, text in enumerate(model.risks, 1):
            add(note_card("K", number, text))
        add("</div>")
    known = ("问题", "方案", "范围", "不在本次范围内", "用户场景", "实现决策", "实施切片", "测试决策",
             "不变量", "端到端验证", "风险", "尚未明确", "取代理由")
    classified = {id(find_section(sections, word)) for word in known}
    preamble = prd_text.split("\n## ", 1)[0] if not prd_text.startswith("## ") else ""
    if preamble.startswith("---\n"):
        preamble = preamble[4:].partition("\n---")[2]
    preamble = [line for line in preamble.splitlines() if line.strip() and not line.startswith("# ")]
    if preamble:
        add('<h3>补充说明</h3><div class="card">%s</div>' % paragraphs_html(preamble))
    for heading, lines in sections.items():
        if id(lines) not in classified and any(line.strip() for line in lines):
            add('<h3>%s</h3><div class="card">%s</div>' % (html.escape(heading), paragraphs_html(lines)))
    for word, patterns in (("用户场景", (R_BULLET, BEFORE_LINE)), ("不变量", (C_BULLET,))):
        remaining = [line for line in find_section(sections, word) or []
                     if line.strip() and not any(pattern.match(line) for pattern in patterns)]
        if remaining:
            add('<h3>%s补充</h3><div class="card">%s</div>' % (word, paragraphs_html(remaining)))
    decisions = find_section(sections, "实现决策") or []
    prefix = decisions[:next((index for index, line in enumerate(decisions) if D_HEAD.match(line)), len(decisions))]
    if any(line.strip() for line in prefix):
        add('<h3>设计的补充边界</h3><div class="card">%s</div>' % paragraphs_html(prefix))
    if decide_items or model.questions:
        fill_count = len(decide_items) + len(model.questions)
        add('<h2 id="decide">需要你拍板 · %d</h2>' % fill_count)
        number = 0
        human_items = [item for item in decide_items if item["human"]]
        contract_items = [item for item in decide_items if not item["human"]]
        if human_items:
            add('<h3>方向与边界</h3><div class="cards">')
            for item in human_items:
                number += 1
                add(decision_card(item, mode, delta, hashes, pose=True, number=number,
                                  previous=previous_decisions.get(item["id"])))
            add("</div>")
        if contract_items:
            add('<h3>需要确认的取舍</h3>')
            add('<div class="cards">')
            for item in contract_items:
                number += 1
                add(decision_card(item, mode, delta, hashes, pose=True, number=number,
                                  previous=previous_decisions.get(item["id"])))
            add("</div>")
        if model.questions:
            add('<h3>疑问回答</h3><div class="cards">')
            for index, text in enumerate(model.questions, 1):
                add(note_card("Q", index, text, answerable=True))
            add("</div>")
    add('<h2 id="submit">反馈</h2>')
    add('<div class="card"><textarea id="global-feedback" placeholder="GLOBAL 反馈（可选）"></textarea>')
    if bridge:
        add('<button id="approve" type="button">全部确定</button> ')
        add('<button id="feedback" type="button">提交反馈</button><div id="result" class="muted"></div></div>')
        add('<script type="application/json" id="bridge-data">%s</script>' % json.dumps(
            {"token": token, "url": url, "spec": prd_name, "spec_digest": digest,
             "items": {item_id: value for item_id, value in hashes.items()}},
            ensure_ascii=False,
        ).replace("</", "<\\/"))
        add("<script>%s</script>" % BRIDGE_JS)
    else:
        add('<div class="muted">静态预览仅收集反馈。复制后贴回对话；'
            '批准请使用 review 命令打开的人审页面，提交并等待保存成功。</div>')
        add('<textarea id="feedback-text" readonly></textarea>')
        add('<button id="copy-feedback" type="button">复制反馈</button></div>')
        add('<script type="application/json" id="feedback-data">%s</script>' % json.dumps(
            {"spec": prd_name, "spec_digest": digest, "items": hashes},
            ensure_ascii=False,
        ).replace("</", "<\\/"))
        add("<script>%s</script>" % STATIC_JS)
    add('<div class="foot">spec %s · digest %s · %s</div>' % (
        html.escape(prd_name), digest[:12], "one-shot bridge" if bridge else "static render"))
    add("</main></body></html>")
    return "".join(out)

BRIDGE_JS = """
(function(){
var data=JSON.parse(document.getElementById('bridge-data').textContent);
function collect(action){
 var items=[];
 document.querySelectorAll('.comment').forEach(function(box){
  var text=box.querySelector('textarea').value.trim();
  if(!text){return;}
  var id=box.getAttribute('data-id');
  items.push({id:id,hash:data.items[id]||'',
              action:id.charAt(0)==='Q'?'answer':'change',comment:text});
 });
 var global=document.getElementById('global-feedback').value.trim();
 if(action==='approve'&&(items.length||global)){action='feedback';}
 return {token:data.token,spec_digest:data.spec_digest,action:action,items:items,
         global_feedback:global};
}
function post(payload,button){
 button.disabled=true;
 fetch(data.url+'submit',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(result){
   document.getElementById('result').textContent=JSON.stringify(result);
   if(result.status==='accepted'){document.getElementById('feedback').disabled=true;}
   if(result.status!=='accepted'&&result.status!=='feedback'){button.disabled=false;}
  })
  .catch(function(err){document.getElementById('result').textContent=''+err;button.disabled=false;});
}
document.getElementById('approve').addEventListener('click',function(){post(collect('approve'),this);});
document.getElementById('feedback').addEventListener('click',function(){
 var payload=collect('feedback');
 if(!payload.items.length&&!payload.global_feedback){
  document.getElementById('result').textContent='没有可提交的反馈';return;
 }
 post(payload,this);});
})();
"""

STATIC_JS = """
(function(){
var data=JSON.parse(document.getElementById('feedback-data').textContent);
var out=document.getElementById('feedback-text');
function build(){
 var lines=['SPEC FEEDBACK','Spec: '+data.spec,'Digest: '+data.spec_digest,''];
 var hasFeedback=false;
 document.querySelectorAll('.comment').forEach(function(box){
  var text=box.querySelector('textarea').value.trim();
  if(!text){return;}
  hasFeedback=true;
  lines.push(box.getAttribute('data-id'));
  lines.push(text);
  lines.push('');
 });
 var global=document.getElementById('global-feedback').value.trim();
 if(global){hasFeedback=true;lines.push('GLOBAL');lines.push(global);lines.push('');}
 lines.push('END FEEDBACK');
 out.textContent=lines.join('\\n');
 return hasFeedback;
}
document.querySelectorAll('.comment textarea,#global-feedback')
 .forEach(function(el){el.addEventListener('input',build);});
build();
async function copy(button){
 build();
 out.focus();out.select();
 var copied=false;
 try{copied=document.execCommand('copy');}catch(e){}
 if(!copied&&navigator.clipboard){
  try{await navigator.clipboard.writeText(out.value);copied=true;}catch(e){}
 }
 if(!copied){button.textContent='复制失败，请手动复制';out.focus();out.select();return;}
 button.textContent='已复制反馈，请贴回对话';
 setTimeout(function(){button.textContent='复制反馈';},1500);
}
document.getElementById('copy-feedback').addEventListener('click',function(){
 return copy(this);
});
})();
"""


def prepare_review(root, feature, force_full=False):
    """Shared render path: validate anchors, classify delta, build next state."""
    feature_dir = Path(root) / ".scratch" / feature
    if not feature_dir.is_dir():
        raise ValueError("feature '%s' not found under %s" % (feature, Path(root) / ".scratch"))
    prd_name = resolve_head_prd(feature_dir)
    prd_path = os.path.join(feature_dir, prd_name)
    prd_text = normalized_text(prd_path)
    model = parse_model(prd_text)
    problems = validate_model(model)
    if problems:
        raise ValueError("PRD R/D/S violations in %s: %s" % (prd_name, "; ".join(problems)))
    digest = prd_digest(prd_path)
    previous = load_state(feature_dir)
    old_items, baseline, baseline_label = {}, None, "上次展示（尚未接受）"
    if not force_full:
        snapshot = accepted_snapshot_path(feature_dir, previous)
        if previous.get("accepted_digest"):
            problems = acceptance_problems(feature_dir, previous, prd_name, previous["accepted_digest"])
            if problems:
                raise ValueError("; ".join(problems))
            if snapshot.is_file():
                baseline = parse_model(normalized_text(snapshot))
                old_items = baseline.hashes()
                baseline_label = "已接受 · %s" % previous.get("accepted_spec", "PRD")
        elif isinstance(previous.get("last_rendered_items"), dict):
            old_items = previous["last_rendered_items"]
            if "section:context" not in old_items:
                old_items = {}  # Legacy hashes did not cover the complete review surface.
    mode = "delta" if old_items else "full"
    delta = classify_delta(model, old_items) if mode == "delta" else None
    return {
        "feature_dir": feature_dir,
        "prd_name": prd_name,
        "prd_text": prd_text,
        "model": model,
        "digest": digest,
        "mode": mode,
        "delta": delta,
        "baseline": baseline,
        "baseline_label": baseline_label,
        "state": render_state(model, prd_name, digest, previous),
        "warnings": model_warnings(model),
    }


def cmd_render(root, feature, force_full, out_path=None):
    prepared = prepare_review(root, feature, force_full)
    html_text = review_html(
        feature, prepared["prd_name"], prepared["prd_text"], prepared["digest"],
        prepared["model"], prepared["delta"], prepared["mode"], bridge=False,
        baseline=prepared["baseline"], baseline_label=prepared["baseline_label"],
    )
    target = write_review_page(prepared["feature_dir"], html_text, out_path)
    save_rendered_state(prepared["feature_dir"], prepared["state"])
    delta = prepared["delta"]
    counts = (
        {state: len(items) for state, items in delta.items()}
        if delta else {"items": len(prepared["model"].item_ids())}
    )
    payload = {
        "status": "rendered",
        "spec": prepared["prd_name"],
        "spec_digest": prepared["digest"],
        "mode": prepared["mode"],
        "html": str(target),
        "counts": counts,
    }
    if prepared["warnings"]:
        payload["warnings"] = prepared["warnings"]
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def make_handler(prd_path, prd_name, digest, model, html_text, token, result, persist=None, current_identity=None, assets=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "spec-review/1"
        protocol_version = "HTTP/1.1"

        def respond(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def loopback_host(self):
            # DNS rebinding sends an attacker-controlled Host; only the loopback
            # names the one-shot bridge ever legitimately serves.
            host = (self.headers.get("Host") or "").strip().lower()
            return re.match(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", host) is not None

        def do_GET(self):
            route = urllib.parse.urlsplit(self.path).path
            if self.loopback_host() and assets and route in assets:
                path, expected = assets[route]
                try:
                    body = Path(path).read_bytes()
                    if hashlib.sha256(body).hexdigest() != expected:
                        raise ValueError("review artifact changed")
                except (OSError, ValueError):
                    self.respond(409, {"status": "error", "message": "fixed artifact is unavailable"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                filename = urllib.parse.quote(Path(path).name, safe="")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + filename)
                self.send_header("Content-Security-Policy", "sandbox")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if route != "/" or not self.loopback_host():
                self.respond(403, {"status": "error", "message": "not found"})
                return
            body = html_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urllib.parse.urlsplit(self.path).path != "/submit" or not self.loopback_host():
                self.respond(404, {"status": "error", "message": "not found"})
                return
            try:
                with result["lock"]:
                    self.handle_submit()
            except (OSError, ValueError, TypeError) as exc:
                self.respond(500, {"status": "error", "message": "%s: %s" % (type(exc).__name__, exc)})

        def handle_submit(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = SUBMIT_CAP + 1
            if length <= 0 or length > SUBMIT_CAP:
                self.respond(400, {"status": "error", "message": "invalid body size"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.respond(400, {"status": "error", "message": "body is not valid JSON"})
                return
            if not isinstance(payload, dict) or not hmac.compare_digest(
                str(payload.get("token", "")).encode("utf-8"), token.encode("utf-8")
            ):
                self.respond(403, {"status": "error", "message": "invalid review token"})
                return
            try:
                current_digest = current_identity() if current_identity else prd_digest(prd_path)
            except (OSError, ValueError):
                self.respond(500, {"status": "error", "message": "PRD unreadable; re-render"})
                return
            if payload.get("spec_digest") != digest or current_digest != digest:
                self.respond(
                    409,
                    {
                        "status": "stale_review",
                        "expected_digest": digest,
                        "current_digest": current_digest,
                    },
                )
                return
            action = payload.get("action")
            items = payload.get("items")
            global_feedback = str(payload.get("global_feedback") or "").strip()
            known = model.hashes()
            if not isinstance(items, list):
                self.respond(400, {"status": "error", "message": "items must be a list"})
                return
            for item in items:
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id not in known and not NOTE_TOKEN.match(str(item_id or "")):
                    self.respond(400, {"status": "error", "message": "unknown item id"})
                    return
                if item.get("action") not in ("approve", "change", "question", "answer"):
                    self.respond(400, {"status": "error", "message": "invalid item action"})
                    return
                item["hash"] = known.get(item_id, "")
            if action == "approve" and (items or global_feedback):
                action = "feedback"
            if action == "approve":
                answer = {"status": "accepted", "spec": prd_name, "spec_digest": digest}
            elif action == "feedback":
                if not items and not global_feedback:
                    self.respond(400, {"status": "error", "message": "empty feedback"})
                    return
                answer = {
                    "status": "feedback",
                    "spec": prd_name,
                    "spec_digest": digest,
                    "items": items,
                }
                if global_feedback:
                    answer["global_feedback"] = global_feedback
            else:
                self.respond(
                    400, {"status": "error", "message": "action must be approve or feedback"}
                )
                return
            event_id = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if result["done"]:
                if result.get("event_id") == event_id:
                    self.respond(200, result["value"])
                else:
                    self.respond(409, {"status": "error", "message": "review already has another decision"})
                return
            if persist:
                persist(answer, payload, event_id)
            else:
                persist_spec_decision(prd_path, prd_name, digest, model, answer, payload, event_id)
            result["value"] = answer
            result["event_id"] = event_id
            result["done"] = True
            self.respond(200, answer)

        def log_message(self, fmt, *args):
            pass

    return Handler


class _Unavailable(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_error(404)

    def do_POST(self):
        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


def start_bridge(prepared, port=0):
    """Create the one-shot listener and page synchronously; no accept loop yet."""
    feature_dir = prepared["feature_dir"]
    prd_path = feature_dir / prepared["prd_name"]
    token = secrets.token_urlsafe(32)
    result = {"done": False, "value": None, "lock": threading.Lock()}
    server = ThreadingHTTPServer(("127.0.0.1", port or 0), _Unavailable)
    try:
        url = "http://127.0.0.1:%d/" % server.server_address[1]
        html_text = review_html(
            feature_dir.name, prepared["prd_name"], prepared["prd_text"], prepared["digest"],
            prepared["model"], prepared["delta"], prepared["mode"], bridge=True,
            token=token, url=url,
            baseline=prepared["baseline"], baseline_label=prepared["baseline_label"],
        )
        server.RequestHandlerClass = make_handler(
            prd_path, prepared["prd_name"], prepared["digest"], prepared["model"],
            html_text, token, result,
        )
        save_rendered_state(feature_dir, prepared["state"])
    except Exception:
        server.server_close()
        raise
    return server, url, token, result


def serve_bridge(server, result, timeout, prepared):
    """Accept loop until one submit or the deadline; records acceptance on approve."""
    server.timeout = 1.0
    deadline = time.monotonic() + timeout
    try:
        while not result["done"]:
            if time.monotonic() >= deadline:
                return {
                    "status": "timeout",
                    "spec": prepared["prd_name"],
                    "spec_digest": prepared["digest"],
                }
            server.handle_request()
    finally:
        server.server_close()
    return dict(result["value"])


def run_bridge(prepared, timeout, open_browser, port=0, on_started=None):
    """One-shot 127.0.0.1 review bridge; returns the stdout payload dict."""
    server, url, token, result = start_bridge(prepared, port)
    try:
        if on_started:
            on_started(url, token)
        print("spec-review: %s" % url, file=sys.stderr)
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:  # best effort; the URL is on stderr either way
                pass
        return serve_bridge(server, result, timeout, prepared)
    finally:
        server.server_close()


def cmd_review(root, feature, force_full, timeout, open_browser, port=0):
    prepared = prepare_review(root, feature, force_full)
    static_html = review_html(
        feature, prepared["prd_name"], prepared["prd_text"], prepared["digest"],
        prepared["model"], prepared["delta"], prepared["mode"], bridge=False,
        baseline=prepared["baseline"], baseline_label=prepared["baseline_label"],
    )
    write_review_page(prepared["feature_dir"], static_html)
    answer = run_bridge(prepared, timeout, open_browser, port)
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("status") in ("accepted", "feedback") else 1


def cmd_validate(root, feature, require_accepted):
    feature_dir = Path(root) / ".scratch" / feature
    if not feature_dir.is_dir():
        print("spec-review validate: feature '%s' not found" % feature)
        return 1
    prd_name = resolve_head_prd(feature_dir)
    prd_path = os.path.join(feature_dir, prd_name)
    model = parse_model(normalized_text(prd_path))
    problems = list(validate_model(model))
    problems += ["warning: %s" % warning for warning in model_warnings(model)]
    if require_accepted:
        state = load_state(feature_dir)
        accepted = state.get("accepted_digest")
        digest = prd_digest(prd_path)
        problems.extend(acceptance_problems(feature_dir, state, prd_name, digest))
        if isinstance(accepted, str) and HEX64.match(accepted):
            if accepted != digest:
                items = state.get("accepted_items")
                if isinstance(items, dict) and items:
                    delta = classify_delta(model, items)
                    moved = sorted(
                        set(delta["ADDED"]) | set(delta["MODIFIED"]) | set(delta["REMOVED"])
                    )
                    problems.append(
                        "changed since acceptance: %s"
                        % (", ".join(moved) if moved
                           else "no R/D/S item moved; the edit is outside the item ledger")
                    )
    if problems:
        print("spec-review validate: %d violation(s)" % len(problems))
        for problem in problems:
            print("  %s: %s" % (prd_name, problem))
        return 1
    print(
        "spec-review validate: OK - %s R %d, D %d, S %d%s."
        % (prd_name, len(model.requirements), len(model.decisions), len(model.slices),
           " · accepted" if require_accepted else "")
    )
    return 0


def write_review_page(feature_dir, text, requested=None):
    name = "spec-review-" + hashlib.sha256(text.encode()).hexdigest() + ".html"
    target = Path(requested) if requested else Path(feature_dir) / name
    with file_lock(target.with_name(target.name + ".lock")):
        if target.exists() and target.read_text(encoding="utf-8") != text:
            raise ValueError("review page is immutable; choose a new path")
        atomic_write(target, text)
    return target


def save_rendered_state(feature_dir, rendered):
    with file_lock(Path(feature_dir) / ".spec-review.lock"):
        latest = load_state(feature_dir)
        current = dict(rendered)
        for key in ("accepted_digest", "accepted_spec", "accepted_items", "accepted_event"):
            if key in latest:
                current[key] = latest[key]
        save_state(feature_dir, current)


def persist_spec_decision(prd_path, prd_name, digest, model, answer, payload, event_id):
    feature_dir = Path(prd_path).parent
    with file_lock(feature_dir / ".spec-review.lock"):
        if prd_digest(prd_path) != digest:
            raise ValueError("Spec changed before decision persistence")
        event = {key: value for key, value in payload.items() if key != "token"}
        record = write_record(feature_dir / "spec-review-events" / (event_id + ".json"),
                              {"kind": "spec_decision", "schema_version": 1, "event_id": event_id,
                               "source": "local_review", "spec_digest": digest, "event": event})
        if answer["status"] == "accepted":
            state = load_state(feature_dir) or render_state(model, prd_name, digest, {})
            record_acceptance(state, feature_dir, prd_path, digest, model)
            state["accepted_event"] = record["digest"]
            save_state(feature_dir, state)


def candidate_review_page(fixed, spec_text, links_html, bridge_data):
    """Deterministic review surface: the fixed record, its bound accepted Spec, then artifacts."""
    spec_block = ""
    if isinstance(spec_text, str):
        spec_block = '<h2>接受的 Spec</h2><pre class="compare">%s</pre>' % html.escape(spec_text)
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>固定候选审核</title>'
            '<style>%s</style><main><h1>固定候选审核</h1><pre class="compare">%s</pre>%s<ul>%s</ul>'
            '<label for="global-feedback">反馈</label><textarea id="global-feedback"></textarea>'
            '<button id="approve">全部确定</button><button id="feedback">提交反馈</button>'
            '<div id="result"></div><script type="application/json" id="bridge-data">%s</script>'
            '<script>%s</script></main></html>') % (CSS, html.escape(json.dumps(fixed, ensure_ascii=False, indent=2)),
                                                    spec_block, links_html, bridge_data, BRIDGE_JS)


def cmd_review_candidate(root, path, timeout, open_browser, port=0):
    from evidence import local, record_decision, validate_candidate, validate_review
    root, path = Path(root).resolve(), Path(path).resolve()
    fixed = validate_review(root, path)
    token = secrets.token_urlsafe(32)
    result = {"done": False, "value": None, "lock": threading.Lock()}
    server = ThreadingHTTPServer(("127.0.0.1", port or 0), _Unavailable)
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    assets = {}
    links = []
    for index, (name, sha) in enumerate(sorted(fixed["artifacts"].items())):
        route = "/artifact/%d" % index
        assets[route] = (local(root, fixed["retained_artifacts"][name]), sha)
        links.append('<li><a href="%s">%s</a> · %s</li>' % (route, html.escape(name), sha))
    bridge_data = json.dumps({"token": token, "url": url, "spec": path.name,
                              "spec_digest": fixed["digest"], "items": {}}).replace("</", "<\\/")
    bound = validate_candidate(root, local(root, fixed["candidate"]))
    page = candidate_review_page(fixed, bound.get("spec_text"), "".join(links), bridge_data)
    class Model:
        def hashes(self):
            return {}
    def identity():
        return validate_review(root, path)["digest"]
    def persist(answer, payload, event_id):
        event = {"event_id": event_id, "source": "local_review", "review_digest": fixed["digest"],
                 "action": "approve" if answer["status"] == "accepted" else "request_changes",
                 "feedback": payload.get("global_feedback", "")}
        destination = path.parent / "decisions" / (event_id + ".json")
        record_decision(root, path, event, destination)
        answer["decision"] = str(destination)
    server.RequestHandlerClass = make_handler(path, path.name, fixed["digest"], Model(), page, token,
                                               result, persist, identity, assets)
    print("spec-review: " + url, file=sys.stderr)
    try:
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception as exc:
                print("spec-review: open browser manually: %s (%s)" % (url, exc), file=sys.stderr)
        answer = serve_bridge(server, result, timeout, {"prd_name": path.name, "digest": fixed["digest"]})
    finally:
        server.server_close()
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("status") in ("accepted", "feedback") else 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="spec-review.py")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "review"):
        command = sub.add_parser(name)
        command.add_argument("root")
        command.add_argument("feature")
        command.add_argument("--full", action="store_true", help="force a Full review instead of Delta")
        if name == "review":
            command.add_argument("--timeout", type=float, default=900.0)
            command.add_argument("--no-browser", action="store_true")
            command.add_argument("--port", type=int, default=0)
        else:
            command.add_argument("--out")
    validate = sub.add_parser("validate")
    validate.add_argument("root")
    validate.add_argument("feature")
    validate.add_argument("--require-accepted", action="store_true")
    candidate = sub.add_parser("review-candidate")
    candidate.add_argument("root")
    candidate.add_argument("review", type=Path)
    candidate.add_argument("--timeout", type=float, default=900.0)
    candidate.add_argument("--no-browser", action="store_true")
    candidate.add_argument("--port", type=int, default=0)
    args = parser.parse_args((argv or sys.argv)[1:])
    try:
        if args.command == "render":
            return cmd_render(args.root, args.feature, args.full, args.out)
        if args.command == "review":
            return cmd_review(
                args.root, args.feature, args.full, args.timeout, not args.no_browser, args.port
            )
        if args.command == "validate":
            return cmd_validate(args.root, args.feature, args.require_accepted)
        return cmd_review_candidate(args.root, args.review, args.timeout, not args.no_browser, args.port)
    except (OSError, ValueError) as exc:
        print("spec-review %s: %s" % (args.command, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
