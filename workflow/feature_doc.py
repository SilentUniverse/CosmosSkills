#!/usr/bin/env python3
"""The single feature document `.scratch/<feat>/FEATURE.md`: parse, validate, admit and close.

Every reader (artifact gate, engineering state, review surface, candidate binding) uses this
module, so a unit judged valid at write time is judged the same way at read time.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from pathlib import Path

FILE = "FEATURE.md"
REVIEWS = "reviews"
ENGINEERING_SECTIONS = ("共享验证", "任务", "变更记录")
KNOWN_SECTIONS = ("目标与边界", "需求", "决策", "不变量", "端到端验证", "尚未明确") + ENGINEERING_SECTIONS
FENCE = re.compile(r"^\s*(```|~~~)")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
NAME = r"[A-Za-z][A-Za-z0-9_-]*"
UNIT_HEAD = re.compile(r"^###\s+(T\d+)\b\s*[—\-–:：]?\s*(.*)$")
FIELD = re.compile(
    r"^-\s+(status|reason|blocked_by|covers|refines|touches|test_paths|resources|experience)\s*[:：]\s*(.*)$")
AC_LINE = re.compile(r"^-\s*\[[ xX]\]\s+(.*)$")
AC_MAP = re.compile(r"^(.*?)\s*(?:→|->)\s*`(" + NAME + r")`\s*$")
COMMAND = re.compile(r"^-\s+命令\s+(" + NAME + r")\s*[:：]\s*`([^`]+)`\s*$")
PREFLIGHT = re.compile(r"^-\s+预检\s+(" + NAME + r")\s*[:：]\s*(.+)$")
DONE_HEAD = re.compile(r"^####\s+完成(?:[^\w]|$)")
R_BULLET = re.compile(r"^\s*[-*]\s+(R\d+)\s*[—\-–]\s*(.+)$")
SUB_LINE = re.compile(r"^\s+(Before|验收)\s*[:：]\s*(.+)$", re.IGNORECASE)
D_HEAD = re.compile(r"^###\s+(D\d+)\s*[—\-–:>]?\s*(.*)$")
META_LINE = re.compile(r"^\s*(?:[-*]\s+)?(Refs|Door|Blast\s+radius|Review)\s*[:：]", re.IGNORECASE)
REFS_LINE = re.compile(r"^\s*(?:[-*]\s+)?Refs\s*[:：]\s*(.*)$", re.IGNORECASE)
META_DOOR = re.compile(r"Door\s*[:：]\s*(one-way|two-way)", re.IGNORECASE)
META_BLAST = re.compile(r"Blast\s+radius\s*[:：]\s*([^\s;；]+)", re.IGNORECASE)
META_HUMAN = re.compile(r"Review\s*[:：]\s*human\b", re.IGNORECASE)
C_BULLET = re.compile(r"^\s*[-*]\s+(C\d+)\s*[—\-–]\s*(.+)$")
GOAL_LINE = re.compile(r"^\s*[-*]\s+(问题|结果|IN|OUT)\s*[:：]\s*(.+)$", re.IGNORECASE)
ID_TOKEN = re.compile(r"^(R|D)\d+$")
STATUSES = ("pending", "ready", "done")
RUNTIME_KEYS = ("unexpected_console_errors", "uncaught_page_errors", "unexpected_failed_requests",
                "csp_violations", "decoded_media_failures")
SECTION_LABELS = {"section:goal": "目标与边界", "section:acceptance": "端到端验证",
                  "section:context": "补充约束与正文", "section:layout": "标题与版式"}


def normalize(text):
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tokens(value):
    return [token for token in re.split(r"[\s,，、;；/]+", (value or "").strip().strip("`")) if token]


def frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("FEATURE.md needs YAML frontmatter")
    data = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return data, index + 1
        match = FM_KEY.match(line)
        if match:
            data[match.group(1)] = match.group(2).strip().strip("\"'")
    raise ValueError("FEATURE.md frontmatter is not closed")


def fenced_flags(lines):
    """Per line: True inside (or on) a fenced code block, where headings and anchors do not count."""
    flags, fence = [], None
    for line in lines:
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
            flags.append(True)
        elif fence is not None:
            flags.append(True)
            if match and match.group(1) == fence:
                fence = None
        else:
            flags.append(False)
    return flags


def section_kind(heading):
    """A heading names a known section only by its leading word: `## 不变量（硬）` is 不变量."""
    return re.split(r"[\s（(:：]", heading.strip(), 1)[0]


def h2_sections(lines):
    """[(heading, [lines])] in document order; deeper and fenced headings stay in the body."""
    sections = []
    for line, fenced in zip(lines, fenced_flags(lines)):
        if line.startswith("## ") and not fenced:
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def section(sections, kind):
    for heading, lines in sections:
        if section_kind(heading) == kind:
            return lines
    return None


def anchor_lines(lines):
    """Lines that may carry anchors: everything outside fenced code blocks."""
    return [line for line, fenced in zip(lines, fenced_flags(lines)) if not fenced]


def contract_text(text):
    """Canonical human-reviewed contract: every non-engineering H2 section, blank lines dropped,
    so every byte of the digest is attributable to a reviewed item."""
    _, body = frontmatter(normalize(text))
    lines = normalize(text).split("\n")[body:]
    kept = []
    for heading, rows in h2_sections(lines):
        if section_kind(heading) in ENGINEERING_SECTIONS:
            continue
        kept.append("## " + heading)
        kept.extend(row.rstrip() for row in rows if row.strip())
    return "\n".join(kept).strip() + "\n"


def item_hash(item_id, canonical):
    return sha256_text("%s\n%s" % (item_id, canonical))


class Model(object):
    """Anchored, human-reviewable items of a feature contract."""

    def __init__(self):
        self.problem, self.outcome, self.scope_in, self.scope_out = [], [], [], []
        self.requirements, self.decisions, self.contracts, self.questions = [], [], [], []
        self.controls = {key: "" for key in SECTION_LABELS}
        self.acceptance = []
        self.problems = []

    def item_texts(self):
        table = dict(self.controls)
        for item in self.requirements:
            table[item["id"]] = "\n".join((item["text"], item["before"], item["check"]))
        for item in self.decisions:
            table[item["id"]] = "\n".join(line.rstrip() for line in item["lines"]).strip()
        table.update({item["id"]: item["text"] for item in self.contracts})
        table.update({"Q%d" % n: text for n, text in enumerate(self.questions, 1)})
        return table

    def hashes(self):
        return {key: item_hash(key, value) for key, value in self.item_texts().items()}

    def refs_of(self, item_id):
        for item in self.decisions:
            if item["id"] == item_id:
                return set(item["refs"])
        return set()

    def review_required_items(self):
        """Decisions the human must see: direction (`Review: human`) and one-way doors."""
        return [item for item in self.decisions if item["human"] or item["door"] == "one-way"]

    def gate_items(self):
        """Decisions whose acceptance must be recorded before execution: one-way doors only."""
        return [item for item in self.decisions if item["door"] == "one-way"]


def parse_model(text):
    """Parse the contract text (FEATURE.md or its canonical contract_text)."""
    text = normalize(text)
    if text.startswith("---\n"):
        text = contract_text(text)
    sections = h2_sections(text.split("\n"))
    model = Model()
    goal = section(sections, "目标与边界")
    for line in anchor_lines(goal or []):
        match = GOAL_LINE.match(line)
        if match:
            key, value = match.group(1).upper(), match.group(2).strip()
            {"问题": model.problem, "结果": model.outcome, "IN": model.scope_in,
             "OUT": model.scope_out}[key].append(value)
    requirements = section(sections, "需求")
    for line in anchor_lines(requirements or []):
        match = R_BULLET.match(line)
        if match:
            model.requirements.append({"id": match.group(1), "text": match.group(2).strip(),
                                       "before": "", "check": ""})
            continue
        sub = SUB_LINE.match(line)
        if sub:
            key = "before" if sub.group(1).lower() == "before" else "check"
            if not model.requirements or model.requirements[-1][key]:
                model.problems.append("%s line must follow its R# once" % sub.group(1))
            else:
                model.requirements[-1][key] = sub.group(2).strip()
    decisions = section(sections, "决策")
    current = None
    for line, fenced in zip(decisions or [], fenced_flags(decisions or [])):
        head = None if fenced else D_HEAD.match(line)
        if head:
            current = {"id": head.group(1), "title": head.group(2).strip(), "lines": [line.rstrip()],
                       "refs": [], "door": "", "blast": "", "human": False}
            model.decisions.append(current)
            continue
        if current is None:
            continue
        current["lines"].append(line.rstrip())
        if fenced or not META_LINE.match(line):
            continue
        refs = REFS_LINE.match(line)
        if refs:
            if current["refs"]:
                model.problems.append("%s repeats Refs; use one declaration" % current["id"])
            current["refs"] = tokens(refs.group(1))
        door, blast = META_DOOR.search(line), META_BLAST.search(line)
        if door and not current["door"]:
            current["door"] = door.group(1).lower()
        if blast and not current["blast"]:
            current["blast"] = blast.group(1)
        if META_HUMAN.search(line):
            current["human"] = True
    for line in anchor_lines(section(sections, "不变量") or []):
        match = C_BULLET.match(line)
        if match:
            model.contracts.append({"id": match.group(1), "text": match.group(2).strip()})
    for line in section(sections, "尚未明确") or []:
        stripped = re.sub(r"^[-*]\s+", "", line.strip())
        if stripped:
            model.questions.append(stripped)
    model.acceptance = [line for line in section(sections, "端到端验证") or [] if line.strip()]
    residual = []
    for heading, lines in sections:
        if lines is goal:
            model.controls["section:goal"] = "\n".join(line.rstrip() for line in lines).strip()
            lines = [line for line in lines if line.strip() and not GOAL_LINE.match(line)]
        elif lines is requirements:
            anchored = set(id(line) for line in anchor_lines(lines) if R_BULLET.match(line) or SUB_LINE.match(line))
            lines = [line for line in lines if id(line) not in anchored]
        elif lines is decisions:
            lines = lines[:next((n for n, (line, fenced) in enumerate(zip(lines, fenced_flags(lines)))
                                 if not fenced and D_HEAD.match(line)), len(lines))]
        elif section_kind(heading) == "不变量":
            lines = [line for line in lines if not C_BULLET.match(line)]
        elif section_kind(heading) == "尚未明确":
            continue
        elif section_kind(heading) == "端到端验证":
            model.controls["section:acceptance"] = "\n".join(model.acceptance)
            continue
        lines = [line.rstrip() for line in lines if line.strip()]
        if lines:
            residual.extend([heading] + lines)
    model.controls["section:context"] = "\n".join(residual)
    # Section headings are reviewed text that no other item carries.
    model.controls["section:layout"] = "\n".join(heading for heading, _ in sections)
    return model


def validate_model(model):
    problems = list(model.problems)
    for family in (model.requirements, model.decisions, model.contracts):
        seen = set()
        for item in family:
            if item["id"] in seen:
                problems.append("duplicate id %s" % item["id"])
            seen.add(item["id"])
    requirement_ids = {item["id"] for item in model.requirements}
    for item in model.decisions:
        for token in item["refs"]:
            if not re.fullmatch(r"R\d+", token):
                problems.append("%s refs %r must reference R#" % (item["id"], token))
            elif token not in requirement_ids:
                problems.append("%s references undeclared %s" % (item["id"], token))
    return problems


def design_matches(current, accepted, needed):
    """Covered R/D anchors (with their refs) and every global item equal the accepted contract."""
    expanded = set(needed)
    while True:
        more = expanded | set().union(*(current.refs_of(key) for key in expanded), set())
        if more == expanded:
            break
        expanded = more
    left, right = current.hashes(), accepted.hashes()
    globals_ = {key for key in set(left) | set(right) if not ID_TOKEN.fullmatch(key)}
    return all(left.get(key) == right.get(key) for key in expanded | globals_)


class Unit(object):
    def __init__(self, unit_id, title, line):
        self.id, self.title, self.line, self.end = unit_id, title, line, line
        self.body, self.completion = [], None
        self.fields = {}
        self.problems = []

    @property
    def status(self):
        return self.fields.get("status", "")

    def values(self, key):
        return tokens(self.fields.get(key, ""))

    def contract_lines(self):
        return [line for line in self.body
                if not re.match(r"^-\s+(status|reason)\s*[:：]", line)]

    def digest(self):
        lines = [line.rstrip() for line in self.contract_lines()]
        while lines and not lines[-1]:
            lines.pop()
        return sha256_text("\n".join(lines) + "\n")

    def objective(self):
        return [line for line in self.body if re.match(r"^-\s+做什么\s*[:：]\s*\S", line.strip())]

    def acceptance(self):
        result = []
        for line in self.body:
            match = AC_LINE.match(line.strip())
            if match:
                mapped = AC_MAP.match(match.group(1))
                result.append((mapped.group(1).strip(), mapped.group(2)) if mapped
                              else (match.group(1).strip(), None))
        return result

    def commands(self):
        return {m.group(1): m.group(2) for m in map(COMMAND.match, (l.strip() for l in self.body)) if m}

    def preflights(self):
        return {m.group(1): m.group(2) for m in map(PREFLIGHT.match, (l.strip() for l in self.body)) if m}

    def completion_values(self, key):
        values = []
        for line in self.completion or []:
            match = re.match(r"^-\s+" + key + r"\s*[:：]\s*(.+)$", line.strip())
            if match:
                values.append(match.group(1).strip().strip("`"))
        return values


class Feature(object):
    def __init__(self, root, name, path, text):
        self.root, self.name, self.path, self.text = Path(root), name, Path(path), normalize(text)
        self.problems = []
        try:
            self.meta, body = frontmatter(self.text)
        except ValueError as exc:
            self.meta, body = None, 0
            self.problems.append(str(exc))
        self.lines = self.text.split("\n")
        self.sections = h2_sections(self.lines[body:])
        kinds = [section_kind(heading) for heading, _ in self.sections]
        for kind in sorted({kind for kind in kinds if kind in KNOWN_SECTIONS and kinds.count(kind) > 1}):
            self.problems.append("section %s appears more than once" % kind)
        self.model = parse_model(contract_text(self.text) if self.meta is not None else "")
        self.verifier, self.shared_preflights = self._verifier()
        self.units = self._units(body)

    @property
    def directory(self):
        return self.path.parent

    def _verifier(self):
        lines = section(self.sections, "共享验证")
        if lines is None:
            return None, {}
        blob, inside, blocks = [], False, 0
        for line in lines:
            if FENCE.match(line):
                if not inside:
                    blocks += 1
                inside = not inside
                continue
            if inside and blocks == 1:
                blob.append(line)
        found = blocks == 1 and not inside
        if blocks > 1:
            self.problems.append("共享验证 must hold exactly one fenced JSON block")
            return None, {}
        preflights = {m.group(1): m.group(2) for m in map(PREFLIGHT.match, (l.strip() for l in lines)) if m}
        if not found:
            self.problems.append("共享验证 needs one fenced JSON block")
            return None, preflights
        try:
            value = json.loads("\n".join(blob))
        except ValueError as exc:
            self.problems.append("共享验证 JSON is invalid: %s" % exc)
            return None, preflights
        problem = verifier_problem(self.root, value)
        if problem:
            self.problems.append("共享验证 " + problem)
            return None, preflights
        return value, preflights

    def _units(self, body):
        """Units under 任务; each records its exclusive end line so writers never re-scan."""
        units, inside = [], False
        lines = self.lines[body:]
        for number, (line, fenced) in enumerate(zip(lines, fenced_flags(lines)), start=body + 1):
            if line.startswith("## ") and not fenced:
                if units and inside:
                    units[-1].end = number - 1
                inside = section_kind(line[3:]) == "任务"
                continue
            if not inside:
                continue
            head = None if fenced else UNIT_HEAD.match(line)
            if head:
                if units:
                    units[-1].end = number - 1
                units.append(Unit(head.group(1), head.group(2).strip(), number))
                continue
            if line.startswith("### ") and not fenced:
                self.problems.append("line %d: unit heading must be '### T<n> — title'" % number)
                continue
            if not units:
                continue
            unit = units[-1]
            unit.end = number
            if DONE_HEAD.match(line) and not fenced:
                if unit.completion is not None:
                    unit.problems.append("has more than one 完成 record")
                unit.completion = []
                continue
            if unit.completion is not None:
                if line.strip() and not re.match(r"^-\s+(contract|candidate|evidence)\s*[:：]", line.strip()):
                    unit.problems.append("完成 record may hold only contract, candidate and evidence lines")
                unit.completion.append(line)
                continue
            unit.body.append(line)
            match = FIELD.match(line.strip())
            if match:
                if match.group(1) in unit.fields:
                    unit.problems.append("repeats field %s" % match.group(1))
                unit.fields[match.group(1)] = match.group(2).strip()
        return units

    def unit(self, unit_id):
        matches = [unit for unit in self.units if unit.id == unit_id]
        if len(matches) != 1:
            raise ValueError("%s: no single unit %s" % (self.name, unit_id))
        return matches[0]

    def review_required(self):
        """Declared, implied by a decision flag, or already accepted once: acceptance never lapses."""
        if (self.meta or {}).get("review") == "required" or self.model.gate_items():
            return True
        records, problems = review_records(self)
        return bool(problems) or any(record.get("accepted") is True for record in records)

    def effective(self, unit):
        """Shared verifier with this unit's named command overrides; None when unavailable."""
        if self.verifier is None:
            return None
        value = dict(self.verifier)
        value["commands"] = dict(self.verifier["commands"], **unit.commands())
        value["preflights"] = dict(self.shared_preflights, **unit.preflights())
        return value


