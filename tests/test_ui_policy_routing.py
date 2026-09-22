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
            issue = root / ".scratch/demo/issues/01-work.md"
            issue.parent.mkdir(parents=True)
            issue.write_text("""---
contract_version: 2
type: issue
feature: demo
status: ready
category: enhancement
touches: [src]
test_paths: []
blocked_by: []
created: 2026-09-22
---
## 做什么
Return the interpreter version through the CLI.
## 验收标准
- [ ] Print the interpreter version successfully.
## 验证设计
- 接缝：CLI
- 工作目录：`.`
- 环境指纹：`git=no-vcs; lock=none; runtime=python; tools=stdlib; services=none`
- 前置条件：`fixtures=none; services=none; permissions=local; network=off`
- 准备动作：`无（已就绪）`
- P1 预检：`python --version` → passed；observed=exit 0；evidence=inline fixture；checked=2026-09-22
- #1 → `python --version`；预检：P1；预期证据：version text and exit 0
## Comments
""", encoding="utf-8")
            state = str(ROOT / "workflow/workflow-state.py")
            evidence = str(ROOT / "workflow/evidence.py")
            original = issue.read_bytes()
            for command in ([state, "survey", str(root), "--format", "json"],
                            [state, "start", str(root), "demo", "01-work"],
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
