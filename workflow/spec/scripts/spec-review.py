#!/usr/bin/env python
# Deterministic spec review surface: parses R/D/S anchors from a feature PRD,
# renders the human Full/Delta review HTML, and runs the one-shot localhost
# review bridge. Stdlib only; no model calls. Exit: 0 ok, 1 violation/timeout,
# 2 usage.
# Invoke: python spec-review.py <render|review|validate|accept> <repo-root> <feature> [options]
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

REVIEW_STATE = "spec-review.json"
REVIEW_HTML = "spec-review.html"
R_BULLET = re.compile(r"^\s*[-*]\s+(R\d+)\s*[—\-–]\s*(.+)$")
BEFORE_LINE = re.compile(r"^\s+Before\s*[:：]\s*(.+)$", re.IGNORECASE)
D_HEAD = re.compile(r"^#{2,4}\s+(D\d+)\s*[—\-–:>]?\s*(.*)$")
REFS_LINE = re.compile(r"^\s*Refs\s*[:：]\s*(.+)$")
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
        self.slice_candidates = 0
        self.has_ids = False

    def item_ids(self):
        return (
            [item["id"] for item in self.requirements]
            + [item["id"] for item in self.decisions]
            + [item["id"] for item in self.slices]
        )

    def hashes(self):
        table = {}
        for item in self.requirements:
            table[item["id"]] = item_hash("R", item["id"], item["text"])
        for item in self.decisions:
            body = "\n".join(line.rstrip() for line in item["lines"])
            table[item["id"]] = item_hash("D", item["id"], body)
        for item in self.slices:
            body = "|".join(
                [item["id"], item["outcome"], " ".join(item["covers"]),
                 " ".join(item["depends"]), item["review"]]
            )
            table[item["id"]] = item_hash("S", item["id"], body)
        return table

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
            if before and model.requirements:
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
            if refs and not current["refs"]:
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
    problems = []
    if not model.has_ids:
        return problems
    for family in (model.requirements, model.decisions, model.slices):
        seen = set()
        for item in family:
            if item["id"] in seen:
                problems.append("duplicate id %s" % item["id"])
            seen.add(item["id"])
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
    changed = set(result["MODIFIED"]) | set(result["REMOVED"])
    affected = sorted(
        item_id for item_id in result["UNCHANGED"] if changed & model.refs_of(item_id)
    )
    result["AFFECTED"] = affected
    result["UNCHANGED"] = [i for i in result["UNCHANGED"] if i not in set(affected)]
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


def load_state(feature_dir):
    path = os.path.join(feature_dir, REVIEW_STATE)
    if not os.path.isfile(path):
        return {}
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(state, dict):
        raise ValueError("%s must be a JSON object" % path)
    return state


def save_state(feature_dir, state):
    Path(os.path.join(feature_dir, REVIEW_STATE)).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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


