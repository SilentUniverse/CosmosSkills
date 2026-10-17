import contextlib
import http.client
import importlib.util
import io
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "spec_review", ROOT / "workflow" / "spec" / "scripts" / "spec-review.py"
)
assert SPEC and SPEC.loader
spec_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spec_review)
feature_doc = spec_review.feature_doc


FEATURE = """---
type: feature
feature: import
created: 2026-09-19
---

## 目标与边界
- 问题：导入取消后仍可能显示成功。
- 结果：取消后导入任务进入 cancelled 终态。
- IN：导入取消
- OUT：导出，另行处理

## 需求
- R1 — 导入取消后必须进入 cancelled。
  Before：取消后可能显示成功。
  验收：cancel → cancelled
- R2 — cancel 后迟到 success 不得覆盖 cancelled。

## 决策
### D1 — State ownership
Refs: R1 R2
Door: one-way
Blast radius: module
终态由 ImportSession 持有。

### D2 — Logging
Refs: R2
日志记录取消原因。

## 不变量
- C1 — 用户数据不得删除。

## 共享验证
```json
{"cwd": ".", "environment": {"runtime": "python 3.9"}, "prepare": "无（已就绪）",
 "commands": {"unit": "python3 -m unittest"}}
```

## 任务
### T1 — state transition
- status: pending
- reason: 等待评审
- covers: R1 D1
- 做什么：实现取消终态。

## 变更记录
- 2026-09-19 初稿
"""

CONTRACT_KEYS = {"section:goal", "section:acceptance", "section:context", "section:layout",
                 "R1", "R2", "D1", "D2", "C1"}


def plant(root, text=FEATURE):
    path = Path(root) / ".scratch" / "import" / feature_doc.FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def accept(root, event_id="accepted-event"):
    """Record acceptance of the current contract through the bridge's own persistence path."""
    prepared = spec_review.prepare_review(root, "import")
    spec_review.persist_spec_decision(prepared, {"status": "accepted"}, {"action": "approve"}, event_id)
    return prepared


def run_cli(*argv):
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = spec_review.main(["spec-review.py"] + [str(arg) for arg in argv])
    return code, output.getvalue(), errors.getvalue()


def render(root, *extra):
    code, output, errors = run_cli("render", root, "import", *extra)
    if code:
        return code, None, errors
    payload = json.loads(output)
    return code, payload, Path(payload["html"]).read_text(encoding="utf-8")


def records(root):
    directory = Path(root) / ".scratch/import" / feature_doc.REVIEWS
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


