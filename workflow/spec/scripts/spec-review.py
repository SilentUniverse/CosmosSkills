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
D_HEAD = re.compile(r"^#{2,4}\s+(D\d+)\s*[—\-–:>]?\s*(.*)$")
REFS_LINE = re.compile(r"^\s*Refs\s*[:：]\s*(.+)$")
DOOR_LINE = re.compile(r"^\s*Door\s*[:：]\s*(one-way|two-way)\s*$", re.IGNORECASE)
BLAST_LINE = re.compile(r"^\s*Blast\s+radius\s*[:：]\s*([^\s].*?)\s*$", re.IGNORECASE)
S_ROW = re.compile(r"^\|\s*(S\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
TEST_ROW = re.compile(r"^\|\s*(R\d+)\s*\|")
WHY_LINE = re.compile(r"^\s*Why\s*[:：]?\s*$", re.IGNORECASE)
PRD_NAME = re.compile(r"^PRD(-v\d+)?\.md$")
ID_TOKEN = re.compile(r"^(R|D|S)(\d+)$")
REVIEW_TOKENS = ("key", "routine", "verification")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SUBMIT_CAP = 65536


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


def first_line(section):
    for line in section or []:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


class Model(object):
    """Parsed R/D/S anchors. Empty families are legal (draft PRDs)."""

    def __init__(self):
        self.requirements = []   # {"id", "text"}
        self.decisions = []      # {"id", "title", "lines", "refs", "door", "blast"}
        self.slices = []         # {"id", "outcome", "covers", "depends", "review"}
        self.test_rows = []      # {"id", "cells"}
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
                model.requirements.append({"id": match.group(1), "text": match.group(2).strip()})

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
                }
                model.decisions.append(current)
                continue
            if current is None:
                continue
            current["lines"].append(line.rstrip())
            refs = REFS_LINE.match(line)
            if refs and not current["refs"]:
                current["refs"] = ref_tokens(refs.group(1))
            door = DOOR_LINE.match(line)
            if door and not current["door"]:
                current["door"] = door.group(1).lower()
            blast = BLAST_LINE.match(line)
            if blast and not current["blast"]:
                current["blast"] = blast.group(1).strip()

    slices = find_section(sections, "实施切片")
    if slices:
        for line in slices:
            match = S_ROW.match(line)
            if not match:
                continue
            depends = ref_tokens(match.group(4))
            model.slices.append({
                "id": match.group(1),
                "outcome": match.group(2).strip(),
                "covers": ref_tokens(match.group(3)),
                "depends": [] if depends == ["-"] else depends,
                "review": match.group(5).strip().lower() or "routine",
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
    """Next spec-review.json: keep accepted_digest, refresh the rendered half."""
    return {
        "schema_version": 1,
        "spec": prd_name,
        "last_rendered_digest": digest,
        "last_rendered_items": model.hashes(),
        "accepted_digest": previous.get("accepted_digest"),
    }


CSS = """body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;color:#1c2733;background:#f6f8fa}
main{max-width:980px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;border-bottom:1px solid #d5dde5;padding-bottom:4px}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:10px;background:#dce8f5;margin-left:8px}
.badge.delta{background:#f5e3c8}.cards{display:grid;gap:12px}
.card{background:#fff;border:1px solid #d5dde5;border-radius:8px;padding:12px 14px}
.card .title{font-weight:600}.card .meta{font-size:12px;color:#5a6b7b;margin-top:6px}
.door{color:#a23b3b;font-weight:600}.risk{color:#8a6d1a}
table{border-collapse:collapse;width:100%;background:#fff;font-size:14px}
th,td{border:1px solid #d5dde5;padding:6px 10px;text-align:left;vertical-align:top}
details{margin-top:6px}summary{cursor:pointer;font-size:13px;color:#345}
textarea{width:100%;min-height:72px;font-family:ui-monospace,monospace;font-size:12px;box-sizing:border-box}
.controls{margin-top:8px;font-size:13px}.controls label{margin-right:14px}
button{margin-top:10px;padding:6px 18px;border-radius:6px;border:1px solid #345;background:#2b5c8a;color:#fff;cursor:pointer}
.foot{margin-top:30px;font-size:12px;color:#5a6b7b}
.first{background:#fff;border:1px solid #d5dde5;border-radius:8px;padding:16px;margin-bottom:8px}
.first .row{display:flex;gap:24px;flex-wrap:wrap;margin-top:8px}
.first .stat b{display:block;font-size:20px}.first .stat span{font-size:12px;color:#5a6b7b}
.muted{color:#5a6b7b;font-size:13px}
.state{font-size:12px;padding:1px 6px;border-radius:8px;margin-right:6px}
.state.MODIFIED,.state.AFFECTED{background:#f5e3c8}.state.ADDED{background:#d9ecd9}
.state.REMOVED{background:#f2d4d4}.state.UNCHANGED{background:#e8edf2}
"""


def svg_design_map(model):
    """Layered SVG of the S# dependency DAG; deterministic coordinates."""
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
            label = html.escape(slices[item_id]["outcome"][:10] or item_id)
            parts.append(
                '<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s"/>'
                '<text x="%d" y="%d" text-anchor="middle" font-size="13" fill="#1c2733">%s</text>'
                '<text x="%d" y="%d" text-anchor="middle" font-size="11" fill="#5a6b7b">%s</text>'
                % (
                    x, y, box_w, box_h,
                    "#f5e3c8" if slices[item_id]["review"] == "key" else "#e8edf2",
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


def first_screen(feature, mode, model, delta, sections):
    goal = first_line(find_section(sections, "问题")) or "（PRD 无 问题 段）"
    success = first_line(find_section(sections, "方案")) or "（PRD 无 方案 段）"
    one_way = [item["id"] for item in model.decisions if item["door"] == "one-way"]
    blasts = [item["blast"] for item in model.decisions if item["blast"]]
    key_slices = [
        item["id"] for item in model.slices if item["review"] in ("key", "verification")
    ]
    proofs = []
    for row in model.test_rows:
        observable = row["cells"][3] if len(row["cells"]) > 3 else (
            row["cells"][1] if len(row["cells"]) > 1 else ""
        )
        if observable and observable not in proofs:
            proofs.append(observable)
    if mode == "delta":
        changed = len(delta["ADDED"]) + len(delta["MODIFIED"]) + len(delta["AFFECTED"])
        counts = "%d 项 changed / %d removed / %d unchanged" % (
            changed, len(delta["REMOVED"]), len(delta["UNCHANGED"])
        )
    else:
        counts = "R %d · D %d · S %d" % (
            len(model.requirements), len(model.decisions), len(model.slices)
        )
    return {
        "feature": feature,
        "mode": mode,
        "goal": goal,
        "success": success,
        "counts": counts,
        "one_way": one_way,
        "blast": "、".join(sorted(set(blasts))) or "未标注",
        "decide": len(one_way) + len(key_slices),
        "proofs": proofs[:3],
    }


def state_badge(mode, delta, item_id):
    if mode != "delta":
        return ""
    for state in ("ADDED", "MODIFIED", "REMOVED", "AFFECTED", "UNCHANGED"):
        if item_id in delta.get(state, []):
            return '<span class="state %s">%s</span>' % (state, state)
    return ""


def review_html(feature, prd_name, prd_text, digest, model, delta, mode, bridge, token="", url=""):
    sections = h2_sections(prd_text)
    screen = first_screen(feature, mode, model, delta, sections)
    hashes = model.hashes()
    out = []
    add = out.append
    add('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    add("<title>%s — spec review</title><style>%s</style></head><body><main>" % (
        html.escape(feature), CSS))
    add('<div class="first"><h1>%s<span class="badge %s">%s Review</span></h1>' % (
        html.escape(feature),
        "delta" if mode == "delta" else "",
        "Delta" if mode == "delta" else "Full"))
    add('<div class="muted">目标：%s</div>' % html.escape(screen["goal"]))
    add('<div class="muted">成功定义：%s</div>' % html.escape(screen["success"]))
    add('<div class="row">')
    add('<div class="stat"><b>%s</b><span>本次变化</span></div>' % html.escape(screen["counts"]))
    add('<div class="stat"><b>%d</b><span>one-way door</span></div>' % len(screen["one_way"]))
    add('<div class="stat"><b>%s</b><span>Blast Radius</span></div>' % html.escape(screen["blast"]))
    add('<div class="stat"><b>%d</b><span>需要你决定</span></div>' % screen["decide"])
    add("</div></div>")
    if mode == "delta" and delta["REMOVED"]:
        add('<details open><summary>本次移除（%d）：%s</summary></details>' % (
            len(delta["REMOVED"]), html.escape("、".join(delta["REMOVED"]))))
    add("<h2>什么与为什么</h2>")
    add('<div class="cards">')
    for word, label in (("问题", "问题"), ("方案", "方案"), ("不在本次范围内", "不做什么")):
        body = find_section(sections, word)
        if body is None:
            continue
        add('<div class="card"><div class="title">%s</div><div class="muted">%s</div></div>' % (
            label, html.escape(first_line(body))))
    add("</div>")
    if len(model.slices) > 1:
        add("<h2>Design Map</h2>")
        add(svg_design_map(model))
    add("<h2>Requirements</h2>")
    add("<table><tr><th>行为</th><th>期望结果</th><th>怎么证明</th></tr>")
    for row in model.test_rows:
        cells = row["cells"]
        scenario = cells[1] if len(cells) > 1 else row["id"]
        seam = cells[2] if len(cells) > 2 else "—"
        observable = cells[3] if len(cells) > 3 else ""
        evidence = cells[4] if len(cells) > 4 else (cells[-1] if len(cells) > 2 else "")
        detail = "%s · 接缝 %s" % (row["id"], seam)
        proof = "%s（%s）" % (observable, evidence) if evidence else observable
        add(
            "<tr><td>%s%s<details><summary>技术细节</summary><div class=\"muted\">%s</div></details></td>"
            "<td>%s</td><td>%s</td></tr>" % (
                state_badge(mode, delta, row["id"]), html.escape(scenario),
                html.escape(detail), html.escape(observable), html.escape(proof)))
    add("</table>")
    if not model.test_rows:
        for item in model.requirements:
            add('<div class="card"><div class="title">%s%s</div><div class="muted">%s</div></div>' % (
                state_badge(mode, delta, item["id"]), html.escape(item["text"]),
                html.escape(item["id"])))
    add("<h2>Key Decisions</h2><div class=\"cards\">")
    for item in model.decisions:
        body = [line for line in item["lines"][1:] if line.strip()]
        decision = html.escape(body[0].strip()) if body else ""
        why = ""
        for index, line in enumerate(body):
            if WHY_LINE.match(line) and index + 1 < len(body):
                why = html.escape(body[index + 1].strip())
                break
        door = '<span class="door">Door: %s</span>' % item["door"] if item["door"] else ""
        blast = (
            '<span class="risk">Blast Radius: %s</span>' % html.escape(item["blast"])
            if item["blast"] else ""
        )
        controls = ""
        if bridge:
            controls = (
                '<div class="controls">'
                '<label><input type="radio" name="%s" value="approve" checked>通过</label>'
                '<label><input type="radio" name="%s" value="change">需要修改</label>'
                '<label><input type="radio" name="%s" value="question">有问题</label>'
                '<textarea name="%s-comment" placeholder="批注（可选）"></textarea></div>'
                % (item["id"], item["id"], item["id"], item["id"])
            )
        add(
            '<div class="card"><div class="title">%s%s %s</div><div>%s</div>'
            '<div class="muted">Why：%s</div><div class="meta">%s %s</div>%s'
            '<details><summary>锚点</summary><div class="muted">%s · %s</div></details></div>'
            % (
                state_badge(mode, delta, item["id"]), html.escape(item["id"]),
                html.escape(item["title"]), decision, why, door, blast, controls,
                html.escape(item["id"]), hashes.get(item["id"], "")[:12],
            )
        )
    add("</div>")
    add("<h2>Implementation Slices</h2>")
    add("<table><tr><th>Slice</th><th>Outcome</th><th>Covers</th><th>Depends</th><th>Review</th></tr>")
    for item in model.slices:
        add("<tr><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            state_badge(mode, delta, item["id"]), html.escape(item["id"]),
            html.escape(item["outcome"]), html.escape(" ".join(item["covers"])),
            html.escape(" ".join(item["depends"]) or "—"), html.escape(item["review"])))
    add("</table>")
    for item in model.slices:
        if item["review"] == "routine":
            add('<details><summary>%s（routine，默认折叠）</summary><div class="muted">%s</div></details>' % (
                html.escape(item["id"]), html.escape(item["outcome"])))
    add("<h2>验证方式</h2><div class=\"cards\">")
    for proof in screen["proofs"]:
        add('<div class="card"><div class="muted">%s</div></div>' % html.escape(proof))
    if not screen["proofs"]:
        add('<div class="card"><div class="muted">PRD 测试决策段无可观察结果行</div></div>')
    add("</div>")
    if bridge:
        add("<h2>提交</h2>")
        add('<div class="card"><textarea id="global-feedback" placeholder="全局反馈（可选）"></textarea>')
        add('<button id="approve">Approve current design</button> ')
        add('<button id="feedback">Submit feedback</button><div id="result" class="muted"></div></div>')
        add('<script type="application/json" id="bridge-data">%s</script>' % json.dumps(
            {"token": token, "url": url, "spec": prd_name, "spec_digest": digest,
             "items": {item_id: value for item_id, value in hashes.items()}},
            ensure_ascii=False,
        ).replace("</", "<\\/"))
        add("<script>%s</script>" % BRIDGE_JS)
    else:
        add("<h2>复制反馈（fallback）</h2>")
        add('<div class="card"><div class="muted">把要改的条目按模板填好后整体复制回 Harness；'
            "digest 与当前 PRD 不一致时反馈视为过期。</div>")
        add('<textarea readonly>{"status":"feedback","spec":"%s","spec_digest":"%s",\n'
            ' "items":[{"id":"D1","hash":"…","action":"change","comment":"…"}],\n'
            ' "global_feedback":"…"}\n</textarea>' % (prd_name, digest))
        add("</div>")
    add('<div class="foot">spec %s · digest %s · %s</div>' % (
        html.escape(prd_name), digest[:12], "one-shot bridge" if bridge else "static render"))
    add("</main></body></html>")
    return "".join(out)

BRIDGE_JS = """
(function(){
var data=JSON.parse(document.getElementById('bridge-data').textContent);
function collect(action){
 var items=[];
 document.querySelectorAll('.controls').forEach(function(box){
  var comment=box.querySelector('textarea').value.trim();
  var choice=box.querySelector('input[type=radio]:checked');
  if(choice&&(choice.value!=='approve'||comment)){
   items.push({id:choice.name,hash:data.items[choice.name],action:choice.value,comment:comment||''});
  }
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
                if not isinstance(item, dict) or item.get("id") not in known:
                    self.respond(400, {"status": "error", "message": "unknown item id"})
                    return
                if item.get("action") not in ("approve", "change", "question"):
                    self.respond(400, {"status": "error", "message": "invalid item action"})
                    return
                item["hash"] = known[item["id"]]
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
        state["accepted_digest"] = prepared["digest"]
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
        if not isinstance(accepted, str) or not HEX64.match(accepted):
            problems.append("%s has no recorded human acceptance" % prd_name)
        elif accepted != digest:
            problems.append(
                "accepted_digest %s… != current %s digest %s…; re-review before materializing"
                % (accepted[:12], prd_name, digest[:12])
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
        "accepted_digest": digest,
    })
    if not state.get("last_rendered_digest"):
        state["last_rendered_digest"] = digest
        state["last_rendered_items"] = model.hashes()
    save_state(feature_dir, state)
    print(json.dumps(
        {"status": "accepted", "spec": prd_name, "spec_digest": digest}, ensure_ascii=False))
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
