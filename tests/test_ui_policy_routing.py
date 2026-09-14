import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UIPolicyRoutingTests(unittest.TestCase):
    def test_non_ui_cli_runs_without_ui_reads_imports_or_processes(self):
        wrapper = """
import os, runpy, sys
ui_modules = {'playwright', 'selenium', 'browser_use', 'workflow_ui'}
ui_executables = {'node', 'npm', 'npx', 'playwright', 'chromium', 'chrome', 'firefox'}
def guard(event, args):
    if event == 'import' and str(args[0]).split('.')[0] in ui_modules:
        raise AssertionError('non-UI path imported a UI module')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        if os.path.basename(os.fsdecode(args[0])) in {'UI-TESTING.md', 'EXPERIENCE-RUBRIC.md', 'workflow_ui.py', 'playwright-reporter.cjs'}:
            raise AssertionError('non-UI path loaded UI instructions')
    if event == 'subprocess.Popen':
        program = args[0] if args[0] is not None else (args[1][0] if isinstance(args[1], list) and args[1] else args[1])
        name = os.path.basename(os.fsdecode(program)).lower().removesuffix('.exe')
        if name in ui_executables:
            raise AssertionError('non-UI path launched a UI executable')
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        with tempfile.TemporaryDirectory(prefix="cosmos non ui ") as directory:
            root = Path(directory).resolve()
            issue = root / ".scratch/demo/issues/01-work.md"
            issue.parent.mkdir(parents=True)
            issue.write_text("---\ntype: issue\nfeature: demo\nstatus: ready\n"
                             "touches: [src]\ntest_paths: [tests/test_cli.py]\nblocked_by: []\n---\n"
                             "## 做什么\nReturn a CLI result.\n", encoding="utf-8")
            state = str(ROOT / "workflow/workflow-state.py")
            supervisor = str(ROOT / "workflow/tdd/scripts/test-supervisor.py")
            for command in ([state, "survey", str(root), "--format", "json"],
                            [state, "start", str(root), "demo", "01-work"],
                            [supervisor, "--cwd", str(root), "--receipt", str(root / ".scratch/result.json"),
                             "--log", str(root / ".scratch/tmp/test.log"), "--scope", "targeted",
                             "--timeout", "5", "--", sys.executable, "-c", "print('1 passed')"]):
                result = subprocess.run([sys.executable, "-B", "-c", wrapper, *command], cwd=root,
                                        capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual("pass", json.loads((root / ".scratch/result.json").read_text())["outcome"])
            self.assertFalse(list(root.rglob("experience-contract.json")))
            self.assertFalse(list(root.rglob("package.json")))
            managed = root / "managed"
            managed.mkdir()
            (managed / "app.py").write_text("print(42)\n", encoding="utf-8")
            plan = {"schema_version": 3, "members": [], "inputs": ["app.py"], "checks": ["result"],
                    "requirements": [{"id": "answer", "body": "Return 42 without UI work", "checks": ["result"]}],
                    "jobs": {"result": {"argv": ["{python}", "app.py"], "timeout": 5,
                                        "result": {"kind": "predicate", "stdout_equals": "42"}}},
                    "milestones": [{"id": "final", "purpose": "final", "members": [], "required_checks": ["result"]}],
                    "budget": {"dispatches": 1}}
            plan_path = managed / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            def invoke(*args):
                process = subprocess.run([sys.executable, "-B", "-c", wrapper, state, *map(str, args)], cwd=managed,
                                         capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(0, process.returncode, process.stdout + process.stderr)
                return json.loads(process.stdout)
            opened = invoke("batch-open", managed, "--plan", plan_path, "--request-id", "no-ui")
            closed = invoke("batch-run", managed, "--batch", opened["batch_id"])
            self.assertEqual("closed", closed["status"])


if __name__ == "__main__":
    unittest.main()
