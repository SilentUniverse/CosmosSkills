import importlib.util
import http.client
import io
import json
import re
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "spec_review", ROOT / "workflow" / "spec" / "scripts" / "spec-review.py"
)
assert SPEC and SPEC.loader
spec_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spec_review)


PRD = """---
type: prd
feature: import
version: 1
created: 2026-09-19
---

## 问题（Problem）

导入取消后仍可能显示成功。

## 方案（Solution）

取消后导入任务必须进入 cancelled 终态。

## 用户场景（User Stories）

- R1 — 导入取消后必须进入 cancelled。
- R2 — cancel 后迟到 success 不得覆盖 cancelled。

## 实现决策（Implementation Decisions）

### D1 — State ownership

Refs: R1 R2

终态由 ImportSession 持有。

Door: one-way

Blast radius: module

Why:

UI 生命周期不能拥有任务终态。

## 测试决策（Testing Decisions）

| ID | 场景 / 不变量 | 公共接缝 | 可观察结果 | 证据形态 |
|---|---|---|---|---|
| R1 | 取消任务 | ImportSession | cancel → cancelled | behavior |
| R2 | 迟到 success | ImportSession | 状态不变化 | regression |

## 实施切片（Execution Slices）

| Slice | Outcome | Covers | Depends | Review |
|---|---|---|---|---|
| S1 | state transition | R1 R2 D1 | - | key |
| S2 | UI binding | R1 D1 | S1 | routine |
| S3 | integration proof | R2 | S1 | verification |
"""


def plant_feature(root, text=PRD, name="PRD.md"):
    feature_dir = root / ".scratch" / "import"
    feature_dir.mkdir(parents=True, exist_ok=True)
    path = feature_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def run_cli(*argv):
    output = io.StringIO()
    errors = io.StringIO()
    import contextlib

    with redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = spec_review.main(["spec-review.py"] + list(argv))
    return code, output.getvalue(), errors.getvalue()


