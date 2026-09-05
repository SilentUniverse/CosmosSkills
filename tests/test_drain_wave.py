import importlib.util
import io
import json
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wave = load_module(
    "drain_wave",
    ROOT / "engineering" / "tdd" / "scripts" / "drain-wave.py",
)
preflight = load_module(
    "preflight_receipt_for_wave",
    ROOT / "engineering" / "tdd" / "scripts" / "preflight-receipt.py",
)
supervisor = load_module(
    "test_supervisor_for_wave",
    ROOT / "engineering" / "tdd" / "scripts" / "test-supervisor.py",
)


def issue_body(touches, action=None, blocked_by=""):
    action = action or shlex.join([sys.executable, "-m", "unittest", "-q"])
    return f"""---
status: ready
blocked_by: [{blocked_by}]
touches: [{touches}]
test_paths: [{touches}/test_feature.py]
---

## 验证设计

- 工作目录：`.`
- 环境指纹：`git=abc; lock=none; runtime=python-3; tools=unittest; services=none`
- P1 预检：`{action}` → passed；observed=exit 0；evidence=inline；checked=2026-08-30
"""


class DrainWaveReceiptTests(unittest.TestCase):
    def call(self, fn, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = fn(*args)
        return code, output.getvalue()

    def test_shared_preflight_is_required_once_and_reaches_serialized_briefs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            # Same touches deliberately serializes the cards into separate waves.
            first = issues / "01-one.md"
            second = issues / "02-two.md"
            first.write_text(issue_body("pkg"), encoding="utf-8")
            second.write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-one"])
            self.assertEqual(5, code, output)
            self.assertIn("preflight-required:", output)

            duplicate = preflight.duplicate_plan(root)["duplicates"][0]
            execution_receipt = root / ".scratch" / "demo" / "preflight-execution.json"
            result, exit_code = supervisor.run_command(
                shlex.split(duplicate["action"]),
                cwd=root,
                receipt=execution_receipt,
                log=root / ".scratch" / "demo" / "preflight.log",
                timeout=5,
                grace=0.1,
                scope="preflight",
            )
            self.assertEqual(("pass", 0), (result["outcome"], exit_code))
            key = preflight.record(
                root / duplicate["receipt"],
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                execution_receipt=execution_receipt,
            )

            code, first_output = self.call(wave.cmd_dispatch, str(root), ["01-one"])
            self.assertEqual(0, code, first_output)
            self.assertIn(f"brief: 01-one receipt-hit:{key}", first_output)
            first.write_text(
                first.read_text(encoding="utf-8").replace("status: ready", "status: done"),
                encoding="utf-8",
            )
            code, collect_output = self.call(
                wave.cmd_collect, str(root), ["01-one=green"]
            )
            self.assertEqual(0, code, collect_output)

            # The live duplicate set now contains only the second card. Its persisted
            # assignment must still reach the later brief without another replay.
            code, second_output = self.call(wave.cmd_dispatch, str(root), ["02-two"])
            self.assertEqual(0, code, second_output)
            self.assertIn(f"brief: 02-two receipt-hit:{key}", second_output)

            receipt = json.loads((root / duplicate["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual([key], list(receipt["entries"]))
            ledger = wave.load_ledger(str(root), "demo")
            self.assertEqual([key], ledger["waves"][0]["receipt_hits"]["01-one"])
            self.assertEqual([key], ledger["waves"][1]["receipt_hits"]["02-two"])

    def test_unique_preflight_keeps_the_ordinary_dispatch_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-only.md").write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-only"])
            self.assertEqual(0, code, output)
            self.assertNotIn("receipt-hit:", output)
            ledger = wave.load_ledger(str(root), "demo")
            self.assertEqual({}, ledger["waves"][0]["receipt_hits"])
            self.assertFalse((root / ".scratch" / "demo" / "preflight-receipt.json").exists())

    def test_receipt_conflict_blocks_until_spec_changes_the_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-conflict.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-conflict"])
            self.assertEqual(0, code, output)
            issue.write_text(
                issue.read_text(encoding="utf-8") + "\n## Comments\n\nreceipt conflict evidence\n",
                encoding="utf-8",
            )
            code, output = self.call(
                wave.cmd_collect, str(root), ["01-conflict=conflict"]
            )
            self.assertEqual(0, code, output)

            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(6, code, output)
            self.assertIn("requires /spec realignment", output)
            code, output = self.call(wave.cmd_dispatch, str(root), ["01-conflict"])
            self.assertEqual(6, code, output)

            issue.write_text(
                issue.read_text(encoding="utf-8") + "\nanother comment cannot realign the contract\n",
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(6, code, output)

            issue.write_text(
                issue.read_text(encoding="utf-8").replace(
                    "## 验证设计", "## 验证设计\n\n- 对齐修订：upstream contract"
                ),
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(0, code, output)

    def test_step_names_dispatch_then_close_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_step, str(root), None)

            self.assertEqual(0, code, output)
            self.assertIn("action: dispatch 01-one", output)
            self.assertIn("drain-wave.py dispatch <repo-root> 01-one", output)

            (issues / "01-one.md").write_text(
                issue_body("pkg").replace("status: ready", "status: done", 1),
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_step, str(root), None)
            self.assertEqual(4, code, output)
            self.assertIn("action: close", output)
            self.assertIn("workflow-state.py gc", output)

    def test_dismissed_false_conflict_preserves_contract_and_resumes_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            issue = issues / "01-one.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")
            original = issue.read_bytes()
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, str(root), ["01-one=conflict"])[0])
            self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])
            evidence = root / ".scratch/demo/receipts/conflict-review.json"
            evidence.parent.mkdir()
            review = {
                "feature": "demo", "slug": "01-one", "wave": 1,
                "contract_sha256": wave.contract_sha256(issue),
                "classification": "noise",
                "reason": "The observed failure came from the wrong working directory.",
                "evidence": "Replaying the recorded P1 in its declared cwd exits 0.",
            }
            evidence.write_text(json.dumps(review), encoding="utf-8")
            code, output = self.call(wave.main, [
                "drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one",
                evidence.relative_to(root).as_posix(),
            ])
            self.assertEqual(0, code, output)
            self.assertEqual(original, issue.read_bytes())
            record = wave.load_ledger(str(root), "demo")["waves"][0]
            self.assertEqual("red", record["closed"]["01-one"])
            self.assertEqual(review["contract_sha256"], record["conflict_contract_sha256"]["01-one"])
            self.assertEqual("noise", record["conflict_dismissals"]["01-one"]["classification"])
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])

    def test_conflict_dismissal_rejects_changed_contract_or_inconclusive_evidence(self):
        for classification, digest, evidence_text in [
            ("contract_change", None, "Public behavior must change."),
            ("insufficient_context", None, "Missing required observation."),
            ("noise", "0" * 64, "Evidence belongs to another contract."),
            ("noise", None, ""),
        ]:
            with self.subTest(classification=classification, digest=digest, evidence=evidence_text):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    issues = root / ".scratch/demo/issues"
                    issues.mkdir(parents=True)
                    issue = issues / "01-one.md"
                    issue.write_text(issue_body("pkg"), encoding="utf-8")
                    self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
                    self.assertEqual(0, self.call(wave.cmd_collect, str(root), ["01-one=conflict"])[0])
                    ledger = root / ".scratch/demo/wave-ledger.json"
                    baseline = ledger.read_bytes()
                    evidence = root / ".scratch/demo/receipts/review.json"
                    evidence.parent.mkdir()
                    evidence.write_text(json.dumps({
                        "feature": "demo", "slug": "01-one", "wave": 1,
                        "contract_sha256": digest or wave.contract_sha256(issue),
                        "classification": classification, "reason": "Reviewed the reported conflict.",
                        "evidence": evidence_text,
                    }), encoding="utf-8")
                    code, output = self.call(wave.main, [
                        "drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one",
                        evidence.relative_to(root).as_posix(),
                    ])
                    self.assertEqual(1, code, output)
                    self.assertEqual(baseline, ledger.read_bytes())
                    self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])

    def test_dismissal_is_scoped_to_one_conflict_and_feature_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            first = issues / "01-one.md"
            first.write_text(issue_body("one"), encoding="utf-8")
            (issues / "02-two.md").write_text(issue_body("two", action="python --version"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, str(root), ["01-one=conflict", "02-two=conflict"])[0])
            ledger = root / ".scratch/demo/wave-ledger.json"
            baseline = ledger.read_bytes()
            review = {
                "feature": "demo", "slug": "01-one", "wave": 1,
                "contract_sha256": wave.contract_sha256(first),
                "classification": "artifact_defect", "reason": "Incorrect harness invocation.",
                "evidence": "The contract-preserving harness correction passes the recorded probe.",
            }
            foreign = root / "foreign.json"
            foreign.write_text(json.dumps(review), encoding="utf-8")
            args = ["drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one"]
            self.assertEqual(1, self.call(wave.main, args + [str(foreign)])[0])
            self.assertEqual(baseline, ledger.read_bytes())
            evidence = root / ".scratch/demo/receipts/review.json"
            evidence.parent.mkdir()
            evidence.write_text(json.dumps(review), encoding="utf-8")
            self.assertEqual(0, self.call(wave.main, args + [str(evidence)])[0])
            self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])
            self.assertEqual("conflict", wave.load_ledger(str(root), "demo")["waves"][0]["closed"]["02-two"])

    def test_archived_done_issue_satisfies_ready_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            archive = issues / "archive"
            archive.mkdir(parents=True)
            (archive / "01-parent.md").write_text(
                """---
status: done
---

### 完成 — 2026-09-03

- 验收：#1 → archived parent delivered
""",
                encoding="utf-8",
            )
            (issues / "02-child.md").write_text(
                issue_body("pkg", blocked_by="01-parent"), encoding="utf-8"
            )

            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(0, code, output)
            self.assertIn("02-child", output)

            code, output = self.call(wave.cmd_dispatch, str(root), ["02-child"])
            self.assertEqual(0, code, output)


if __name__ == "__main__":
    unittest.main()
