"""Architecture constraints that keep engineering validators independent of execution."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RETIRED = {"workflow_batch", "workflow_runtime", "workflow_jobs", "workflow_managed",
           "workflow_incremental", "workflow_members", "workflow_resources", "checkpoint_store", "process_tree"}


class WorkflowContractTests(unittest.TestCase):
    def test_retired_runtime_is_not_shipped_or_imported(self):
        for name in RETIRED:
            self.assertFalse((ROOT / "workflow" / (name + ".py")).exists(), name)
        for path in (ROOT / "workflow").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], RETIRED, str(path))
                elif isinstance(node, ast.Import):
                    for name in node.names:
                        self.assertNotIn(name.name.split(".")[0], RETIRED, str(path))

    def test_continuation_skills_have_no_recovery_runtime(self):
        for name in ("handoff", "resume"):
            self.assertTrue((ROOT / "workflow" / name / "SKILL.md").is_file())
            self.assertFalse(list((ROOT / "workflow" / name).rglob("*.py")))

    def test_engineering_rules_keep_native_execution_ownership(self):
        text = (ROOT / "workflow/tdd/FULL-SUITE.md").read_text()
        self.assertIn("evidence.py", text)
        for name in ("batch-run", "drain-wave.py", "test-supervisor.py"):
            self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
