import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow_projections", ROOT / "workflow/workflow-state.py")
workflow_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_state)


class WorkflowProjectionTests(unittest.TestCase):
    def issue(self, root, slug, *, status="done", feature="demo", archive=False, refines=None):
        directory = root / ".scratch" / feature / "issues"
        if archive:
            directory /= "archive"
        directory.mkdir(parents=True, exist_ok=True)
        lineage = "category: redo\nrefines: %s\n" % refines if refines else "category: enhancement\n"
        path = directory / (slug + ".md")
        path.write_text("""---
contract_version: 2
type: issue
feature: %s
status: %s
%sblocked_by: []
created: 2026-09-23
---
## 做什么
Verify the public output.
## 验收标准
- [ ] Public output is correct.
## 验证设计
- 工作目录：`.`
- 环境指纹：`git=fixture; lock=none; runtime=python; tools=unittest; services=none`
- 前置条件：`fixtures=ready; services=none; permissions=local; network=off`
- 准备动作：`无（已就绪）`
- #1 → `python -m unittest tests.test_fixture`
## Comments
### 完成 — 2026-09-23
- 验收：#1 → reported complete
""" % (feature, status, lineage), encoding="utf-8")
        return path

    def retain_legacy_proof(self, root, issue):
        directory = root / ".scratch/demo/receipts"
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / (issue.stem + ".log")
        log.write_bytes(b"fixture native result\n")
        receipt = directory / (issue.stem + ".json")
        receipt.write_text(json.dumps({
            "schema_version": 1, "argv_style": "posix", "scope": "targeted",
            "outcome": "pass", "exit_code": 0, "cwd": ".",
            "argv": ["python", "-m", "unittest", "tests.test_fixture"],
            "log": log.relative_to(root).as_posix(),
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        with issue.open("a", encoding="utf-8") as stream:
            stream.write("- receipt: %s; AC 1\n" % receipt.relative_to(root).as_posix())
        return log

    def snapshot(self, root):
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def test_all_projections_distinguish_retained_proof_from_invalid_history_without_writing(self):
        for corruption in ("missing", "changed"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                proven = self.issue(root, "01-proven", archive=True)
                self.retain_legacy_proof(root, proven)
                damaged = self.issue(root, "02-damaged")
                log = self.retain_legacy_proof(root, damaged)
                self.issue(root, "03-narrative")
                if corruption == "missing":
                    log.unlink()
                else:
                    log.write_bytes(b"changed result\n")
                before = self.snapshot(root)

                frontier = workflow_state.survey_states(root, features=["demo"])[0]
                history = workflow_state.inspect_feature(root, "demo")
                statistics = workflow_state.stats(root)

                self.assertEqual(["01-proven"], frontier["done"])
                self.assertEqual(["01-proven"], [row["slug"] for row in history["delivered"]])
                for projection in (frontier, history):
                    self.assertEqual(2, projection["counts"]["invalid"])
                    self.assertEqual(["02-damaged", "03-narrative"], [row["slug"] for row in projection["invalid"]])
                    self.assertTrue(all(row["reason"] for row in projection["invalid"]))
                    human = workflow_state.render_human(projection)
                    self.assertIn("02-damaged — 完成证明无效", human)
                    self.assertIn("03-narrative — 完成证明无效", human)
                self.assertEqual({"done": 1, "invalid": 2}, statistics["completion"])
                self.assertEqual(["demo", "demo"], [row["feature"] for row in statistics["invalid"]])
                self.assertEqual(before, self.snapshot(root))

    def test_unproven_redo_does_not_replace_proven_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = self.issue(root, "01-parent")
            self.retain_legacy_proof(root, parent)
            self.issue(root, "02-redo", refines="01-parent")

            projection = workflow_state.inspect_feature(root, "demo")

            self.assertEqual(["01-parent"], [row["slug"] for row in projection["delivered"]])
            self.assertEqual([], projection["replaced"])
            self.assertEqual(["02-redo"], [row["slug"] for row in projection["invalid"]])

    def test_start_and_scoped_survey_do_not_validate_unrelated_completed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.issue(root, "01-ready", status="ready")
            self.issue(root, "01-unrelated", feature="other")

            with mock.patch.object(workflow_state, "validate_completion", side_effect=AssertionError("unrelated proof scan")):
                self.assertTrue(workflow_state.start_issue(root, "demo", "01-ready")["admitted"])
                projection = workflow_state.survey_states(root, features=["demo"])[0]

            self.assertEqual(["01-ready"], [row["slug"] for row in projection["ready"]])
            self.assertEqual([], projection["invalid"])
