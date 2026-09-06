import importlib.util
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
            stored = next(iter(json.loads(path.read_text(encoding="utf-8"))["entries"].values()))
            self.assertEqual(
                {"evidence", "evidence_sha256"},
                set(stored),
            )

    def test_hit_revalidates_the_execution_receipt_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipt.json"
            action = shlex.join([sys.executable, "-c", "print('ok')"])
            execution = passing_execution(root, action)
            fingerprint = "git=abc; lock=none; runtime=python; tools=unittest; services=none"
            preflight.record(
                path,
                cwd=str(root),
                action=action,
                fingerprint=fingerprint,
                execution_receipt=execution,
            )
            self.assertIsNotNone(
                preflight.check(path, cwd=str(root), action=action, fingerprint=fingerprint)
            )

            execution.write_text("{}\n", encoding="utf-8")

            self.assertIsNone(
                preflight.check(path, cwd=str(root), action=action, fingerprint=fingerprint)
            )

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
            digest = "d" * 64
            with self.assertRaisesRegex(ValueError, "requires --verifier-digest"):
                preflight.record(
                    path,
                    cwd=str(root),
                    action="profile:scoped",
                    fingerprint="git=abc; lock=none",
                    execution_receipt=passing_execution(root, command),
                )
            preflight.record(
                path,
                cwd=str(root),
                action="profile:scoped",
                fingerprint="git=abc; lock=none",
                execution_receipt=passing_execution(root, command),
                verifier_digest=digest,
            )
            hit = preflight.check(
                path,
                cwd=str(root),
                action="profile:scoped",
                fingerprint="git=abc; lock=none",
                verifier_digest=digest,
            )
            self.assertIsNotNone(hit)

    def test_v3_cards_derive_rows_from_verifier_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            body = (
                "---\ncontract_version: 3\nverifier_schema: 2\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 验证设计（Verification Design）\n\n"
                "- profile: verifier.json\n"
                "- P1 预检：`profile:scoped` → passed；observed=exit 0；evidence=inline；checked=2026-09-03\n"
            )
            (issues / "01-lean.md").write_text(body, encoding="utf-8")
            (issues / "02-lean.md").write_text(body, encoding="utf-8")
            profile = root / ".scratch" / "demo" / "verifier.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "cwd": ".",
                        "fingerprint": "git=abc; lock=none; runtime=py-3.9; tools=pytest; services=none",
                        "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                        "prepare": "无（已就绪）",
                        "commands": {"scoped": "pytest -q"},
                        "completion_commands": ["scoped"],
                    }
                ),
                encoding="utf-8",
            )
            original_read_bytes = Path.read_bytes
            profile_reads = []

            def tracked_read_bytes(path):
                if path.resolve() == profile.resolve():
                    profile_reads.append(path)
                return original_read_bytes(path)

            with mock.patch.object(Path, "read_bytes", tracked_read_bytes):
                rows = preflight.issue_preflight_rows(root)

            self.assertEqual(2, len(rows))
            self.assertEqual(1, len(profile_reads))
            self.assertEqual("pytest -q", rows[0]["action"])
            self.assertEqual("profile:scoped", rows[0]["declared_action"])
            self.assertEqual(64, len(rows[0]["verifier_digest"]))
            self.assertEqual(
                "git=abc; lock=none; runtime=py-3.9; tools=pytest; services=none",
                rows[0]["fingerprint"],
            )
            duplicate = preflight.duplicate_plan(root, rows=rows)["duplicates"][0]
            self.assertEqual("profile:scoped", duplicate["declared_action"])
            self.assertEqual(rows[0]["verifier_digest"], duplicate["verifier_digest"])

    def test_profile_or_card_deviation_changes_preflight_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            issues = feature / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-lean.md"
            body = (
                "---\ncontract_version: 3\nverifier_schema: 2\ntype: issue\nfeature: demo\nstatus: ready\n---\n"
                "## 验证设计\n- profile: verifier.json\n"
                "- P1 预检：`profile:scoped` → passed\n"
            )
            issue.write_text(body, encoding="utf-8")
            profile = {
                "schema_version": 2,
                "cwd": ".",
                "fingerprint": "git=abc; lock=none; runtime=py; tools=pytest; services=none",
                "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                "prepare": "无（已就绪）",
                "commands": {"scoped": "pytest -q", "full": "pytest tests -q"},
                "completion_commands": ["scoped", "full"],
            }
            profile_path = feature / "verifier.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            original = preflight.issue_preflight_rows(root)[0]

            profile_path.write_text(json.dumps(profile, indent=4), encoding="utf-8")
            reformatted = preflight.issue_preflight_rows(root)[0]
            self.assertEqual(original["key"], reformatted["key"])

            profile["fingerprint"] = (
                "services=none; tools=pytest; runtime=py; lock=none; git=abc"
            )
            profile["prerequisites"] = (
                "network=off; permissions=local; services=none; fixtures=ready"
            )
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            reordered = preflight.issue_preflight_rows(root)[0]
            self.assertEqual(original["key"], reordered["key"])

            profile["completion_commands"].reverse()
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            reordered_completions = preflight.issue_preflight_rows(root)[0]
            self.assertEqual(original["key"], reordered_completions["key"])

            profile["commands"]["scoped"] = "pytest tests/unit -q"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            changed_profile = preflight.issue_preflight_rows(root)[0]
            self.assertNotEqual(original["key"], changed_profile["key"])

            issue.write_text(
                body + "- 偏差 fingerprint.git：`def`\n",
                encoding="utf-8",
            )
            changed_card = preflight.issue_preflight_rows(root)[0]
            self.assertEqual("git=def; lock=none; runtime=py; tools=pytest; services=none", changed_card["fingerprint"])
            self.assertNotEqual(changed_profile["key"], changed_card["key"])

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
            self.assertIsNotNone(
                preflight.check(
                    path,
                    cwd=str(root),
                    action=action,
                    fingerprint=" lock=none ; git=abc ",
                )
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

            def body(status, action, fixtures="ready"):
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
- 前置条件：`fixtures={fixtures}; services=none; permissions=local; network=off`
- 准备动作：`无（已就绪）`
- P1 预检：`{action}` → passed；observed=exit 0；evidence=inline；checked=2026-08-30
"""

            unittest_action = shlex.join([sys.executable, "-m", "unittest", "-q"])
            (issues / "01-one.md").write_text(body("ready", unittest_action), encoding="utf-8")
            (issues / "02-two.md").write_text(body("ready", unittest_action), encoding="utf-8")
            (issues / "03-different-readiness.md").write_text(
                body("ready", unittest_action, fixtures="empty"), encoding="utf-8"
            )
            (issues / "04-unique.md").write_text(
                body("ready", "python -m compileall ."), encoding="utf-8"
            )
            (issues / "05-done.md").write_text(
                body("done", unittest_action), encoding="utf-8"
            )

            plan = preflight.duplicate_plan(root)
            self.assertEqual(1, len(plan["duplicates"]))
            duplicate = plan["duplicates"][0]
            self.assertEqual("miss", duplicate["status"])
            self.assertNotIn("declared_action", duplicate)
            self.assertNotIn("verifier_digest", duplicate)
            self.assertRegex(duplicate["readiness_digest"], r"^[0-9a-f]{64}$")
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
                readiness_digest=duplicate["readiness_digest"],
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
