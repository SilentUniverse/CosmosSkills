import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workflow_state", ROOT / "engineering" / "workflow-state.py"
)
assert SPEC and SPEC.loader
workflow_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_state)


def plant_issue(root, slug, *, status="done", category="enhancement", refines="", archive=False):
    directory = root / ".scratch" / "demo" / "issues"
    if archive:
        directory /= "archive"
    directory.mkdir(parents=True, exist_ok=True)
    refines_line = f"refines: {refines}\n" if refines else ""
    (directory / f"{slug}.md").write_text(
        f"""---
type: issue
feature: demo
status: {status}
category: {category}
{refines_line}created: 2026-09-03
---

## 做什么（What to build）

Deliver {slug} behavior.

## Comments

### 完成 — 2026-09-03

- 验收：#1 → delivered
""",
        encoding="utf-8",
    )


class WorkflowStateTests(unittest.TestCase):
    def test_inspect_folds_done_redo_across_live_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            plant_issue(root, "02-detail", category="detail", refines="01-base", archive=True)
            plant_issue(root, "03-redo-base", category="redo", refines="01-base", archive=True)
            plant_issue(root, "04-open", status="ready")

            state = workflow_state.inspect_feature(root, "demo")

            self.assertEqual(["02-detail", "03-redo-base"], [item["slug"] for item in state["delivered"]])
            self.assertEqual(["01-base"], state["replaced"])

    def test_json_projection_has_source_digest_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")

            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            output = io.StringIO()
            with redirect_stdout(output):
                code = workflow_state.main(
                    ["workflow-state.py", "inspect", str(root), "demo", "--format", "json"]
                )
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            payload = json.loads(output.getvalue())

            self.assertEqual(0, code)
            self.assertEqual(before, after)
            self.assertEqual(64, len(payload["source_digest"]))
            self.assertEqual(64, len(payload["delivered"][0]["digest"]))
            self.assertEqual(".scratch/demo/issues/01-base.md", payload["delivered"][0]["path"])
            self.assertFalse((root / ".scratch" / "demo" / "SUMMARY.md").exists())

    def test_human_projection_shows_effective_reality_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            plant_issue(root, "03-redo-base", category="redo", refines="01-base", archive=True)
            output = io.StringIO()

            with redirect_stdout(output):
                code = workflow_state.main(
                    ["workflow-state.py", "inspect", str(root), "demo", "--format", "human"]
                )

            self.assertEqual(0, code)
            self.assertIn("03-redo-base", output.getvalue())
            self.assertNotIn("01-base —", output.getvalue())

    def test_gc_only_removes_closed_transient_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            feature = root / ".scratch" / "demo"
            receipt = feature / "preflight-receipt.json"
            ledger = feature / "wave-ledger.json"
            receipt.write_text("{}", encoding="utf-8")
            ledger.write_text(
                json.dumps({"waves": [{"dispatched": ["01-base"], "closed": {"01-base": "green"}}]}),
                encoding="utf-8",
            )

            preview = workflow_state.gc_feature(root, "demo")
            applied = workflow_state.gc_feature(root, "demo", apply=True)

            self.assertEqual(
                [".scratch/demo/preflight-receipt.json", ".scratch/demo/wave-ledger.json"],
                preview["candidates"],
            )
            self.assertEqual(preview["candidates"], applied["removed"])
            self.assertFalse(receipt.exists())
            self.assertFalse(ledger.exists())

    def test_gc_refuses_while_ready_work_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-open", status="ready")
            receipt = root / ".scratch" / "demo" / "preflight-receipt.json"
            receipt.write_text("{}", encoding="utf-8")

            plan = workflow_state.gc_feature(root, "demo", apply=True)

            self.assertTrue(plan["ready"])
            self.assertEqual([], plan["candidates"])
            self.assertTrue(receipt.exists())

    def test_packet_projects_one_issue_without_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-base.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "blocked_by: [09-other, 10-x]\ntest_paths: [tests/test_a.py]\n"
                "---\n\n## 做什么（What to build）\n\nDeliver base behavior.\n\n"
                "## 相关面（Read contract）\n\n"
                "- invariants: CODEBASE.md 的 billing 不变量块\n"
                "- adr: 0007-refund-ordering\n"
                "- neighbors: src/billing/ledger.py\n\n"
                "## 前置依赖（Blocked by）\n\n- 无\n",
                encoding="utf-8",
            )
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            packet = workflow_state.issue_packet(root, "demo", "01-base")

            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual("ready", packet["status"])
            self.assertEqual(["09-other", "10-x"], packet["blocked_by"])
            self.assertEqual(["tests/test_a.py"], packet["test_paths"])
            self.assertEqual(
                [
                    "- invariants: CODEBASE.md 的 billing 不变量块",
                    "- adr: 0007-refund-ordering",
                    "- neighbors: src/billing/ledger.py",
                ],
                packet["context"],
            )
            self.assertEqual(64, len(packet["digest"]))
            self.assertEqual(".scratch/demo/issues/01-base.md", packet["source"])

    def test_packet_parses_block_style_frontmatter_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-block.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "test_paths:\n  - tests/test_a.py\n  - tests/test_b.py\n"
                "---\n\n## 做什么（What to build）\n\nDeliver.\n",
                encoding="utf-8",
            )

            packet = workflow_state.issue_packet(root, "demo", "01-block")

            self.assertEqual(["tests/test_a.py", "tests/test_b.py"], packet["test_paths"])

    def test_close_flips_ready_with_record_and_reports_gc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            path = issue_dir / "01-base.md"
            path.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 做什么（What to build）\n\nDeliver base.\n\n"
                "## Comments\n\n### 完成 — 2026-09-03\n\n- 验收：#1 → tests/test_a.py::test_base\n",
                encoding="utf-8",
            )
            receipt = root / ".scratch" / "demo" / "preflight-receipt.json"
            receipt.write_text("{}", encoding="utf-8")

            result = workflow_state.close_issue(root, "demo", "01-base")

            self.assertEqual("done", result["status"])
            self.assertEqual([".scratch/demo/preflight-receipt.json"], result["gc_candidates"])
            self.assertIn("status: done", path.read_text(encoding="utf-8"))
            self.assertEqual([], list(issue_dir.glob("*.tmp.*")))

    def test_close_rejects_missing_record_and_non_ready_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            bare = issue_dir / "01-bare.md"
            bare.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 做什么（What to build）\n\nDeliver.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "### 完成"):
                workflow_state.close_issue(root, "demo", "01-bare")

            finished = issue_dir / "02-done.md"
            finished.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: done\n"
                "---\n\n## Comments\n\n### 完成 — 2026-09-03\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "requires status: ready"):
                workflow_state.close_issue(root, "demo", "02-done")

            self.assertIn("status: ready", bare.read_text(encoding="utf-8"))

    def test_stats_reports_timing_and_card_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / ".scratch" / "demo" / "receipts"
            receipts.mkdir(parents=True)
            for name, duration in (("a.json", 0.2), ("b.json", 0.4), ("c.json", 2.0)):
                (receipts / name).write_text(
                    json.dumps({"scope": "targeted", "outcome": "pass", "duration_seconds": duration}),
                    encoding="utf-8",
                )
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-old.md").write_text(
                "---\ncontract_version: 2\ntype: issue\nfeature: demo\nstatus: done\n---\nbody\n",
                encoding="utf-8",
            )
            (issues / "02-lean.md").write_text(
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: ready\n---\nbody\n",
                encoding="utf-8",
            )

            report = workflow_state.stats(root)

            self.assertEqual(3, report["timing"]["targeted"]["count"])
            self.assertEqual(0.4, report["timing"]["targeted"]["p50"])
            self.assertEqual(2.0, report["timing"]["targeted"]["p95"])
            self.assertEqual({"v2": 1, "v3": 1}, report["cards"])
            self.assertEqual(
                report["card_bytes"]["v2"], len(
                    (issues / "01-old.md").read_text(encoding="utf-8").encode("utf-8")
                )
            )

    def test_close_verifies_v3_receipt_before_flipping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            path = issue_dir / "01-v3.md"
            body = (
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 验收标准（Acceptance Criteria）\n\n- [ ] works\n\n"
                "## Comments\n\n### 完成 — 2026-09-03\n\n"
                "- receipt: .scratch/demo/receipts/01-v3-targeted.json；AC 1 pass\n"
                "- 审查：pass\n"
            )
            path.write_text(body, encoding="utf-8")
            receipts = root / ".scratch" / "demo" / "receipts"
            receipts.mkdir(parents=True)
            receipt = receipts / "01-v3-targeted.json"
            receipt.write_text('{"outcome": "fail"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outcome 'fail' != pass"):
                workflow_state.close_issue(root, "demo", "01-v3")
            self.assertIn("status: ready", path.read_text(encoding="utf-8"))

            receipt.write_text('{"outcome": "pass"}', encoding="utf-8")
            result = workflow_state.close_issue(root, "demo", "01-v3")
            self.assertEqual("done", result["status"])


if __name__ == "__main__":
    unittest.main()
