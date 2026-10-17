"""survey / start / close / park over a real FEATURE.md and real fixed evidence."""
import importlib.util
import io
import json
import shlex
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
from evidence_fixtures import FIXTURE_VERIFIER, EvidenceRepository, accept, evidence, feature_doc, feature_text

STATE_SPEC = importlib.util.spec_from_file_location("workflow_state", TESTS.parent / "workflow" / "workflow-state.py")
workflow_state = importlib.util.module_from_spec(STATE_SPEC)
STATE_SPEC.loader.exec_module(workflow_state)

LOCAL = "- 预检 local：`python -c pass` → passed；evidence=inline；checked=2026-10-01"
UNITS = """### T1 — first unit
- status: ready
- covers: D1
- 做什么：Deliver the first result.
- [ ] first result → `unit`
- [ ] second result → `unit`

### T2 — dependent unit
- status: ready
- blocked_by: T1
- covers: R2
- 做什么：Build on the first result.
- [ ] dependent result → `unit`

### T3 — standalone unit
- status: ready
- covers: R2
- 做什么：Use a unit-local command.
- [ ] local result → `local`
- 命令 local：`python -c pass`
""" + LOCAL + "\n"


class FeatureStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = EvidenceRepository(self.root, feature="demo")
        self.path = self.repo.spec
        self.repo.accept_spec(feature_text("demo", units=UNITS))

    def states(self):
        row = workflow_state.survey(self.root)[0]
        return {item["unit"]: (state, item["reasons"]) for state in ("ready", "blocked", "pending", "done", "invalid")
                for item in row[state]}

    def receipt(self, candidate=None, **definition):
        return self.repo.receipt(candidate, **definition).relative_to(self.root).as_posix()

    def close(self, *evidence_lines, unit="T1", candidate=None):
        return workflow_state.close(self.root, "demo", unit, list(evidence_lines), candidate)

    def assert_close_fails(self, message, *evidence_lines, unit="T1"):
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, message):
            self.close(*evidence_lines, unit=unit)
        self.assertEqual(original, self.path.read_bytes())

    def test_survey_separates_ready_from_unfinished_dependency(self):
        states = self.states()
        self.assertEqual("ready", states["T1"][0])
        self.assertEqual("ready", states["T3"][0])
        self.assertEqual(("blocked", ["unfinished dependency T1"]), states["T2"])

    def test_start_refuses_a_unit_that_is_not_ready(self):
        with self.assertRaisesRegex(ValueError, "T2 is blocked: unfinished dependency T1"):
            workflow_state.start(self.root, "demo", "T2")

    def test_start_packet_projects_contract_anchors_invariants_and_used_commands(self):
        original = self.path.read_bytes()
        packet = workflow_state.start(self.root, "demo", "T1")
        unit = feature_doc.load(self.root, "demo").unit("T1")
        self.assertIn("- 做什么：Deliver the first result.", packet["contract"])
        self.assertNotIn("status", packet["contract"])
        self.assertEqual(unit.digest(), packet["contract_sha256"])
        self.assertEqual({"D1", "R1"}, set(packet["covers"]))
        self.assertIn("Keep the fixture small.", packet["covers"]["D1"])
        self.assertEqual({"C1": "fixture invariant"}, packet["invariants"])
        self.assertEqual(["unit"], list(packet["verifier"]["commands"]))
        self.assertEqual({"runtime": "fixture"}, packet["verifier"]["environment"])
        local = workflow_state.start(self.root, "demo", "T3")
        self.assertEqual({"local": "python -c pass"}, local["verifier"]["commands"])
        self.assertEqual(original, self.path.read_bytes())

    def test_close_writes_completion_flips_status_and_unlocks_dependents(self):
        digest = feature_doc.load(self.root, "demo").unit("T1").digest()
        receipt = self.receipt()
        self.assertEqual({"feature": "demo", "unit": "T1", "status": "done"}, self.close(receipt + "; AC 1-2"))
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("#### 完成 — ", text)
        self.assertIn("- contract: " + digest, text)
        self.assertIn("- evidence: %s; AC 1-2" % receipt, text)
        unit = feature_doc.load(self.root, "demo").unit("T1")
        self.assertEqual("done", unit.status)
        states = self.states()
        self.assertEqual("done", states["T1"][0])
        self.assertEqual("ready", states["T2"][0])
        with self.assertRaisesRegex(ValueError, "T1 is done"):
            self.close(receipt + "; AC 1-2")

    def test_editing_a_done_unit_contract_makes_it_invalid_and_blocks_dependents(self):
        self.close(self.receipt() + "; AC 1-2")
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text.replace("- [ ] second result", "- [ ] other result"), encoding="utf-8")
        states = self.states()
        self.assertEqual("invalid", states["T1"][0])
        self.assertIn("contract changed after completion", states["T1"][1][0])
        self.assertIn("dependency T1 has no valid completion proof", states["T2"][1])

    def test_removing_a_command_a_done_unit_proves_with_reports_invalid_without_crashing(self):
        self.close(self.receipt() + "; AC 1-2")
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text.replace('"unit":', '"renamed":', 1), encoding="utf-8")
        state, reasons = self.states()["T1"]
        self.assertEqual("invalid", state)
        self.assertTrue(any("unknown command" in reason for reason in reasons), reasons)

    def test_close_rejects_evidence_that_does_not_match_the_contract(self):
        cases = {
            "wrong argv": ({"argv": [sys.executable, "-c", "print('other')"]}, "check command does not prove AC #1"),
            "wrong cwd": ({"cwd": "module"}, "check cwd differs"),
            "environment": ({"environment": {"runtime": "other"}}, "check environment differs"),
            "preflight": ({"scope": "preflight"}, "passing non-preflight"),
        }
        for name, (definition, message) in cases.items():
            with self.subTest(case=name):
                self.assert_close_fails(message, self.receipt(**definition) + "; AC 1-2")

    def test_close_rejects_failing_partial_and_conflicting_evidence(self):
        candidate = self.repo.candidate()
        failing = self.repo.receipt(candidate, exit_code=1).relative_to(self.root).as_posix()
        self.assert_close_fails("passing non-preflight", failing + "; AC 1-2")
        passing = self.receipt(candidate)
        self.assert_close_fails("completion needs every AC", passing + "; AC 1")
        self.assert_close_fails("valid AC selectors", passing + "; AC 3")
        self.assert_close_fails("known failed attempt", passing + "; AC 1-2")

    def test_reviewed_feature_needs_a_candidate_bound_to_the_accepted_contract(self):
        unbound = self.repo.feature / "unbound" / "candidate.json"
        unbound.parent.mkdir()
        evidence.candidate(self.root, "HEAD", None, [], unbound)
        self.assert_close_fails("candidate bound to an accepted contract", self.receipt(unbound) + "; AC 1-2")
        self.close(self.receipt(self.repo.candidate()) + "; AC 1-2")

    def test_review_required_feature_waits_for_an_accepted_record(self):
        shutil.rmtree(self.repo.feature / "reviews")
        states = self.states()
        self.assertEqual(("blocked", ["feature contract awaits human review"]), states["T1"])
        with self.assertRaisesRegex(ValueError, "awaits human review"):
            workflow_state.start(self.root, "demo", "T1")
        accept(self.repo.feature)
        self.assertEqual("ready", self.states()["T1"][0])

    def test_changed_covered_anchor_blocks_only_its_units_until_reaccepted(self):
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text.replace("R2 — second requirement", "R2 — changed requirement"), encoding="utf-8")
        states = self.states()
        self.assertEqual("ready", states["T1"][0])
        self.assertEqual(("blocked", ["contract changed since acceptance; re-review before starting"]), states["T3"])
        self.repo.accept_spec()
        self.assertEqual("ready", self.states()["T3"][0])

    def test_close_rejects_a_candidate_bound_to_an_outdated_acceptance(self):
        stale = self.repo.candidate()
        receipt = self.receipt(stale)
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text.replace("R1 — first requirement", "R1 — changed requirement"), encoding="utf-8")
        self.repo.accept_spec()
        self.assert_close_fails("misses this unit's latest accepted design", receipt + "; AC 1-2")

    def test_park_writes_pending_with_reason_and_refuses_done_units(self):
        result = workflow_state.park(self.root, "demo", "T3", "local tool is missing")
        self.assertEqual("pending", result["status"])
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("- status: pending\n- reason: local tool is missing\n", text)
        self.assertEqual(("pending", ["local tool is missing"]), self.states()["T3"])
        with self.assertRaisesRegex(ValueError, "one-line engineering reason"):
            workflow_state.park(self.root, "demo", "T3", " ")
        self.close(self.receipt() + "; AC 1-2")
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "completed units cannot be parked"):
            workflow_state.park(self.root, "demo", "T1", "reopen")
        self.assertEqual(original, self.path.read_bytes())

    def test_cli_survey_json_and_close_error_exit(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, workflow_state.main(["survey", str(self.root), "--format", "json"]))
        self.assertEqual({"ready": 2, "blocked": 1, "pending": 0, "done": 0, "invalid": 0},
                         json.loads(output.getvalue())[0]["counts"])
        errors = io.StringIO()
        with redirect_stdout(io.StringIO()), unittest.mock.patch("sys.stderr", errors):
            code = workflow_state.main(["close", str(self.root), "demo", "T2", "--evidence", "x.json; AC 1"])
        self.assertEqual(1, code)
        self.assertIn("T2 is blocked", errors.getvalue())


