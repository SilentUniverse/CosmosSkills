import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "preflight_receipt",
    ROOT / "engineering" / "tdd" / "scripts" / "preflight-receipt.py",
)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class PreflightReceiptTests(unittest.TestCase):
    def test_exact_tuple_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            preflight.record(
                path,
                cwd=".",
                action="npm run test:smoke",
                fingerprint="git=abc; lock=123; runtime=node-24; tools=playwright-1; services=none",
                observed="exit 0, 1 passed",
                evidence="artifacts/preflight.log",
            )
            hit = preflight.check(
                path,
                cwd=".",
                action="npm run test:smoke",
                fingerprint="git=abc; lock=123; runtime=node-24; tools=playwright-1; services=none",
            )
            self.assertIsNotNone(hit)
            self.assertEqual("exit 0, 1 passed", hit["observed"])

    def test_fingerprint_or_action_drift_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            preflight.record(
                path,
                cwd=".",
                action="pytest --collect-only -q",
                fingerprint="git=abc; lock=none",
                observed="exit 0",
                evidence="inline",
            )
            self.assertIsNone(
                preflight.check(
                    path,
                    cwd=".",
                    action="pytest --collect-only -q",
                    fingerprint="git=def; lock=none",
                )
            )
            self.assertIsNone(
                preflight.check(
                    path,
                    cwd=".",
                    action="pytest -q",
                    fingerprint="git=abc; lock=none",
                )
            )

    def test_corrupt_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                preflight.check(path, cwd=".", action="pytest", fingerprint="git=abc")

    def test_plan_lists_only_tuples_shared_by_multiple_ready_issues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)

            def body(status, action):
                return f"""---
contract_version: 2
type: issue
feature: demo
status: {status}
category: enhancement
blocked_by: []
created: 2026-08-30
---

## 验证设计

- 工作目录：`.`
- 环境指纹：`git=abc; lock=none; runtime=python-3; tools=unittest; services=none`
- P1 预检：`{action}` → passed；observed=exit 0；evidence=inline；checked=2026-08-30
"""

            (issues / "01-one.md").write_text(body("ready", "python -m unittest -q"), encoding="utf-8")
            (issues / "02-two.md").write_text(body("ready", "python -m unittest -q"), encoding="utf-8")
            (issues / "03-unique.md").write_text(body("ready", "python -m compileall ."), encoding="utf-8")
            (issues / "04-done.md").write_text(body("done", "python -m unittest -q"), encoding="utf-8")

            plan = preflight.duplicate_plan(root)
            self.assertEqual(1, len(plan["duplicates"]))
            duplicate = plan["duplicates"][0]
            self.assertEqual("miss", duplicate["status"])
            self.assertEqual(
                [".scratch/demo/issues/01-one.md", ".scratch/demo/issues/02-two.md"],
                duplicate["issues"],
            )

            receipt = root / duplicate["receipt"]
            preflight.record(
                receipt,
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                observed="exit 0",
                evidence="inline",
            )
            self.assertEqual("hit", preflight.duplicate_plan(root)["duplicates"][0]["status"])


if __name__ == "__main__":
    unittest.main()

    def test_stale_writer_lock_is_taken_over(self):
        import os
        import time

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            lock = path.with_name(path.name + ".lock")
            path.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("12345", encoding="ascii")
            ancient = time.time() - 600
            os.utime(lock, (ancient, ancient))
            preflight.record(
                path,
                cwd=".",
                action="npm run build",
                fingerprint="git=abc; lock=none",
                observed="exit 0",
                evidence="inline",
            )
            self.assertTrue(path.exists())
            self.assertFalse(lock.exists())

    def test_duplicate_plan_accepts_precalculated_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "search" / "issues"
            feature.mkdir(parents=True)
            fingerprint = "git=abc; lock=none; runtime=py; tools=pytest; services=none"
            for name in ("01-a.md", "02-b.md"):
                (feature / name).write_text(
                    "---\nstatus: ready\n---\n## 验证设计\n"
                    "- 工作目录：`.`\n- 环境指纹：`%s`\n"
                    "- P1 预检：`pytest --collect-only -q` → passed；observed=exit 0\n" % fingerprint,
                    encoding="utf-8",
                )
            scanned = preflight.issue_preflight_rows(root)
            self.assertEqual(2, len(scanned))
            self.assertEqual(
                preflight.duplicate_plan(root),
                preflight.duplicate_plan(root, rows=scanned),
            )
