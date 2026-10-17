#!/usr/bin/env python
# Deterministic human review of a feature contract (.scratch/<feat>/FEATURE.md): renders the
# Full/Delta page and runs the one-shot localhost bridge that records the decision.
# Stdlib only; no model calls. Exit: 0 ok, 1 violation/timeout, 2 usage.
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
import feature_doc
from evidence import atomic_write, file_lock, write_record

NOTE_TOKEN = re.compile(r"^Q\d+$")
META_LINE = feature_doc.META_LINE
SUBMIT_CAP = 65536


def classify_delta(model, old_items):
    """Item-level classification against the accepted hashes; refs propagate as AFFECTED."""
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
    global_change = any(not feature_doc.ID_TOKEN.fullmatch(key) for key in changed)
    affected = set()
    while True:
        added = {key for key in result["UNCHANGED"] if key not in affected
                 and ((global_change and feature_doc.ID_TOKEN.fullmatch(key))
                      or model.refs_of(key) & (changed | affected))}
        if not added:
            break
        affected.update(added)
    result["AFFECTED"] = sorted(affected)
    result["UNCHANGED"] = [key for key in result["UNCHANGED"] if key not in affected]
    return result


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
    """The decision area: direction decisions (`Review: human`) first, then one-way doors."""
    return sorted(model.review_required_items(), key=lambda item: not item["human"])


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


def requirement_card(item, mode, delta, previous=None):
    parts = []
    if previous is not None and mode == "delta" and item["id"] in delta["MODIFIED"]:
        parts.append('<p class="before">已接受：%s</p>' % html.escape(previous["text"]))
        if previous["check"] != item["check"]:
            parts.append('<p class="before">原验收观察：%s</p>' % html.escape(previous["check"] or "未记录"))
    if item["before"]:
        parts.append('<p class="before">现状：%s</p>' % html.escape(item["before"]))
    parts.append('<p class="after">预期：%s</p>' % html.escape(item["text"]))
    if item["check"]:
        parts.append('<p>验收观察：%s</p>' % html.escape(item["check"]))
    return ('<div class="card" id="%s"><div class="title">%s%s</div><div class="body">%s</div></div>'
            % (item["id"], state_badge(mode, delta, item["id"]), html.escape(item["id"]), "".join(parts)))