def verifier_problem(root, value):
    if not isinstance(value, dict):
        return "must be a JSON object"
    allowed = {"cwd", "environment", "prepare", "commands", "experience"}
    if set(value) - allowed:
        return "has unknown keys: " + ", ".join(sorted(set(value) - allowed))
    cwd = value.get("cwd")
    if not isinstance(cwd, str) or not cwd or os.path.isabs(cwd) or ".." in cwd.replace("\\", "/").split("/"):
        return "cwd must be a repo-relative directory"
    if not (Path(root) / cwd).is_dir():
        return "cwd does not exist: " + cwd
    environment = value.get("environment")
    if not isinstance(environment, dict) or not environment or any(
            not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in environment.items()):
        return "environment must map identity names to non-empty strings"
    prepare = value.get("prepare")
    if not isinstance(prepare, str) or not prepare.strip():
        return "prepare must record the executed setup or 无"
    commands = value.get("commands")
    if not isinstance(commands, dict) or not commands or any(
            not re.fullmatch(NAME, str(k)) or not isinstance(v, str) or not v.strip() for k, v in commands.items()):
        return "commands must map names to non-empty command lines"
    if "experience" in value:
        problem = experience_contract_problem(value["experience"])
        if problem:
            return "experience " + problem
    return None


def load(root, name):
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("feature must be one directory name")
    root = Path(root).resolve()
    path = root / ".scratch" / name / FILE
    if not path.is_file():
        raise ValueError("feature '%s' has no %s" % (name, FILE))
    return Feature(root, name, path, path.read_bytes().decode("utf-8-sig"))