class ParseValidateTests(unittest.TestCase):
    def test_parse_reads_all_families_and_refs(self):
        model = feature_doc.parse_model(FEATURE)
        self.assertEqual(["R1", "R2"], [item["id"] for item in model.requirements])
        self.assertEqual("取消后可能显示成功。", model.requirements[0]["before"])
        self.assertEqual("cancel → cancelled", model.requirements[0]["check"])
        self.assertEqual(["D1", "D2"], [item["id"] for item in model.decisions])
        self.assertEqual(["R1", "R2"], model.decisions[0]["refs"])
        self.assertEqual(("one-way", "module"), (model.decisions[0]["door"], model.decisions[0]["blast"]))
        self.assertEqual(["C1"], [item["id"] for item in model.contracts])
        self.assertEqual(["导入取消"], model.scope_in)
        self.assertEqual(CONTRACT_KEYS, set(model.hashes()))
        self.assertEqual({"R1", "R2"}, feature_doc.parse_model(FEATURE.replace("Refs:", "refs:")).refs_of("D1"))
        self.assertEqual([], feature_doc.validate_model(model))

    def test_duplicate_ids_repeated_and_undeclared_refs_are_rejected(self):
        cases = ((FEATURE.replace("- R2 —", "- R1 —"), "duplicate id R1"),
                 (FEATURE.replace("Refs: R1 R2", "Refs: R1 R9"), "D1 references undeclared R9"),
                 (FEATURE.replace("Refs: R1 R2", "Refs: R1\nRefs: R2"), "D1 repeats Refs"),
                 (FEATURE.replace("Refs: R2", "Refs: D1"), "must reference R#"))
        for text, message in cases:
            with self.subTest(message=message):
                problems = feature_doc.validate_model(feature_doc.parse_model(text))
                self.assertTrue(any(message in problem for problem in problems), problems)

    def test_digest_normalizes_bom_and_crlf_but_not_content(self):
        digest = lambda text: feature_doc.sha256_text(feature_doc.contract_text(text))
        self.assertEqual(digest(FEATURE), digest("﻿" + FEATURE.replace("\n", "\r\n")))
        self.assertNotEqual(digest(FEATURE), digest(FEATURE.replace("持有。", "持有！")))

    def test_engineering_sections_do_not_change_the_contract(self):
        edited = (FEATURE.replace("python 3.9", "python 3.12").replace("- status: pending", "- status: ready")
                  .replace("初稿", "初稿\n- 2026-09-20 调整任务") + "### T2 — extra\n- status: pending\n")
        self.assertEqual(feature_doc.contract_text(FEATURE), feature_doc.contract_text(edited))
        self.assertNotIn("共享验证", feature_doc.contract_text(FEATURE))
        self.assertNotIn("T1", feature_doc.contract_text(FEATURE))

    def test_delta_propagates_through_refs_and_global_changes(self):
        old = feature_doc.parse_model(FEATURE).hashes()
        delta = spec_review.classify_delta(
            feature_doc.parse_model(FEATURE.replace("必须进入 cancelled。", "必须进入 cancelled 并显示原因。")), old)
        self.assertEqual((["R1"], ["D1"], []), (delta["MODIFIED"], delta["AFFECTED"], delta["ADDED"]))
        self.assertIn("D2", delta["UNCHANGED"])
        for before, after in (("用户数据不得删除", "允许删除缓存"), ("- OUT：导出", "- OUT：同步")):
            with self.subTest(before=before):
                delta = spec_review.classify_delta(feature_doc.parse_model(FEATURE.replace(before, after)), old)
                self.assertTrue(delta["MODIFIED"])
                self.assertEqual(["D1", "D2", "R1", "R2"], delta["AFFECTED"])
        delta = spec_review.classify_delta(
            feature_doc.parse_model(FEATURE.replace("## 共享验证", "## 外部约束\n必须离线。\n\n## 共享验证")), old)
        self.assertIn("section:context", delta["MODIFIED"])
        self.assertEqual(["D1", "D2", "R1", "R2"], delta["AFFECTED"])