def review_html(feature, digest, model, delta, mode, bridge, token="", url="", baseline=None):
    hashes = model.hashes()
    decide_items = review_items(model)
    if mode == "delta":
        reviewed = {item["id"] for item in review_items(baseline)}
        touched = set(delta["ADDED"] + delta["MODIFIED"] + delta["AFFECTED"])
        decide_items += [item for item in model.decisions if item not in decide_items
                         and (item["id"] in reviewed or item["id"] in touched)]
    previous_decisions = {item["id"]: item for item in baseline.decisions} if baseline else {}
    previous_requirements = {item["id"]: item for item in baseline.requirements} if baseline else {}
    out = []
    add = out.append
    label = "Delta" if mode == "delta" else "Full"
    add('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    add("<title>%s — feature review</title><style>%s</style></head><body><main>" % (html.escape(feature), CSS))
    add('<nav class="topnav"><span class="brand">%s · %s Review</span>' % (html.escape(feature), label))
    for anchor, text, show in (("goal", "目标", True), ("behavior", "需求 %d" % len(model.requirements), model.requirements),
                               ("contracts", "不变量 %d" % len(model.contracts), model.contracts),
                               ("acceptance", "验收", model.acceptance)):
        if show:
            add('<a href="#%s">%s</a>' % (anchor, text))
    if decide_items or model.questions:
        add('<a href="#decide"><b>填写 %d</b></a>' % (len(decide_items) + len(model.questions)))
    add('<a href="#submit"><b>提交</b></a></nav>')
    add('<section class="hero"><h1>%s<span class="badge %s">%s Review</span></h1>'
        % (html.escape(feature), "delta" if mode == "delta" else "", label))
    add('<p class="counts">%d 项决策 · %d 项需求 · %d 条不变量 · %d 条疑问</p>'
        % (len(decide_items), len(model.requirements), len(model.contracts), len(model.questions)))
    if mode == "delta":
        add('<p class="muted">对照已接受的版本：先看变化与影响，再到页尾集中填写意见。</p>')
    add("</section>")
    if mode == "delta":
        current_text, previous_text = model.item_texts(), baseline.item_texts()
        boundary = [key for kind in ("ADDED", "MODIFIED", "REMOVED") for key in delta[kind]
                    if not feature_doc.ID_TOKEN.fullmatch(key)]
        if boundary:
            add('<h2 id="changes">需要留意的边界变化</h2>')
        for key in boundary:
            add('<div class="card"><div class="title">%s%s</div><div class="scopecols">'
                % (state_badge(mode, delta, key), html.escape(feature_doc.SECTION_LABELS.get(key, key))))
            add('<div><b>已接受</b><pre class="compare">%s</pre></div>' % html.escape(previous_text.get(key, "")))
            add('<div><b>本次</b><pre class="compare">%s</pre></div></div></div>' % html.escape(current_text.get(key, "")))
        removed = [key for key in delta["REMOVED"] if feature_doc.ID_TOKEN.fullmatch(key)]
        if removed:
            add('<h2>本次移除</h2>')
            for key in removed:
                old = previous_requirements.get(key) or previous_decisions.get(key)
                body = [old["text"]] if "text" in old else old["lines"]
                add('<div class="card"><div class="title">%s</div>%s</div>' % (html.escape(key), paragraphs_html(body)))
        if not any(delta[kind] for kind in ("ADDED", "MODIFIED", "REMOVED", "AFFECTED")):
            add('<p>没有待审内容变化。</p>')
    add('<h2 id="goal">目标与边界</h2>')
    for title, lines in (("问题", model.problem), ("预期结果", model.outcome)):
        if lines:
            add('<div class="card"><div class="title">%s</div><div class="body">%s</div></div>' % (title, paragraphs_html(lines)))
    if model.scope_in or model.scope_out:
        add('<div class="card scopecard"><div class="scopecols"><div><b>IN</b>%s</div><div><b>OUT</b>%s</div></div></div>' % (
            "".join('<div class="in">✓ %s</div>' % html.escape(line) for line in model.scope_in),
            "".join('<div class="out">— %s</div>' % html.escape(line) for line in model.scope_out)))
    if model.requirements:
        add('<h2 id="behavior">需求 · %d</h2><div class="cards">' % len(model.requirements))
        for item in model.requirements:
            add(requirement_card(item, mode, delta, previous_requirements.get(item["id"])))
        add("</div>")
    if model.contracts:
        add('<h2 id="contracts">必须守住的边界 · %d</h2><div class="cards">' % len(model.contracts))
        add("".join(contract_card(item) for item in model.contracts) + "</div>")
    if model.acceptance:
        add('<h2 id="acceptance">如何判断交付合格</h2><div class="card"><div class="body">%s</div></div>'
            % paragraphs_html(model.acceptance, by_line=True))
    if model.controls["section:context"]:
        add('<h3>补充说明</h3><div class="card">%s</div>' % paragraphs_html(model.controls["section:context"].split("\n")))
    shown = {item["id"] for item in decide_items}
    others = [item for item in model.decisions if item["id"] not in shown]
    if others:
        add('<h3>AI 负责的工程决策</h3><div class="cards">%s</div>'
            % "".join(decision_card(item, mode, delta, hashes) for item in others))
    if decide_items or model.questions:
        add('<h2 id="decide">需要你拍板 · %d</h2><div class="cards">' % (len(decide_items) + len(model.questions)))
        for number, item in enumerate(decide_items, 1):
            add(decision_card(item, mode, delta, hashes, pose=True, number=number,
                              previous=previous_decisions.get(item["id"])))
        for number, text in enumerate(model.questions, 1):
            add(note_card("Q", number, text, answerable=True))
        add("</div>")
    add('<h2 id="submit">反馈</h2>')
    add('<div class="card"><textarea id="global-feedback" placeholder="GLOBAL 反馈（可选）"></textarea>')
    data = {"spec": feature, "spec_digest": digest, "items": hashes}
    if bridge:
        data.update(token=token, url=url)
        add('<button id="approve" type="button">全部确定</button> ')
        add('<button id="feedback" type="button">提交反馈</button><div id="result" class="muted"></div></div>')
        add('<script type="application/json" id="bridge-data">%s</script>'
            % json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
        add("<script>%s</script>" % BRIDGE_JS)
    else:
        add('<div class="muted">静态预览仅收集反馈。复制后贴回对话；批准请使用 review 命令打开的人审页面。</div>')
        add('<textarea id="feedback-text" readonly></textarea>')
        add('<button id="copy-feedback" type="button">复制反馈</button></div>')
        add('<script type="application/json" id="feedback-data">%s</script>'
            % json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
        add("<script>%s</script>" % STATIC_JS)
    add('<div class="foot">feature %s · contract digest %s · %s</div>'
        % (html.escape(feature), digest[:12], "one-shot bridge" if bridge else "static render"))
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


def prepare_review(root, name, force_full=False):
    """Validate the contract, pick the accepted baseline and classify the delta."""
    feature = feature_doc.load(root, name)
    problems = feature_doc.validate_model(feature.model) + feature.model.problems
    if problems:
        raise ValueError("feature contract violations: " + "; ".join(sorted(set(problems))))
    text = feature_doc.contract_text(feature.text)
    record = feature_doc.accepted_record(feature)
    baseline = None if force_full or record is None else feature_doc.parse_model(record["text"])
    delta = classify_delta(feature.model, baseline.hashes()) if baseline else None
    return {"feature": feature, "text": text, "digest": feature_doc.sha256_text(text),
            "model": feature.model, "baseline": baseline, "delta": delta,
            "mode": "delta" if baseline else "full"}


def page(prepared, bridge, token="", url=""):
    return review_html(prepared["feature"].name, prepared["digest"], prepared["model"], prepared["delta"],
                       prepared["mode"], bridge, token, url, prepared["baseline"])


def write_review_page(feature_dir, text, requested=None):
    name = "page-" + hashlib.sha256(text.encode()).hexdigest()[:16] + ".html"
    target = Path(requested) if requested else Path(feature_dir) / feature_doc.REVIEWS / name
    with file_lock(target.with_name(target.name + ".lock")):
        if target.exists() and target.read_text(encoding="utf-8") != text:
            raise ValueError("review page is immutable; choose a new path")
        atomic_write(target, text)
    return target


def cmd_render(root, name, force_full, out_path=None):
    prepared = prepare_review(root, name, force_full)
    target = write_review_page(prepared["feature"].directory, page(prepared, False), out_path)
    counts = ({state: len(items) for state, items in prepared["delta"].items()} if prepared["delta"]
              else {"items": len(prepared["model"].hashes())})
    print(json.dumps({"status": "rendered", "feature": name, "spec_digest": prepared["digest"],
                      "mode": prepared["mode"], "html": str(target), "counts": counts}, ensure_ascii=False))
    return 0


def persist_spec_decision(prepared, answer, payload, event_id):
    """One immutable record per human event; acceptance carries the exact accepted contract text."""
    feature = prepared["feature"]
    with file_lock(feature.directory / feature_doc.REVIEWS / ".decision.lock"):
        if feature_doc.sha256_text(feature_doc.contract_text(feature.path.read_text(encoding="utf-8-sig"))) != prepared["digest"]:
            raise ValueError("feature contract changed before decision persistence")
        event = {key: value for key, value in payload.items() if key != "token"}
        accepted = answer["status"] == "accepted"
        write_record(feature.directory / feature_doc.REVIEWS / (event_id + ".json"), {
            "kind": "spec_decision", "schema_version": 1, "event_id": event_id, "source": "local_review",
            "spec_digest": prepared["digest"], "accepted": accepted, "decided_at": time.time(),
            "text": prepared["text"] if accepted else None, "event": event})


def make_handler(spec_name, digest, model, html_text, token, result, persist, current_identity, assets=None):
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
                current_digest = current_identity()
            except (OSError, ValueError):
                self.respond(500, {"status": "error", "message": "contract unreadable; re-render"})
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
                answer = {"status": "accepted", "spec": spec_name, "spec_digest": digest}
            elif action == "feedback":
                if not items and not global_feedback:
                    self.respond(400, {"status": "error", "message": "empty feedback"})
                    return
                answer = {
                    "status": "feedback",
                    "spec": spec_name,
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
            persist(answer, payload, event_id)
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
    feature = prepared["feature"]
    token = secrets.token_urlsafe(32)
    result = {"done": False, "value": None, "lock": threading.Lock()}
    server = ThreadingHTTPServer(("127.0.0.1", port or 0), _Unavailable)
    try:
        url = "http://127.0.0.1:%d/" % server.server_address[1]
        identity = lambda: feature_doc.sha256_text(feature_doc.contract_text(feature.path.read_text(encoding="utf-8-sig")))
        persist = lambda answer, payload, event_id: persist_spec_decision(prepared, answer, payload, event_id)
        server.RequestHandlerClass = make_handler(
            feature.name, prepared["digest"], prepared["model"], page(prepared, True, token, url),
            token, result, persist, identity)
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
                return {"status": "timeout", "spec": prepared["name"], "spec_digest": prepared["digest"]}
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
        return serve_bridge(server, result, timeout, {"name": prepared["feature"].name, "digest": prepared["digest"]})
    finally:
        server.server_close()



def cmd_review(root, name, force_full, timeout, open_browser, port=0):
    prepared = prepare_review(root, name, force_full)
    write_review_page(prepared["feature"].directory, page(prepared, False))
    answer = run_bridge(prepared, timeout, open_browser, port)
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("status") in ("accepted", "feedback") else 1


def cmd_validate(root, name, require_accepted):
    feature = feature_doc.load(root, name)
    problems = sorted(set(feature_doc.validate_model(feature.model) + feature.model.problems))
    if require_accepted:
        try:
            record = feature_doc.accepted_record(feature)
        except ValueError as exc:
            record, problems = None, problems + [str(exc)]
        current = feature_doc.contract_text(feature.text)
        if record is None:
            problems.append("no recorded human acceptance")
        elif record["spec_digest"] != feature_doc.sha256_text(current):
            delta = classify_delta(feature.model, feature_doc.parse_model(record["text"]).hashes())
            moved = sorted(set(delta["ADDED"]) | set(delta["MODIFIED"]) | set(delta["REMOVED"]))
            problems.append("changed since acceptance: " + ", ".join(moved))
    if problems:
        print("spec-review validate: %d violation(s)" % len(problems))
        for problem in problems:
            print("  %s: %s" % (name, problem))
        return 1
    print("spec-review validate: OK - %s R %d, D %d%s." % (name, len(feature.model.requirements),
          len(feature.model.decisions), " · accepted" if require_accepted else ""))
    return 0


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
    server.RequestHandlerClass = make_handler(path.name, fixed["digest"], Model(), page, token,
                                               result, persist, identity, assets)
    print("spec-review: " + url, file=sys.stderr)
    try:
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception as exc:
                print("spec-review: open browser manually: %s (%s)" % (url, exc), file=sys.stderr)
        answer = serve_bridge(server, result, timeout, {"name": path.name, "digest": fixed["digest"]})
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