if __name__ == "__main__":
    unittest.main()


class LightweightEvidenceTests(unittest.TestCase):
    """Features without a recorded gate close from `run` logs; the log bytes stay pinned."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.feature = self.root / ".scratch" / "demo"
        self.feature.mkdir(parents=True)
        self.path = self.feature / "FEATURE.md"
        text = feature_text("demo", review=False, units=UNITS)
        self.path.write_text(text.replace("Door: two-way", "Review: human"), encoding="utf-8")

    def run_unit(self, unit="T1", command="unit"):
        with redirect_stdout(io.StringIO()):
            return workflow_state.run(self.root, "demo", unit, command)

    def test_review_human_is_confirmed_in_conversation_and_does_not_gate(self):
        self.assertFalse(feature_doc.load(self.root, "demo").review_required())
        self.assertIn("T1", [item["unit"] for item in workflow_state.survey(self.root)[0]["ready"]])

    def test_run_log_closes_the_unit_and_tampering_invalidates_it(self):
        result = self.run_unit()
        self.assertEqual(0, result["exit"])
        self.assertEqual(result["log"] + "; AC 1,2", result["evidence"])
        log = self.root / result["log"]
        self.assertTrue(log.read_text(encoding="utf-8").startswith("$ "))
        workflow_state.close(self.root, "demo", "T1", [result["evidence"]])
        text = self.path.read_text(encoding="utf-8")
        self.assertRegex(text, r"- evidence: \S+\.log sha256=[0-9a-f]{64}; AC 1,2")
        self.assertIn("T1", [item["unit"] for item in workflow_state.survey(self.root)[0]["done"]])
        with log.open("a", encoding="utf-8") as stream:
            stream.write("edited\n")
        invalid = workflow_state.survey(self.root)[0]["invalid"]
        self.assertIn("run log is missing or changed", invalid[0]["reasons"][0])

    def test_failing_or_foreign_logs_cannot_close(self):
        verifier = dict(FIXTURE_VERIFIER, commands=dict(FIXTURE_VERIFIER["commands"],
                                                         unit=shlex.join([sys.executable, "-c", "raise SystemExit(3)"])))
        self.path.write_text(feature_text("demo", review=False, units=UNITS, verifier=verifier), encoding="utf-8")
        failed = self.run_unit()
        self.assertEqual(3, failed["exit"])
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "exit=0"):
            workflow_state.close(self.root, "demo", "T1", [failed["evidence"]])
        forged = self.feature / "runs" / "forged.log"
        forged.write_text("$ some other command\n# tree=%s\nok\nexit=0\n" % workflow_state.work_tree(self.root),
                          encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must start with"):
            workflow_state.close(self.root, "demo", "T1", [".scratch/demo/runs/forged.log; AC 1,2"])
        self.assertEqual(original, self.path.read_bytes())

    def test_recorded_gate_requires_receipts_not_run_logs(self):
        self.path.write_text(feature_text("demo", review=True, units=UNITS), encoding="utf-8")
        accept(self.feature)
        result = self.run_unit()
        with self.assertRaisesRegex(ValueError, "fixed receipts"):
            workflow_state.close(self.root, "demo", "T1", [result["evidence"]])

    def test_log_from_older_working_files_cannot_close(self):
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        result = self.run_unit()
        self.assertNotIn("# tree=no-vcs", (self.root / result["log"]).read_text(encoding="utf-8"))
        (self.root / "changed.py").write_text("VALUE = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not produced from the current working files"):
            workflow_state.close(self.root, "demo", "T1", [result["evidence"]])
        fresh = self.run_unit()
        workflow_state.close(self.root, "demo", "T1", [fresh["evidence"]])
