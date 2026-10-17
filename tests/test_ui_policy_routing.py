import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NON_UI_FEATURE = """---
type: feature
feature: demo
created: 2026-09-22
---

## 目标与边界
- 问题：the CLI hides the interpreter version
- 结果：the CLI prints it

## 需求
- R1 — Print the interpreter version.

## 共享验证
```json
{"cwd": ".", "environment": {"runtime": "python"}, "prepare": "无（已就绪）",
 "commands": {"version": "python --version"}}
```
- 预检 version：`python --version` → passed；evidence=inline fixture；checked=2026-09-22

## 任务
### T1 — print the version
- status: ready
- covers: R1
- 做什么：Return the interpreter version through the CLI.
- [ ] Print the interpreter version successfully. → `version`
"""


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
        name = os.path.basename(os.fsdecode(program)).lower()
        for suffix in ('.exe', '.cmd', '.bat'):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        if name in ui_executables:
            raise AssertionError('non-UI path launched a UI executable')
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        with tempfile.TemporaryDirectory(prefix="cosmos non ui ") as directory:
            root = Path(directory).resolve()
            issue = root / ".scratch/demo/FEATURE.md"
            issue.parent.mkdir(parents=True)
            issue.write_text(NON_UI_FEATURE, encoding="utf-8")
            state = str(ROOT / "workflow/workflow-state.py")
            evidence = str(ROOT / "workflow/evidence.py")
            original = issue.read_bytes()
            for command in ([state, "survey", str(root), "--format", "json"],
                            [state, "start", str(root), "demo", "T1"],
                            [evidence, "--help"]):
                result = subprocess.run([sys.executable, "-B", "-c", wrapper, *command], cwd=root,
                                        capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(original, issue.read_bytes())
            self.assertFalse(list(root.rglob("experience-contract.json")))
            self.assertFalse(list(root.rglob("package.json")))
            self.assertFalse((root / ".scratch/batches").exists())


if __name__ == "__main__":
    unittest.main()
