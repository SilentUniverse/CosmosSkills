import importlib.util
import json
import shlex
import sys
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

SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "test_supervisor_for_preflight",
    ROOT / "engineering" / "tdd" / "scripts" / "test-supervisor.py",
)
assert SUPERVISOR_SPEC and SUPERVISOR_SPEC.loader
supervisor = importlib.util.module_from_spec(SUPERVISOR_SPEC)
SUPERVISOR_SPEC.loader.exec_module(supervisor)


def passing_execution(root, action):
    receipt = root / ".scratch" / "demo" / "execution-receipt.json"
    result, code = supervisor.run_command(
        shlex.split(action),
        cwd=root,
        receipt=receipt,
        log=root / ".scratch" / "demo" / "execution.log",
        timeout=5,
        grace=0.1,
        scope="preflight",
    )
    if code != 0:
        raise AssertionError(result)
    return receipt


class PreflightReceiptTests(unittest.TestCase):
    def test_exact_tuple_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipt.json"
            action = shlex.join([sys.executable, "-c", "print('ok')"])
            preflight.record(
                path,
                cwd=str(root),
                action=action,
                fingerprint="git=abc; lock=123; runtime=node-24; tools=playwright-1; services=none",
                execution_receipt=passing_execution(root, action),
            )
            hit = preflight.check(
                path,
                cwd=str(root),
                action=action,
                fingerprint="git=abc; lock=123; runtime=node-24; tools=playwright-1; services=none",
            )
            self.assertIsNotNone(hit)
            self.assertEqual("exit 0", hit["observed"])

    def test_profile_action_resolves_via_verifier_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            feature.mkdir(parents=True)
            command = shlex.join([sys.executable, "-c", "print('ok')"])
            (feature / "verifier.json").write_text(
                json.dumps({"commands": {"scoped": command}}), encoding="utf-8"
            )
            path = feature / "preflight-receipt.json"
            preflight.record(
                path,
                cwd=str(root),
                action="profile:scoped",
                fingerprint="git=abc; lock=none",
                execution_receipt=passing_execution(root, command),
            )
            hit = preflight.check(
                path,
                cwd=str(root),
                action="profile:scoped",
                fingerprint="git=abc; lock=none",
            )
            self.assertIsNotNone(hit)

    def test_v3_cards_derive_rows_from_verifier_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-lean.md").write_text(
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 验证设计（Verification Design）\n\n"
                "- profile: verifier.json\n"
                "- P1 预检：`profile:scoped` → passed；observed=exit 0；evidence=inline；checked=2026-09-03\n",
                encoding="utf-8",
            )
            (root / ".scratch" / "demo" / "verifier.json").write_text(
                json.dumps(
                    {
                        "cwd": ".",
                        "fingerprint": "git=abc; lock=none; runtime=py-3.9; tools=pytest; services=none",
                        "commands": {"scoped": "pytest -q"},
                    }
                ),
                encoding="utf-8",
            )

            rows = preflight.issue_preflight_rows(root)

            self.assertEqual(1, len(rows))
            self.assertEqual("profile:scoped", rows[0]["action"])
            self.assertEqual(
                "git=abc; lock=none; runtime=py-3.9; tools=pytest; services=none",
                rows[0]["fingerprint"],
            )

    def test_profile_action_with_unknown_name_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            feature.mkdir(parents=True)
            (feature / "verifier.json").write_text(
                json.dumps({"commands": {"scoped": "pytest -q"}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "no command 'missing'"):
                preflight.record(
                    feature / "preflight-receipt.json",
                    cwd=str(root),
                    action="profile:missing",
                    fingerprint="git=abc; lock=none",
                    execution_receipt=feature / "execution-receipt.json",
                )

    def test_fingerprint_or_action_drift_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipt.json"
            action = shlex.join([sys.executable, "-c", "pass"])
            preflight.record(
                path,
                cwd=str(root),
                action=action,
                fingerprint="git=abc; lock=none",
                execution_receipt=passing_execution(root, action),
            )
            self.assertIsNone(
                preflight.check(
                    path,
                    cwd=str(root),
                    action=action,
                    fingerprint="git=def; lock=none",
                )
            )
            self.assertIsNone(
                preflight.check(
                    path,
                    cwd=str(root),
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

            unittest_action = shlex.join([sys.executable, "-m", "unittest", "-q"])
            (issues / "01-one.md").write_text(body("ready", unittest_action), encoding="utf-8")
            (issues / "02-two.md").write_text(body("ready", unittest_action), encoding="utf-8")
            (issues / "03-unique.md").write_text(body("ready", "python -m compileall ."), encoding="utf-8")
            (issues / "04-done.md").write_text(body("done", unittest_action), encoding="utf-8")

            plan = preflight.duplicate_plan(root)
            self.assertEqual(1, len(plan["duplicates"]))
            duplicate = plan["duplicates"][0]
            self.assertEqual("miss", duplicate["status"])
            self.assertEqual(
                [".scratch/demo/issues/01-one.md", ".scratch/demo/issues/02-two.md"],
                duplicate["issues"],
            )

            receipt = root / duplicate["receipt"]
            execution = passing_execution(root, duplicate["action"])
            preflight.record(
                receipt,
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                execution_receipt=execution,
            )
            self.assertEqual("hit", preflight.duplicate_plan(root)["duplicates"][0]["status"])


    def test_stale_writer_lock_is_taken_over(self):
        import os
        import time

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipt.json"
            action = shlex.join([sys.executable, "-c", "pass"])
            lock = path.with_name(path.name + ".lock")
            path.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("12345", encoding="ascii")
            ancient = time.time() - 600
            os.utime(lock, (ancient, ancient))
            preflight.record(
                path,
                cwd=str(root),
                action=action,
                fingerprint="git=abc; lock=none",
                execution_receipt=passing_execution(root, action),
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


if __name__ == "__main__":
    unittest.main()