def feature_names(root):
    scratch = Path(root) / ".scratch"
    if not scratch.is_dir():
        return []
    return sorted(p.name for p in scratch.iterdir() if (p / FILE).is_file())


def _windows_argv(command):
    """CommandLineToArgvW double-quote rules, plus POSIX-shell single-quote grouping."""
    argv, index = [], 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index == len(command):
            break
        argument, quote = [], ""
        while index < len(command):
            char = command[index]
            if char in " \t" and not quote:
                break
            if char == "'" and quote != '"':
                quote = "" if quote == "'" else "'"
                index += 1
                continue
            if char == "\\" and quote != "'":
                start = index
                while index < len(command) and command[index] == "\\":
                    index += 1
                count = index - start
                if index < len(command) and command[index] == '"':
                    argument.extend("\\" * (count // 2))
                    if count % 2:
                        argument.append('"')
                    else:
                        quote = "" if quote == '"' else '"'
                    index += 1
                else:
                    argument.extend("\\" * count)
                continue
            if char == '"' and quote != "'":
                quote = "" if quote == '"' else '"'
                index += 1
                continue
            argument.append(char)
            index += 1
        if quote:
            raise ValueError("unclosed quote in command")
        argv.append("".join(argument))
    return argv


def command_argv(command, style):
    if style == "windows":
        return _windows_argv(command)
    if style == "posix":
        return shlex.split(command)
    raise ValueError("unsupported argv style: %r" % style)


def preflight_problem(detail):
    if not (detail.count("`") >= 2 and re.search(r"(?:→|->)\s*passed", detail) and "evidence=" in detail
            and re.search(r"checked=\d{4}-\d{2}-\d{2}(?:\b|$)", detail)):
        return "needs `action` → passed；evidence=…；checked=YYYY-MM-DD"
    return None


def unit_problems(feature, unit, ids):
    problems = list(unit.problems)
    status = unit.status
    if status not in STATUSES:
        problems.append("status %r not in pending|ready|done" % status)
    if status == "pending" and not unit.fields.get("reason"):
        problems.append("pending needs a concrete reason")
    if not unit.objective():
        problems.append("needs a 做什么 line")
    for key in ("blocked_by", "refines"):
        for value in unit.values(key):
            if value == unit.id:
                problems.append("%s itself" % key)
            elif value not in ids:
                problems.append("%s names undeclared unit %s" % (key, value))
    anchors = {item["id"] for item in feature.model.requirements + feature.model.decisions}
    for value in unit.values("covers"):
        if value not in anchors:
            problems.append("covers undeclared %s" % value)
    if status in ("ready", "done"):
        acceptance = unit.acceptance()
        if not acceptance:
            problems.append("needs at least one checkbox AC")
        verifier = feature.effective(unit)
        if verifier is None:
            problems.append("needs a valid 共享验证 block")
            return problems
        for number, (_, name) in enumerate(acceptance, 1):
            if name is None:
                problems.append("AC #%d needs exactly one → `command-name`" % number)
            elif name not in verifier["commands"]:
                problems.append("AC #%d names unknown command %s" % (number, name))
            elif name not in verifier["preflights"]:
                problems.append("command %s has no 预检 line" % name)
        for name in {name for _, name in acceptance if name}:
            if name in verifier["commands"]:
                try:
                    command_argv(verifier["commands"][name], "posix")
                except ValueError as exc:
                    problems.append("command %s cannot be parsed: %s" % (name, exc))
            detail = verifier["preflights"].get(name)
            if detail is not None and preflight_problem(detail):
                problems.append("预检 %s %s" % (name, preflight_problem(detail)))
        experience = unit.fields.get("experience")
        if experience:
            problems.extend(experience_field_problems(feature, verifier, experience))
    return problems


def cycle_members(graph):
    remaining = {key: [dep for dep in deps if dep in graph] for key, deps in graph.items()}
    changed = True
    while changed:
        changed = False
        for key in list(remaining):
            if not [dep for dep in remaining[key] if dep in remaining]:
                del remaining[key]
                changed = True
    return sorted(remaining)


def review_records(feature):
    """Digest-checked review decisions; malformed records are problems, never ignored."""
    from evidence import read_record
    directory = feature.directory / REVIEWS
    records, problems = [], []
    if not directory.is_dir():
        return records, problems
    for path in sorted(directory.glob("*.json")):
        try:
            record = read_record(path, "spec_decision")
            if record.get("accepted") is True and (not isinstance(record.get("text"), str)
                                                   or sha256_text(record["text"]) != record.get("spec_digest")):
                raise ValueError("accepted text does not match its digest")
            records.append(record)
        except (OSError, ValueError, KeyError) as exc:
            problems.append("%s: %s" % (path.name, exc))
    return records, problems


def accepted_record(feature):
    records, problems = review_records(feature)
    if problems:
        raise ValueError("review record is invalid: " + "; ".join(problems))
    accepted = [record for record in records if record.get("accepted") is True]
    return max(accepted, key=lambda record: record.get("decided_at", 0)) if accepted else None


def problems(feature):
    """Structural problems as (unit id or None, message); proof and admission are separate."""
    result = [(None, message) for message in feature.problems]
    if feature.meta is not None:
        if feature.meta.get("type") != "feature":
            result.append((None, "type must be feature"))
        if feature.meta.get("feature") != feature.name:
            result.append((None, "feature %r != directory %r" % (feature.meta.get("feature"), feature.name)))
        if not ISO_DATE.match(feature.meta.get("created", "")):
            result.append((None, "created must be ISO YYYY-MM-DD"))
        if feature.meta.get("review", "required") != "required":
            result.append((None, "review may only be 'required'"))
    result.extend((None, message) for message in validate_model(feature.model))
    _, record_problems = review_records(feature)
    result.extend((None, "review record " + message) for message in record_problems)
    ids, seen = {unit.id for unit in feature.units}, set()
    graph = {}
    for unit in feature.units:
        if unit.id in seen:
            result.append((unit.id, "duplicate unit id"))
        seen.add(unit.id)
        graph[unit.id] = unit.values("blocked_by")
        result.extend((unit.id, message) for message in unit_problems(feature, unit, ids))
        if unit.status != "done" and unit.completion is not None:
            result.append((unit.id, "only done units carry a 完成 record"))
        if unit.status == "done" and unit.completion is None:
            result.append((unit.id, "done needs a 完成 record"))
    for unit_id in cycle_members(graph):
        result.append((unit_id, "is in (or depends on) a blocked_by cycle"))
    return result


RUN_EVIDENCE = re.compile(r"^(?P<path>\S+)\s+sha256=(?P<sha>[0-9a-f]{64})$")


def run_log_problem(feature, path, sha, commands):
    """A run log is the lightweight proof: exact command header, unchanged bytes, `exit=0` trailer."""
    from evidence import local, sha as file_sha
    log = local(feature.root, path)
    if not log.is_file() or file_sha(log) != sha:
        return "run log is missing or changed: " + path
    lines = [line for line in log.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
             if line.strip()]
    if not lines or lines[0].strip() not in {"$ " + command for command in commands} or len(set(commands)) != 1:
        return "run log must start with '$ <the AC command>' and cover one command: " + path
    if len(lines) < 2 or not lines[1].startswith("# tree="):
        return "run log must record the working tree it ran against: " + path
    if lines[-1].strip() != "exit=0":
        return "run log must end with exit=0: " + path
    return None


def completion_problem(feature, unit, closing=False):
    """None when the 完成 record proves every AC: fixed receipts, or run logs without review."""
    from evidence import local, read_record, relative, validate_candidate, validate_receipt
    from evidence import _applies_to_candidate, _reject_known_failures
    root = feature.root
    try:
        if unit.completion is None:
            raise ValueError("needs a 完成 record")
        if unit.completion_values("contract") != [unit.digest()]:
            raise ValueError("contract changed after completion; add a refining unit instead")
        verifier = feature.effective(unit)
        if verifier is None:
            raise ValueError("needs a valid 共享验证 block")
        acceptance = unit.acceptance()
        expected = set(range(1, len(acceptance) + 1))
        targets = unit.completion_values("candidate")
        if len(targets) > 1:
            raise ValueError("completion names at most one candidate")
        target = validate_candidate(root, local(root, targets[0])) if targets else None
        references = unit.completion_values("evidence")
        if not references:
            raise ValueError("completion needs evidence lines")
        accepted = {}
        if feature.review_required():
            records, record_problems = review_records(feature)
            if record_problems:
                raise ValueError("review record is invalid: " + "; ".join(record_problems))
            accepted = {record["spec_digest"]: record for record in records if record.get("accepted") is True}
            latest = max(accepted.values(), key=lambda record: record.get("decided_at", 0)) if accepted else None
        covered, receipts, paths, candidates = set(), [], [], set()
        for reference in references:
            name = re.split(r"[;；]", reference, 1)[0].strip().strip("`")
            claim = set()
            for match in re.findall(r"\bAC\s*([0-9,\-\s]+)", reference):
                claim.update(parse_ac_spec(match))
            if not claim or not claim <= expected:
                raise ValueError("evidence needs valid AC selectors: " + reference)
            run = RUN_EVIDENCE.match(name)
            if run:
                if feature.review_required():
                    raise ValueError("reviewed feature needs fixed receipts, not run logs")
                missing = [n for n in claim if verifier["commands"].get(acceptance[n - 1][1]) is None]
                if missing:
                    raise ValueError("AC #%d names an unknown command" % missing[0])
                problem = run_log_problem(feature, run.group("path"), run.group("sha"),
                                          [verifier["commands"][acceptance[n - 1][1]] for n in claim])
                if problem:
                    raise ValueError(problem)
                covered.update(claim)
                continue
            path = local(root, name)
            try:
                receipt = validate_receipt(root, path)
            except (OSError, KeyError, TypeError) as exc:
                raise ValueError("evidence is missing or malformed: " + name) from exc
            if receipt["outcome"] != "pass" or receipt["scope"] == "preflight":
                raise ValueError("evidence needs a passing non-preflight check: " + name)
            if target is not None and not _applies_to_candidate(root, receipt, target):
                raise ValueError("evidence does not apply to the named candidate: " + name)
            observed = receipt["definition"]["environment"]
            if any(observed.get(key) != value for key, value in verifier["environment"].items()):
                raise ValueError("check environment differs from 共享验证: " + name)
            if receipt["cwd"] != relative(os.path.normpath(verifier["cwd"])):
                raise ValueError("check cwd differs from 共享验证: " + name)
            for number in claim:
                command = verifier["commands"].get(acceptance[number - 1][1])
                if command is None:
                    raise ValueError("AC #%d names an unknown command" % number)
                if receipt["argv"] not in [command_argv(command, style) for style in ("posix", "windows")]:
                    raise ValueError("check command does not prove AC #%d" % number)
            if feature.review_required():
                fixed = target or read_record(local(root, read_record(
                    local(root, receipt["context"]), "check_input")["candidate"]), "candidate")
                if fixed.get("spec_digest") not in accepted:
                    raise ValueError("reviewed feature needs a candidate bound to an accepted contract")
                if closing and not design_matches(parse_model(latest["text"]), parse_model(fixed["spec_text"]),
                                                  set(unit.values("covers"))):
                    raise ValueError("candidate contract misses this unit's latest accepted design")
            candidates.add(receipt["candidate_digest"])
            covered.update(claim)
            receipts.append(receipt)
            paths.append(path)
        if covered != expected or (target is None and len(candidates) > 1):
            raise ValueError("completion needs every AC proven, with receipts from one fixed candidate")
        if closing and receipts:
            _reject_known_failures(root, paths, receipts)
        experience = unit.fields.get("experience")
        if experience:
            problem = experience_evidence_problem(feature, verifier, experience)
            if problem:
                raise ValueError(problem)
    except (OSError, ValueError) as exc:
        return str(exc)
    return None


def parse_ac_spec(value):
    result = set()
    for token in value.replace(" ", "").split(","):
        if re.fullmatch(r"\d+", token):
            result.add(int(token))
        elif re.fullmatch(r"\d+-\d+", token):
            low, high = (int(part) for part in token.split("-", 1))
            if low > high:
                raise ValueError("invalid AC range: " + token)
            result.update(range(low, high + 1))
        elif token:
            raise ValueError("invalid AC selector: " + token)
    return result


def unit_states(feature):
    """Engineering view: every unit is ready (admitted), blocked, pending, done or invalid."""
    structural = problems(feature)
    global_problems = [message for unit_id, message in structural if unit_id is None]
    by_unit = {}
    for unit_id, message in structural:
        if unit_id:
            by_unit.setdefault(unit_id, []).append(message)
    accepted, accept_problem = None, None
    if feature.review_required():
        try:
            record = accepted_record(feature)
            accepted = parse_model(record["text"]) if record else None
            if record is None:
                accept_problem = "feature contract awaits human review"
        except ValueError as exc:
            accept_problem = str(exc)
    proof = {}
    for unit in feature.units:
        if unit.status == "done":
            proof[unit.id] = by_unit.get(unit.id) or global_problems or [completion_problem(feature, unit)]
            proof[unit.id] = [item for item in proof[unit.id] if item]
    states = {}
    for unit in feature.units:
        reasons = global_problems + by_unit.get(unit.id, [])
        if unit.status == "done":
            states[unit.id] = ("invalid", proof[unit.id]) if proof[unit.id] else ("done", [])
            continue
        if unit.status == "pending":
            states[unit.id] = ("pending", reasons or [unit.fields.get("reason", "")])
            continue
        for dependency in unit.values("blocked_by"):
            if proof.get(dependency) is None:
                reasons.append("unfinished dependency " + dependency)
            elif proof[dependency]:
                reasons.append("dependency %s has no valid completion proof" % dependency)
        if accept_problem:
            reasons.append(accept_problem)
        elif accepted is not None and not design_matches(feature.model, accepted, set(unit.values("covers"))):
            reasons.append("contract changed since acceptance; re-review before starting")
        states[unit.id] = ("blocked", reasons) if reasons else ("ready", [])
    return states


def packet(feature, unit):
    """Self-contained worker input: the unit, its resolved verifier and covered anchors."""
    verifier = feature.effective(unit) or {}
    covered = set(unit.values("covers"))
    for key in list(covered):
        covered |= feature.model.refs_of(key)
    anchors = {item["id"]: item["text"] for item in feature.model.requirements if item["id"] in covered}
    anchors.update({item["id"]: "\n".join(item["lines"]) for item in feature.model.decisions if item["id"] in covered})
    names = {name for _, name in unit.acceptance() if name}
    return {
        "schema_version": 1,
        "feature": feature.name,
        "unit": unit.id,
        "title": unit.title,
        "source": "%s:%d" % (feature.path.relative_to(feature.root).as_posix(), unit.line),
        "contract": "\n".join(unit.contract_lines()).strip(),
        "contract_sha256": unit.digest(),
        "covers": anchors,
        "invariants": {item["id"]: item["text"] for item in feature.model.contracts},
        "verifier": {"cwd": verifier.get("cwd"), "environment": verifier.get("environment"),
                     "prepare": verifier.get("prepare"),
                     "commands": {name: verifier.get("commands", {}).get(name) for name in sorted(names)}},
    }


def set_status(text, unit, status, reason=None):
    """Rewrite one unit's status (and reason) lines; everything else stays byte-identical."""
    lines = normalize(text).split("\n")
    start, end = unit.line - 1, unit.end
    rewritten, replaced = [], False
    for line in lines[start:end]:
        if re.match(r"^-\s+reason\s*[:：]", line.strip()):
            continue
        if re.match(r"^-\s+status\s*[:：]", line.strip()) and not replaced:
            rewritten.append("- status: " + status)
            if reason:
                rewritten.append("- reason: " + reason)
            replaced = True
            continue
        rewritten.append(line)
    if not replaced:
        raise ValueError("%s has no status line" % unit.id)
    return "\n".join(lines[:start] + rewritten + lines[end:])


def with_completion(text, unit, block):
    lines = normalize(text).split("\n")
    end = unit.end
    while end > unit.line and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[:end] + block + lines[end:])


def experience_contract_problem(value):
    if not isinstance(value, dict):
        return "must be an object"
    if value.get("surface") != "graphical-ui" or not isinstance(value.get("id"), str) or not value["id"].strip():
        return "needs id and surface graphical-ui"
    viewport = value.get("viewport")
    if not isinstance(viewport, dict) or any(type(viewport.get(k)) is not int or viewport[k] <= 0
                                             for k in ("width", "height")):
        return "viewport needs positive integer width/height"
    states = value.get("states")
    if not isinstance(states, list) or not states or len(set(states)) != len(states) or any(
            not isinstance(state, str) or not state.strip() for state in states):
        return "states must be unique non-empty names"
    gate = value.get("runtime_gate")
    if not isinstance(gate, dict) or any(gate.get(key) != 0 or isinstance(gate.get(key), bool) for key in RUNTIME_KEYS):
        return "runtime_gate must set every unexpected/error counter to 0"
    rubric = value.get("rubric")
    if rubric is not None:
        number = lambda item: isinstance(item, (int, float)) and not isinstance(item, bool)
        dimensions = rubric.get("dimensions") if isinstance(rubric, dict) else None
        if (not isinstance(rubric, dict) or not isinstance(rubric.get("id"), str)
                or not isinstance(dimensions, list) or not dimensions or len(set(dimensions)) != len(dimensions)
                or not all(number(rubric.get(k)) for k in ("score_min", "score_max", "min_total", "min_dimension"))
                or rubric["score_min"] >= rubric["score_max"] or rubric["min_dimension"] > rubric["score_max"]
                or rubric["min_total"] > rubric["score_max"] * len(dimensions)):
            return "rubric needs id, unique dimensions and satisfiable score bounds"
    return None


def _experience_field(value):
    parts = dict(item.split("=", 1) for item in re.split(r"[;；]\s*", value) if "=" in item)
    mode = value.split(";")[0].split("；")[0].strip()
    return mode, tokens(parts.get("states", "")), parts.get("evidence", "").strip()


def experience_field_problems(feature, verifier, value):
    mode, states, evidence = _experience_field(value)
    contract = verifier.get("experience")
    problems = []
    if mode not in ("runtime", "graded"):
        problems.append("experience mode must be runtime or graded")
    if contract is None:
        return problems + ["experience needs 共享验证 experience contract"]
    if (mode == "graded") != ("rubric" in contract):
        problems.append("graded experience needs a rubric; runtime experience must omit it")
    if not states or set(states) - set(contract["states"]):
        problems.append("experience states must be declared contract states")
    prefix = ".scratch/%s/evidence/" % feature.name
    if not evidence.startswith(prefix) or not evidence.endswith(".json") or ".." in evidence.split("/"):
        problems.append("experience evidence must be JSON under " + prefix)
    return problems


def _screenshot(path):
    data = path.read_bytes() if path.is_file() else b""
    name = path.name.lower()
    if name.endswith(".png"):
        return (len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR"
                and int.from_bytes(data[16:20], "big") > 0 and int.from_bytes(data[20:24], "big") > 0
                and b"IEND" in data[-32:])
    if name.endswith((".jpg", ".jpeg")):
        return len(data) > 4 and data.startswith(b"\xff\xd8") and data.rfind(b"\xff\xd9") >= len(data) - 64
    if name.endswith(".webp"):
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return name.endswith(".gif") and data.startswith((b"GIF87a", b"GIF89a"))


def experience_evidence_problem(feature, verifier, value):
    from evidence import local
    mode, states, evidence = _experience_field(value)
    contract = verifier["experience"]
    try:
        data = json.loads(local(feature.root, evidence).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "experience evidence unreadable: %s" % exc
    if not isinstance(data, dict) or data.get("contract_id") != contract["id"] or data.get("mode") != mode:
        return "experience evidence does not match its contract and mode"
    if data.get("verdict") != "pass" or not isinstance(data.get("runtime"), dict) or any(
            data["runtime"].get(key) != 0 for key in RUNTIME_KEYS):
        return "experience evidence needs verdict pass and zero runtime counters"
    rows = {row.get("name"): row for row in data.get("states", []) if isinstance(row, dict)}
    for state in states:
        artifacts = rows.get(state, {}).get("artifacts")
        if not isinstance(artifacts, list) or not any(
                isinstance(item, str) and _screenshot(local(feature.root, item)) for item in artifacts):
            return "experience state %s needs a retained screenshot" % state
    if mode == "graded":
        rubric, judge = contract["rubric"], data.get("judge")
        scores = judge.get("dimensions") if isinstance(judge, dict) else None
        if (not isinstance(scores, dict) or judge.get("rubric_id") != rubric["id"]
                or sorted(scores) != sorted(rubric["dimensions"])
                or any(not isinstance(v, (int, float)) or v < rubric["min_dimension"] or v > rubric["score_max"]
                       for v in scores.values())
                or judge.get("total") != sum(scores.values()) or judge["total"] < rubric["min_total"]):
            return "graded experience scores miss the contract rubric or its floors"
    elif "judge" in data:
        return "runtime experience evidence must not contain judge scores"
    return None
