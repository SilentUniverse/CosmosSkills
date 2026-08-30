#!/usr/bin/env python
# Mechanical gate for the ARTIFACT-FORMAT.md contract (.scratch/ artifacts + CODEBASE.md map).
# Stdlib only. Exit: 0 clean, 1 violations, 2 usage.
# Invoke: python verify-artifacts.py [<repo-root>]
# If the `python` interpreter is missing, python3 verify-artifacts.py [<repo-root>]
# Do not retry python3 after a non-zero gate exit (that is a contract violation).
import json
import os
import re
import sys

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".scratch",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "out",
    ".next",
    "__pycache__",
}
ROSTER_ILLEGAL = re.compile(r'[<>:"|?*{}]')
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NN_SLUG = re.compile(r"^(\d{2,})-")
PRD_VN = re.compile(r"^PRD-v(\d+)\.md$")
FM_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
FLOW_LIST = re.compile(r"^\[\s*(.*)\s*\]$")
BLOCK_ITEM = re.compile(r"^\s+-\s+(.+)$")
BEGIN_GEN = re.compile(r"^<!--.*BEGIN GENERATED codebase")
END_GEN = re.compile(r"^<!--.*END GENERATED codebase")
GIT_BASE = re.compile(r"^git_base:\s*\S+")
FEN_QU = "\u5206\u533a"  # roster heading word 分区
DONE_HEAD = re.compile(r"^#{2,3}\s*\u5b8c\u6210(?:[^\w]|$)")  # ### 完成 + non-word delimiter or EOL
XINZENG = "\u65b0\u589e\u6d4b\u8bd5"  # 新增测试
YANSHOU = "\u9a8c\u6536"  # 验收
YANZHENG_SHEJI = "\u9a8c\u8bc1\u8bbe\u8ba1"  # 验证设计
YANZHENG_MINGLING = "\u9a8c\u8bc1\u547d\u4ee4"  # 验证命令
JIEFENG = "\u63a5\u7f1d"  # 接缝
GONGZUO_MULU = "\u5de5\u4f5c\u76ee\u5f55"  # 工作目录
HUANJING_ZHIWEN = "\u73af\u5883\u6307\u7eb9"  # 环境指纹
QIANZHI_TIAOJIAN = "\u524d\u7f6e\u6761\u4ef6"  # 前置条件
ZHUNBEI_DONGZUO = "\u51c6\u5907\u52a8\u4f5c"  # 准备动作
YUJIAN = "\u9884\u68c0"  # 预检
YUJIAN_CHONGFANG = "\u9884\u68c0\u91cd\u653e"  # 预检重放
FANZHENG = "\u53cd\u8bc1"  # 反证
TIYAN_YANZHENG = "\u4f53\u9a8c\u9a8c\u8bc1"  # 体验验证
AC_CHECKBOX = re.compile(r"^\s*-\s*\[[ xX]\]\s+\S")
EVIDENCE_MAP = re.compile(r"^\s*-\s*#(\d+)\s*(?:\u2192|->)")
PREFLIGHT_LINE = re.compile(r"^\s*-\s*P(\d+)\s+" + YUJIAN + r"[\uff1a:]\s*(.+)$")
PREFLIGHT_REF = re.compile(YUJIAN + r"[\uff1a:]\s*P(\d+)")
FALSIFIER_REF = re.compile(FANZHENG + r"[\uff1a:]\s*([^\uff1b;]+)")
# A placeholder is a value that is entirely one angle-bracket token (<defect>, <具体缺陷>);
# a real falsifier may still contain "<" as a comparison operator (行数 < 1).
PLACEHOLDER_REF = re.compile(r"^\s*<[^<>]*>\s*$")
EXPERIENCE_RUNTIME_KEYS = (
    "unexpected_console_errors",
    "uncaught_page_errors",
    "unexpected_failed_requests",
    "csp_violations",
    "decoded_media_failures",
)
TEST_PATH = re.compile(
    r"(?:[A-Za-z]:)?"
    r"[A-Za-z0-9_.\-]+(?:[\\/][A-Za-z0-9_.\-]+)*\."
    r"(?:py|ts|tsx|js|jsx|mjs|cjs|go|rs|java|cs|cpp|cc|c|h|hpp|rb|php|kt|swift)"
)


BAD_UTF8 = set()


