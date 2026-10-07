import importlib.util
import http.client
import hashlib
import io
import json
import re
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
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


def accepted_spec_fixture(root, feature="import"):
    """Build historical accepted Spec data for gate tests without a public approval command."""
    prepared = spec_review.prepare_review(root, feature)
    state = spec_review.record_acceptance(
        prepared["state"], prepared["feature_dir"],
        prepared["feature_dir"] / prepared["prd_name"], prepared["digest"], prepared["model"],
    )
    spec_review.save_state(prepared["feature_dir"], state)
    return state


class ParseValidateTests(unittest.TestCase):
    def test_scope_heading_and_case_insensitive_refs_cannot_hide_design_changes(self):
        original = PRD + "\n## 范围\n- Export API\n"
        old = spec_review.parse_model(original)
        new = spec_review.parse_model(original.replace("## 范围", "## 不在本次范围内"))
        self.assertIn("section:scope", spec_review.classify_delta(new, old.hashes())["MODIFIED"])
        self.assertFalse(spec_review._design_matches(new, old, {"S1"}))
        lower = spec_review.parse_model(PRD.replace("Refs: R1 R2", "refs: R1 R2"))
        self.assertEqual({"R1", "R2"}, lower.refs_of("D1"))
        repeated = spec_review.parse_model(PRD.replace("Refs: R1 R2", "Refs: R1\nrefs: R2"))
        self.assertTrue(any("repeats Refs" in problem for problem in spec_review.validate_model(repeated)))

    def test_delta_covers_observations_and_transitive_slice_impact(self):
        base = PRD.replace("R1 R2 D1 | -", "D1 | -").replace("R1 D1 | S1", "D1 | S1")
        old = spec_review.parse_model(base)
        changed = spec_review.parse_model(base.replace("cancel → cancelled |", "cancel → success |"))
        delta = spec_review.classify_delta(changed, old.hashes())
        self.assertIn("R1", delta["MODIFIED"])
        self.assertTrue({"D1", "S1", "S2", "S3"} <= set(delta["AFFECTED"]))

    def test_delta_covers_global_review_content_and_unclassified_text(self):
        base = PRD + "\n## 不变量\n- C1 — 保留数据。\n## 端到端验证\n检查 cancelled。\n"
        for before, after in (("保留数据", "删除数据"), ("检查 cancelled", "跳过验证"),
                              ("导入取消后仍可能显示成功", "导入必须支持离线")):
            with self.subTest(before=before):
                delta = spec_review.classify_delta(spec_review.parse_model(base.replace(before, after)),
                                                   spec_review.parse_model(base).hashes())
                self.assertTrue(delta["MODIFIED"])
                self.assertIn("S2", delta["AFFECTED"])
        delta = spec_review.classify_delta(spec_review.parse_model(base + "\n## 外部约束\n必须离线。\n"),
                                           spec_review.parse_model(base).hashes())
        self.assertTrue(delta["MODIFIED"] or delta["ADDED"])
        self.assertIn("S1", delta["AFFECTED"])

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
    def test_delta_cannot_hide_previously_human_decision_by_changing_flags(self):
        old = spec_review.parse_model(PRD)
        text = PRD.replace("Door: one-way", "Door: two-way").replace("终态由 ImportSession 持有。", "允许丢弃取消终态。")
        new = spec_review.parse_model(text)
        page = spec_review.review_html("import", "PRD-v2.md", text, "a" * 64, new,
                                      spec_review.classify_delta(new, old.hashes()), "delta", False, baseline=old)
        self.assertIn('class="comment" data-id="D1"', page)
        self.assertIn("终态由 ImportSession 持有。", page)
        self.assertIn("允许丢弃取消终态。", page)

    def test_freeform_constraints_in_structured_sections_remain_visible(self):
        text = PRD.replace("- R1 —", "用户场景的补充权限限制。\n\n- R1 —", 1)
        text += "\n## 范围\n只允许读取选中的目录，禁止网络传输。\n\n## 不变量\n用户的数据不能被删除。\n"
        model = spec_review.parse_model(text)
        page = spec_review.review_html("import", "PRD.md", text, "a" * 64, model, None, "full", False)
        for constraint in ("用户场景的补充权限限制。", "只允许读取选中的目录，禁止网络传输。", "用户的数据不能被删除。"):
            self.assertIn(constraint, page)

    def test_delta_shows_changed_before_and_observation(self):
        original = PRD.replace("- R1 — 导入取消后必须进入 cancelled。", "- R1 — 导入取消后必须进入 cancelled。\n  Before：原始现状。")
        revised = original.replace("原始现状。", "修正现状。").replace("cancel → cancelled |", "显示取消原因 |")
        old, new = spec_review.parse_model(original), spec_review.parse_model(revised)
        page = spec_review.review_html("import", "PRD-v2.md", revised, "a" * 64, new,
                                      spec_review.classify_delta(new, old.hashes()), "delta", False, baseline=old)
        for evidence in ("原始现状。", "修正现状。", "cancel → cancelled", "显示取消原因"):
            self.assertIn(evidence, page)

    def test_review_keeps_human_contract_without_execution_mirrors(self):
        text = PRD.replace("| ImportSession |", "| internal_seam_only |")
        text = text.replace("## 测试决策", "### D2 — internal-selector\n\nRefs: R1\nDoor: two-way\nImplementation detail only.\n\n## 测试决策")
        text += "\n## 补充约束\n\n必须兼容旧客户端。\n<script>alert('unsafe')</script>\n"
        text += "\n## 风险\n- 首项风险。\n\n## 风险补充\n- 不得漏掉第二段约束。\n"
        text = text.replace("## 问题", "前言中的边界也要保留。\n\n## 问题", 1)
        model = spec_review.parse_model(text)
        page = spec_review.review_html("import", "PRD.md", text, "a" * 64,
                                      model, None, "full", False)
        self.assertEqual(1, page.count("导入取消后必须进入 cancelled。"))
        self.assertIn("cancel → cancelled", page)
        self.assertIn("State ownership", page)
        self.assertIn("必须兼容旧客户端。", page)
        self.assertIn("不得漏掉第二段约束。", page)
        self.assertIn("前言中的边界也要保留。", page)
        self.assertIn("&lt;script&gt;", page)
        for noise in ("完整需求", "切片表", "证明表", "internal_seam_only", "internal-selector", "state transition", "created: 2026"):
            self.assertNotIn(noise, page)
        self.assertIn('class="comment" data-id="D1"', page)
        self.assertIn('id="global-feedback"', page)
        self.assertNotIn("<details", page)

    def test_repeated_render_keeps_accepted_baseline_and_visible_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            accepted_spec_fixture(root)
            feature = root / ".scratch/import"
            draft = PRD.replace("version: 1", "version: 2\nsupersedes: PRD.md").replace(
                "- R1 — 导入取消后必须进入 cancelled。", "- R1 — 取消后保留终态且显示原因。")
            (feature / "PRD-v2.md").write_text(draft, encoding="utf-8")
            first = spec_review.prepare_review(root, "import")
            code, output, errors = run_cli("render", str(root), "import")
            self.assertEqual(0, code, errors)
            second = spec_review.prepare_review(root, "import")
            self.assertEqual(first["delta"], second["delta"])
            self.assertEqual(["R1"], second["delta"]["MODIFIED"])
            self.assertEqual({"D1", "S1", "S2", "S3"}, set(second["delta"]["AFFECTED"]))
            html_text = Path(json.loads(output)["html"]).read_text(encoding="utf-8")
            self.assertIn("已接受 · PRD.md", html_text)
            self.assertIn("导入取消后必须进入 cancelled", html_text)
            self.assertIn("取消后保留终态且显示原因", html_text)
            self.assertNotIn("<details", html_text)
            self.assertIn('id="R2"', html_text)
            self.assertLess(html_text.index('id="behavior"'), html_text.index('id="decide"'))
            self.assertNotIn('class="comment"', html_text[:html_text.index('id="decide"')])

    def test_all_content_and_feedback_fields_stay_visible_in_both_modes(self):
        text = PRD + "\n## 尚未明确\n- 是否显示取消原因？\n"
        model = spec_review.parse_model(text)
        for bridge in (False, True):
            for mode in ("full", "delta"):
                with self.subTest(bridge=bridge, mode=mode):
                    delta = spec_review.classify_delta(model, model.hashes()) if mode == "delta" else None
                    page = spec_review.review_html("import", "PRD.md", text, "a" * 64,
                                                   model, delta, mode, bridge)
                    self.assertNotIn("<details", page)
                    self.assertEqual({"D1", "Q1"}, set(re.findall(r'class="comment" data-id="([^"]+)"', page)))
                    self.assertEqual(1, page.count('id="global-feedback"'))
                    self.assertEqual(int(bridge), page.count('id="approve"'))
                    if bridge:
                        self.assertIn('>全部确定</button>', page)
                    else:
                        self.assertIn("静态预览仅收集反馈", page)
                    self.assertIn("需要你拍板", page)

    def test_legacy_render_hashes_require_full_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            run_cli("render", str(root), "import")
            feature = root / ".scratch/import"
            state = spec_review.load_state(feature)
            state["last_rendered_items"] = {"R1": "a" * 64}
            spec_review.save_state(feature, state)
            self.assertEqual("full", spec_review.prepare_review(root, "import")["mode"])

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
            html_text = Path(json.loads(output)["html"]).read_text(encoding="utf-8")
            self.assertIn("需要你拍板", html_text)
            self.assertNotIn("<svg", html_text)
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
                {"R1", "R2", "D1", "S1", "S2", "S3", "section:problem", "section:solution",
                 "section:scope", "section:acceptance", "section:context", "section:change"}, set(state["last_rendered_items"])
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
            self.assertEqual(4, payload["counts"]["AFFECTED"])
            self.assertEqual(7, payload["counts"]["UNCHANGED"])
            html_text = Path(json.loads(output)["html"]).read_text(encoding="utf-8")
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
            html_text = Path(json.loads(output)["html"]).read_text(encoding="utf-8")
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
            self.assertEqual(7, counts["UNCHANGED"])

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

    def test_render_names_pages_by_content_and_preserves_prior_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            code, output, errors = run_cli("render", str(root), "import", "--full")
            self.assertEqual(0, code, errors)
            first = Path(json.loads(output)["html"])
            content = first.read_bytes()
            self.assertEqual("spec-review-" + hashlib.sha256(content).hexdigest() + ".html", first.name)
            code, output, errors = run_cli("render", str(root), "import", "--full")
            self.assertEqual(0, code, errors)
            self.assertEqual(first, Path(json.loads(output)["html"]))
            prd.write_text(PRD + "\n## 范围\n只能读取本地选中的文件。\n", encoding="utf-8")
            code, output, errors = run_cli("render", str(root), "import", "--full")
            self.assertEqual(0, code, errors)
            self.assertNotEqual(first, Path(json.loads(output)["html"]))
            self.assertEqual(content, first.read_bytes())
            code, _, errors = run_cli("render", str(root), "import", "--full", "--out", str(first))
            self.assertEqual(1, code)
            self.assertIn("immutable", errors)
            self.assertEqual(content, first.read_bytes())