class ParseValidateTests(unittest.TestCase):
    def test_parse_reads_all_families_and_refs(self):
        model = spec_review.parse_model(PRD)
        self.assertEqual(["R1", "R2"], [item["id"] for item in model.requirements])
        self.assertEqual(["D1"], [item["id"] for item in model.decisions])
        self.assertEqual(["R1", "R2"], model.decisions[0]["refs"])
        self.assertEqual("one-way", model.decisions[0]["door"])
        self.assertEqual("module", model.decisions[0]["blast"])
        self.assertEqual(["S1", "S2", "S3"], [item["id"] for item in model.slices])
        self.assertEqual([], model.slices[0]["depends"])
        self.assertEqual(["S1"], model.slices[1]["depends"])
        self.assertEqual(["R1", "R2"], [row["id"] for row in model.test_rows])

    def test_valid_model_has_no_problems(self):
        self.assertEqual([], spec_review.validate_model(spec_review.parse_model(PRD)))
        self.assertEqual([], spec_review.model_warnings(spec_review.parse_model(PRD)))

    def test_legacy_prd_without_ids_is_skipped(self):
        text = PRD.replace("- R1 — 导入取消后必须进入 cancelled。\n", "").replace(
            "- R2 — cancel 后迟到 success 不得覆盖 cancelled。\n", ""
        ).replace("### D1 — State ownership", "### State ownership").replace(
            "## 实施切片（Execution Slices）", "## 切片"
        )
        model = spec_review.parse_model(text)
        self.assertFalse(model.has_ids)
        self.assertEqual([], spec_review.validate_model(model))

    def test_duplicate_ids_are_rejected(self):
        text = PRD.replace("- R2 —", "- R1 —")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("duplicate id R1" in problem for problem in problems))

    def test_unknown_refs_are_rejected(self):
        text = PRD.replace("Refs: R1 R2", "Refs: R1 R9")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("D1 references undeclared R9" in problem for problem in problems))
        text = PRD.replace("| S2 | UI binding | R1 D1 | S1 | routine |",
                           "| S2 | UI binding | R1 D9 | S1 | routine |")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("S2 covers undeclared D9" in problem for problem in problems))
        text = PRD.replace("| S2 | UI binding | R1 D1 | S1 | routine |",
                           "| S2 | UI binding | R1 D1 | S9 | routine |")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("S2 depends on undeclared S9" in problem for problem in problems))

    def test_depends_cycle_is_rejected(self):
        text = PRD.replace("| S1 | state transition | R1 R2 D1 | - | key |",
                           "| S1 | state transition | R1 R2 D1 | S2 | key |")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("Depends cycle" in problem for problem in problems))

    def test_bad_review_token_is_rejected(self):
        text = PRD.replace("| routine |", "| optional |")
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("S2 review 'optional' not in" in problem for problem in problems))

    def test_testing_row_without_requirement_is_rejected(self):
        text = PRD.replace(
            "| R2 | 迟到 success | ImportSession | 状态不变化 | regression |",
            "| R9 | 迟到 success | ImportSession | 状态不变化 | regression |",
        )
        problems = spec_review.validate_model(spec_review.parse_model(text))
        self.assertTrue(any("undeclared R9" in problem for problem in problems))

    def test_requirement_without_test_row_warns(self):
        text = PRD.replace(
            "| R2 | 迟到 success | ImportSession | 状态不变化 | regression |\n", ""
        )
        warnings = spec_review.model_warnings(spec_review.parse_model(text))
        self.assertEqual(["R2 has no 测试决策 row"], warnings)

    def test_digest_ignores_bom_and_crlf_but_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PRD.md"
            path.write_bytes(PRD.encode("utf-8"))
            crlf = Path(directory) / "PRD-crlf.md"
            crlf.write_bytes(b"\xef\xbb\xbf" + PRD.replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(spec_review.prd_digest(path), spec_review.prd_digest(crlf))
            changed = Path(directory) / "PRD-changed.md"
            changed.write_text(PRD + "\nextra\n", encoding="utf-8")
            self.assertNotEqual(spec_review.prd_digest(path), spec_review.prd_digest(changed))

    def test_resolve_head_prd_follows_supersedes_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            plant_feature(
                root,
                PRD.replace("version: 1", "version: 2").replace(
                    "created: 2026-09-19", "created: 2026-09-19\nsupersedes: PRD.md"
                ),
                name="PRD-v2.md",
            )
            feature = root / ".scratch" / "import"
            self.assertEqual("PRD-v2.md", spec_review.resolve_head_prd(feature))
            plant_feature(root, PRD.replace("version: 1", "version: 3"), name="PRD-v3.md")
            with self.assertRaises(ValueError):
                spec_review.resolve_head_prd(feature)


class RenderDeltaTests(unittest.TestCase):
    def render(self, root):
        return run_cli("render", str(root), "import")

    def test_first_render_is_full_and_writes_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            code, output, _ = self.render(root)
            self.assertEqual(0, code, output)
            payload = json.loads(output)
            self.assertEqual("full", payload["mode"])
            self.assertEqual(6, payload["counts"]["items"])
            html_text = (root / ".scratch" / "import" / "spec-review.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("技术细节", html_text)
            self.assertIn("<svg", html_text)
            self.assertIn("SPEC FEEDBACK", html_text)
            self.assertIn("复制反馈", html_text)
            self.assertNotIn("bridge-data", html_text)
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(1, state["schema_version"])
            self.assertEqual("PRD.md", state["spec"])
            self.assertEqual(payload["spec_digest"], state["last_rendered_digest"])
            self.assertEqual(
                {"R1", "R2", "D1", "S1", "S2", "S3"}, set(state["last_rendered_items"])
            )
            self.assertIsNone(state["accepted_digest"])

    def test_second_render_after_edit_is_delta_with_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            code, _, _ = self.render(root)
            self.assertEqual(0, code)
            prd.write_text(
                PRD.replace(
                    "- R1 — 导入取消后必须进入 cancelled。",
                    "- R1 — 导入取消后必须进入 cancelled（终态）。",
                ).replace(
                    "| S3 | integration proof | R2 | S1 | verification |",
                    "| S3 | integration proof | R2 | S1 | verification |\n"
                    "| S4 | telemetry | R2 | S1 | routine |",
                ),
                encoding="utf-8",
            )
            code, output, _ = self.render(root)
            self.assertEqual(0, code, output)
            payload = json.loads(output)
            self.assertEqual("delta", payload["mode"])
            self.assertEqual(1, payload["counts"]["MODIFIED"])
            self.assertEqual(1, payload["counts"]["ADDED"])
            self.assertEqual(0, payload["counts"]["REMOVED"])
            self.assertEqual(3, payload["counts"]["AFFECTED"])
            self.assertEqual(2, payload["counts"]["UNCHANGED"])
            html_text = (root / ".scratch" / "import" / "spec-review.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("Delta Review", html_text)
            self.assertIn('class="state MODIFIED"', html_text)

    def test_removed_items_get_tombstones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            self.render(root)
            prd.write_text(
                PRD.replace("- R2 — cancel 后迟到 success 不得覆盖 cancelled。\n", "").replace(
                    "| R2 | 迟到 success | ImportSession | 状态不变化 | regression |\n", ""
                ).replace("Refs: R1 R2", "Refs: R1").replace(
                    "| S1 | state transition | R1 R2 D1 | - | key |",
                    "| S1 | state transition | R1 D1 | - | key |",
                ).replace(
                    "| S3 | integration proof | R2 | S1 | verification |",
                    "| S3 | integration proof | R1 | S1 | verification |",
                ),
                encoding="utf-8",
            )
            code, output, _ = self.render(root)
            self.assertEqual(0, code, output)
            html_text = (root / ".scratch" / "import" / "spec-review.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("本次移除", html_text)
            self.assertIn("R2", html_text)

    def test_removed_requirement_marks_dependents_affected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            self.render(root)
            cleaned = (
                PRD.replace("- R2 — cancel 后迟到 success 不得覆盖 cancelled。\n", "")
                .replace("| R2 | 迟到 success | ImportSession | 状态不变化 | regression |\n", "")
                .replace("Refs: R1 R2", "Refs: R1")
                .replace("| S1 | state transition | R1 R2 D1 | - | key |",
                         "| S1 | state transition | R1 D1 | - | key |")
                .replace("| S3 | integration proof | R2 | S1 | verification |",
                         "| S3 | integration proof | R1 | S1 | verification |")
            )
            prd.write_text(cleaned, encoding="utf-8")
            code, output, _ = self.render(root)
            self.assertEqual(0, code, output)
            counts = json.loads(output)["counts"]
            self.assertEqual(1, counts["REMOVED"])
            self.assertEqual(3, counts["MODIFIED"])
            self.assertEqual(1, counts["AFFECTED"])
            self.assertEqual(1, counts["UNCHANGED"])

    def test_removed_requirement_with_dangling_ref_refuses_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            self.render(root)
            prd.write_text(
                PRD.replace("- R2 — cancel 后迟到 success 不得覆盖 cancelled。\n", "").replace(
                    "| R2 | 迟到 success | ImportSession | 状态不变化 | regression |\n", ""
                ),
                encoding="utf-8",
            )
            code, _, errors = self.render(root)
            self.assertEqual(1, code)
            self.assertIn("undeclared R2", errors)

    def test_render_rejects_broken_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root, PRD.replace("Refs: R1 R2", "Refs: R1 R7"))
            code, _, errors = self.render(root)
            self.assertEqual(1, code)
            self.assertIn("undeclared R7", errors)

    def test_render_force_full(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            self.render(root)
            code, output, _ = self.render(root)  # no edit would still be delta
            self.assertEqual("delta", json.loads(output)["mode"])
            code, output, errors = run_cli("render", str(root), "import", "--full")
            self.assertEqual(0, code)
            self.assertEqual("full", json.loads(output)["mode"])


class AcceptGateTests(unittest.TestCase):
    def test_require_accepted_gates_on_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            code, output, errors = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("no recorded human acceptance", output)

            code, output, errors = run_cli("accept", str(root), "import")
            self.assertEqual(0, code)
            payload = json.loads(output)
            self.assertEqual("accepted", payload["status"])
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["spec_digest"], state["accepted_digest"])

            code, output, errors = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(0, code, output)
            self.assertIn("accepted", output)

            prd.write_text(PRD + "\n## 后记\n\n- 一句改动。\n", encoding="utf-8")
            code, output, errors = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("re-review before materializing", output)

    def test_render_preserves_accepted_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            run_cli("accept", str(root), "import")
            run_cli("render", str(root), "import")
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertIsNotNone(state["accepted_digest"])

    def test_accept_rejects_broken_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root, PRD.replace("| S1 | state transition | R1 R2 D1 | - | key |",
                                            "| S1 | state transition | R1 R2 D1 | S2 | key |"))
            code, _, _ = run_cli("accept", str(root), "import")
            self.assertEqual(1, code)

    def test_accept_pins_snapshot_and_item_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            code, _, _ = run_cli("accept", str(root), "import")
            self.assertEqual(0, code)
            feature_dir = root / ".scratch" / "import"
            state = json.loads(
                (feature_dir / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["D1", "R1", "R2", "S1", "S2", "S3"], sorted(state["accepted_items"])
            )
            self.assertEqual("PRD.md", state["accepted_spec"])
            snapshot = feature_dir / "spec-accepted.md"
            self.assertTrue(snapshot.is_file())
            self.assertEqual(spec_review.prd_digest(snapshot), state["accepted_digest"])

    def test_validate_reports_item_delta_after_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            run_cli("accept", str(root), "import")
            prd.write_text(
                PRD.replace("- R1 — 导入取消后必须进入 cancelled。", "- R1 — 改动的条目。"),
                encoding="utf-8",
            )
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("re-review before materializing", output)
            self.assertIn("changed since acceptance: R1", output)

    def test_validate_reports_edits_outside_the_item_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            run_cli("accept", str(root), "import")
            prd.write_text(PRD + "\n## 后记\n\n- 一句改动。\n", encoding="utf-8")
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("changed since acceptance: no R/D/S item moved", output)

    def test_validate_flags_edited_or_missing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            run_cli("accept", str(root), "import")
            snapshot = root / ".scratch" / "import" / "spec-accepted.md"
            snapshot.write_text("被篡改的快照。\n", encoding="utf-8")
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("spec-accepted.md no longer matches accepted_digest", output)
            snapshot.unlink()
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("spec-accepted.md is missing", output)

    def test_render_preserves_acceptance_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            run_cli("accept", str(root), "import")
            accepted = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            prd = root / ".scratch" / "import" / "PRD.md"
            prd.write_text(PRD + "\n## 后记\n\n- 一句改动。\n", encoding="utf-8")
            run_cli("render", str(root), "import")
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(accepted["accepted_digest"], state["accepted_digest"])
            self.assertEqual(accepted["accepted_items"], state["accepted_items"])
            self.assertNotEqual(
                state["last_rendered_digest"], state["accepted_digest"]
            )


def post(url, payload):
    request = Request(
        url + "submit",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # HTTPError carries the JSON body
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body)


class BridgeTests(unittest.TestCase):
    def bridge(self, root, timeout=3.0):
        # The listener starts synchronously; only the accept loop runs in a
        # thread, so a slow runner cannot race the test past bridge startup.
        prepared = spec_review.prepare_review(root, "import")
        server, url, token, result = spec_review.start_bridge(prepared)
        holder = {"url": url, "token": token}
        outcome = []
        thread = threading.Thread(
            target=lambda: outcome.append(
                spec_review.serve_bridge(server, result, timeout, prepared)
            )
        )
        thread.start()
        return prepared, holder, thread, outcome

    def test_feedback_submit_returns_structured_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root)
            hashes = prepared["model"].hashes()
            status, body = post(holder["url"], {
                "token": holder["token"],
                "spec_digest": prepared["digest"],
                "action": "feedback",
                "items": [
                    {"id": "D1", "hash": hashes["D1"], "action": "change",
                     "comment": "不要改变公共 ImportSession API"}
                ],
                "global_feedback": "取消后后台任务允许继续，但 UI 不能显示成功。",
            })
            self.assertEqual(200, status)
            self.assertEqual("feedback", body["status"])
            self.assertEqual("PRD.md", body["spec"])
            self.assertEqual("D1", body["items"][0]["id"])
            thread.join(5)
            self.assertEqual("feedback", result[0]["status"])
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(state["accepted_digest"])

    def test_approve_records_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root)
            status, body = post(holder["url"], {
                "token": holder["token"],
                "spec_digest": prepared["digest"],
                "action": "approve",
                "items": [],
                "global_feedback": "",
            })
            self.assertEqual(200, status)
            self.assertEqual("accepted", body["status"])
            thread.join(5)
            self.assertEqual("accepted", result[0]["status"])
            feature_dir = root / ".scratch" / "import"
            state = json.loads(
                (feature_dir / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(prepared["digest"], state["accepted_digest"])
            self.assertEqual(
                sorted(prepared["model"].hashes()), sorted(state["accepted_items"])
            )
            self.assertEqual(
                prepared["digest"], spec_review.prd_digest(feature_dir / "spec-accepted.md")
            )

    def test_wrong_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.5)
            status, body = post(holder["url"], {
                "token": "not-the-token",
                "spec_digest": prepared["digest"],
                "action": "approve",
            })
            self.assertEqual(403, status)
            self.assertEqual("error", body["status"])
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])

    def test_non_ascii_token_is_rejected_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.5)
            status, body = post(holder["url"], {
                "token": "汉",
                "spec_digest": prepared["digest"],
                "action": "approve",
            })
            self.assertEqual(403, status)
            self.assertEqual("error", body["status"])
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])

    def test_foreign_host_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.5)
            connection = http.client.HTTPConnection(
                "127.0.0.1", port=int(re.search(r":(\d+)/", holder["url"]).group(1)), timeout=5
            )
            connection.request("GET", "/", headers={"Host": "evil.example"})
            response = connection.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            connection.close()
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])

    def test_bridge_data_script_is_valid_json(self):
        prepared_model = spec_review.parse_model(PRD)
        html_text = spec_review.review_html(
            "import", "PRD.md", PRD, "0" * 64, prepared_model, None, "full",
            bridge=True, token="tok", url="http://127.0.0.1:1/",
        )
        match = re.search(
            r'<script type="application/json" id="bridge-data">(.*?)</script>', html_text, re.S
        )
        self.assertTrue(match)
        payload = json.loads(match.group(1))
        self.assertEqual("tok", payload["token"])
        self.assertEqual(set(prepared_model.hashes()), set(payload["items"]))
        self.assertNotIn("&quot;", match.group(1))

    def test_stale_prd_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.5)
            prd.write_text(PRD + "\n## 后记\n\n- PRD 在页面打开后被修改。\n", encoding="utf-8")
            status, body = post(holder["url"], {
                "token": holder["token"],
                "spec_digest": prepared["digest"],
                "action": "approve",
            })
            self.assertEqual(409, status)
            self.assertEqual("stale_review", body["status"])
            self.assertEqual(prepared["digest"], body["expected_digest"])
            self.assertNotEqual(body["expected_digest"], body["current_digest"])
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])

    def test_one_successful_submit_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root)
            connection = http.client.HTTPConnection(
                "127.0.0.1", port=int(re.search(r":(\d+)/", holder["url"]).group(1)), timeout=5
            )
            payload = json.dumps({
                "token": holder["token"],
                "spec_digest": prepared["digest"],
                "action": "feedback",
                "items": [{"id": "S2", "action": "question", "comment": "能否与 S1 合并？"}],
            }).encode("utf-8")
            connection.request(
                "POST", "/submit", body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            response.read()
            connection.request(
                "POST", "/submit", body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            self.assertEqual(410, response.status)
            response.read()
            connection.close()
            thread.join(5)
            self.assertEqual("feedback", result[0]["status"])

    def test_timeout_returns_timeout_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.2)
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])


if __name__ == "__main__":
    unittest.main()