class RenderTests(unittest.TestCase):
    def test_first_render_is_full_static_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            code, payload, page = render(directory)
            self.assertEqual(0, code, page)
            self.assertEqual("full", payload["mode"])
            self.assertEqual({"items": len(CONTRACT_KEYS)}, payload["counts"])
            self.assertIn("Full Review", page)
            self.assertIn("SPEC FEEDBACK", page)
            self.assertNotIn("bridge-data", page)
            self.assertEqual({"D1"}, set(re.findall(r'class="comment" data-id="([^"]+)"', page)))
            self.assertEqual([], records(directory))

    def test_render_after_acceptance_and_edit_is_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            accept(directory)
            edited = (FEATURE.replace("必须进入 cancelled。", "必须进入 cancelled（终态）。")
                      .replace("  验收：cancel → cancelled", "  验收：显示取消原因")
                      .replace("- R2 — cancel 后迟到 success 不得覆盖 cancelled。\n",
                               "- R3 — 取消后可重新导入。\n")
                      .replace("Refs: R1 R2", "Refs: R1").replace("Refs: R2", "Refs: R3"))
            path.write_text(edited, encoding="utf-8")
            code, payload, page = render(directory)
            self.assertEqual(0, code, page)
            self.assertEqual("delta", payload["mode"])
            delta = spec_review.prepare_review(directory, "import")["delta"]
            self.assertEqual((["R3"], ["D1", "D2", "R1"], ["R2"]), (delta["ADDED"], delta["MODIFIED"], delta["REMOVED"]))
            self.assertEqual({"ADDED": 1, "MODIFIED": 3, "REMOVED": 1, "AFFECTED": 0, "UNCHANGED": 5},
                             payload["counts"])
            self.assertIn("Delta Review", page)
            self.assertIn('class="state MODIFIED"', page)
            self.assertIn("本次移除", page)
            for evidence in ("cancel 后迟到 success 不得覆盖 cancelled。", "已接受：导入取消后必须进入 cancelled。",
                             "原验收观察：cancel → cancelled", "显示取消原因"):
                self.assertIn(evidence, page)

    def test_render_marks_ref_affected_and_survives_engineering_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            accept(directory)
            path.write_text(FEATURE.replace("- status: pending", "- status: ready"), encoding="utf-8")
            code, payload, page = render(directory)
            self.assertEqual(0, code)
            self.assertEqual(len(CONTRACT_KEYS), payload["counts"]["UNCHANGED"])
            self.assertIn("没有待审内容变化", page)
            path.write_text(FEATURE.replace("迟到 success", "迟到 failure"), encoding="utf-8")
            code, payload, page = render(directory)
            self.assertEqual(["D1", "D2"], spec_review.prepare_review(directory, "import")["delta"]["AFFECTED"])
            self.assertIn('class="state AFFECTED"', page)
            code, payload, _ = render(directory, "--full")
            self.assertEqual("full", payload["mode"])

    def test_render_rejects_broken_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory, FEATURE.replace("Refs: R1 R2", "Refs: R1 R7"))
            code, _, errors = render(directory)
            self.assertEqual(1, code)
            self.assertIn("undeclared R7", errors)
            self.assertFalse((Path(directory) / ".scratch/import/reviews").exists())

    def test_freeform_text_in_structured_sections_stays_visible_and_escaped(self):
        text = (FEATURE.replace("- R1 —", "需求的补充权限限制。\n- R1 —", 1)
                .replace("- C1 —", "用户的文件不能离开本机。\n- C1 —")
                .replace("## 共享验证", "## 端到端验证\n手动取消并检查列表。\n\n## 补充约束\n<script>x</script>\n\n## 共享验证"))
        page = spec_review.review_html("import", "a" * 64, feature_doc.parse_model(text), None, "full", False)
        for line in ("需求的补充权限限制。", "用户的文件不能离开本机。", "手动取消并检查列表。", "&lt;script&gt;x"):
            self.assertIn(line, page)
        self.assertNotIn("<script>x", page)
        self.assertNotIn("实现取消终态", page)

    def test_human_and_one_way_decisions_cannot_leave_review_in_delta(self):
        text = FEATURE.replace("Refs: R2\n", "Refs: R2\nReview: human\n")
        old = feature_doc.parse_model(text)
        self.assertEqual(["D2", "D1"], [item["id"] for item in spec_review.review_items(old)])
        flipped = (text.replace("Door: one-way", "Door: two-way").replace("Review: human\n", "")
                   .replace("终态由 ImportSession 持有。", "允许丢弃取消终态。"))
        new = feature_doc.parse_model(flipped)
        self.assertEqual([], new.review_required_items())
        page = spec_review.review_html("import", "a" * 64, new, spec_review.classify_delta(new, old.hashes()),
                                       "delta", False, baseline=old)
        self.assertEqual({"D1", "D2"}, set(re.findall(r'class="comment" data-id="([^"]+)"', page)))
        for evidence in ("终态由 ImportSession 持有。", "允许丢弃取消终态。", "人工确认或撤回条件有变化"):
            self.assertIn(evidence, page)

    def test_pages_are_named_by_content_and_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            _, payload, page = render(directory)
            first = Path(payload["html"])
            self.assertEqual(Path(directory).resolve() / ".scratch/import/reviews", first.parent.resolve())
            self.assertRegex(first.name, r"^page-[0-9a-f]{16}\.html$")
            self.assertEqual(first, Path(render(directory)[1]["html"]))
            path.write_text(FEATURE.replace("持有。", "持有并广播。"), encoding="utf-8")
            second = Path(render(directory)[1]["html"])
            self.assertNotEqual(first, second)
            self.assertEqual(page, first.read_text(encoding="utf-8"))
            code, _, errors = run_cli("render", directory, "import", "--out", first)
            self.assertEqual(1, code)
            self.assertIn("immutable", errors)
            self.assertEqual(page, first.read_text(encoding="utf-8"))