class AcceptGateTests(unittest.TestCase):
    def test_public_accept_command_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            with self.assertRaises(SystemExit) as result:
                run_cli("accept", str(root), "import")
            self.assertEqual(2, result.exception.code)
            self.assertFalse((root / ".scratch/import/spec-accepted.md").exists())
            self.assertFalse((root / ".scratch/import/spec-review.json").exists())

    def test_require_accepted_gates_on_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            code, output, errors = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("no recorded human acceptance", output)

            accepted = accepted_spec_fixture(root)
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(accepted["accepted_digest"], state["accepted_digest"])

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
            accepted_spec_fixture(root)
            run_cli("render", str(root), "import")
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertIsNotNone(state["accepted_digest"])

    def test_review_rejects_broken_anchors_before_listening(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root, PRD.replace("| S1 | state transition | R1 R2 D1 | - | key |",
                                            "| S1 | state transition | R1 R2 D1 | S2 | key |"))
            code, _, errors = run_cli("review", str(root), "import", "--no-browser", "--timeout", "0.1")
            self.assertEqual(1, code)
            self.assertIn("Depends cycle", errors)
            self.assertFalse((root / ".scratch/import/spec-accepted.md").exists())

    def test_acceptance_fixture_pins_snapshot_and_item_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            accepted_spec_fixture(root)
            feature_dir = root / ".scratch" / "import"
            state = json.loads(
                (feature_dir / "spec-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["D1", "R1", "R2", "S1", "S2", "S3", "section:acceptance", "section:change",
                 "section:context", "section:problem", "section:scope", "section:solution"], sorted(state["accepted_items"])
            )
            self.assertEqual("PRD.md", state["accepted_spec"])
            snapshot = feature_dir / "spec-acceptances" / (state["accepted_digest"] + ".md")
            self.assertTrue(snapshot.is_file())
            self.assertEqual(spec_review.prd_digest(snapshot), state["accepted_digest"])
            self.assertFalse((feature_dir / "spec-accepted.md").exists())

    def test_validate_reports_item_delta_after_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prd = plant_feature(root)
            accepted_spec_fixture(root)
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
            accepted_spec_fixture(root)
            prd.write_text(PRD + "\n## 后记\n\n- 一句改动。\n", encoding="utf-8")
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("changed since acceptance: section:context", output)

    def test_validate_flags_edited_or_missing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            accepted_spec_fixture(root)
            state = json.loads(
                (root / ".scratch" / "import" / "spec-review.json").read_text(encoding="utf-8")
            )
            snapshot = root / ".scratch" / "import" / "spec-acceptances" / (state["accepted_digest"] + ".md")
            snapshot.write_text("被篡改的快照。\n", encoding="utf-8")
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("accepted snapshot no longer matches accepted_digest", output)
            snapshot.unlink()
            code, output, _ = run_cli("validate", str(root), "import", "--require-accepted")
            self.assertEqual(1, code)
            self.assertIn("the accepted snapshot is missing", output)

    def test_render_preserves_acceptance_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            accepted_spec_fixture(root)
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
                prepared["digest"],
                spec_review.prd_digest(
                    feature_dir / "spec-acceptances" / (prepared["digest"] + ".md")
                ),
            )

    def test_failed_persistence_returns_error_and_can_retry_same_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root)
            payload = {"token": holder["token"], "spec_digest": prepared["digest"],
                       "action": "approve", "items": [], "global_feedback": ""}
            try:
                with mock.patch.object(spec_review, "save_state", side_effect=OSError("disk full")):
                    status, body = post(holder["url"], payload)
                self.assertEqual(500, status)
                self.assertEqual("error", body["status"])
                self.assertIn("disk full", body["message"])
                state = spec_review.load_state(root / ".scratch/import")
                self.assertIsNone(state["accepted_digest"])
                self.assertFalse(result)
                status, body = post(holder["url"], payload)
                self.assertEqual(200, status)
                self.assertEqual("accepted", body["status"])
                state = spec_review.load_state(root / ".scratch/import")
                self.assertEqual(prepared["digest"], state["accepted_digest"])
                self.assertRegex(state["accepted_event"], r"^[0-9a-f]{64}$")
            finally:
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual("accepted", result[0]["status"])
            self.assertEqual(1, len(list((root / ".scratch/import/spec-review-events").glob("*.json"))))

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

    def test_identical_submit_is_idempotent_and_conflicting_decision_is_rejected(self):
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
            self.assertEqual(200, response.status)
            self.assertEqual("feedback", json.loads(response.read().decode("utf-8"))["status"])
            changed = json.loads(payload.decode("utf-8"))
            changed["items"][0]["comment"] = "另一条审核意见"
            connection.request("POST", "/submit", body=json.dumps(changed).encode("utf-8"),
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(409, response.status)
            response.read()
            connection.close()
            thread.join(5)
            self.assertEqual("feedback", result[0]["status"])
            events = list((root / ".scratch/import/spec-review-events").glob("*.json"))
            self.assertEqual(1, len(events))

    def test_timeout_returns_timeout_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_feature(root)
            prepared, holder, thread, result = self.bridge(root, timeout=0.2)
            thread.join(5)
            self.assertEqual("timeout", result[0]["status"])

    def test_candidate_review_page_renders_bound_spec_text(self):
        fixed = {"digest": "a" * 64, "spec_digest": "b" * 64, "scope": "Fixture delivery"}
        page = spec_review.candidate_review_page(
            fixed, "# Spec\naccepted <body> & bytes", "", '{"token":"t"}'
        )
        self.assertIn("接受的 Spec", page)
        self.assertIn("# Spec", page)
        self.assertIn("accepted &lt;body&gt; &amp; bytes", page)
        self.assertIn("b" * 64, page)

    def test_candidate_review_page_omits_spec_block_without_spec(self):
        page = spec_review.candidate_review_page(
            {"digest": "a" * 64, "spec_digest": None}, None, "", '{"token":"t"}'
        )
        self.assertNotIn("接受的 Spec", page)
        self.assertIn("固定候选审核", page)


if __name__ == "__main__":
    unittest.main()