def record_acceptance(state, feature_dir, prd_path, digest, model):
    """Pin the accepted bytes: digest, item ledger, and a durable snapshot file.

    The snapshot stores the normalized PRD text so its own prd_digest equals
    accepted_digest; editing it in place is detectable by any gate.
    """
    state["accepted_digest"] = digest
    state["accepted_spec"] = os.path.basename(prd_path)
    state["accepted_items"] = model.hashes()
    snapshot = os.path.join(feature_dir, ACCEPTED_SNAPSHOT)
    with open(snapshot, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(normalized_text(prd_path))
    return state


def acceptance_barrier(feature_dir):
    """None when dispatch may proceed, else the blocking message.

    Binds only features with recorded acceptance; legacy features without
    review state pass unchanged.
    """
    feature_dir = Path(feature_dir)
    state = load_state(feature_dir)
    accepted = state.get("accepted_digest")
    if not isinstance(accepted, str) or not HEX64.match(accepted):
        return None
    try:
        prd_name = resolve_head_prd(feature_dir)
    except ValueError as exc:
        return "cannot verify acceptance binding: %s" % exc
    digest = prd_digest(os.path.join(feature_dir, prd_name))
    if digest == accepted:
        return None
    return (
        "%s drifted from accepted_digest %s… (current %s…); run spec-review.py validate "
        "<repo-root> <feature> --require-accepted for the item delta, re-review, then "
        "dispatch again" % (prd_name, accepted[:12], digest[:12])
    )


CSS = """*{box-sizing:border-box}
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
.card summary{cursor:pointer;font-weight:600;font-size:16px;color:#345}
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
details{margin-top:6px}summary{cursor:pointer;font-size:13px;color:#345}
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


def svg_design_map(model, highlight=()):
    """Layered SVG of the S# dependency DAG; deterministic coordinates.

    highlight: slice ids carrying a contract change — drawn with a red fill."""
    slices = {item["id"]: item for item in model.slices}
    if len(slices) <= 1:
        return ""
    remaining = dict(slices)
    layers = []
    while remaining:
        ready = sorted(
            item_id for item_id, item in remaining.items()
            if not [dep for dep in item["depends"] if dep in remaining]
        )
        if not ready:  # a cycle survived validation; draw the rest flat
            ready = sorted(remaining)
        layers.append(ready)
        for item_id in ready:
            del remaining[item_id]
    box_w, box_h, gap_x, gap_y = 168, 46, 36, 42
    widest = max(len(layer) for layer in layers)
    width = widest * (box_w + gap_x) - gap_x
    height = len(layers) * (box_h + gap_y) - gap_y
    parts = [
        '<svg viewBox="0 0 %d %d" width="100%%" style="max-width:%dpx;background:#fff" '
        'role="img" aria-label="实施切片依赖图">' % (width, height, width)
    ]
    centers = {}
    for depth, layer in enumerate(layers):
        offset = (widest - len(layer)) * (box_w + gap_x) // 2
        for index, item_id in enumerate(layer):
            x = offset + index * (box_w + gap_x)
            y = depth * (box_h + gap_y)
            centers[item_id] = (x + box_w // 2, y + box_h // 2)
            label = html.escape(
                (slices[item_id]["label"] or slices[item_id]["outcome"])[:12] or item_id
            )
            if item_id in highlight:
                fill = "#f2c8c8"
            elif slices[item_id]["review"] == "key":
                fill = "#f5e3c8"
            else:
                fill = "#e8edf2"
            parts.append(
                '<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s"/>'
                '<text x="%d" y="%d" text-anchor="middle" font-size="13" fill="#1c2733">%s</text>'
                '<text x="%d" y="%d" text-anchor="middle" font-size="11" fill="#5a6b7b">%s</text>'
                % (
                    x, y, box_w, box_h, fill,
                    x + box_w // 2, y + 18, html.escape(item_id),
                    x + box_w // 2, y + 34, label,
                )
            )
    for item_id in sorted(slices):
        for dep in sorted(slices[item_id]["depends"]):
            if dep in centers:
                parts.append(
                    '<path d="M%d %d L%d %d" stroke="#5a6b7b" stroke-width="1.4" '
                    'marker-end="url(#arrow)"/>' % (
                        centers[dep][0], centers[dep][1] + box_h // 2,
                        centers[item_id][0], centers[item_id][1] - box_h // 2,
                    )
                )
    parts.append(
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#5a6b7b"/>'
        "</marker></defs></svg>"
    )
    return "".join(parts)


def delta_line(mode, delta):
    if mode != "delta":
        return ""
    return "较上次：+%d 新增 · %d 变更 · %d 移除 · %d 不变" % (
        len(delta["ADDED"]), len(delta["MODIFIED"]),
        len(delta["REMOVED"]), len(delta["UNCHANGED"]),
    )


def state_badge(mode, delta, item_id):
    if mode != "delta":
        return ""
    for state in ("ADDED", "MODIFIED", "REMOVED", "AFFECTED", "UNCHANGED"):
        if item_id in delta.get(state, []):
            return '<span class="state %s">%s</span>' % (state, state)
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


def decision_card(item, mode, delta, hashes, pose=False, number=0):
    """pose=True: the decision area — one question, body fully typeset. Else: collapsed reference."""
    badge = state_badge(mode, delta, item["id"])
    refs = "".join('<a class="ref" href="#%s">%s</a>' % (r, r) for r in item["refs"])
    chips = []
    if item["door"] == "one-way":
        chips.append('<span class="door">one-way</span>')
    if item["blast"]:
        chips.append('<span class="risk">%s</span>' % html.escape(item["blast"]))
    meta = ""
    if refs or chips:
        meta = '<div class="meta">%s</div>' % " ".join([refs] + chips)
    head = "%s%s %s" % (badge, html.escape(item["id"]), html.escape(item["title"]))
    anchor = "%s · %s" % (item["id"], hashes.get(item["id"], "")[:12])
    first, rest = decision_body(item)
    if pose:
        mark = "%s%d. " % (badge, number) if number else badge
        return (
            '<div class="card decide" title="%s">'
            '<div class="q">%s%s %s %s</div>'
            '<div class="body">%s</div>%s%s</div>'
            % (anchor, mark, html.escape(item["id"]), html.escape(item["title"]),
               " ".join(chips), paragraphs_html(first + rest), meta,
               item_comment(item["id"]))
        )
    summary_chips = (" " + " ".join(chips)) if chips else ""
    return (
        '<div class="card"><details title="%s"><summary>%s%s</summary>'
        '<div class="body">%s</div>%s</details></div>'
        % (anchor, head, summary_chips, paragraphs_html(first + rest), meta)
    )


def behavior_card(row, mode, delta, before=""):
    cells = row["cells"]
    scenario = cells[1] if len(cells) > 1 else row["id"]
    observable = cells[3] if len(cells) > 3 else ""
    change = '<div class="body">%s</div>' % paragraphs_html([observable])
    if before:
        change = (
            '<div class="body"><p class="before">Before：%s</p>'
            '<p class="after">After：%s</p></div>'
            % (html.escape(before), html.escape(observable))
        )
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


def review_html(feature, prd_name, prd_text, digest, model, delta, mode, bridge, token="", url=""):
    sections = h2_sections(prd_text)
    hashes = model.hashes()
    decide_items = review_items(model)
    decide_ids = {item["id"] for item in decide_items}
    other_items = [item for item in model.decisions if item["id"] not in decide_ids]
    acceptance = find_section(sections, "端到端验证") or []
    acceptance = [line for line in acceptance if line.strip() and line.strip() != "（无）"]
    problem = [line for line in (find_section(sections, "问题") or []) if line.strip()]
    outcome = [line for line in (find_section(sections, "方案") or []) if line.strip()]
    counts = []
    if decide_items:
        counts.append("%d 项决策" % len(decide_items))
    if model.test_rows:
        counts.append("%d 项行为" % len(model.test_rows))
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
    if model.scope_in or model.scope_out:
        add('<a href="#scope">范围</a>')
    if model.test_rows or model.requirements:
        add('<a href="#behavior">行为 %d</a>' % len(model.test_rows))
    if model.contracts:
        add('<a href="#contracts">不变量 %d</a>' % len(model.contracts))
    if acceptance:
        add('<a href="#acceptance">验收</a>')
    if model.risks:
        add('<a href="#notes">风险 %d</a>' % len(model.risks))
    add('<a href="#tech">技术细节</a>')
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
        add('<p class="counts delta">%s</p>' % html.escape(delta_line(mode, delta)))
    add("</section>")
    if mode == "delta" and delta["REMOVED"]:
        add('<details open><summary>本次移除（%d）：%s</summary></details>' % (
            len(delta["REMOVED"]), html.escape("、".join(delta["REMOVED"]))))
    add('<h2 id="problem">要解决的问题</h2>')
    if problem:
        add('<div class="card"><div class="title">问题</div><div class="body">%s</div></div>'
            % paragraphs_html(problem))
    if outcome:
        add('<div class="card"><div class="title">预期结果</div><div class="body">%s</div></div>'
            % paragraphs_html(outcome))
    if model.scope_in or model.scope_out:
        add('<h2 id="scope">范围</h2><div class="card scopecard"><div class="scopecols">')
        add('<div><b>IN</b>%s</div>' % "".join(
            '<div class="in">✓ %s</div>' % html.escape(line) for line in model.scope_in))
        add('<div><b>OUT</b>%s</div>' % "".join(
            '<div class="out">— %s</div>' % html.escape(line) for line in model.scope_out))
        add("</div></div>")
    if model.test_rows or model.requirements:
        add('<h2 id="behavior">行为 · %d</h2><div class="cards">' % len(model.test_rows))
        before_of = {item["id"]: item.get("before", "")
                     for item in model.requirements}
        for row in model.test_rows:
            add(behavior_card(row, mode, delta, before_of.get(row["id"], "")))
        for item in model.requirements:
            if not any(row["id"] == item["id"] for row in model.test_rows):
                add('<div class="card" id="%s"><div class="title">%s%s</div>'
                    '<div class="body">%s</div></div>' % (
                        item["id"], state_badge(mode, delta, item["id"]),
                        html.escape(item["id"]), paragraphs_html([item["text"]])))
        add("</div>")
    if model.contracts:
        add('<h2 id="contracts">不变量 · %d</h2><div class="cards">' % len(model.contracts))
        for item in model.contracts:
            add(contract_card(item))
        add("</div>")
    if acceptance:
        add('<h2 id="acceptance">验收</h2>')
        add('<div class="card"><div class="body">%s</div></div>'
            % paragraphs_html(acceptance, by_line=True))
    if model.risks:
        add('<h2 id="notes">风险</h2><div class="cards">')
        for number, text in enumerate(model.risks, 1):
            add(note_card("K", number, text))
        add("</div>")
    add('<h2 id="tech">技术细节</h2>')
    if len(model.slices) > 1:
        add('<h3>切片依赖图（黄 = key）</h3>')
        add(svg_design_map(model))
    if model.slices:
        add('<h3>切片表 · %d</h3>' % len(model.slices))
        add('<table><tr><th>Slice</th><th>Outcome</th><th>Covers</th><th>Depends</th><th>Review</th></tr>')
        for item in model.slices:
            name = "%s %s" % (item["id"], item["label"]) if item["label"] else item["id"]
            add("<tr><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                state_badge(mode, delta, item["id"]), html.escape(name),
                html.escape(item["outcome"]), html.escape(" ".join(item["covers"])),
                html.escape(" ".join(item["depends"]) or "—"), html.escape(item["review"])))
        add("</table>")
    if other_items:
        add('<h3>工程决策 · %d</h3><div class="cards">' % len(other_items))
        for item in other_items:
            add(decision_card(item, mode, delta, hashes))
        add("</div>")
    if model.test_rows:
        add('<h3>证明表（接缝与证据形态）</h3>')
        covering = {}
        for item in model.slices:
            for ref in item["covers"]:
                covering.setdefault(ref, []).append(item["id"])
        add('<table><tr><th>R</th><th>接缝</th><th>证据形态</th><th>切片</th></tr>')
        for row in model.test_rows:
            cells = row["cells"]
            seam = cells[2] if len(cells) > 2 else "—"
            evidence = cells[4] if len(cells) > 4 else "—"
            add('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                html.escape(row["id"]), html.escape(seam), html.escape(evidence),
                html.escape("、".join(covering.get(row["id"], [])) or "—")))
        add("</table>")
    if decide_items or model.questions:
        fill_count = len(decide_items) + len(model.questions)
        add('<h2 id="decide">决策与疑问 · %d</h2>' % fill_count)
        number = 0
        human_items = [item for item in decide_items if item["human"]]
        contract_items = [item for item in decide_items if not item["human"]]
        if human_items:
            add('<h3>方向与边界</h3><div class="cards">')
            for item in human_items:
                number += 1
                add(decision_card(item, mode, delta, hashes, pose=True, number=number))
            add("</div>")
        if contract_items:
            add('<h3>接口与架构变动（one-way）</h3>')
            contract_ids = {item["id"] for item in contract_items}
            for item in contract_items:
                contract_ids |= set(item["refs"])
            touched = {
                sl["id"] for sl in model.slices if set(sl["covers"]) & contract_ids
            }
            chart = svg_design_map(model, highlight=touched)
            if chart:
                add('<div class="muted">整体架构切片图 — 红 = 本次契约变动涉及，黄 = key</div>')
                add(chart)
            add('<div class="cards">')
            for item in contract_items:
                number += 1
                add(decision_card(item, mode, delta, hashes, pose=True, number=number))
            add("</div>")
        if model.questions:
            add('<h3>疑问回答</h3><div class="cards">')
            for index, text in enumerate(model.questions, 1):
                add(note_card("Q", index, text, answerable=True))
            add("</div>")
    add('<h2 id="submit">反馈</h2>')
    add('<div class="card"><textarea id="global-feedback" placeholder="GLOBAL 反馈（可选）"></textarea>')
    if bridge:
        add('<button id="approve" type="button">确定</button> ')
        add('<button id="feedback" type="button">提交反馈</button><div id="result" class="muted"></div></div>')
        add('<script type="application/json" id="bridge-data">%s</script>' % json.dumps(
            {"token": token, "url": url, "spec": prd_name, "spec_digest": digest,
             "items": {item_id: value for item_id, value in hashes.items()}},
            ensure_ascii=False,
        ).replace("</", "<\\/"))
        add("<script>%s</script>" % BRIDGE_JS)
    else:
        add('<div class="muted">无异议时直接在 Harness 说明通过；有异议则点对应条目的'
            '「需要修改 / 提问」，复制下面的反馈文本贴回 Harness。</div>')
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
 return {token:data.token,spec_digest:data.spec_digest,action:action,items:items,
         global_feedback:document.getElementById('global-feedback').value.trim()};
}
function post(payload,button){
 button.disabled=true;
 fetch(data.url+'submit',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(result){
   document.getElementById('result').textContent=JSON.stringify(result);
   if(result.status==='accepted'){document.getElementById('feedback').disabled=true;}
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
 document.querySelectorAll('.comment').forEach(function(box){
  var text=box.querySelector('textarea').value.trim();
  if(!text){return;}
  lines.push(box.getAttribute('data-id'));
  lines.push(text);
  lines.push('');
 });
 var global=document.getElementById('global-feedback').value.trim();
 if(global){lines.push('GLOBAL');lines.push(global);lines.push('');}
 lines.push('END FEEDBACK');
 out.textContent=lines.join('\\n');
}
document.querySelectorAll('.comment textarea,#global-feedback')
 .forEach(function(el){el.addEventListener('input',build);});
build();
document.getElementById('copy-feedback').addEventListener('click',function(){
 out.focus();out.select();
 var copied=false;
 try{copied=document.execCommand('copy');}catch(e){}
 if(!copied&&navigator.clipboard){navigator.clipboard.writeText(out.value);}
 this.textContent='已复制';
 var button=this;
 setTimeout(function(){button.textContent='复制反馈';},1500);
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
    old_items = {}
    if not force_full and isinstance(previous.get("last_rendered_items"), dict):
        old_items = previous["last_rendered_items"]
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
        "state": render_state(model, prd_name, digest, previous),
        "warnings": model_warnings(model),
    }


def cmd_render(root, feature, force_full, out_path=None):
    prepared = prepare_review(root, feature, force_full)
    html_text = review_html(
        feature, prepared["prd_name"], prepared["prd_text"], prepared["digest"],
        prepared["model"], prepared["delta"], prepared["mode"], bridge=False,
    )
    target = Path(out_path) if out_path else prepared["feature_dir"] / REVIEW_HTML
    target.write_text(html_text, encoding="utf-8")
    save_state(prepared["feature_dir"], prepared["state"])
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


def make_handler(prd_path, prd_name, digest, model, html_text, token, result):
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
            if urllib.parse.urlsplit(self.path).path != "/" or not self.loopback_host():
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
            if result["done"]:
                self.respond(410, {"status": "error", "message": "review already submitted"})
                return
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
                current_digest = prd_digest(prd_path)
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
            self.respond(200, answer)
            result["value"] = answer
            result["done"] = True

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
        )
        server.RequestHandlerClass = make_handler(
            prd_path, prepared["prd_name"], prepared["digest"], prepared["model"],
            html_text, token, result,
        )
        save_state(feature_dir, prepared["state"])
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
    answer = dict(result["value"])
    if answer["status"] == "accepted":
        state = prepared["state"]
        record_acceptance(
            state,
            prepared["feature_dir"],
            os.path.join(prepared["feature_dir"], prepared["prd_name"]),
            prepared["digest"],
            prepared["model"],
        )
        save_state(prepared["feature_dir"], state)
    return answer


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
    )
    (prepared["feature_dir"] / REVIEW_HTML).write_text(static_html, encoding="utf-8")
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
        snapshot = os.path.join(feature_dir, ACCEPTED_SNAPSHOT)
        if not isinstance(accepted, str) or not HEX64.match(accepted):
            problems.append("%s has no recorded human acceptance" % prd_name)
        else:
            if os.path.isfile(snapshot):
                if prd_digest(snapshot) != accepted:
                    problems.append(
                        "%s no longer matches accepted_digest" % ACCEPTED_SNAPSHOT
                    )
            elif state.get("accepted_items") is not None:
                problems.append(
                    "acceptance ledger exists but %s is missing" % ACCEPTED_SNAPSHOT
                )
            if accepted != digest:
                problems.append(
                    "accepted_digest %s… != current %s digest %s…; re-review before materializing"
                    % (accepted[:12], prd_name, digest[:12])
                )
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


def cmd_accept(root, feature):
    feature_dir = Path(root) / ".scratch" / feature
    if not feature_dir.is_dir():
        print("spec-review accept: feature '%s' not found" % feature)
        return 1
    prd_name = resolve_head_prd(feature_dir)
    prd_path = os.path.join(feature_dir, prd_name)
    digest = prd_digest(prd_path)
    model = parse_model(normalized_text(prd_path))
    problems = validate_model(model)
    if problems:
        print("spec-review accept: %s" % "; ".join(problems), file=sys.stderr)
        return 1
    state = load_state(feature_dir)
    state.update({
        "schema_version": 1,
        "spec": prd_name,
    })
    if not state.get("last_rendered_digest"):
        state["last_rendered_digest"] = digest
        state["last_rendered_items"] = model.hashes()
    record_acceptance(state, feature_dir, prd_path, digest, model)
    save_state(feature_dir, state)
    print(json.dumps(
        {
            "status": "accepted",
            "spec": prd_name,
            "spec_digest": digest,
            "snapshot": ACCEPTED_SNAPSHOT,
        }, ensure_ascii=False))
    return 0


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
    accept = sub.add_parser("accept")
    accept.add_argument("root")
    accept.add_argument("feature")
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
        return cmd_accept(args.root, args.feature)
    except (OSError, ValueError) as exc:
        print("spec-review %s: %s" % (args.command, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