class ValidateTests(unittest.TestCase):
    def test_require_accepted_gates_on_the_latest_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            code, output, _ = run_cli("validate", directory, "import")
            self.assertEqual(0, code, output)
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("no recorded human acceptance", output)
            accept(directory)
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(0, code, output)
            self.assertIn("accepted", output)
            path.write_text(FEATURE.replace("必须进入 cancelled。", "改动的条目。") + "### T2 — x\n", encoding="utf-8")
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("changed since acceptance: R1", output)

    def test_heading_and_blank_line_edits_are_attributed_or_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            accept(directory)
            path.write_text(FEATURE.replace("\n- C1", "\n\n- C1", 1), encoding="utf-8")
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(0, code, output)
            path.write_text(FEATURE.replace("## 不变量", "## 不变量（硬）", 1), encoding="utf-8")
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("changed since acceptance: section:layout", output)

    def test_tampered_review_record_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            accept(directory)
            record = Path(directory) / ".scratch/import/reviews/accepted-event.json"
            record.write_text(record.read_text(encoding="utf-8").replace("ImportSession", "Other"), encoding="utf-8")
            code, output, _ = run_cli("validate", directory, "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("review record is invalid", output)


def post(url, payload):
    request = Request(url + "submit", data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # HTTPError carries the JSON body
        return exc.code, json.loads(exc.read().decode("utf-8"))


def start(root, timeout=3.0):
    """Listener starts synchronously; only the accept loop runs in a thread."""
    prepared = spec_review.prepare_review(root, "import")
    server, url, token, result = spec_review.start_bridge(prepared)
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(spec_review.serve_bridge(
        server, result, timeout, {"name": "import", "digest": prepared["digest"]})))
    thread.start()
    return prepared, url, token, thread, outcome


def approve_payload(token, prepared):
    return {"token": token, "spec_digest": prepared["digest"], "action": "approve",
            "items": [], "global_feedback": ""}


class BridgeTests(unittest.TestCase):
    def test_feedback_submit_returns_json_and_records_non_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, url, token, thread, outcome = start(directory)
            status, body = post(url, {"token": token, "spec_digest": prepared["digest"], "action": "feedback",
                                      "items": [{"id": "D1", "hash": "x", "action": "change", "comment": "保留 API"}],
                                      "global_feedback": "UI 不能显示成功。"})
            thread.join(5)
            self.assertEqual(200, status)
            self.assertEqual(("feedback", "import", "D1"), (body["status"], body["spec"], body["items"][0]["id"]))
            self.assertEqual(prepared["model"].hashes()["D1"], body["items"][0]["hash"])
            self.assertEqual(body, outcome[0])
            (record,) = records(directory)
            self.assertEqual(("spec_decision", False, None), (record["kind"], record["accepted"], record["text"]))
            self.assertNotIn("token", record["event"])
            self.assertIsNone(feature_doc.accepted_record(feature_doc.load(directory, "import")))

    def test_approve_writes_accepted_record_with_contract_text(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, url, token, thread, outcome = start(directory)
            status, body = post(url, approve_payload(token, prepared))
            thread.join(5)
            self.assertEqual((200, "accepted"), (status, body["status"]))
            self.assertEqual("accepted", outcome[0]["status"])
            feature = feature_doc.load(directory, "import")
            record = feature_doc.accepted_record(feature)
            self.assertEqual(feature_doc.contract_text(feature.text), record["text"])
            self.assertEqual(prepared["digest"], record["spec_digest"])
            self.assertEqual([record], records(directory))

    def test_approve_with_comments_downgrades_to_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, url, token, thread, _ = start(directory)
            payload = dict(approve_payload(token, prepared), global_feedback="再想想")
            status, body = post(url, payload)
            thread.join(5)
            self.assertEqual("feedback", body["status"])
            self.assertFalse(records(directory)[0]["accepted"])

    def test_failed_persistence_returns_error_and_same_decision_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, url, token, thread, outcome = start(directory)
            payload = approve_payload(token, prepared)
            try:
                with mock.patch.object(spec_review, "write_record", side_effect=OSError("disk full")):
                    status, body = post(url, payload)
                self.assertEqual(500, status)
                self.assertIn("disk full", body["message"])
                self.assertEqual([], records(directory))
                self.assertFalse(outcome)
                status, body = post(url, payload)
                self.assertEqual((200, "accepted"), (status, body["status"]))
            finally:
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(1, len(records(directory)))
            self.assertTrue(records(directory)[0]["accepted"])

    def test_wrong_or_non_ascii_token_is_rejected(self):
        for bad in ("not-the-token", "汉"):
            with self.subTest(token=bad), tempfile.TemporaryDirectory() as directory:
                plant(directory)
                prepared, url, token, thread, outcome = start(directory, timeout=0.5)
                status, body = post(url, dict(approve_payload(token, prepared), token=bad))
                thread.join(5)
                self.assertEqual((403, "error"), (status, body["status"]))
                self.assertEqual("timeout", outcome[0]["status"])
                self.assertEqual([], records(directory))

    def test_foreign_host_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            _, url, _, thread, outcome = start(directory, timeout=0.5)
            connection = http.client.HTTPConnection("127.0.0.1", int(re.search(r":(\d+)/", url).group(1)), timeout=5)
            connection.request("GET", "/", headers={"Host": "evil.example"})
            response = connection.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            connection.close()
            thread.join(5)
            self.assertEqual("timeout", outcome[0]["status"])

    def test_bridge_data_script_is_valid_json(self):
        model = feature_doc.parse_model(FEATURE.replace("持有。", "持有 </script> \"引号\"。"))
        page = spec_review.review_html("import", "0" * 64, model, None, "full", True,
                                       token="tok", url="http://127.0.0.1:1/")
        match = re.search(r'<script type="application/json" id="bridge-data">(.*?)</script>', page, re.S)
        payload = json.loads(match.group(1))
        self.assertEqual(("tok", "import"), (payload["token"], payload["spec"]))
        self.assertEqual(model.hashes(), payload["items"])
        self.assertEqual(1, page.count('id="approve"'))

    def test_contract_edited_after_page_creation_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = plant(directory)
            prepared, url, token, thread, outcome = start(directory, timeout=0.5)
            path.write_text(FEATURE.replace("必须进入 cancelled。", "页面打开后被修改。"), encoding="utf-8")
            status, body = post(url, approve_payload(token, prepared))
            thread.join(5)
            self.assertEqual((409, "stale_review"), (status, body["status"]))
            self.assertEqual(prepared["digest"], body["expected_digest"])
            self.assertNotEqual(body["expected_digest"], body["current_digest"])
            self.assertEqual("timeout", outcome[0]["status"])
            self.assertEqual([], records(directory))

    def test_identical_submit_is_idempotent_and_conflicting_decision_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, url, token, thread, outcome = start(directory)
            connection = http.client.HTTPConnection("127.0.0.1", int(re.search(r":(\d+)/", url).group(1)), timeout=5)
            payload = {"token": token, "spec_digest": prepared["digest"], "action": "feedback",
                       "items": [{"id": "Q1", "action": "answer", "comment": "需要显示原因"}]}

            def send(value):
                connection.request("POST", "/submit", body=json.dumps(value).encode("utf-8"),
                                   headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                return response.status, json.loads(response.read().decode("utf-8"))

            first = send(payload)
            self.assertEqual((200, "feedback"), (first[0], first[1]["status"]))
            self.assertEqual(first, send(payload))
            changed = dict(payload, items=[dict(payload["items"][0], comment="另一条意见")])
            self.assertEqual(409, send(changed)[0])
            self.assertEqual(409, send(approve_payload(token, prepared))[0])
            connection.close()
            thread.join(5)
            self.assertEqual("feedback", outcome[0]["status"])
            self.assertEqual(1, len(records(directory)))

    def test_timeout_returns_timeout_status(self):
        with tempfile.TemporaryDirectory() as directory:
            plant(directory)
            prepared, _, _, thread, outcome = start(directory, timeout=0.2)
            thread.join(5)
            self.assertEqual({"status": "timeout", "spec": "import", "spec_digest": prepared["digest"]}, outcome[0])
            self.assertEqual([], records(directory))


class CandidatePageTests(unittest.TestCase):
    def test_candidate_review_page_renders_bound_spec_text(self):
        page = spec_review.candidate_review_page({"digest": "a" * 64, "spec_digest": "b" * 64},
                                                 "## 需求\naccepted <body> & bytes", "", '{"token":"t"}')
        self.assertIn("接受的 Spec", page)
        self.assertIn("accepted &lt;body&gt; &amp; bytes", page)
        self.assertIn("b" * 64, page)

    def test_candidate_review_page_omits_spec_block_without_spec(self):
        page = spec_review.candidate_review_page({"digest": "a" * 64, "spec_digest": None}, None, "", "{}")
        self.assertNotIn("接受的 Spec", page)
        self.assertIn("固定候选审核", page)


if __name__ == "__main__":
    unittest.main()