def read_lines(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig", errors="replace")
    if "\ufffd" in text:
        BAD_UTF8.add(path)
    return text.splitlines()


def get_frontmatter(path):
    """Scalars -> str; flow/block lists -> list[str]. None if absent or unterminated."""
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
                if items:
                    fm[key] = items
                    i = j - 1
                else:
                    fm[key] = ""
            else:
                fm_list = FLOW_LIST.match(val)
                if fm_list:
                    inner = fm_list.group(1).strip()
                    if inner == "":
                        fm[key] = []
                    else:
                        fm[key] = [
                            p.strip().strip('"').strip("'") for p in inner.split(",")
                        ]
                else:
                    fm[key] = val.strip('"').strip("'")
        i += 1
    if i >= len(lines):
        return None
    return fm


def as_list(val):
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return val
    return [val]


def done_record(lines):
    """Lines of the last ### 完成 block; None if absent. Ends at the next heading."""
    block = None
    for s in lines:
        if DONE_HEAD.match(s):
            block = []
            continue
        if block is not None:
            if s.startswith("#"):
                break
            block.append(s)
    return block


def h2_section(lines, word):
    """Body lines under the first ## heading containing word."""
    block = None
    for line in lines:
        if line.startswith("## "):
            if block is not None:
                break
            if word in line:
                block = []
            continue
        if block is not None:
            block.append(line)
    return block


def bullet_value(lines, word):
    """Value of `- <word>: ...` or its full-width-colon form; None when absent."""
    for line in lines:
        stripped = line.strip()
        for separator in ("\uff1a", ":"):
            prefix = "- " + word + separator
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return None


def inline_value(text, key):
    """Read `key=value` from a semicolon-delimited prose contract."""
    match = re.search(
        r"(?:^|[;\uff1b\s`])" + re.escape(key) + r"\s*=\s*([^;\uff1b`]+)",
        text or "",
    )
    return match.group(1).strip() if match else ""


def comma_values(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_zero_runtime_counters(value):
    return isinstance(value, dict) and all(
        is_number(value.get(key)) and value.get(key) == 0
        for key in EXPERIENCE_RUNTIME_KEYS
    )


def load_json_object(path, label, err):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as exc:
        err("%s: %s is not readable JSON: %s" % (path, label, exc))
        return None
    if not isinstance(value, dict):
        err("%s: %s must be a JSON object" % (path, label))
        return None
    return value


def repo_artifact_path(root, value, label, err, *, must_exist):
    value = (value or "").strip().replace("\\", "/")
    if not value or os.path.isabs(value) or value == ".." or value.startswith("../"):
        err("%s: %s must be a repo-relative path" % (root, label))
        return None
    path = os.path.abspath(os.path.join(root, value.replace("/", os.sep)))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:
        inside = False
    if not inside:
        err("%s: %s escapes the repository: %s" % (root, label, value))
        return None
    if must_exist and not os.path.isfile(path):
        err("%s: %s file does not exist: %s" % (root, label, value))
        return None
    if must_exist:
        try:
            if os.path.getsize(path) == 0:
                err("%s: %s file is empty: %s" % (root, label, value))
                return None
        except OSError as exc:
            err("%s: cannot stat %s %s: %s" % (root, label, value, exc))
            return None
    return path


def is_retained_screenshot(path):
    """Cheap stdlib signature check; proves an image artifact, not visual quality."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return False
    lower = path.lower()
    if lower.endswith(".png"):
        return (
            len(data) >= 24
            and data.startswith(b"\x89PNG\r\n\x1a\n")
            and data[12:16] == b"IHDR"
            and int.from_bytes(data[16:20], "big") > 0
            and int.from_bytes(data[20:24], "big") > 0
            and b"IEND" in data[-32:]
        )
    if lower.endswith((".jpg", ".jpeg")):
        # EOI may trail padding/metadata, as PNG tolerates bytes after IEND.
        if len(data) <= 4 or not data.startswith(b"\xff\xd8"):
            return False
        eoi = data.rfind(b"\xff\xd9")
        return eoi != -1 and eoi >= len(data) - 64
    if lower.endswith(".webp"):
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if lower.endswith(".gif"):
        return data.startswith((b"GIF87a", b"GIF89a"))
    return False


def under_scratch_dir(root, prefix, value):
    """Normalized containment under `<root>/<prefix>`; a raw startswith lets `../` escape."""
    expected_dir = os.path.abspath(os.path.join(root, prefix.replace("/", os.sep)))
    path = os.path.abspath(
        os.path.join(root, (value or "").replace("\\", "/").replace("/", os.sep))
    )
    try:
        return os.path.commonpath([expected_dir, path]) == expected_dir
    except ValueError:
        return False


def validate_experience_contract(root, feat, path_value, mode, err):
    expected_prefix = ".scratch/%s/" % feat
    normalized = (path_value or "").replace("\\", "/")
    if not under_scratch_dir(root, expected_prefix, normalized):
        err("%s: experience contract must stay under %s: %s" % (root, expected_prefix, normalized))
        return None
    path = repo_artifact_path(root, normalized, "experience contract", err, must_exist=True)
    if path is None:
        return None
    data = load_json_object(path, "experience contract", err)
    if data is None:
        return None
    valid = True

    def contract_error(message):
        nonlocal valid
        valid = False
        err(message)

    if data.get("schema_version") != 1:
        contract_error("%s: experience contract schema_version must be 1" % path)
    if not isinstance(data.get("id"), str) or not data.get("id", "").strip():
        contract_error("%s: experience contract needs non-empty id" % path)
    if data.get("surface") != "graphical-ui":
        contract_error("%s: experience contract surface must be graphical-ui" % path)
    if data.get("mode") != mode:
        contract_error(
            "%s: experience contract mode %r != issue mode %r"
            % (path, data.get("mode"), mode)
        )
    viewport = data.get("viewport")
    if not isinstance(viewport, dict) or any(
        type(viewport.get(key)) is not int or viewport.get(key) <= 0
        for key in ("width", "height")
    ):
        contract_error(
            "%s: experience contract viewport needs positive integer width/height" % path
        )
    if not isinstance(data.get("theme"), str) or not data.get("theme", "").strip():
        contract_error("%s: experience contract needs non-empty theme" % path)
    states = data.get("states")
    if (
        not isinstance(states, list)
        or not states
        or any(not isinstance(state, str) or not state.strip() for state in states)
        or len(set(states)) != len(states)
    ):
        contract_error(
            "%s: experience contract states must be unique non-empty strings" % path
        )
    runtime_gate = data.get("runtime_gate")
    if not has_zero_runtime_counters(runtime_gate):
        contract_error(
            "%s: experience runtime_gate must set every unexpected/error counter to numeric 0"
            % path
        )
    if mode == "graded":
        rubric = data.get("rubric")
        if (
            not isinstance(rubric, dict)
            or not isinstance(rubric.get("id"), str)
            or not rubric.get("id", "").strip()
            or not is_number(rubric.get("min_total"))
            or not is_number(rubric.get("min_dimension"))
        ):
            contract_error(
                "%s: graded experience contract needs rubric id/min_total/min_dimension" % path
            )
        else:
            dimensions = rubric.get("dimensions")
            if (
                not isinstance(dimensions, list)
                or not dimensions
                or any(not isinstance(name, str) or not name.strip() for name in dimensions)
                or len(set(dimensions)) != len(dimensions)
            ):
                contract_error(
                    "%s: graded experience rubric needs unique dimension names" % path
                )
            if (
                not is_number(rubric.get("score_min"))
                or not is_number(rubric.get("score_max"))
                or rubric.get("score_min", 0) >= rubric.get("score_max", 0)
            ):
                contract_error(
                    "%s: graded experience rubric needs score_min < score_max" % path
                )
            elif is_number(rubric.get("score_max")):
                dim_count = len(dimensions) if isinstance(dimensions, list) else 0
                if is_number(rubric.get("min_dimension")) and rubric[
                    "min_dimension"
                ] > rubric["score_max"]:
                    contract_error(
                        "%s: graded rubric min_dimension %s exceeds score_max %s; no run can pass"
                        % (path, rubric["min_dimension"], rubric["score_max"])
                    )
                if (
                    dim_count
                    and is_number(rubric.get("min_total"))
                    and rubric["min_total"] > rubric["score_max"] * dim_count
                ):
                    contract_error(
                        "%s: graded rubric min_total %s exceeds score_max %s x %d dimensions; "
                        "no run can pass" % (path, rubric["min_total"], rubric["score_max"], dim_count)
                    )
    return data if valid else None


def validate_experience_evidence(root, feat, path_value, mode, contract, required_states, err):
    expected_prefix = ".scratch/%s/evidence/" % feat
    normalized = (path_value or "").replace("\\", "/")
    if not under_scratch_dir(root, expected_prefix, normalized):
        err("%s: experience evidence must stay under %s: %s" % (root, expected_prefix, normalized))
        return
    path = repo_artifact_path(root, normalized, "experience evidence", err, must_exist=True)
    if path is None:
        return
    data = load_json_object(path, "experience evidence", err)
    if data is None:
        return
    if data.get("schema_version") != 1:
        err("%s: experience evidence schema_version must be 1" % path)
    if not contract or data.get("contract_id") != contract.get("id"):
        err("%s: experience evidence contract_id does not match contract" % path)
    if data.get("mode") != mode:
        err("%s: experience evidence mode %r != issue mode %r" % (path, data.get("mode"), mode))
    if data.get("verdict") != "pass":
        err("%s: experience evidence verdict must be pass" % path)
    runtime = data.get("runtime")
    if not has_zero_runtime_counters(runtime):
        err(
            "%s: experience evidence has non-zero or missing runtime counters "
            "(numeric zero required)" % path
        )
    state_rows = data.get("states")
    by_name = {}
    if not isinstance(state_rows, list):
        err("%s: experience evidence states must be a list" % path)
        state_rows = []
    for row in state_rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            err("%s: experience evidence state rows need a name" % path)
            continue
        name = row["name"].strip()
        if name in by_name:
            err("%s: duplicate experience evidence state %r" % (path, name))
            continue
        by_name[name] = row
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            err("%s: state %r needs retained artifacts" % (path, name))
            continue
        retained_paths = []
        for artifact in artifacts:
            if not isinstance(artifact, str):
                err("%s: state %r artifact path must be text" % (path, name))
                continue
            retained = repo_artifact_path(
                root, artifact, "experience state artifact", err, must_exist=True
            )
            if retained is not None:
                retained_paths.append(retained)
        if retained_paths and not any(is_retained_screenshot(item) for item in retained_paths):
            err("%s: state %r needs at least one valid retained screenshot" % (path, name))
    missing_states = sorted(set(required_states) - set(by_name))
    if missing_states:
        err("%s: experience evidence missing states: %s" % (path, ", ".join(missing_states)))
    if mode == "graded":
        judge = data.get("judge")
        rubric = contract.get("rubric", {}) if contract else {}
        if not isinstance(judge, dict) or judge.get("rubric_id") != rubric.get("id"):
            err("%s: graded experience evidence needs matching judge rubric_id" % path)
            return
        dimensions = judge.get("dimensions")
        total = judge.get("total")
        if not isinstance(dimensions, dict) or not dimensions:
            err("%s: graded experience evidence needs dimension scores" % path)
            return
        values = list(dimensions.values())
        expected_dimensions = rubric.get("dimensions", [])
        if sorted(dimensions) != sorted(expected_dimensions):
            err("%s: graded experience dimensions do not match the contract" % path)
        if any(not is_number(value) for value in values):
            err("%s: graded experience dimensions must be numeric" % path)
            return
        score_min = rubric.get("score_min", float("inf"))
        score_max = rubric.get("score_max", float("-inf"))
        if any(value < score_min or value > score_max for value in values):
            err("%s: graded experience dimension is outside the contract score range" % path)
        if not is_number(total) or abs(total - sum(values)) > 1e-9:
            err("%s: graded experience total must equal the dimension sum" % path)
        if is_number(total) and total < rubric.get("min_total", float("inf")):
            err("%s: graded experience total is below contract threshold" % path)
        if any(value < rubric.get("min_dimension", float("inf")) for value in values):
            err("%s: graded experience dimension is below contract floor" % path)


def ref_suggest(bad, candidates, self_slug):
    name = re.sub(r"^\d+-", "", bad)
    if len(name) >= 3:
        for c in candidates:
            if c != self_slug and re.sub(r"^\d+-", "", c) == name:
                return c
    m = re.match(r"^(\d+)-", bad)
    if m:
        nn = m.group(1)
        for c in candidates:
            if c != self_slug and re.match(r"^%s-" % re.escape(nn), c):
                return c
    return None


def nested_claude_files(root):
    out = []
    stack = [root]
    root_abs = os.path.abspath(root)
    while stack:
        d = stack.pop()
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            p = os.path.join(d, name)
            try:
                is_dir = os.path.isdir(p)
            except OSError:
                continue
            if is_dir:
                if name in SKIP_DIRS:
                    continue
                stack.append(p)
            elif name == "CLAUDE.md":
                rel = os.path.relpath(p, root_abs).replace("\\", "/")
                if rel != "CLAUDE.md":
                    out.append((p, rel))
    out.sort(key=lambda x: x[1])
    return out


def cyclic_slugs(graph):
    remaining = {k: [d for d in deps if d in graph] for k, deps in graph.items()}
    changed = True
    while changed:
        changed = False
        for k in list(remaining.keys()):
            if not [d for d in remaining[k] if d in remaining]:
                del remaining[k]
                changed = True
    return list(remaining.keys())


def main(argv):
    # Stock Windows consoles/pipes default to the ANSI code page; never let an
    # un-encodable path or message kill the report mid-list.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(argv) > 2:
        print("verify-artifacts: usage: python verify-artifacts.py [<repo-root>]", file=sys.stderr)
        return 2
    root = os.path.abspath(argv[1] if len(argv) == 2 else os.getcwd())
    scratch = os.path.join(root, ".scratch")
    has_scratch = os.path.isdir(scratch)
    cb_path = os.path.join(root, "CODEBASE.md")
    has_cb = os.path.isfile(cb_path)

    errors = []
    n_issues = n_prds = n_handoffs = n_summaries = n_cb_blocks = 0

    def err(msg):
        errors.append(msg)

    def check_handoff(path, expected_feature):
        nonlocal n_handoffs
        n_handoffs += 1
        fm = get_frontmatter(path)
        if fm is None:
            err("%s: no YAML frontmatter" % path)
            return
        if fm.get("type") != "handoff":
            err("%s: type '%s' != handoff" % (path, fm.get("type", "")))
        feat = str(fm.get("feature", ""))
        if expected_feature == "":
            if feat not in ("", "null"):
                err("%s: cross-feature handoff must have feature null, got '%s'" % (path, feat))
        elif feat != expected_feature:
            err("%s: feature '%s' != directory '%s'" % (path, feat, expected_feature))
        if not fm.get("git_base"):
            err("%s: git_base missing" % path)
        if fm.get("status") not in ("active", "consumed"):
            err("%s: status '%s' not in active|consumed" % (path, fm.get("status", "")))
        if not ISO_DATE.match(str(fm.get("date", ""))):
            err("%s: date not ISO YYYY-MM-DD" % path)

    budget = 40
    roster_paths = {}
    if has_cb:
        fm = get_frontmatter(cb_path)
        if fm is None:
            err("%s: no YAML frontmatter" % cb_path)
        else:
            if fm.get("type") != "codebase":
                err("%s: type '%s' != codebase" % (cb_path, fm.get("type", "")))
            if not ISO_DATE.match(str(fm.get("generated", ""))):
                err("%s: generated not ISO YYYY-MM-DD" % cb_path)
            b = str(fm.get("budget", ""))
            if re.match(r"^\d+$", b):
                budget = int(b)
        cb_lines = read_lines(cb_path)
        fm_end = -1
        if len(cb_lines) >= 2 and cb_lines[0].strip() == "---":
            for i in range(1, len(cb_lines)):
                if cb_lines[i].strip() == "---":
                    fm_end = i
                    break
        in_roster = False
        body_count = 0
        for i in range(fm_end + 1, len(cb_lines)):
            line = cb_lines[i]
            if line.startswith("## "):
                in_roster = ("roster" in line) or (FEN_QU in line)
                body_count += 1
                continue
            if line.strip() == "":
                continue
            if in_roster and re.match(r"^\s*-", line):
                m = re.match(r"^\s*-\s+`([^`]+)", line)
                if m:
                    roster_paths[m.group(1).rstrip("/")] = True
                continue
            body_count += 1
        if body_count > budget:
            err(
                "%s: root body %d lines (excl. roster) > budget %d - relocate -> condense -> raise "
                "(raise carries justification in the change; set 'budget:' in frontmatter to adopt current size)"
                % (cb_path, body_count, budget)
            )
        for p in list(roster_paths.keys()):
            if ROSTER_ILLEGAL.search(p):
                err(
                    "%s: roster path '%s' uses placeholder/glob syntax - write a real existing directory "
                    "(one representative path per pattern)" % (cb_path, p)
                )
                continue
            dir_path = os.path.join(root, p.replace("/", os.sep))
            try:
                ok = os.path.isdir(dir_path)
            except (OSError, ValueError):
                ok = False
            if not ok:
                err("%s: roster path '%s' is not an existing directory" % (cb_path, p))

    if not has_scratch and not has_cb:
        print("verify-artifacts: no .scratch/ and no CODEBASE.md under %s - nothing to check, clean." % root)
        return 0

    for nf_path, rel in nested_claude_files(root):
        nf_lines = read_lines(nf_path)
        begins = sum(1 for x in nf_lines if BEGIN_GEN.match(x))
        ends = sum(1 for x in nf_lines if END_GEN.match(x))
        if begins == 0:
            continue
        if begins != ends:
            err("%s: BEGIN/END GENERATED marker count mismatch (%d/%d)" % (nf_path, begins, ends))
            continue
        in_block = False
        has_base = False
        content = 0
        bi = 0
        for s in nf_lines:
            if BEGIN_GEN.match(s):
                in_block = True
                bi += 1
                has_base = False
                content = 0
                n_cb_blocks += 1
                continue
            if END_GEN.match(s):
                if not has_base:
                    err("%s: block %d missing git_base:" % (nf_path, bi))
                if content > 8:
                    err(
                        "%s: block %d has %d content lines > 8 - relocate -> condense -> raise"
                        % (nf_path, bi, content)
                    )
                in_block = False
                continue
            if not in_block:
                continue
            if GIT_BASE.match(s):
                has_base = True
                continue
            if s.strip() != "":
                content += 1
        area = re.sub(r"/CLAUDE\.md$", "", rel)
        if has_cb:
            if area not in roster_paths:
                err("%s: generated block but area '%s' not in root roster" % (nf_path, area))
        else:
            err("%s: generated block exists but root CODEBASE.md is missing" % nf_path)

    scratch_dirs = []
    if has_scratch:
        scratch_dirs = sorted(
            [
                os.path.join(scratch, n)
                for n in os.listdir(scratch)
                if os.path.isdir(os.path.join(scratch, n))
            ]
        )
    for fd in scratch_dirs:
        feat = os.path.basename(fd)

        prd_files = sorted(
            [os.path.join(fd, n) for n in os.listdir(fd) if n.startswith("PRD") and n.endswith(".md") and os.path.isfile(os.path.join(fd, n))]
        )
        if prd_files:
            names = {os.path.basename(p): True for p in prd_files}
            parsed = {}
            for p in prd_files:
                n_prds += 1
                base = os.path.basename(p)
                fm = get_frontmatter(p)
                parsed[base] = fm
                if fm is None:
                    err("%s: no YAML frontmatter" % p)
                    continue
                if fm.get("type") != "prd":
                    err("%s: type '%s' != prd" % (p, fm.get("type", "")))
                if base == "PRD.md":
                    if str(fm.get("version", "")) != "1":
                        err("%s: PRD.md must carry version 1, got '%s'" % (p, fm.get("version", "")))
                else:
                    m = PRD_VN.match(base)
                    if m:
                        if str(fm.get("version", "")) != m.group(1):
                            err(
                                "%s: filename says v%s but version: %s"
                                % (p, m.group(1), fm.get("version", ""))
                            )
                    else:
                        err("%s: PRD filename must be PRD.md or PRD-vN.md" % p)
                sup = fm.get("supersedes")
                if sup:
                    if str(sup) not in names:
                        err("%s: supersedes '%s' not found in this directory" % (p, sup))
            if len(prd_files) > 1:
                superseded = {}
                for e in parsed.values():
                    if e and e.get("supersedes"):
                        superseded[str(e.get("supersedes"))] = True
                live = [os.path.basename(p) for p in prd_files if os.path.basename(p) not in superseded]
                if len(live) != 1:
                    err("%s: PRD chain must leave exactly one live head, found: %s" % (fd, ", ".join(live)))

        sum_path = os.path.join(fd, "SUMMARY.md")
        if os.path.isfile(sum_path):
            n_summaries += 1
            fm = get_frontmatter(sum_path)
            if fm is None:
                err("%s: no YAML frontmatter" % sum_path)
            elif fm.get("type") != "summary":
                err("%s: type '%s' != summary" % (sum_path, fm.get("type", "")))

        h_path = os.path.join(fd, "handoff.md")
        if os.path.isfile(h_path):
            check_handoff(h_path, feat)

        i_dir = os.path.join(fd, "issues")
        if os.path.isdir(i_dir):
            files = sorted(
                [
                    os.path.join(i_dir, n)
                    for n in os.listdir(i_dir)
                    if n.endswith(".md") and os.path.isfile(os.path.join(i_dir, n))
                ]
            )
            by_slug = {}
            nn_seen = {}
            for f in files:
                slug = os.path.splitext(os.path.basename(f))[0]
                by_slug[slug] = f
                m = NN_SLUG.match(slug)
                if m:
                    nn = m.group(1)
                    if nn in nn_seen:
                        err("%s: duplicate NN %s (also %s)" % (f, nn, nn_seen[nn]))
                    else:
                        nn_seen[nn] = slug
                else:
                    err("%s: filename not NN-slug" % f)
            resolved = dict(by_slug)
            arch_dir = os.path.join(i_dir, "archive")
            if os.path.isdir(arch_dir):
                for n in os.listdir(arch_dir):
                    af = os.path.join(arch_dir, n)
                    if n.endswith(".md") and os.path.isfile(af):
                        slug = os.path.splitext(n)[0]
                        if slug not in resolved:
                            resolved[slug] = af
            graph = {}
            for f in files:
                n_issues += 1
                issue_lines = read_lines(f)
                fm = get_frontmatter(f)
                if fm is None:
                    err("%s: no YAML frontmatter" % f)
                    continue
                if fm.get("type") != "issue":
                    err("%s: type '%s' != issue" % (f, fm.get("type", "")))
                if fm.get("feature") != feat:
                    err("%s: feature '%s' != directory '%s'" % (f, fm.get("feature", ""), feat))
                if fm.get("status") not in ("ready", "done"):
                    err("%s: status '%s' not in ready|done" % (f, fm.get("status", "")))
                contract_version = str(fm.get("contract_version", ""))
                required_preflight_ids = set()
                experience_review = str(fm.get("experience_review", ""))
                experience_contract = None
                experience_states = []
                experience_evidence_value = ""
                if contract_version not in ("", "1", "2"):
                    err("%s: contract_version '%s' not in 1|2" % (f, contract_version))
                if experience_review not in ("", "runtime", "graded"):
                    err(
                        "%s: experience_review '%s' not in runtime|graded or omitted"
                        % (f, experience_review)
                    )
                if experience_review and contract_version != "2":
                    err(
                        "%s: experience_review requires contract_version 2; bump the card or "
                        "drop the field" % f
                    )
                if contract_version == "2":
                    ac_lines = h2_section(issue_lines, YANSHOU) or []
                    ac_count = sum(1 for line in ac_lines if AC_CHECKBOX.match(line))
                    verification = h2_section(issue_lines, YANZHENG_SHEJI)
                    if ac_count == 0:
                        err("%s: contract v2 needs at least one checkbox AC" % f)
                    if verification is None:
                        err("%s: contract v2 missing ## 验证设计" % f)
                    else:
                        if not bullet_value(verification, JIEFENG):
                            err("%s: contract v2 验证设计 missing 接缝" % f)
                        workdir = bullet_value(verification, GONGZUO_MULU)
                        if not workdir:
                            err("%s: contract v2 验证设计 missing 工作目录" % f)
                        fingerprint = bullet_value(verification, HUANJING_ZHIWEN)
                        if not fingerprint:
                            err("%s: contract v2 验证设计 missing 环境指纹" % f)
                        else:
                            missing_keys = [
                                key
                                for key in ("git", "lock", "runtime", "tools", "services")
                                if not re.search(r"(?:^|[;；\s`])" + key + r"\s*=", fingerprint)
                            ]
                            if missing_keys:
                                err(
                                    "%s: contract v2 环境指纹 missing keys: %s"
                                    % (f, ", ".join(missing_keys))
                                )
                        prerequisites = bullet_value(verification, QIANZHI_TIAOJIAN)
                        if not prerequisites:
                            err("%s: contract v2 验证设计 missing 前置条件" % f)
                        else:
                            missing_keys = [
                                key
                                for key in ("fixtures", "services", "permissions", "network")
                                if not re.search(r"(?:^|[;；\s`])" + key + r"\s*=", prerequisites)
                            ]
                            if missing_keys:
                                err(
                                    "%s: contract v2 前置条件 missing keys: %s"
                                    % (f, ", ".join(missing_keys))
                                )
                        setup = bullet_value(verification, ZHUNBEI_DONGZUO)
                        if not setup:
                            err("%s: contract v2 验证设计 missing 准备动作" % f)
                        elif "无" not in setup and "result=" not in setup:
                            err("%s: contract v2 准备动作 needs result= or explicit 无" % f)

                        experience = bullet_value(verification, TIYAN_YANZHENG)
                        if experience_review:
                            if not experience:
                                err("%s: opted-in experience review missing 体验验证 contract" % f)
                            else:
                                contract_value = inline_value(experience, "contract")
                                states_value = inline_value(experience, "states")
                                experience_evidence_value = inline_value(experience, "evidence")
                                missing_keys = [key for key, value in (
                                    ("contract", contract_value),
                                    ("states", states_value),
                                    ("evidence", experience_evidence_value),
                                ) if not value]
                                if missing_keys:
                                    err(
                                        "%s: 体验验证 contract missing keys: %s"
                                        % (f, ", ".join(missing_keys))
                                    )
                                else:
                                    experience_contract = validate_experience_contract(
                                        root, feat, contract_value, experience_review, err
                                    )
                                    experience_states = comma_values(states_value)
                                    if not experience_states or len(set(experience_states)) != len(experience_states):
                                        err("%s: 体验验证 states must be unique non-empty names" % f)
                                    elif experience_contract:
                                        unknown_states = sorted(
                                            set(experience_states) - set(experience_contract.get("states", []))
                                        )
                                        if unknown_states:
                                            err(
                                                "%s: 体验验证 references states outside contract: %s"
                                                % (f, ", ".join(unknown_states))
                                            )
                                    evidence_path = repo_artifact_path(
                                        root,
                                        experience_evidence_value,
                                        "planned experience evidence",
                                        err,
                                        must_exist=False,
                                    )
                                    expected_evidence_prefix = os.path.join(root, ".scratch", feat, "evidence")
                                    if evidence_path is not None:
                                        try:
                                            under_evidence = os.path.commonpath(
                                                [expected_evidence_prefix, evidence_path]
                                            ) == expected_evidence_prefix
                                        except ValueError:
                                            under_evidence = False
                                        if not under_evidence or not evidence_path.endswith(".json"):
                                            err(
                                                "%s: planned experience evidence must be JSON under .scratch/%s/evidence/"
                                                % (f, feat)
                                            )
                        elif experience:
                            err("%s: non-graphical issue must omit 体验验证 and experience_review" % f)

                        preflights = {}
                        for line in verification:
                            preflight_match = PREFLIGHT_LINE.match(line)
                            if not preflight_match:
                                continue
                            preflight_id = int(preflight_match.group(1))
                            detail = preflight_match.group(2)
                            if preflight_id in preflights:
                                err("%s: duplicate P%d 预检" % (f, preflight_id))
                            preflights[preflight_id] = detail
                            valid = (
                                detail.count("`") >= 2
                                and ("→ passed" in detail or "-> passed" in detail)
                                and "observed=" in detail
                                and "evidence=" in detail
                                and re.search(r"checked=\d{4}-\d{2}-\d{2}(?:\b|$)", detail)
                            )
                            if not valid:
                                err(
                                    "%s: P%d 预检 needs backticked action, passed, observed=, evidence=, checked=YYYY-MM-DD"
                                    % (f, preflight_id)
                                )
                        if not preflights:
                            err("%s: contract v2 验证设计 missing passed P# 预检" % f)

                        mapped = set()
                        map_preflights = {}
                        map_falsifiers = {}
                        for line in verification:
                            match = EVIDENCE_MAP.match(line)
                            if not match:
                                continue
                            ac_id = int(match.group(1))
                            mapped.add(ac_id)
                            map_preflights[ac_id] = {
                                int(value) for value in PREFLIGHT_REF.findall(line)
                            }
                            falsifier = FALSIFIER_REF.search(line)
                            falsifier_value = falsifier.group(1).strip() if falsifier else ""
                            if (
                                falsifier_value.lower() in ("无", "none", "n/a")
                                or PLACEHOLDER_REF.match(falsifier_value)
                            ):
                                falsifier_value = ""
                            map_falsifiers[ac_id] = falsifier_value
                        missing_maps = sorted(set(range(1, ac_count + 1)) - mapped)
                        if missing_maps:
                            err(
                                "%s: contract v2 AC missing evidence map: %s"
                                % (f, ", ".join("#%d" % n for n in missing_maps))
                            )
                        for ac_id in sorted(set(range(1, ac_count + 1)) & mapped):
                            refs = map_preflights.get(ac_id, set())
                            required_preflight_ids.update(refs)
                            if experience_review and not map_falsifiers.get(ac_id):
                                err("%s: contract v2 AC #%d missing 反证" % (f, ac_id))
                            if not refs:
                                err("%s: contract v2 AC #%d missing 预检 P# reference" % (f, ac_id))
                                continue
                            unknown = sorted(refs - set(preflights))
                            if unknown:
                                err(
                                    "%s: contract v2 AC #%d references unknown 预检: %s"
                                    % (f, ac_id, ", ".join("P%d" % n for n in unknown))
                                )
                cat = str(fm.get("category", ""))
                if cat not in ("enhancement", "detail", "redo", "fix"):
                    err(
                        "%s: category '%s' not in enhancement|detail|redo|fix" % (f, cat)
                    )
                deps = []
                slug = os.path.splitext(os.path.basename(f))[0]
                for b in as_list(fm.get("blocked_by")):
                    if b == "":
                        continue
                    if b not in resolved:
                        sug = ref_suggest(b, list(resolved.keys()), slug)
                        extra = " (did you mean '%s'?)" % sug if sug else ""
                        err(
                            "%s: blocked_by '%s' resolves to no sibling or archived file%s"
                            % (f, b, extra)
                        )
                    elif b == slug:
                        err("%s: blocked_by itself" % f)
                    else:
                        deps.append(b)
                graph[slug] = deps
                if cat in ("detail", "redo", "fix"):
                    ref = fm.get("refines")
                    if ref:
                        if ref not in resolved:
                            sug = ref_suggest(str(ref), list(resolved.keys()), slug)
                            extra = " (did you mean '%s'?)" % sug if sug else ""
                            err(
                                "%s: refines '%s' resolves to no sibling or archived file%s"
                                % (f, ref, extra)
                            )
                    else:
                        err("%s: category '%s' requires refines:" % (f, cat))
                created = str(fm.get("created", ""))
                if created == "":
                    err("%s: created missing" % f)
                elif not ISO_DATE.match(created):
                    err("%s: created not ISO YYYY-MM-DD" % f)
                if fm.get("status") == "done":
                    rec = done_record(issue_lines)
                    fields = []
                    if rec is not None:
                        for line in rec:
                            s = line.lstrip()
                            if s.startswith("- " + XINZENG) or s.startswith("- " + YANSHOU):
                                fields.append(s)
                    if not fields:
                        err("%s: status done but no ### 完成 record" % f)
                    else:
                        if contract_version == "2" and not any(
                            line.lstrip().startswith("- " + YANZHENG_MINGLING + "：")
                            or line.lstrip().startswith("- " + YANZHENG_MINGLING + ":")
                            for line in (rec or [])
                        ):
                            err("%s: contract v2 done record missing 验证命令" % f)
                        if contract_version == "2":
                            replay = bullet_value(rec or [], YUJIAN_CHONGFANG)
                            if not replay:
                                err("%s: contract v2 done record missing 预检重放" % f)
                            else:
                                replayed = {int(value) for value in re.findall(r"\bP(\d+)\b", replay)}
                                missing_replays = sorted(required_preflight_ids - replayed)
                                if missing_replays:
                                    err(
                                        "%s: contract v2 done record missing preflight replays: %s"
                                        % (f, ", ".join("P%d" % n for n in missing_replays))
                                    )
                                if "fingerprint" not in replay or "match" not in replay:
                                    err("%s: contract v2 预检重放 needs fingerprint match" % f)
                            if experience_review:
                                experience = bullet_value(rec or [], TIYAN_YANZHENG)
                                valid_experience = (
                                    bool(experience)
                                    and ("→ passed" in experience or "-> passed" in experience)
                                    and "evidence=" in experience
                                )
                                if not valid_experience:
                                    err(
                                        "%s: opted-in experience done record needs passed 体验验证 with evidence="
                                        % f
                                    )
                                else:
                                    completed_evidence = inline_value(experience, "evidence")
                                    if completed_evidence != experience_evidence_value:
                                        err(
                                            "%s: completion experience evidence %r != planned %r"
                                            % (f, completed_evidence, experience_evidence_value)
                                        )
                                    validate_experience_evidence(
                                        root,
                                        feat,
                                        completed_evidence,
                                        experience_review,
                                        experience_contract,
                                        experience_states,
                                        err,
                                    )
                        for m in sorted(set(TEST_PATH.findall("\n".join(fields)))):
                            cand = m.replace("\\", "/")
                            if not (
                                os.path.isfile(os.path.join(root, cand))
                                or os.path.isfile(os.path.join(fd, cand))
                            ):
                                err("%s: ### 完成 names missing test file '%s'" % (f, m))
                        # records are prose-typed: normalize ./ prefix, separators, and case
                        # (Windows-first repos) before membership comparison
                        def _norm(p):
                            return p.replace("\\", "/").rstrip("/").lstrip("./").lower()

                        declared = {
                            _norm(p) for p in as_list(fm.get("test_paths")) if p
                        }
                        if declared:
                            xin = [
                                line.lstrip()
                                for line in (rec or [])
                                if line.lstrip().startswith("- " + XINZENG)
                            ]
                            for m in sorted(set(TEST_PATH.findall("\n".join(xin)))):
                                if _norm(m) not in declared:
                                    err(
                                        "%s: 新增测试 '%s' outside declared test_paths - "
                                        "add the path to test_paths or correct the record"
                                        % (f, m)
                                    )
            for c in cyclic_slugs(graph):
                err("%s: in (or depends on) a blocked_by cycle" % by_slug[c])

    cfh = os.path.join(scratch, "handoff.md")
    if os.path.isfile(cfh):
        check_handoff(cfh, "")

    for p in sorted(BAD_UTF8):
        err("%s: not valid UTF-8" % p)

    if errors:
        print("verify-artifacts: %d violation(s)" % len(errors))
        for e in errors:
            print("  %s" % e)
        return 1
    print(
        "verify-artifacts: OK - checked %d issue(s), %d PRD(s), %d handoff(s), %d summary(s), %d codebase block(s)."
        % (n_issues, n_prds, n_handoffs, n_summaries, n_cb_blocks)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
